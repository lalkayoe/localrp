"""
Relevance retrieval engine.

Default mode ("tags"): score memory entities by overlap between tags/
entity-names extracted from the latest user message and the tags/links
already stored against each entity. Cheap, deterministic, explainable —
which matters for the Prompt Inspector.

Optional mode ("embeddings"): cosine similarity against MemoryEmbedding
rows, computed in Python (fine at this data scale; swap for sqlite-vec
if a chat grows huge). Selected per Settings.memory_retrieval_mode.

Either mode is capped by settings.memory_max_injected_tokens so a prompt
can never balloon regardless of how much matches.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import (
    Character, EntityTag, EntityType, Event, Fact, Goal, Item, Location, MemoryEmbedding, MemoryLink,
    MemoryTag, Organization, Promise, Relationship, SceneSummary, Secret, StoryArc, ArcSummary,
)
from app.utils.tokens import count_tokens

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9']+")


@dataclass
class ScoredEntity:
    entity_type: EntityType
    entity_id: str
    label: str            # short human-readable identifier, e.g. character name
    content: str           # text that would be injected into the prompt
    score: float
    reasons: list[str] = field(default_factory=list)  # why it was selected — shown in Prompt Inspector
    token_count: int = 0


def _extract_keywords(text: str) -> set[str]:
    words = {w.lower() for w in _WORD_RE.findall(text) if len(w) > 2}
    return words


async def _candidate_entities(db: AsyncSession, chat_id: str) -> list[tuple[EntityType, object]]:
    """Pull all enabled, non-false entities for a chat. Cheap at typical RP-chat scale."""
    candidates: list[tuple[EntityType, object]] = []

    for model, etype in (
        (Character, EntityType.character), (Location, EntityType.location),
        (Item, EntityType.item), (Organization, EntityType.organization), (Event, EntityType.event),
        (Fact, EntityType.fact), (Goal, EntityType.goal), (Promise, EntityType.promise),
        (Secret, EntityType.secret), (SceneSummary, EntityType.scene_summary),
        (StoryArc, EntityType.story_arc), (ArcSummary, EntityType.arc_summary),
    ):
        result = await db.execute(select(model).where(model.chat_id == chat_id, model.is_enabled == True, model.is_false == False))  # noqa: E712
        for row in result.scalars():
            candidates.append((etype, row))

    result = await db.execute(select(Relationship).where(Relationship.chat_id == chat_id, Relationship.is_enabled == True))  # noqa: E712
    for row in result.scalars():
        candidates.append((EntityType.relationship, row))

    return candidates


def _entity_to_text(etype: EntityType, row: object) -> tuple[str, str]:
    """Returns (label, injectable_text)."""
    if etype == EntityType.character:
        parts = [row.name]
        if row.current_state:
            parts.append(f"current state: {row.current_state}")
        elif row.description:
            parts.append(row.description[:200])
        return row.name, f"{row.name} — {'; '.join(parts[1:]) or 'no notable state'}"
    if etype == EntityType.location:
        return row.name, f"{row.name}: {row.description or ''}".strip()
    if etype == EntityType.item:
        owner_suffix = ""  # owner name resolution would need a join; keep this pass cheap and name-free
        return row.name, f"{row.name}: {row.description or ''}".strip() + owner_suffix
    if etype == EntityType.organization:
        return row.name, f"{row.name}: {row.description or ''}".strip()
    if etype == EntityType.event:
        day = f"Day {row.story_day}: " if row.story_day is not None else ""
        return row.title, f"{day}{row.title} — {row.description or ''}".strip()
    if etype == EntityType.fact:
        return row.content[:40], row.content
    if etype == EntityType.goal:
        return row.description[:40], f"Goal: {row.description}" + (" (completed)" if row.is_completed else "")
    if etype == EntityType.promise:
        status = "broken" if row.is_broken else ("fulfilled" if row.is_fulfilled else "open")
        return row.description[:40], f"Promise ({status}): {row.description}"
    if etype == EntityType.secret:
        return row.description[:40], f"Secret: {row.description}"
    if etype == EntityType.scene_summary:
        return f"scene@{row.story_day}", row.summary
    if etype == EntityType.story_arc:
        status = "resolved" if row.is_resolved else "ongoing"
        return row.title, f"Story arc ({status}): {row.title}" + (f" — {row.description}" if row.description else "")
    if etype == EntityType.arc_summary:
        return f"arc-summary:{row.story_arc_id}", row.summary
    if etype == EntityType.relationship:
        return row.label, f"Relationship ({row.label}): {row.description or ''}".strip()
    return str(row), str(row)


async def _tags_for_entity(db: AsyncSession, etype: EntityType, entity_id: str) -> set[str]:
    result = await db.execute(
        select(MemoryTag.name)
        .join(EntityTag, EntityTag.tag_id == MemoryTag.id)
        .where(EntityTag.entity_type == etype, EntityTag.entity_id == entity_id)
    )
    return {t.lower() for t in result.scalars()}


async def _linked_boost(db: AsyncSession, chat_id: str, seed_ids: set[str]) -> dict[str, float]:
    """Entities directly linked (MemoryLink) to an already-high-scoring entity get a small boost —
    this is how e.g. mentioning a character pulls in their close relationships/items too."""
    if not seed_ids:
        return {}
    boosts: dict[str, float] = {}
    result = await db.execute(select(MemoryLink).where(MemoryLink.chat_id == chat_id, MemoryLink.is_canon == True))  # noqa: E712
    for link in result.scalars():
        if link.from_id in seed_ids:
            boosts[link.to_id] = boosts.get(link.to_id, 0.0) + 0.3 * link.strength
        if link.to_id in seed_ids:
            boosts[link.from_id] = boosts.get(link.from_id, 0.0) + 0.3 * link.strength
    return boosts


async def retrieve_relevant_memory(
    db: AsyncSession,
    chat_id: str,
    latest_user_message: str,
) -> list[ScoredEntity]:
    """Main entry point: called by the chat service right before building the generation prompt."""
    keywords = _extract_keywords(latest_user_message)
    candidates = await _candidate_entities(db, chat_id)

    scored: list[ScoredEntity] = []
    for etype, row in candidates:
        label, text = _entity_to_text(etype, row)
        reasons: list[str] = []
        score = 0.0

        # 1) direct keyword overlap against name/content
        text_keywords = _extract_keywords(f"{label} {text}")
        overlap = keywords & text_keywords
        if overlap:
            score += len(overlap) * 1.0
            reasons.append(f"keyword match: {', '.join(sorted(overlap))}")

        # 2) tag overlap
        entity_tags = await _tags_for_entity(db, etype, row.id)
        tag_overlap = keywords & entity_tags
        if tag_overlap:
            score += len(tag_overlap) * 1.5
            reasons.append(f"tag match: {', '.join(sorted(tag_overlap))}")

        # 3) pinned entries always included, high floor score
        if getattr(row, "is_pinned", False):
            score += 10.0
            reasons.append("pinned")

        # 3b) arc-level summaries and still-open story arcs exist specifically to carry
        # far-back context forward, so they get a baseline floor even with zero keyword
        # overlap against the current message — otherwise a long chat's early setup can
        # only resurface if the player happens to reuse the same words again.
        if etype == EntityType.arc_summary:
            score += 3.0
            reasons.append("arc summary (always considered relevant)")
        if etype == EntityType.story_arc and not getattr(row, "is_resolved", False):
            score += 1.5
            reasons.append("ongoing story arc")

        # 4) importance weight
        importance = getattr(row, "importance", 5)
        score += (importance - 5) * 0.2

        # 5) recency decay via last_referenced_at is intentionally omitted here to keep
        #    this pass stateless/cheap; recency is instead handled by scene summaries
        #    naturally aging out of keyword relevance.

        if score > 0:
            scored.append(ScoredEntity(
                entity_type=etype, entity_id=row.id, label=label, content=text,
                score=score, reasons=reasons, token_count=count_tokens(text),
            ))

    # graph boost: entities linked to whatever already scored highest
    seed_ids = {s.entity_id for s in sorted(scored, key=lambda s: -s.score)[:5]}
    boosts = await _linked_boost(db, chat_id, seed_ids)
    for s in scored:
        if s.entity_id in boosts:
            s.score += boosts[s.entity_id]
            s.reasons.append("linked to a relevant entity")

    # top-K per entity type, then hard token cap across the whole selection
    by_type: dict[EntityType, list[ScoredEntity]] = {}
    for s in scored:
        by_type.setdefault(s.entity_type, []).append(s)

    selected: list[ScoredEntity] = []
    for etype, items in by_type.items():
        items.sort(key=lambda s: -s.score)
        selected.extend(items[: settings.memory_top_k_per_type])

    selected.sort(key=lambda s: -s.score)

    final: list[ScoredEntity] = []
    token_budget = settings.memory_max_injected_tokens
    for s in selected:
        if s.token_count <= token_budget:
            final.append(s)
            token_budget -= s.token_count
        if token_budget <= 0:
            break

    return final
