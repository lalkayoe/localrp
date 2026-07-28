"""
Chat routes — the heart of the visible product.

POST /chats/{id}/messages streams the assistant reply as
text/event-stream. When the stream finishes, the full assistant message
is persisted and the hidden memory-extraction pass is kicked off as a
background task so it never adds latency to the visible reply.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db, AsyncSessionLocal
from app.models.models import Chat, Message, MessageRole, User
from app.schemas.chat import ChatCreate, ChatResponse, ChatUpdate, EditMessageRequest, MessageResponse, SendMessageRequest
from app.services.auth.deps import get_current_user
from app.services.memory.extractor import run_memory_extraction
from app.services.memory.prompt_builder import build_prompt
from app.services.providers.base import GenerationParams
from app.services.providers.factory import create_provider
from app.services.settings_store import get_effective_settings
from app.utils.tokens import count_tokens
from app.utils.reasoning import ThinkTagStripper

router = APIRouter(prefix="/chats", tags=["chats"])


async def _get_owned_chat(db: AsyncSession, chat_id: str, user: User) -> Chat:
    chat = await db.get(Chat, chat_id)
    if chat is None or chat.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


async def _resolve_provider(db: AsyncSession, chat: Chat):
    eff = await get_effective_settings(db)
    provider_type = chat.provider or eff["default_provider"]
    model = chat.model_name or eff["default_model"]
    cfg = chat.settings_json or {}
    params = GenerationParams(
        temperature=cfg.get("temperature", eff["default_temperature"]),
        top_p=cfg.get("top_p", eff["default_top_p"]),
        top_k=cfg.get("top_k", eff["default_top_k"]),
        repeat_penalty=cfg.get("repeat_penalty", eff["default_repeat_penalty"]),
        max_tokens=cfg.get("max_tokens", eff["default_max_tokens"]),
        context_size=cfg.get("context_size", eff["default_context_size"]),
    )
    api_base = cfg.get("api_base", eff["default_api_base"])
    return create_provider(provider_type, api_base, model, params), params


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(payload: ChatCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Chat:
    chat = Chat(
        owner_id=user.id, title=payload.title, folder_id=payload.folder_id,
        primary_character_id=payload.primary_character_id,
        provider=payload.provider, model_name=payload.model_name,
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.get("", response_model=list[ChatResponse])
async def list_chats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> list[Chat]:
    result = await db.execute(
        select(Chat).where(Chat.owner_id == user.id, Chat.is_archived == False).order_by(Chat.updated_at.desc())  # noqa: E712
    )
    return list(result.scalars())


@router.patch("/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_id: str, payload: ChatUpdate,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> Chat:
    chat = await _get_owned_chat(db, chat_id, user)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(chat, field, value)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_chat(
    chat_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> None:
    chat = await _get_owned_chat(db, chat_id, user)
    await db.delete(chat)
    await db.commit()


@router.get("/{chat_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    chat_id: str,
    limit: int = Query(200, ge=1, le=1000),
    before_sequence: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Message]:
    """Returns up to `limit` messages, oldest-first within the page.
    Without before_sequence: the most recent page (i.e. the tail of the chat).
    With before_sequence: the page immediately preceding that sequence number —
    used by the frontend's "load earlier history" control so opening a long
    chat doesn't have to fetch and parse its entire message history at once."""
    chat = await _get_owned_chat(db, chat_id, user)
    stmt = select(Message).where(Message.chat_id == chat.id, Message.is_deleted == False)  # noqa: E712
    if before_sequence is not None:
        stmt = stmt.where(Message.sequence < before_sequence)
    stmt = stmt.order_by(Message.sequence.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(reversed(result.scalars().all()))


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    payload: SendMessageRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Streams the assistant reply as Server-Sent Events. Persists both
    messages and schedules the hidden memory extraction pass afterward."""
    chat = await _get_owned_chat(db, chat_id, user)

    next_seq = (await db.execute(select(func.max(Message.sequence)).where(Message.chat_id == chat.id))).scalar() or 0
    user_msg = Message(
        chat_id=chat.id, role=MessageRole.user, content=payload.content,
        sequence=next_seq + 1, token_count=count_tokens(payload.content),
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    provider, params = await _resolve_provider(db, chat)
    built = await build_prompt(db, chat, payload.content, params.context_size, params.max_tokens)

    async def event_stream():
        full_text = ""
        think_filter = ThinkTagStripper()
        try:
            async for delta in provider.stream_chat(built.messages):
                visible = think_filter.feed(delta)
                if not visible:
                    continue  # entirely reasoning content (or a buffered partial tag) — nothing to show yet
                full_text += visible
                yield f"data: {json.dumps({'delta': visible})}\n\n"
        except Exception as exc:  # provider unreachable, model error, etc.
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return

        trailing = think_filter.flush()
        if trailing:
            full_text += trailing
            yield f"data: {json.dumps({'delta': trailing})}\n\n"

        # persist assistant message in its own session (request-scoped db
        # session may be closed by the time the generator finishes on some
        # ASGI servers, so we open a fresh one for the write + background task)
        async with AsyncSessionLocal() as write_db:
            seq = (await write_db.execute(select(func.max(Message.sequence)).where(Message.chat_id == chat.id))).scalar() or 0
            assistant_msg = Message(
                chat_id=chat.id, role=MessageRole.assistant, content=full_text,
                sequence=seq + 1, token_count=count_tokens(full_text),
            )
            write_db.add(assistant_msg)
            chat_row = await write_db.get(Chat, chat.id)
            await write_db.commit()
            await write_db.refresh(assistant_msg)

            yield f"data: {json.dumps({'done': True, 'message_id': assistant_msg.id})}\n\n"

            eff = await get_effective_settings(write_db)
            if eff["memory_extraction_enabled"]:
                every_n = max(1, int(eff.get("memory_extraction_every_n_messages", 4)))
                unprocessed_count = (
                    await write_db.execute(
                        select(func.count()).select_from(Message).where(
                            Message.chat_id == chat.id,
                            Message.role == MessageRole.assistant,
                            Message.memory_processed == False,  # noqa: E712
                            Message.is_deleted == False,  # noqa: E712
                        )
                    )
                ).scalar() or 0
                total_assistant_count = (
                    await write_db.execute(
                        select(func.count()).select_from(Message).where(
                            Message.chat_id == chat.id,
                            Message.role == MessageRole.assistant,
                            Message.is_deleted == False,  # noqa: E712
                        )
                    )
                ).scalar() or 0
                # The very first exchange gets extracted right away regardless of the
                # batch threshold — opening scene-setting (world rules, the character's
                # backstory, initial relationships) is exactly the kind of thing that's
                # most costly to lose, and it's cheap to run once per chat rather than
                # making it wait for every_n messages to accumulate.
                is_first_exchange = total_assistant_count == 1
                if unprocessed_count >= every_n or is_first_exchange:
                    background_tasks.add_task(_run_extraction_task, chat.id)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _run_extraction_task(chat_id: str) -> None:
    """Runs in a background task with its own DB session and provider instance.
    Processes every unprocessed assistant reply accumulated for this chat in
    one batched call (see memory_extraction_every_n_messages)."""
    async with AsyncSessionLocal() as db:
        chat = await db.get(Chat, chat_id)
        if not chat:
            return
        provider, _ = await _resolve_provider(db, chat)
        await run_memory_extraction(db, provider, chat_id)


@router.patch("/{chat_id}/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    chat_id: str, message_id: str, payload: EditMessageRequest,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> Message:
    chat = await _get_owned_chat(db, chat_id, user)
    msg = await db.get(Message, message_id)
    if msg is None or msg.chat_id != chat.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    msg.content = payload.content
    msg.token_count = count_tokens(payload.content)
    await db.commit()
    await db.refresh(msg)
    return msg


@router.delete("/{chat_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_message(
    chat_id: str, message_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> None:
    chat = await _get_owned_chat(db, chat_id, user)
    msg = await db.get(Message, message_id)
    if msg is None or msg.chat_id != chat.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    msg.is_deleted = True
    await db.commit()
