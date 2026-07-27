from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ChatCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: str = "New Chat"
    folder_id: Optional[str] = None
    primary_character_id: Optional[str] = None
    provider: Optional[str] = None
    model_name: Optional[str] = None


class ChatResponse(BaseModel):
    id: str
    title: str
    folder_id: Optional[str]
    primary_character_id: Optional[str]
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: Optional[str] = None
    folder_id: Optional[str] = None
    primary_character_id: Optional[str] = None
    provider: Optional[str] = None
    model_name: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sequence: int
    created_at: datetime

    class Config:
        from_attributes = True


class SendMessageRequest(BaseModel):
    content: str


class EditMessageRequest(BaseModel):
    content: str
