from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MemoryFlagsUpdate(BaseModel):
    is_pinned: Optional[bool] = None
    is_canon: Optional[bool] = None
    is_false: Optional[bool] = None
    is_enabled: Optional[bool] = None
    importance: Optional[int] = None


class CharacterCreate(BaseModel):
    name: str
    description: Optional[str] = None
    age: Optional[str] = None
    gender: Optional[str] = None
    race: Optional[str] = None
    personality: Optional[str] = None
    backstory: Optional[str] = None
    is_player_character: bool = False


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    age: Optional[str] = None
    gender: Optional[str] = None
    race: Optional[str] = None
    personality: Optional[str] = None
    backstory: Optional[str] = None
    current_state: Optional[str] = None


class CharacterResponse(BaseModel):
    id: str
    chat_id: str
    name: str
    description: Optional[str]
    age: Optional[str]
    gender: Optional[str]
    race: Optional[str]
    personality: Optional[str]
    backstory: Optional[str]
    current_state: Optional[str]
    is_pinned: bool
    is_canon: bool
    is_false: bool
    is_enabled: bool
    importance: int
    updated_at: datetime

    class Config:
        from_attributes = True


class TimelineEntryResponse(BaseModel):
    story_day: int
    title: str
    entity_type: str
    entity_id: str

    class Config:
        from_attributes = True


class SearchResultItem(BaseModel):
    entity_type: str
    entity_id: str
    chat_id: str
    title: str
    snippet: str


class PromptInspectorBlock(BaseModel):
    label: str
    content: str
    token_count: int
    selected_entities: list[dict]


class PromptInspectorResponse(BaseModel):
    blocks: list[PromptInspectorBlock]
    total_tokens: int
