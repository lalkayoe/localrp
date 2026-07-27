"""
Prompt construction for the hidden memory-extraction call.

Kept deliberately strict: the model is told exactly what JSON shape to
return and instructed to leave arrays empty rather than invent content.

Extraction runs in batches (every N messages, see
memory_extraction_every_n_messages) rather than after every single reply,
so a batch can contain more than one user/assistant exchange. The model
is asked to extract everything NEW across the whole batch at once, which
also gives it more context to resolve things like "who does 'she' refer
to" than a single exchange would.
"""
from __future__ import annotations

EXTRACTION_SYSTEM_PROMPT = """You are a silent story-state extractor running after one or more roleplay replies.
You do not talk to the user. You output ONLY a single JSON object matching the given schema.

Every array item below MUST be a JSON object with these exact keys — NEVER a bare string.
Wrong: "new_characters": ["Anna"]
Right: "new_characters": [{"name": "Anna"}]

Required JSON shape (omit a key from an object only if it's genuinely optional and unknown):
{
  "new_characters": [{"name": str, "description": str|null, "age": str|null, "gender": str|null, "race": str|null, "personality": str|null}],
  "character_updates": [{"name": str, "current_state": str|null, "personality_delta": str|null, "new_backstory_fragment": str|null}],
  "relationship_changes": [{"character_a": str, "character_b": str, "label": str, "description": str|null, "intensity": int|null}],
  "new_events": [{"title": str, "description": str|null, "story_day": int|null, "location": str|null, "involved_characters": [str]}],
  "new_locations": [{"name": str, "description": str|null, "parent_location": str|null}],
  "new_items": [{"name": str, "description": str|null, "owner": str|null}],
  "new_organizations": [{"name": str, "description": str|null}],
  "new_facts": [{"content": str, "subject": str|null}],
  "new_goals": [{"character": str|null, "description": str}],
  "new_promises": [{"made_by": str|null, "made_to": str|null, "description": str}],
  "new_secrets": [{"owner": str|null, "description": str, "known_by": [str]}],
  "story_arc_updates": [{"title": str, "description": str|null, "is_resolved": bool}],
  "scene_summary": str|null,
  "tags": [str]
}

Rules:
- You may be given SEVERAL exchanges at once (a batch). Extract everything NEW or CHANGED across
  the WHOLE batch, deduplicated — if the same character/location/fact shows up in two exchanges,
  report it once. Do not repeat facts that were already true before this batch started.
- If nothing new happened in a category, leave its array empty. Do not invent content to fill fields.
- Use the "Known" lists to reuse existing names exactly as given, instead of creating duplicates
  with slightly different spelling. This matters most for items and organizations: if an item or
  organization from the Known lists is merely mentioned, used, or picked up/handed over again,
  do NOT add it to new_items/new_organizations — only list an item/organization there the first
  time it appears.
- scene_summary should be null unless a scene/beat genuinely concluded during this batch; when set, keep
  it to 2-5 sentences, plain prose, no meta-commentary, covering the whole batch not just its last line.
- tags should be 3-8 short lowercase keywords capturing what this batch was about (characters,
  locations, themes) — they drive future memory retrieval, so be concrete, not generic.
- Output raw JSON only. No markdown fences, no prose before or after.
"""


def build_extraction_user_prompt(
    exchanges: list[tuple[str, str]],
    known_character_names: list[str],
    known_location_names: list[str],
    known_item_names: list[str],
    known_organization_names: list[str],
    current_story_day: int | None,
) -> str:
    """`exchanges` is an ordered list of (user_message, assistant_reply) pairs
    forming the batch to extract from — usually memory_extraction_every_n_messages
    long, but may be shorter (e.g. right before a chat is archived) or a single
    pair if batching is disabled."""
    known_block = (
        f"Known characters: {', '.join(known_character_names) or '(none yet)'}\n"
        f"Known locations: {', '.join(known_location_names) or '(none yet)'}\n"
        f"Known items: {', '.join(known_item_names) or '(none yet)'}\n"
        f"Known organizations: {', '.join(known_organization_names) or '(none yet)'}\n"
        f"Current story day: {current_story_day if current_story_day is not None else 'unknown'}\n"
    )
    exchange_blocks = []
    for i, (user_message, assistant_message) in enumerate(exchanges, start=1):
        exchange_blocks.append(
            f"--- Exchange {i} ---\n"
            f"User: {user_message}\n\n"
            f"Assistant: {assistant_message}"
        )
    return (
        f"{known_block}\n"
        + "\n\n".join(exchange_blocks)
        + "\n\nExtract the JSON now, covering everything new across all exchanges above."
    )
