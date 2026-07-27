"""
Effective settings resolution.

Settings entered in the UI are persisted as key/value rows in the
`settings_kv` table (see SettingsKV). The static `app_settings` object
(app/core/config.py) only holds the *fallback* defaults loaded from
.env at process start — it is never mutated at runtime.

Anything that actually needs to know "what provider/model/api_base is
currently configured" (chat generation, memory extraction, the prompt
inspector) must go through `get_effective_settings()` below rather than
reading `app_settings` directly, or it will silently ignore whatever
the user configured in Settings.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.models.models import SettingsKV

DEFAULTS_MAP = {
    "default_provider": lambda: app_settings.default_provider,
    "default_model": lambda: app_settings.default_model,
    "default_api_base": lambda: app_settings.default_api_base,
    "default_context_size": lambda: app_settings.default_context_size,
    "default_temperature": lambda: app_settings.default_temperature,
    "default_top_p": lambda: app_settings.default_top_p,
    "default_top_k": lambda: app_settings.default_top_k,
    "default_repeat_penalty": lambda: app_settings.default_repeat_penalty,
    "default_max_tokens": lambda: app_settings.default_max_tokens,
    "memory_retrieval_mode": lambda: app_settings.memory_retrieval_mode,
    "memory_extraction_enabled": lambda: app_settings.memory_extraction_enabled,
    "memory_extraction_every_n_messages": lambda: app_settings.memory_extraction_every_n_messages,
}


async def get_effective_settings(db: AsyncSession) -> dict:
    """Static .env defaults, overridden by whatever is stored in settings_kv."""
    defaults = {key: factory() for key, factory in DEFAULTS_MAP.items()}
    result = await db.execute(select(SettingsKV))
    stored = {row.key: row.value_json for row in result.scalars()}
    defaults.update(stored)
    return defaults
