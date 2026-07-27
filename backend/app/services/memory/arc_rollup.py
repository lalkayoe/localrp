"""
Automatic long-term compression: once `arc_summary_every_n_scenes` new
SceneSummary rows have piled up unrolled for a chat, compress them into a
single ArcSummary via one extra hidden LLM call. This is what lets far-back
context survive in a long chat even after it has scrolled out of the raw
message window and out of any single scene summary — the ArcSummary gets a
baseline relevance floor in retrieval.py regardless of keyword match.

Runs at the end of run_memory_extraction, after that batch's own scene
summary (if any) has been committed, so it always sees up-to-date data.
Failures here (provider timeout, bad output) are non-fatal: the scenes
stay unrolled and get picked up again the next time enough of them pile up.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import ArcSummary, SceneSummary, StoryArc
from app.services.providers.base import LLMProvider

logger = logging.getLogger(__name__)

_ROLLUP_SYSTEM_PROMPT = """You compress several short scene summaries from an ongoing roleplay into ONE
higher-level paragraph capturing the overall arc so far: who's involved, what's changed, and what's
still unresolved. Write 4-8 sentences of plain prose. No meta-commentary, no markdown, no headers,
no bullet points — a paragraph a narrator could read to recall "the story so far"."""


async def maybe_roll_up_arc_summary(db: AsyncSession, provider: LLMProvider, chat_id: str) -> None:
    threshold = max(1, settings.arc_summary_every_n_scenes)

    unrolled = (
        await db.execute(
            select(SceneSummary)
            .where(SceneSummary.chat_id == chat_id, SceneSummary.arc_summary_id.is_(None))
            .order_by(SceneSummary.created_at)
        )
    ).scalars().all()

    if len(unrolled) < threshold:
        return

    story_arc = (
        await db.execute(
            select(StoryArc)
            .where(StoryArc.chat_id == chat_id, StoryArc.is_resolved == False)  # noqa: E712
            .order_by(StoryArc.created_at.desc())
        )
    ).scalars().first()
    if story_arc is None:
        # No arc has been explicitly named yet (the model hasn't reported a
        # story_arc_updates entry) — open an untitled one just to hang the
        # rollup on. It can be renamed later from the Memory Editor once a
        # real arc title emerges.
        story_arc = StoryArc(chat_id=chat_id, title="Untitled arc")
        db.add(story_arc)
        await db.flush()

    combined = "\n".join(f"- {s.summary}" for s in unrolled)

    try:
        raw_summary = await provider.complete(
            system_prompt=_ROLLUP_SYSTEM_PROMPT,
            user_prompt=combined,
            temperature=0.3,
            max_tokens=400,
        )
    except Exception:
        logger.warning("Arc summary rollup request to the model provider failed, will retry next batch", exc_info=True)
        return

    raw_summary = raw_summary.strip()
    if not raw_summary:
        return

    arc_summary = ArcSummary(chat_id=chat_id, story_arc_id=story_arc.id, summary=raw_summary)
    db.add(arc_summary)
    await db.flush()

    for scene in unrolled:
        scene.arc_summary_id = arc_summary.id

    await db.commit()
