"""
Central application configuration.

All values are overridable via environment variables or a .env file
in the backend/ directory (see .env.example).
"""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LOCALRP_", extra="ignore")

    # --- General ---
    app_name: str = "LocalRP"
    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/localrp.db")
    backups_dir: Path = Path("./data/backups")
    avatars_dir: Path = Path("./data/avatars")

    # --- Server ---
    host: str = "0.0.0.0"          # bind on all interfaces so the phone-on-LAN use case works
    port: int = 8420
    cors_origins: list[str] = ["http://localhost:1420", "http://localhost:5173"]

    # --- Auth ---
    jwt_secret: str = "CHANGE_ME_ON_FIRST_RUN"  # regenerated automatically if left default, see security.py
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 30
    # Only rotate the refresh token itself once it's within this long of its own
    # expiry (see the refresh() route) — rotating on every single silent refresh
    # is what causes "randomly logged out" when several requests race each other.
    refresh_rotate_threshold_days: int = 3
    csrf_secret: str = "CHANGE_ME_ON_FIRST_RUN"

    # --- Rate limiting ---
    login_rate_limit: str = "5/minute"
    api_rate_limit: str = "120/minute"

    # --- Memory engine ---
    memory_extraction_enabled: bool = True
    memory_extraction_every_n_messages: int = 4  # batch the hidden extraction pass instead of running after every reply
    memory_max_injected_tokens: int = 3000       # hard ceiling on how much memory gets injected per prompt
    memory_retrieval_mode: str = "tags"          # "tags" | "embeddings" | "hybrid"
    memory_top_k_per_type: int = 3               # max entries per entity type pulled into a prompt
    scene_summary_every_n_messages: int = 20     # auto-roll a SceneSummary after this many new messages
    arc_summary_every_n_scenes: int = 5          # auto-compress this many SceneSummaries into one ArcSummary

    # --- Default generation provider ---
    default_provider: str = "openai_compatible"  # "llama_cpp" | "lmstudio" | "ollama" | "openai_compatible"
    default_model: str = "gemma-4-26b"
    default_api_base: str = "http://localhost:11434"
    default_context_size: int = 8192
    default_temperature: float = 0.8
    default_top_p: float = 0.95
    default_top_k: int = 40
    default_repeat_penalty: float = 1.1
    default_max_tokens: int = 1024

    # Non-streaming calls (memory extraction, health checks) can legitimately
    # take a while on local hardware for a large model — this is separate
    # from stream_chat, which has no timeout since it's bounded by the user
    # watching tokens arrive.
    provider_request_timeout_seconds: float = 300.0

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.avatars_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
