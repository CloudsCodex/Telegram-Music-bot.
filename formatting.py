# Developer by : Mr_Manas_Op
"""Text formatting and parsing helpers."""

from __future__ import annotations

import html
import re


def esc(value: object) -> str:
    """Escape text for Telegram HTML parse mode."""
    return html.escape(str(value), quote=False)


def fmt_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


_TIMESTAMP = re.compile(r"^\d{1,5}(:\d{1,2}){0,2}$")


def parse_timestamp(text: str) -> int | None:
    """Parse ``90``, ``1:30`` or ``1:02:03`` into seconds."""
    text = text.strip()
    if not _TIMESTAMP.match(text):
        return None
    parts = [int(p) for p in text.split(":")]
    if len(parts) > 1 and any(p >= 60 for p in parts[1:]):
        return None
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


def progress_bar(position: float, duration: float, width: int = 14) -> str:
    if duration <= 0:
        return ""
    ratio = min(max(position / duration, 0.0), 1.0)
    filled = int(round(ratio * width))
    return "━" * filled + "●" + "─" * (width - filled)


def fmt_uptime(seconds: float) -> str:
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def split_text(text: str, limit: int = 3900) -> list[str]:
    """Split long text on line boundaries to fit Telegram's message limit."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current.strip():
        chunks.append(current)
    return chunks


def display_name(user) -> str:
    name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    return (name or "User")[:64]


def command_args(message) -> str:
    """Return everything after the command (works with ``/cmd@botname``)."""
    text = message.text or message.caption or ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""
