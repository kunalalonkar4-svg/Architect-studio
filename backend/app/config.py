"""Protected server configuration, loaded from environment (see .env.example)."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _normalize_db_url(u: str) -> str:
    """Accept the plain postgres:// / postgresql:// string copied from Supabase."""
    u = u.strip()
    for pre in ("postgres://", "postgresql://"):
        if u.startswith(pre):
            return "postgresql+psycopg://" + u[len(pre):]
    return u


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _normalize_db_url(os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://studio:studio@localhost:5432/studio")))
    jwt_secret: str = field(default_factory=lambda: os.environ.get("JWT_SECRET", "dev-only-change-me-please-32-bytes!"))
    jwt_hours: int = field(default_factory=lambda: _int("JWT_HOURS", 72))
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", ""))
    # auto: anthropic when a key is configured, otherwise the deterministic mock
    ai_provider: str = field(default_factory=lambda: os.environ.get("AI_PROVIDER", "auto"))
    ai_timeout_s: int = field(default_factory=lambda: _int("AI_TIMEOUT_S", 60))
    ai_max_retries: int = field(default_factory=lambda: _int("AI_MAX_RETRIES", 2))
    ai_max_rounds: int = field(default_factory=lambda: _int("AI_MAX_ROUNDS", 3))
    ai_max_tokens: int = field(default_factory=lambda: _int("AI_MAX_TOKENS", 4096))
    ai_daily_request_limit: int = field(default_factory=lambda: _int("AI_DAILY_REQUEST_LIMIT", 200))
    ai_daily_token_limit: int = field(default_factory=lambda: _int("AI_DAILY_TOKEN_LIMIT", 600000))
    storage_backend: str = field(default_factory=lambda: os.environ.get("STORAGE_BACKEND", "disk"))   # disk | db (db = PostgreSQL bytea; for hosts without persistent disk)
    storage_dir: Path = field(default_factory=lambda: Path(os.environ.get("STORAGE_DIR", "./storage")).resolve())
    max_upload_mb: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 10))
    cors_origins: list = field(default_factory=lambda: [o for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o])
    frontend_dir: str = field(default_factory=lambda: os.environ.get("FRONTEND_DIR", "../frontend/dist"))
    worker_threads: int = field(default_factory=lambda: _int("WORKER_THREADS", 2))
    run_worker_in_api: bool = field(default_factory=lambda: os.environ.get("RUN_WORKER_IN_API", "1") == "1")

    @property
    def live_ai(self) -> bool:
        if self.ai_provider == "mock":
            return False
        return bool(self.anthropic_api_key)


settings = Settings()
