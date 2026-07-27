"""
Builds the final message list sent to the model for a chat turn.

Structure (in order):
1. A short system prompt: character/persona description ONLY — no memory dump.
2. A single compact "context" system message built from the retrieval
   engine's selection, grouped by entity type, each line attributed
   so the Prompt Inspector can show exactly why it's there.
3. A sliding window of the most recent raw messages (bounded by
   context_size minus the above and minus max_tokens headroom).

This is intentionally the ONLY place in the codebase that assembles a
prompt, so token accounting for the Inspector stays accurate in one spot.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Character, Chat, Message, MessageRole
from app.services.memory.retrieval import ScoredEntity, retrieve_relevant_memory
from app.utils.tokens import count_tokens


@dataclass
class PromptBlock:
    """One labeled block of the final prompt, for the Prompt Inspector."""
    label: str
    content: str
    token_count: int
    source_entities: list[ScoredEntity]


@dataclass
class BuiltPrompt:
    messages: list[dict]              # what actually gets sent to the provider
    blocks: list[PromptBlock]         # what gets shown in the Prompt Inspector
    total_tokens: int


def _character_system_prompt(character: Character | None) -> str:
    if character is None:
        return "You are a skilled roleplay narrator. Stay in character, be vivid and concise."
    lines = [f"You are roleplaying as {character.name}."]
    if character.personality:
        lines.append(f"Personality: {character.personality}")
    if character.description:
        lines.append(f"Description: {character.description}")
    if character.current_state:
        lines.append(f"Current state: {character.current_state}")
    lines.append("Stay fully in character. Write vivid, concise prose. Never break the fourth wall.")
    return "\n".join(lines)


def _memory_context_block(selected: list[ScoredEntity]) -> str | None:
    if not selected:
        return None
    by_type: dict[str, list[str]] = {}
    for s in selected:
        by_type.setdefault(s.entity_type.value, []).append(f"- {s.content}")

    sections = []
    for etype, lines in by_type.items():
        sections.append(f"[{etype}]\n" + "\n".join(lines))
    return (
        "Relevant story context (use only what's relevant, do not restate verbatim):\n\n"
        + "\n\n".join(sections)
    )


async def build_prompt(
    db: AsyncSession,
    chat: Chat,
    latest_user_message: str,
    context_size: int,
    max_tokens_for_reply: int,
) -> BuiltPrompt:
    blocks: list[PromptBlock] = []
    messages: list[dict] = []

    # 1. character/persona system prompt
    character = None
    if chat.primary_character_id:
        character = await db.get(Character, chat.primary_character_id)
    persona_text = _character_system_prompt(character)
    persona_tokens = count_tokens(persona_text)
    blocks.append(PromptBlock(label="persona", content=persona_text, token_count=persona_tokens, source_entities=[]))
    messages.append({"role": "system", "content": persona_text})

    # 2. relevant memory
    selected = await retrieve_relevant_memory(db, chat.id, latest_user_message)
    memory_text = _memory_context_block(selected)
    if memory_text:
        mem_tokens = count_tokens(memory_text)
        blocks.append(PromptBlock(label="memory_context", content=memory_text, token_count=mem_tokens, source_entities=selected))
        messages.append({"role": "system", "content": memory_text})

    # 3. sliding window of recent raw messages, bounded by remaining budget
    used_tokens = sum(b.token_count for b in blocks)
    budget = context_size - max_tokens_for_reply - used_tokens - 200  # 200-token safety margin

    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat.id, Message.is_deleted == False)  # noqa: E712
        .order_by(Message.sequence.desc())
        .limit(200)
    )
    recent = list(result.scalars())[::-1]  # oldest-first after reversing the desc-limited slice

    window: list[Message] = []
    running = 0
    for msg in reversed(recent):
        t = msg.token_count or count_tokens(msg.content)
        if running + t > budget:
            break
        window.insert(0, msg)
        running += t

    history_text_for_inspector = "\n".join(f"[{m.role.value}] {m.content[:80]}..." for m in window)
    blocks.append(PromptBlock(
        label="conversation_history",
        content=history_text_for_inspector,
        token_count=running,
        source_entities=[],
    ))

    for msg in window:
        role = "assistant" if msg.role == MessageRole.assistant else "user"
        messages.append({"role": role, "content": msg.content})

    total_tokens = sum(b.token_count for b in blocks)
    return BuiltPrompt(messages=messages, blocks=blocks, total_tokens=total_tokens)
