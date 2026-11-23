# Developer by : Mr_Manas_Op
"""Plain data models shared across the project."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SOURCE_JAMENDO = "jamendo"
SOURCE_URL = "url"
SOURCE_TELEGRAM = "telegram"


@dataclass
class Track:
    title: str
    source: str
    location: str  # stream URL, direct URL, or Telegram file_id
    artist: str = ""
    duration: int = 0  # seconds, 0 = unknown
    is_video: bool = False
    thumb: str | None = None
    license_url: str | None = None
    requested_by_id: int = 0
    requested_by_name: str = ""
    local_path: str | None = None  # downloaded copy (Telegram files only)

    @property
    def display_name(self) -> str:
        return f"{self.artist} – {self.title}" if self.artist else self.title

    @classmethod
    def from_row(cls, row: dict[str, Any], requested_by_id: int, requested_by_name: str) -> "Track":
        return cls(
            title=row["title"],
            artist=row["artist"] or "",
            duration=int(row["duration"] or 0),
            source=row["source"],
            location=row["location"],
            is_video=bool(row["is_video"]),
            thumb=row["thumb"],
            license_url=row["license_url"],
            requested_by_id=requested_by_id,
            requested_by_name=requested_by_name,
        )
