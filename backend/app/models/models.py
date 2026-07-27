"""
Core database schema for LocalRP.

Design principles:
- Memory lives in the DB, never dumped wholesale into the prompt.
- Every memory-type table carries: canon/false flags, pinned flag,
  enabled flag, and a revision history (via MemoryRevision).
- MemoryLink is a generic graph edge table connecting any two
  entities (character<->location, character<->character, etc.)
  so the retrieval engine can walk relationships without needing
  a new join table for every pair of types.
- MemoryTag + entity-tag association tables drive the non-embedding
  retrieval path (tag/entity overlap scoring).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, Index, JSON
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def gen_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------

class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class MemoryFlagsMixin:
    """Common flags every memory-bearing entity needs."""
    is_pinned = Column(Boolean, default=False, nullable=False)      # always included when relevant, skip scoring decay
    is_canon = Column(Boolean, default=True, nullable=False)        # false = contradicted / retconned
    is_false = Column(Boolean, default=False, nullable=False)       # explicitly marked wrong by user
    is_enabled = Column(Boolean, default=True, nullable=False)      # soft-disable without deleting
    importance = Column(Integer, default=5, nullable=False)         # 1-10, used in relevance scoring
    last_referenced_at = Column(DateTime, nullable=True)            # last time this was pulled into a prompt


# ---------------------------------------------------------------------------
# Users / Auth
# ---------------------------------------------------------------------------

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)  # argon2
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    chats = relationship("Chat", back_populates="owner", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    user_agent = Column(String(255), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


# ---------------------------------------------------------------------------
# Chats / Messages
# ---------------------------------------------------------------------------

class ChatFolder(Base, TimestampMixin):
    __tablename__ = "chat_folders"

    id = Column(String, primary_key=True, default=gen_uuid)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    parent_id = Column(String, ForeignKey("chat_folders.id", ondelete="SET NULL"), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)

    chats = relationship("Chat", back_populates="folder")


class Chat(Base, TimestampMixin):
    __tablename__ = "chats"

    id = Column(String, primary_key=True, default=gen_uuid)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    folder_id = Column(String, ForeignKey("chat_folders.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False, default="New Chat")
    primary_character_id = Column(String, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)

    # generation settings snapshot (can override global settings per-chat)
    provider = Column(String(50), nullable=True)
    model_name = Column(String(120), nullable=True)
    settings_json = Column(JSON, nullable=True)  # temperature, top_p, top_k, repeat_penalty, max_tokens, ctx_size

    is_archived = Column(Boolean, default=False, nullable=False)

    owner = relationship("User", back_populates="chats")
    folder = relationship("ChatFolder", back_populates="chats")
    messages = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan",
        passive_deletes=True, order_by="Message.sequence",
    )


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    sequence = Column(Integer, nullable=False)  # ordering within chat
    is_deleted = Column(Boolean, default=False, nullable=False)
    edited_from_id = Column(String, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)  # points to prior version
    token_count = Column(Integer, nullable=True)

    # Set on assistant messages once the memory-extraction pass has run
    memory_processed = Column(Boolean, default=False, nullable=False)

    chat = relationship("Chat", back_populates="messages")

    __table_args__ = (
        Index("ix_messages_chat_seq", "chat_id", "sequence"),
    )


# ---------------------------------------------------------------------------
# Generic tagging (drives non-embedding relevance search)
# ---------------------------------------------------------------------------

class MemoryTag(Base):
    __tablename__ = "memory_tags"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("chat_id", "name", name="uq_tag_per_chat"),
    )


class EntityType(str, enum.Enum):
    character = "character"
    location = "location"
    item = "item"
    organization = "organization"
    event = "event"
    fact = "fact"
    goal = "goal"
    promise = "promise"
    secret = "secret"
    relationship = "relationship"
    story_arc = "story_arc"
    scene_summary = "scene_summary"
    arc_summary = "arc_summary"


class EntityTag(Base):
    """Generic association: any memory entity <-> any tag."""
    __tablename__ = "entity_tags"

    id = Column(String, primary_key=True, default=gen_uuid)
    tag_id = Column(String, ForeignKey("memory_tags.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(Enum(EntityType), nullable=False)
    entity_id = Column(String, nullable=False, index=True)

    __table_args__ = (
        Index("ix_entity_tags_lookup", "entity_type", "entity_id"),
    )


class MemoryLink(Base, TimestampMixin):
    """Generic graph edge between two memory entities of any type.

    e.g. character --[knows]--> character
         character --[owns]--> item
         event --[occurred_at]--> location
         character --[involved_in]--> event
    """
    __tablename__ = "memory_links"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)

    from_type = Column(Enum(EntityType), nullable=False)
    from_id = Column(String, nullable=False, index=True)
    to_type = Column(Enum(EntityType), nullable=False)
    to_id = Column(String, nullable=False, index=True)

    relation = Column(String(80), nullable=False)  # free-text edge label, e.g. "ally_of", "owns", "located_in"
    strength = Column(Float, default=1.0, nullable=False)  # decays / boosts relevance scoring
    is_canon = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_links_from", "from_type", "from_id"),
        Index("ix_links_to", "to_type", "to_id"),
    )


class MemoryRevision(Base):
    """Audit history for any edit to a memory entity (edit/delete/pin/canon toggle)."""
    __tablename__ = "memory_revisions"

    id = Column(String, primary_key=True, default=gen_uuid)
    entity_type = Column(Enum(EntityType), nullable=False)
    entity_id = Column(String, nullable=False, index=True)
    changed_by_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    change_type = Column(String(30), nullable=False)  # created|edited|deleted|pinned|unpinned|marked_canon|marked_false|disabled|enabled
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_revisions_entity", "entity_type", "entity_id"),
    )


# Optional, disabled-by-default vector index. Architecture kept so the
# retrieval engine can be switched to embedding-based search per chat
# or globally via Settings, without a schema migration later.
class MemoryEmbedding(Base):
    __tablename__ = "memory_embeddings"

    id = Column(String, primary_key=True, default=gen_uuid)
    entity_type = Column(Enum(EntityType), nullable=False)
    entity_id = Column(String, nullable=False, index=True)
    model_name = Column(String(120), nullable=False)
    vector_json = Column(JSON, nullable=False)  # list[float]; swap to sqlite-vec/faiss later if enabled
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "model_name", name="uq_embedding_entity_model"),
    )


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

class Character(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "characters"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(120), nullable=False, index=True)
    aliases = Column(JSON, nullable=True)  # list[str], helps entity matching in retrieval
    description = Column(Text, nullable=True)
    age = Column(String(30), nullable=True)     # free text: exact ages rarely matter in RP, keep flexible
    gender = Column(String(30), nullable=True)
    race = Column(String(60), nullable=True)
    personality = Column(Text, nullable=True)
    backstory = Column(Text, nullable=True)
    current_state = Column(Text, nullable=True)   # short, frequently-updated "where they are / how they feel now"
    last_seen_message_id = Column(String, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    avatar_path = Column(String(255), nullable=True)

    is_player_character = Column(Boolean, default=False, nullable=False)


class Relationship(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "relationships"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    character_a_id = Column(String, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    character_b_id = Column(String, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(80), nullable=False)     # "friends", "rivals", "in love", "distrustful"
    description = Column(Text, nullable=True)
    intensity = Column(Integer, default=5, nullable=False)  # 1-10


class Location(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "locations"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)
    parent_location_id = Column(String, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)


class Item(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "items"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)
    owner_character_id = Column(String, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)


class Organization(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)


class Event(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "events"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    story_day = Column(Integer, nullable=True)          # in-fiction day counter, drives Timeline ordering
    occurred_at_message_id = Column(String, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    location_id = Column(String, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)


class Fact(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "facts"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    subject_entity_type = Column(Enum(EntityType), nullable=True)
    subject_entity_id = Column(String, nullable=True)


class Goal(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "goals"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    character_id = Column(String, ForeignKey("characters.id", ondelete="CASCADE"), nullable=True)
    description = Column(Text, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False)


class Promise(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "promises"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    made_by_character_id = Column(String, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    made_to_character_id = Column(String, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=False)
    is_fulfilled = Column(Boolean, default=False, nullable=False)
    is_broken = Column(Boolean, default=False, nullable=False)


class Secret(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "secrets"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_character_id = Column(String, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=False)
    known_by_character_ids = Column(JSON, nullable=True)  # list[str] of character ids who know it


class StoryArc(Base, TimestampMixin, MemoryFlagsMixin):
    __tablename__ = "story_arcs"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False, nullable=False)
    started_story_day = Column(Integer, nullable=True)
    resolved_story_day = Column(Integer, nullable=True)


class SceneSummary(Base, TimestampMixin, MemoryFlagsMixin):
    """Short summary of a bounded span of messages (a 'scene'). Kept small on purpose."""
    __tablename__ = "scene_summaries"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    start_message_id = Column(String, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    end_message_id = Column(String, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    story_day = Column(Integer, nullable=True)
    summary = Column(Text, nullable=False)  # kept short: 2-5 sentences, enforced in the extraction prompt
    # Set once this scene has been folded into an ArcSummary rollup, so the
    # rollup job knows which scenes are still pending. NULL = not rolled up yet.
    arc_summary_id = Column(String, ForeignKey("arc_summaries.id", ondelete="SET NULL"), nullable=True, index=True)


class ArcSummary(Base, TimestampMixin, MemoryFlagsMixin):
    """Higher-level rollup of multiple SceneSummaries belonging to one StoryArc."""
    __tablename__ = "arc_summaries"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    story_arc_id = Column(String, ForeignKey("story_arcs.id", ondelete="CASCADE"), nullable=False)
    summary = Column(Text, nullable=False)


class TimelineEntry(Base, TimestampMixin):
    """Materialized, ordered view feeding the Timeline UI directly (denormalized on purpose for fast reads)."""
    __tablename__ = "timeline_entries"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    story_day = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    entity_type = Column(Enum(EntityType), nullable=False)
    entity_id = Column(String, nullable=False)

    __table_args__ = (
        Index("ix_timeline_chat_day", "chat_id", "story_day"),
    )


# ---------------------------------------------------------------------------
# App / global settings (single-row style table, keyed)
# ---------------------------------------------------------------------------

class SettingsKV(Base, TimestampMixin):
    __tablename__ = "settings_kv"

    key = Column(String(120), primary_key=True)
    value_json = Column(JSON, nullable=False)
