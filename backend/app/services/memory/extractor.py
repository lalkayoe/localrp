"""
Runs once memory_extraction_every_n_messages unprocessed assistant replies
have accumulated for a chat: calls the model a second time (hidden from the
user) to extract structured story-state changes across the whole batch at
once, then merges them into the DB.

Entity resolution is name-based within a chat: if a character/location/
etc with a matching name (case-insensitive, alias-aware) already exists,
it's updated; otherwise a new row is created. This keeps the extraction
prompt simple (the model just says names) while avoiding duplicate rows.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Character, EntityTag, EntityType, Event, Fact, Goal, Item, Location,
    MemoryTag, Message, MessageRole, Organization, Promise, Relationship, SceneSummary, Secret, StoryArc,
)
from app.services.memory.extraction_prompt import EXTRACTION_SYSTEM_PROMPT, build_extraction_user_prompt
from app.services.memory.arc_rollup import maybe_roll_up_arc_summary
from app.services.memory.schemas import ExtractionResult
from app.services.providers.base import LLMProvider

logger = logging.getLogger(__name__)


async def _find_character_by_name(db: AsyncSession, chat_id: str, name: str) -> Character | None:
    result = await db.execute(select(Character).where(Character.chat_id == chat_id))
    name_lower = name.strip().lower()
    for c in result.scalars():
        if c.name.strip().lower() == name_lower:
            return c
        if c.aliases and any(a.strip().lower() == name_lower for a in c.aliases):
            return c
    return None


async def _find_location_by_name(db: AsyncSession, chat_id: str, name: str) -> Location | None:
    result = await db.execute(select(Location).where(Location.chat_id == chat_id))
    name_lower = name.strip().lower()
    for loc in result.scalars():
        if loc.name.strip().lower() == name_lower:
            return loc
    return None


async def _find_item_by_name(db: AsyncSession, chat_id: str, name: str) -> Item | None:
    result = await db.execute(select(Item).where(Item.chat_id == chat_id))
    name_lower = name.strip().lower()
    for it in result.scalars():
        if it.name.strip().lower() == name_lower:
            return it
    return None


async def _find_organization_by_name(db: AsyncSession, chat_id: str, name: str) -> Organization | None:
    result = await db.execute(select(Organization).where(Organization.chat_id == chat_id))
    name_lower = name.strip().lower()
    for org in result.scalars():
        if org.name.strip().lower() == name_lower:
            return org
    return None


async def _get_or_create_tag(db: AsyncSession, chat_id: str, name: str) -> MemoryTag:
    result = await db.execute(select(MemoryTag).where(MemoryTag.chat_id == chat_id, MemoryTag.name == name))
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = MemoryTag(chat_id=chat_id, name=name)
        db.add(tag)
        await db.flush()
    return tag


async def _attach_tags(db: AsyncSession, chat_id: str, entity_type: EntityType, entity_id: str, tag_names: list[str]) -> None:
    for raw in tag_names:
        name = raw.strip().lower()
        if not name:
            continue
        tag = await _get_or_create_tag(db, chat_id, name)
        db.add(EntityTag(tag_id=tag.id, entity_type=entity_type, entity_id=entity_id))


def _parse_json_response(raw_text: str) -> dict:
    """Model output should be raw JSON, but strip markdown fences defensively."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Memory extraction returned non-JSON output, skipping this pass")
        return {}


async def run_memory_extraction(
    db: AsyncSession,
    provider: LLMProvider,
    chat_id: str,
) -> None:
    """Entry point called by the chat service once memory_extraction_every_n_messages
    unprocessed assistant replies have accumulated for this chat (see
    memory_extraction_every_n_messages in settings). Batches all of them into a
    single hidden extraction call instead of one call per reply, so the model
    isn't hit with a second generation after every single message."""
    all_messages = (
        await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id, Message.is_deleted == False)  # noqa: E712
            .order_by(Message.sequence)
        )
    ).scalars().all()

    # Pair each not-yet-processed assistant reply with the user message that
    # prompted it, walking the chat in order. Already-processed assistant
    # messages (from a previous batch) are skipped entirely.
    exchanges: list[tuple[str, str]] = []
    unprocessed_assistant_msgs: list[Message] = []
    pending_user_content = ""
    for msg in all_messages:
        if msg.role == MessageRole.user:
            pending_user_content = msg.content
        elif msg.role == MessageRole.assistant and not msg.memory_processed:
            exchanges.append((pending_user_content, msg.content))
            unprocessed_assistant_msgs.append(msg)
            pending_user_content = ""

    if not unprocessed_assistant_msgs:
        return  # nothing new to extract (e.g. batch already processed, or chat has no replies yet)

    last_assistant_message = unprocessed_assistant_msgs[-1]

    known_chars = (await db.execute(select(Character.name).where(Character.chat_id == chat_id))).scalars().all()
    known_locs = (await db.execute(select(Location.name).where(Location.chat_id == chat_id))).scalars().all()
    known_items = (await db.execute(select(Item.name).where(Item.chat_id == chat_id))).scalars().all()
    known_orgs = (await db.execute(select(Organization.name).where(Organization.chat_id == chat_id))).scalars().all()

    last_event = (
        await db.execute(
            select(Event).where(Event.chat_id == chat_id).order_by(Event.story_day.desc()).limit(1)
        )
    ).scalar_one_or_none()
    current_story_day = last_event.story_day if last_event else None

    prompt = build_extraction_user_prompt(
        exchanges=exchanges,
        known_character_names=list(known_chars),
        known_location_names=list(known_locs),
        known_item_names=list(known_items),
        known_organization_names=list(known_orgs),
        current_story_day=current_story_day,
    )

    try:
        raw_response = await provider.complete(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.2,   # low temperature: this is extraction, not creative writing
            max_tokens=1200 + 300 * (len(exchanges) - 1),  # a bigger batch needs a bit more room to report everything
        )
    except Exception:
        # Provider unreachable, timed out, or returned an HTTP error. The
        # visible reply has already been sent to the user by this point —
        # this pass runs silently in the background — so we just skip this
        # batch rather than let the exception propagate into the ASGI
        # background-task machinery. It will be retried once enough new
        # messages accumulate to trigger the next batch.
        logger.warning("Memory extraction request to the model provider failed, skipping this batch", exc_info=True)
        return

    data = _parse_json_response(raw_response)
    if not data:
        return

    try:
        result = ExtractionResult.model_validate(data)
    except Exception:
        logger.warning(
            "Memory extraction JSON failed schema validation, skipping this batch. Raw payload: %s",
            raw_response[:2000],
            exc_info=True,
        )
        return

    await _apply_extraction(db, chat_id, last_assistant_message, result, current_story_day)
    for msg in unprocessed_assistant_msgs:
        msg.memory_processed = True
    await db.commit()

    # Long-term compression: if enough SceneSummaries have piled up unrolled,
    # fold them into one ArcSummary now. Cheap to check (one indexed query)
    # even when it's a no-op, and keeps this the single place that runs
    # after every extraction batch.
    await maybe_roll_up_arc_summary(db, provider, chat_id)


async def _apply_extraction(
    db: AsyncSession,
    chat_id: str,
    assistant_message: Message,
    result: ExtractionResult,
    current_story_day: int | None,
) -> None:
    # --- characters ---
    for nc in result.new_characters:
        existing = await _find_character_by_name(db, chat_id, nc.name)
        if existing:
            continue
        char = Character(
            chat_id=chat_id, name=nc.name, description=nc.description,
            age=nc.age, gender=nc.gender, race=nc.race, personality=nc.personality,
            last_seen_message_id=assistant_message.id,
        )
        db.add(char)
        await db.flush()
        await _attach_tags(db, chat_id, EntityType.character, char.id, result.tags)

    for cu in result.character_updates:
        char = await _find_character_by_name(db, chat_id, cu.name)
        if not char:
            continue
        if cu.current_state:
            char.current_state = cu.current_state
        if cu.new_backstory_fragment:
            char.backstory = f"{char.backstory or ''}\n{cu.new_backstory_fragment}".strip()
        char.last_seen_message_id = assistant_message.id

    # --- relationships ---
    for rc in result.relationship_changes:
        char_a = await _find_character_by_name(db, chat_id, rc.character_a)
        char_b = await _find_character_by_name(db, chat_id, rc.character_b)
        if not char_a or not char_b:
            continue
        rel = Relationship(
            chat_id=chat_id, character_a_id=char_a.id, character_b_id=char_b.id,
            label=rc.label, description=rc.description, intensity=rc.intensity or 5,
        )
        db.add(rel)

    # --- locations ---
    location_cache: dict[str, Location] = {}
    for nl in result.new_locations:
        existing = await _find_location_by_name(db, chat_id, nl.name)
        if existing:
            location_cache[nl.name.lower()] = existing
            continue
        loc = Location(chat_id=chat_id, name=nl.name, description=nl.description)
        db.add(loc)
        await db.flush()
        location_cache[nl.name.lower()] = loc

    # --- items ---
    for ni in result.new_items:
        owner = await _find_character_by_name(db, chat_id, ni.owner) if ni.owner else None
        existing_item = await _find_item_by_name(db, chat_id, ni.name)
        if existing_item:
            # already known — just update ownership/description if the model gave new info
            if owner:
                existing_item.owner_character_id = owner.id
            if ni.description:
                existing_item.description = ni.description
            continue
        db.add(Item(chat_id=chat_id, name=ni.name, description=ni.description, owner_character_id=owner.id if owner else None))

    # --- organizations ---
    for no in result.new_organizations:
        existing_org = await _find_organization_by_name(db, chat_id, no.name)
        if existing_org:
            if no.description:
                existing_org.description = no.description
            continue
        db.add(Organization(chat_id=chat_id, name=no.name, description=no.description))

    # --- events ---
    for ne in result.new_events:
        loc = None
        if ne.location:
            loc = location_cache.get(ne.location.lower()) or await _find_location_by_name(db, chat_id, ne.location)
        event = Event(
            chat_id=chat_id, title=ne.title, description=ne.description,
            story_day=ne.story_day if ne.story_day is not None else current_story_day,
            occurred_at_message_id=assistant_message.id,
            location_id=loc.id if loc else None,
        )
        db.add(event)
        await db.flush()
        await _attach_tags(db, chat_id, EntityType.event, event.id, result.tags)

    # --- facts ---
    for nf in result.new_facts:
        subject_char = await _find_character_by_name(db, chat_id, nf.subject) if nf.subject else None
        db.add(Fact(
            chat_id=chat_id, content=nf.content,
            subject_entity_type=EntityType.character if subject_char else None,
            subject_entity_id=subject_char.id if subject_char else None,
        ))

    # --- goals / promises / secrets ---
    for ng in result.new_goals:
        char = await _find_character_by_name(db, chat_id, ng.character) if ng.character else None
        db.add(Goal(chat_id=chat_id, character_id=char.id if char else None, description=ng.description))

    for np_ in result.new_promises:
        made_by = await _find_character_by_name(db, chat_id, np_.made_by) if np_.made_by else None
        made_to = await _find_character_by_name(db, chat_id, np_.made_to) if np_.made_to else None
        db.add(Promise(
            chat_id=chat_id, description=np_.description,
            made_by_character_id=made_by.id if made_by else None,
            made_to_character_id=made_to.id if made_to else None,
        ))

    for ns in result.new_secrets:
        owner = await _find_character_by_name(db, chat_id, ns.owner) if ns.owner else None
        known_ids = []
        for name in ns.known_by:
            c = await _find_character_by_name(db, chat_id, name)
            if c:
                known_ids.append(c.id)
        db.add(Secret(
            chat_id=chat_id, owner_character_id=owner.id if owner else None,
            description=ns.description, known_by_character_ids=known_ids,
        ))

    # --- story arcs ---
    for sa in result.story_arc_updates:
        existing_arc = (
            await db.execute(select(StoryArc).where(StoryArc.chat_id == chat_id, StoryArc.title == sa.title))
        ).scalar_one_or_none()
        if existing_arc:
            existing_arc.is_resolved = sa.is_resolved
            if sa.description:
                existing_arc.description = sa.description
        else:
            db.add(StoryArc(chat_id=chat_id, title=sa.title, description=sa.description, is_resolved=sa.is_resolved))

    # --- scene summary ---
    if result.scene_summary:
        summary = SceneSummary(
            chat_id=chat_id,
            start_message_id=assistant_message.id,
            end_message_id=assistant_message.id,
            story_day=current_story_day,
            summary=result.scene_summary,
        )
        db.add(summary)
        await db.flush()
        await _attach_tags(db, chat_id, EntityType.scene_summary, summary.id, result.tags)
