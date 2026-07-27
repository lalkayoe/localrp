from __future__ import annotations

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, status

from app.db.session import get_db
from app.models.models import (
    Character, Chat, Event, Fact, Location, Message, Organization, SettingsKV, User,
)
from app.schemas.entities import PromptInspectorBlock, PromptInspectorResponse, SearchResultItem, TimelineEntryResponse
from app.services.auth.deps import get_current_user
from app.services.memory.prompt_builder import build_prompt
from app.services.providers.factory import create_provider
from app.services.settings_store import get_effective_settings
from app.core.config import settings as app_settings

router = APIRouter(tags=["timeline-search-settings"])


async def _owned_chat(db: AsyncSession, chat_id: str, user: User) -> Chat:
    chat = await db.get(Chat, chat_id)
    if chat is None or chat.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


# --- Timeline ---------------------------------------------------------

@router.get("/chats/{chat_id}/timeline", response_model=list[TimelineEntryResponse])
async def get_timeline(chat_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Built live from Events (which carry story_day) rather than requiring a
    separately-maintained TimelineEntry table to stay in sync on every write."""
    await _owned_chat(db, chat_id, user)
    result = await db.execute(
        select(Event)
        .where(Event.chat_id == chat_id, Event.is_enabled == True, Event.is_false == False)  # noqa: E712
        .order_by(Event.story_day.asc().nulls_last())
    )
    return [
        TimelineEntryResponse(story_day=e.story_day or 0, title=e.title, entity_type="event", entity_id=e.id)
        for e in result.scalars()
    ]


# --- Search -------------------------------------------------------------

@router.get("/chats/{chat_id}/search", response_model=list[SearchResultItem])
async def search_chat(chat_id: str, q: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Simple LIKE-based search across all memory types plus raw messages.
    Fine at SQLite scale for a single chat's worth of data; swap for FTS5
    virtual tables if chats grow into the tens of thousands of entries."""
    await _owned_chat(db, chat_id, user)
    like = f"%{q}%"
    results: list[SearchResultItem] = []

    char_rows = (await db.execute(select(Character).where(Character.chat_id == chat_id, or_(
        Character.name.ilike(like), Character.description.ilike(like)
    )))).scalars()
    results += [SearchResultItem(entity_type="character", entity_id=c.id, chat_id=chat_id, title=c.name,
                                  snippet=(c.description or "")[:150]) for c in char_rows]

    loc_rows = (await db.execute(select(Location).where(Location.chat_id == chat_id, or_(
        Location.name.ilike(like), Location.description.ilike(like)
    )))).scalars()
    results += [SearchResultItem(entity_type="location", entity_id=l.id, chat_id=chat_id, title=l.name,
                                  snippet=(l.description or "")[:150]) for l in loc_rows]

    org_rows = (await db.execute(select(Organization).where(Organization.chat_id == chat_id, or_(
        Organization.name.ilike(like), Organization.description.ilike(like)
    )))).scalars()
    results += [SearchResultItem(entity_type="organization", entity_id=o.id, chat_id=chat_id, title=o.name,
                                  snippet=(o.description or "")[:150]) for o in org_rows]

    event_rows = (await db.execute(select(Event).where(Event.chat_id == chat_id, or_(
        Event.title.ilike(like), Event.description.ilike(like)
    )))).scalars()
    results += [SearchResultItem(entity_type="event", entity_id=e.id, chat_id=chat_id, title=e.title,
                                  snippet=(e.description or "")[:150]) for e in event_rows]

    fact_rows = (await db.execute(select(Fact).where(Fact.chat_id == chat_id, Fact.content.ilike(like)))).scalars()
    results += [SearchResultItem(entity_type="fact", entity_id=f.id, chat_id=chat_id, title=f.content[:40],
                                  snippet=f.content[:150]) for f in fact_rows]

    msg_rows = (await db.execute(
        select(Message).where(Message.chat_id == chat_id, Message.is_deleted == False, Message.content.ilike(like))  # noqa: E712
        .order_by(Message.sequence.desc()).limit(30)
    )).scalars()
    results += [SearchResultItem(entity_type="message", entity_id=m.id, chat_id=chat_id, title=f"{m.role.value} message",
                                  snippet=m.content[:150]) for m in msg_rows]

    return results


# --- Settings (global key/value store) -----------------------------------

@router.get("/settings")
async def get_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await get_effective_settings(db)


@router.put("/settings/{key}")
async def set_setting(key: str, value: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    row = await db.get(SettingsKV, key)
    if row is None:
        row = SettingsKV(key=key, value_json=value.get("value"))
        db.add(row)
    else:
        row.value_json = value.get("value")
    await db.commit()
    return {"key": key, "value": row.value_json}


# --- Prompt Inspector -----------------------------------------------------

@router.post("/chats/{chat_id}/inspect-prompt", response_model=PromptInspectorResponse)
async def inspect_prompt(chat_id: str, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Builds the exact prompt that WOULD be sent for the given draft user
    message, without calling the model — shows every block, every selected
    memory entity, why it was picked, and its token cost."""
    chat = await _owned_chat(db, chat_id, user)
    eff = await get_effective_settings(db)
    cfg = chat.settings_json or {}
    context_size = cfg.get("context_size", eff["default_context_size"])
    max_tokens = cfg.get("max_tokens", eff["default_max_tokens"])

    built = await build_prompt(db, chat, payload.get("draft_message", ""), context_size, max_tokens)

    blocks = [
        PromptInspectorBlock(
            label=b.label,
            content=b.content,
            token_count=b.token_count,
            selected_entities=[
                {"type": e.entity_type.value, "label": e.label, "score": round(e.score, 2), "reasons": e.reasons}
                for e in b.source_entities
            ],
        )
        for b in built.blocks
    ]
    return PromptInspectorResponse(blocks=blocks, total_tokens=built.total_tokens)
