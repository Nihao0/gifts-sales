from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram credentials
    api_id: int | None = None
    api_hash: str | None = None
    phone: str | None = None
    session_name: str = "data/session"
    session_password: str | None = None

    # Database
    db_url: str = "sqlite+aiosqlite:///data/gifts.db"

    # Behaviour
    dry_run: bool = False
    flood_sleep_threshold: int = 60
    max_job_attempts: int = 5
    ton_to_stars_rate: float | None = None
    require_ton_rate_for_sales: bool = True
    max_bulk_jobs: int = 50
    max_price_ton: float | None = None
    portals_recipient: str | None = None
    portals_api_base: str = "https://portal-market.com/api"
    portals_auth_data: str | None = None
    bot_token: str | None = None
    approval_chat_id: str | None = None

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        if v not in ("json", "console"):
            raise ValueError("log_format must be 'json' or 'console'")
        return v

    def ensure_data_dir(self) -> None:
        Path("data").mkdir(exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
