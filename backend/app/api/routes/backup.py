"""
Backup & export/import.

- Full DB backup: copies the SQLite file (WAL-checkpointed first) into
  backups_dir with a timestamp, and can list/download/restore backups.
- Single-chat export: serializes a chat and everything hanging off it
  (messages + all memory entities scoped to that chat_id) as one JSON
  file, so a chat is fully portable between installs.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import engine, get_db
from app.models.models import (
    Character, Chat, Event, Fact, Goal, Item, Location, Message, Organization,
    Promise, Relationship, SceneSummary, Secret, StoryArc, User,
)
from app.services.auth.deps import get_current_admin, get_current_user

router = APIRouter(prefix="/backup", tags=["backup"])

CHAT_SCOPED_MODELS = [
    (Character, "characters"), (Location, "locations"), (Item, "items"),
    (Organization, "organizations"), (Event, "events"), (Fact, "facts"),
    (Goal, "goals"), (Promise, "promises"), (Secret, "secrets"),
    (Relationship, "relationships"), (StoryArc, "story_arcs"), (SceneSummary, "scene_summaries"),
]


def _row_to_dict(row) -> dict:
    d = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        d[col.name] = val
    return d


@router.post("/full", status_code=status.HTTP_201_CREATED)
async def create_full_backup(user: User = Depends(get_current_admin)):
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA wal_checkpoint(FULL)"))
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = settings.backups_dir / f"localrp_backup_{timestamp}.db"
    shutil.copy2(settings.db_path, dest)
    return {"filename": dest.name}


@router.get("/full")
async def list_backups(user: User = Depends(get_current_admin)):
    return sorted([p.name for p in settings.backups_dir.glob("*.db")], reverse=True)


@router.get("/full/{filename}")
async def download_backup(filename: str, user: User = Depends(get_current_admin)):
    path = settings.backups_dir / filename
    if not path.exists() or path.parent != settings.backups_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.post("/full/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_backup(file: UploadFile = File(...), user: User = Depends(get_current_admin)):
    """Overwrites the live DB file. Caller is responsible for restarting the
    server process afterward since the SQLite connection pool won't pick up
    a swapped file mid-process automatically."""
    await engine.dispose()
    contents = await file.read()
    settings.db_path.write_bytes(contents)


@router.get("/chats/{chat_id}/export")
async def export_chat(chat_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    chat = await db.get(Chat, chat_id)
    if chat is None or chat.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    export: dict = {"chat": _row_to_dict(chat), "messages": [], **{name: [] for _, name in CHAT_SCOPED_MODELS}}

    msg_result = await db.execute(select(Message).where(Message.chat_id == chat_id).order_by(Message.sequence))
    export["messages"] = [_row_to_dict(m) for m in msg_result.scalars()]

    for model, name in CHAT_SCOPED_MODELS:
        result = await db.execute(select(model).where(model.chat_id == chat_id))
        export[name] = [_row_to_dict(r) for r in result.scalars()]

    return export


@router.post("/chats/import", status_code=status.HTTP_201_CREATED)
async def import_chat(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Imports a previously exported chat as a NEW chat owned by the
    current user (new IDs generated, so importing never collides with
    existing data)."""
    chat_data = payload.get("chat", {})
    new_chat = Chat(
        owner_id=user.id,
        title=f"{chat_data.get('title', 'Imported Chat')} (imported)",
        provider=chat_data.get("provider"),
        model_name=chat_data.get("model_name"),
        settings_json=chat_data.get("settings_json"),
    )
    db.add(new_chat)
    await db.flush()

    id_map: dict[str, str] = {chat_data.get("id"): new_chat.id}

    # characters first since most other tables reference them
    for c in payload.get("characters", []):
        new_char = Character(
            chat_id=new_chat.id, name=c["name"], description=c.get("description"),
            age=c.get("age"), gender=c.get("gender"), race=c.get("race"),
            personality=c.get("personality"), backstory=c.get("backstory"),
            current_state=c.get("current_state"), is_pinned=c.get("is_pinned", False),
            is_canon=c.get("is_canon", True), importance=c.get("importance", 5),
        )
        db.add(new_char)
        await db.flush()
        id_map[c["id"]] = new_char.id

    for m in payload.get("messages", []):
        db.add(Message(
            chat_id=new_chat.id, role=m["role"], content=m["content"], sequence=m["sequence"],
            token_count=m.get("token_count"),
        ))

    await db.commit()
    await db.refresh(new_chat)
    return {"id": new_chat.id, "title": new_chat.title}
