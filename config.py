# Developer by : Mr_Manas_Op
"""Central configuration loader.

Every secret and tunable value is read from environment variables (optionally
from a local ``.env`` file). Nothing sensitive is ever hardcoded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

VERSION = "1.0.0"


class ConfigError(RuntimeError):
    """Raised when the configuration is missing or invalid."""


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number.") from None
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_list(name: str) -> tuple[int, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ()
    try:
        return tuple(int(part) for part in raw.replace(" ", "").split(",") if part)
    except ValueError:
        raise ConfigError(f"{name} must be a comma separated list of numeric IDs.") from None


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    bot_token: str
    session_string: str
    owner_ids: tuple[int, ...]
    jamendo_client_id: str
    data_dir: Path
    database_path: Path
    download_dir: Path
    log_dir: Path
    log_level: str
    max_queue: int
    max_duration_minutes: int
    max_file_mb: int
    rate_limit_count: int
    rate_limit_window: int
    allow_direct_urls: bool


@lru_cache(maxsize=1)
def get_config() -> Config:
    load_dotenv()
    try:
        api_id = int(_required("API_ID"))
    except ValueError:
        raise ConfigError("API_ID must be a number.") from None

    data_dir = Path(os.getenv("DATA_DIR", "data").strip() or "data")
    database_path = Path(os.getenv("DATABASE_PATH", "").strip() or data_dir / "music.db")
    download_dir = Path(os.getenv("DOWNLOAD_DIR", "").strip() or data_dir / "downloads")
    log_dir = Path(os.getenv("LOG_DIR", "logs").strip() or "logs")

    return Config(
        api_id=api_id,
        api_hash=_required("API_HASH"),
        bot_token=_required("BOT_TOKEN"),
        session_string=_required("SESSION_STRING"),
        owner_ids=_int_list("OWNER_IDS"),
        jamendo_client_id=os.getenv("JAMENDO_CLIENT_ID", "").strip(),
        data_dir=data_dir.resolve(),
        database_path=database_path.resolve(),
        download_dir=download_dir.resolve(),
        log_dir=log_dir.resolve(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        max_queue=_int("MAX_QUEUE", 50, 1, 500),
        max_duration_minutes=_int("MAX_DURATION_MINUTES", 180, 1, 1440),
        max_file_mb=_int("MAX_FILE_MB", 100, 1, 2000),
        rate_limit_count=_int("RATE_LIMIT_COUNT", 6, 1, 100),
        rate_limit_window=_int("RATE_LIMIT_WINDOW", 10, 1, 600),
        allow_direct_urls=_bool("ALLOW_DIRECT_URLS", True),
    )
