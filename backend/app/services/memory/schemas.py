"""
Schema for the structured memory extraction pass.

After every assistant reply, a hidden second call is made to the same
model asking it to return ONLY this JSON shape describing what changed
in the story. Nothing here is shown to the user. Every field is optional
because most turns won't touch most categories.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


def _coerce_bare_string(key: str):
    """Some local models shortcut a `{"name": "..."}`-shaped item down to a
    bare string (e.g. new_characters: ["Anna", "Marcus"] instead of
    [{"name": "Anna"}, ...]). Rather than let one bad item invalidate the
    *entire* extraction pass (losing every other category from this turn
    too), accept the shorthand and normalize it to the expected shape."""

    def _validator(cls, data: Any) -> Any:  # noqa: ANN001
        if isinstance(data, str):
            return {key: data}
        return data

    return model_validator(mode="before")(classmethod(_validator))


class NewCharacter(BaseModel):
    name: str
    description: Optional[str] = None
    age: Optional[str] = None
    gender: Optional[str] = None
    race: Optional[str] = None
    personality: Optional[str] = None

    _coerce = _coerce_bare_string("name")


class CharacterUpdate(BaseModel):
    name: str  # matched against existing characters by name/alias
    current_state: Optional[str] = None
    personality_delta: Optional[str] = None
    new_backstory_fragment: Optional[str] = None

    _coerce = _coerce_bare_string("name")


class RelationshipChange(BaseModel):
    character_a: str
    character_b: str
    label: str
    description: Optional[str] = None
    intensity: Optional[int] = Field(default=None, ge=1, le=10)


class NewEvent(BaseModel):
    title: str
    description: Optional[str] = None
    story_day: Optional[int] = None
    location: Optional[str] = None
    involved_characters: list[str] = Field(default_factory=list)

    _coerce = _coerce_bare_string("title")


class NewLocation(BaseModel):
    name: str
    description: Optional[str] = None
    parent_location: Optional[str] = None

    _coerce = _coerce_bare_string("name")


class NewItem(BaseModel):
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None

    _coerce = _coerce_bare_string("name")


class NewOrganization(BaseModel):
    name: str
    description: Optional[str] = None

    _coerce = _coerce_bare_string("name")


class NewFact(BaseModel):
    content: str
    subject: Optional[str] = None  # name of the character/location/etc this fact is about

    _coerce = _coerce_bare_string("content")


class NewGoal(BaseModel):
    character: Optional[str] = None
    description: str

    _coerce = _coerce_bare_string("description")


class NewPromise(BaseModel):
    made_by: Optional[str] = None
    made_to: Optional[str] = None
    description: str

    _coerce = _coerce_bare_string("description")


class NewSecret(BaseModel):
    owner: Optional[str] = None
    description: str
    known_by: list[str] = Field(default_factory=list)

    _coerce = _coerce_bare_string("description")


class StoryArcUpdate(BaseModel):
    title: str
    description: Optional[str] = None
    is_resolved: bool = False

    _coerce = _coerce_bare_string("title")


class ExtractionResult(BaseModel):
    """Top-level shape the model must return, and nothing else."""
    new_characters: list[NewCharacter] = Field(default_factory=list)
    character_updates: list[CharacterUpdate] = Field(default_factory=list)
    relationship_changes: list[RelationshipChange] = Field(default_factory=list)
    new_events: list[NewEvent] = Field(default_factory=list)
    new_locations: list[NewLocation] = Field(default_factory=list)
    new_items: list[NewItem] = Field(default_factory=list)
    new_organizations: list[NewOrganization] = Field(default_factory=list)
    new_facts: list[NewFact] = Field(default_factory=list)
    new_goals: list[NewGoal] = Field(default_factory=list)
    new_promises: list[NewPromise] = Field(default_factory=list)
    new_secrets: list[NewSecret] = Field(default_factory=list)
    story_arc_updates: list[StoryArcUpdate] = Field(default_factory=list)
    scene_summary: Optional[str] = None  # 2-5 sentences, only set when a scene genuinely closed
    tags: list[str] = Field(default_factory=list)  # free tags describing this exchange, feeds retrieval
