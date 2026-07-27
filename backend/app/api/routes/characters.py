"""
Characters API — CRUD plus the Memory Editor actions (pin, mark canon/
false, enable/disable), each of which writes a MemoryRevision row so
the change is auditable, as required by the Memory Editor spec.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, status

from app.db.session import get_db
from app.models.models import Character, Chat, EntityType, MemoryRevision, User
from app.schemas.entities import CharacterCreate, CharacterResponse, CharacterUpdate, MemoryFlagsUpdate
from app.services.auth.deps import get_current_user

router = APIRouter(prefix="/chats/{chat_id}/characters", tags=["characters"])


async def _owned_chat(db: AsyncSession, chat_id: str, user: User) -> Chat:
    chat = await db.get(Chat, chat_id)
    if chat is None or chat.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


async def _get_character(db: AsyncSession, chat_id: str, character_id: str) -> Character:
    char = await db.get(Character, character_id)
    if char is None or char.chat_id != chat_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return char


def _snapshot(char: Character) -> dict:
    return {
        "name": char.name, "description": char.description, "current_state": char.current_state,
        "is_pinned": char.is_pinned, "is_canon": char.is_canon, "is_false": char.is_false,
        "is_enabled": char.is_enabled, "importance": char.importance,
    }


@router.get("", response_model=list[CharacterResponse])
async def list_characters(chat_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _owned_chat(db, chat_id, user)
    result = await db.execute(select(Character).where(Character.chat_id == chat_id).order_by(Character.name))
    return list(result.scalars())


@router.post("", response_model=CharacterResponse, status_code=status.HTTP_201_CREATED)
async def create_character(chat_id: str, payload: CharacterCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _owned_chat(db, chat_id, user)
    char = Character(chat_id=chat_id, **payload.model_dump())
    db.add(char)
    await db.flush()
    db.add(MemoryRevision(entity_type=EntityType.character, entity_id=char.id, changed_by_user_id=user.id,
                           change_type="created", before_json=None, after_json=_snapshot(char)))
    await db.commit()
    await db.refresh(char)
    return char


@router.patch("/{character_id}", response_model=CharacterResponse)
async def update_character(chat_id: str, character_id: str, payload: CharacterUpdate,
                            user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _owned_chat(db, chat_id, user)
    char = await _get_character(db, chat_id, character_id)
    before = _snapshot(char)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(char, field, value)
    db.add(MemoryRevision(entity_type=EntityType.character, entity_id=char.id, changed_by_user_id=user.id,
                           change_type="edited", before_json=before, after_json=_snapshot(char)))
    await db.commit()
    await db.refresh(char)
    return char


@router.patch("/{character_id}/flags", response_model=CharacterResponse)
async def update_character_flags(chat_id: str, character_id: str, payload: MemoryFlagsUpdate,
                                  user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Pin / mark canon / mark false / enable-disable — the Memory Editor actions."""
    await _owned_chat(db, chat_id, user)
    char = await _get_character(db, chat_id, character_id)
    before = _snapshot(char)

    change_labels = []
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(char, field, value)
        if field == "is_pinned":
            change_labels.append("pinned" if value else "unpinned")
        elif field == "is_canon" and value:
            change_labels.append("marked_canon")
        elif field == "is_false" and value:
            change_labels.append("marked_false")
        elif field == "is_enabled":
            change_labels.append("enabled" if value else "disabled")

    db.add(MemoryRevision(entity_type=EntityType.character, entity_id=char.id, changed_by_user_id=user.id,
                           change_type=",".join(change_labels) or "edited", before_json=before, after_json=_snapshot(char)))
    await db.commit()
    await db.refresh(char)
    return char


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_character(chat_id: str, character_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _owned_chat(db, chat_id, user)
    char = await _get_character(db, chat_id, character_id)
    db.add(MemoryRevision(entity_type=EntityType.character, entity_id=char.id, changed_by_user_id=user.id,
                           change_type="deleted", before_json=_snapshot(char), after_json=None))
    await db.delete(char)
    await db.commit()


@router.get("/{character_id}/history")
async def character_history(chat_id: str, character_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _owned_chat(db, chat_id, user)
    result = await db.execute(
        select(MemoryRevision)
        .where(MemoryRevision.entity_type == EntityType.character, MemoryRevision.entity_id == character_id)
        .order_by(MemoryRevision.created_at.desc())
    )
    return [
        {"id": r.id, "change_type": r.change_type, "before": r.before_json, "after": r.after_json, "created_at": r.created_at}
        for r in result.scalars()
    ]
