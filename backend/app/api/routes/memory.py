"""
Generic Memory API — covers every memory entity type EXCEPT Character,
which already has its own richer router (characters.py) with fields
specific to it (personality, backstory, aliases, etc).

Rather than hand-writing eleven near-identical route files (Location,
Item, Organization, Event, Fact, Goal, Promise, Secret, Relationship,
StoryArc, SceneSummary, ArcSummary), this module drives everything off
a single ENTITY_REGISTRY table: model class + allowed writable fields.
Every entity type still gets the full Memory Editor contract:

    GET    /chats/{chat_id}/memory/summary                counts per type
    GET    /chats/{chat_id}/memory/{entity_type}           list (+ filters)
    POST   /chats/{chat_id}/memory/{entity_type}           create
    GET    /chats/{chat_id}/memory/{entity_type}/{id}      read one
    PATCH  /chats/{chat_id}/memory/{entity_type}/{id}      edit fields
    PATCH  /chats/{chat_id}/memory/{entity_type}/{id}/flags  pin/canon/false/enable/importance
    DELETE /chats/{chat_id}/memory/{entity_type}/{id}      delete
    GET    /chats/{chat_id}/memory/{entity_type}/{id}/history  revision log

Every write still produces a MemoryRevision row, exactly like the
Character Memory Editor actions, so the audit trail is uniform across
all entity types.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.models import (
    ArcSummary, Chat, Event, EntityType, Fact, Goal, Item, Location,
    MemoryRevision, Organization, Promise, Relationship, SceneSummary,
    Secret, StoryArc, User,
)
from app.services.auth.deps import get_current_user

router = APIRouter(prefix="/chats/{chat_id}/memory", tags=["memory"])

FLAG_FIELDS = {"is_pinned", "is_canon", "is_false", "is_enabled", "importance"}


class _Registration:
    def __init__(self, model, create_fields: list[str], update_fields: list[str] | None = None, label_field: str = "name"):
        self.model = model
        self.create_fields = create_fields
        self.update_fields = update_fields or create_fields
        self.label_field = label_field


ENTITY_REGISTRY: dict[str, _Registration] = {
    "location": _Registration(Location, ["name", "description", "parent_location_id"]),
    "item": _Registration(Item, ["name", "description", "owner_character_id"]),
    "organization": _Registration(Organization, ["name", "description"]),
    "event": _Registration(
        Event, ["title", "description", "story_day", "occurred_at_message_id", "location_id"], label_field="title"
    ),
    "fact": _Registration(Fact, ["content", "subject_entity_type", "subject_entity_id"], label_field="content"),
    "goal": _Registration(Goal, ["character_id", "description", "is_completed"], label_field="description"),
    "promise": _Registration(
        Promise,
        ["made_by_character_id", "made_to_character_id", "description", "is_fulfilled", "is_broken"],
        label_field="description",
    ),
    "secret": _Registration(
        Secret, ["owner_character_id", "description", "known_by_character_ids"], label_field="description"
    ),
    "relationship": _Registration(
        Relationship, ["character_a_id", "character_b_id", "label", "description", "intensity"], label_field="label"
    ),
    "story_arc": _Registration(
        StoryArc, ["title", "description", "is_resolved", "started_story_day", "resolved_story_day"], label_field="title"
    ),
    "scene_summary": _Registration(
        SceneSummary, ["start_message_id", "end_message_id", "story_day", "summary"], label_field="summary"
    ),
    "arc_summary": _Registration(ArcSummary, ["story_arc_id", "summary"], label_field="summary"),
}


class MemoryFlagsUpdate(BaseModel):
    is_pinned: bool | None = None
    is_canon: bool | None = None
    is_false: bool | None = None
    is_enabled: bool | None = None
    importance: int | None = None


def _registration(entity_type: str) -> _Registration:
    reg = ENTITY_REGISTRY.get(entity_type)
    if reg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown memory entity type '{entity_type}'")
    return reg


def _serialize(obj: Any) -> dict:
    """Column-generic serializer: reads every mapped column off the
    SQLAlchemy instance so we don't need a bespoke Pydantic schema per
    entity type. Enum values are unwrapped to their raw string/value."""
    mapper = inspect(obj).mapper
    out: dict[str, Any] = {}
    for col in mapper.column_attrs:
        value = getattr(obj, col.key)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        elif hasattr(value, "value") and not isinstance(value, (int, float, str, bool, list, dict)):
            value = value.value
        out[col.key] = value
    return out


async def _owned_chat(db: AsyncSession, chat_id: str, user: User) -> Chat:
    chat = await db.get(Chat, chat_id)
    if chat is None or chat.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


async def _get_entity(db: AsyncSession, reg: _Registration, chat_id: str, entity_id: str):
    obj = await db.get(reg.model, entity_id)
    if obj is None or obj.chat_id != chat_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    return obj


def _label(reg: _Registration, obj: Any) -> str:
    val = getattr(obj, reg.label_field, None) or ""
    return str(val)[:80]


@router.get("/summary")
async def memory_summary(chat_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Counts per entity type, used to render the Memory Editor's type list."""
    await _owned_chat(db, chat_id, user)
    counts: dict[str, int] = {}
    for entity_type, reg in ENTITY_REGISTRY.items():
        total = (await db.execute(
            select(func.count()).select_from(reg.model).where(reg.model.chat_id == chat_id)
        )).scalar_one()
        counts[entity_type] = total
    return counts


@router.get("/{entity_type}")
async def list_entities(
    entity_type: str, chat_id: str,
    enabled_only: bool = False, canon_only: bool = False, pinned_only: bool = False,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    reg = _registration(entity_type)
    await _owned_chat(db, chat_id, user)
    stmt = select(reg.model).where(reg.model.chat_id == chat_id)
    if enabled_only:
        stmt = stmt.where(reg.model.is_enabled == True)  # noqa: E712
    if canon_only:
        stmt = stmt.where(reg.model.is_canon == True)  # noqa: E712
    if pinned_only:
        stmt = stmt.where(reg.model.is_pinned == True)  # noqa: E712
    rows = (await db.execute(stmt)).scalars()
    items = []
    for obj in rows:
        d = _serialize(obj)
        d["entity_type"] = entity_type
        d["label"] = _label(reg, obj)
        items.append(d)
    return items


@router.post("/{entity_type}", status_code=status.HTTP_201_CREATED)
async def create_entity(
    entity_type: str, chat_id: str, payload: dict,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    reg = _registration(entity_type)
    await _owned_chat(db, chat_id, user)
    fields = {k: v for k, v in payload.items() if k in reg.create_fields}
    obj = reg.model(chat_id=chat_id, **fields)
    db.add(obj)
    await db.flush()
    after = _serialize(obj)
    db.add(MemoryRevision(
        entity_type=EntityType(entity_type), entity_id=obj.id, changed_by_user_id=user.id,
        change_type="created", before_json=None, after_json=after,
    ))
    await db.commit()
    await db.refresh(obj)
    d = _serialize(obj)
    d["entity_type"] = entity_type
    d["label"] = _label(reg, obj)
    return d


@router.get("/{entity_type}/{entity_id}")
async def get_entity(
    entity_type: str, chat_id: str, entity_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    reg = _registration(entity_type)
    await _owned_chat(db, chat_id, user)
    obj = await _get_entity(db, reg, chat_id, entity_id)
    d = _serialize(obj)
    d["entity_type"] = entity_type
    d["label"] = _label(reg, obj)
    return d


@router.patch("/{entity_type}/{entity_id}")
async def update_entity(
    entity_type: str, chat_id: str, entity_id: str, payload: dict,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    reg = _registration(entity_type)
    await _owned_chat(db, chat_id, user)
    obj = await _get_entity(db, reg, chat_id, entity_id)
    before = _serialize(obj)
    for field, value in payload.items():
        if field in reg.update_fields:
            setattr(obj, field, value)
    db.add(MemoryRevision(
        entity_type=EntityType(entity_type), entity_id=obj.id, changed_by_user_id=user.id,
        change_type="edited", before_json=before, after_json=_serialize(obj),
    ))
    await db.commit()
    await db.refresh(obj)
    d = _serialize(obj)
    d["entity_type"] = entity_type
    d["label"] = _label(reg, obj)
    return d


@router.patch("/{entity_type}/{entity_id}/flags")
async def update_entity_flags(
    entity_type: str, chat_id: str, entity_id: str, payload: MemoryFlagsUpdate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Pin / mark canon / mark false / enable-disable / importance — the Memory Editor actions."""
    reg = _registration(entity_type)
    await _owned_chat(db, chat_id, user)
    obj = await _get_entity(db, reg, chat_id, entity_id)
    before = _serialize(obj)

    change_labels = []
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(obj, field, value)
        if field == "is_pinned":
            change_labels.append("pinned" if value else "unpinned")
        elif field == "is_canon" and value:
            change_labels.append("marked_canon")
        elif field == "is_false" and value:
            change_labels.append("marked_false")
        elif field == "is_enabled":
            change_labels.append("enabled" if value else "disabled")

    db.add(MemoryRevision(
        entity_type=EntityType(entity_type), entity_id=obj.id, changed_by_user_id=user.id,
        change_type=",".join(change_labels) or "edited", before_json=before, after_json=_serialize(obj),
    ))
    await db.commit()
    await db.refresh(obj)
    d = _serialize(obj)
    d["entity_type"] = entity_type
    d["label"] = _label(reg, obj)
    return d


@router.delete("/{entity_type}/{entity_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_entity(
    entity_type: str, chat_id: str, entity_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    reg = _registration(entity_type)
    await _owned_chat(db, chat_id, user)
    obj = await _get_entity(db, reg, chat_id, entity_id)
    db.add(MemoryRevision(
        entity_type=EntityType(entity_type), entity_id=obj.id, changed_by_user_id=user.id,
        change_type="deleted", before_json=_serialize(obj), after_json=None,
    ))
    await db.delete(obj)
    await db.commit()


@router.get("/{entity_type}/{entity_id}/history")
async def entity_history(
    entity_type: str, chat_id: str, entity_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    reg = _registration(entity_type)
    await _owned_chat(db, chat_id, user)
    await _get_entity(db, reg, chat_id, entity_id)
    result = await db.execute(
        select(MemoryRevision)
        .where(MemoryRevision.entity_type == EntityType(entity_type), MemoryRevision.entity_id == entity_id)
        .order_by(MemoryRevision.created_at.desc())
    )
    return [
        {"id": r.id, "change_type": r.change_type, "before": r.before_json, "after": r.after_json, "created_at": r.created_at}
        for r in result.scalars()
    ]
