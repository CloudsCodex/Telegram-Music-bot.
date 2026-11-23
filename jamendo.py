# Developer by : Mr_Manas_Op
"""Music search using the Jamendo API (Creative Commons licensed catalogue)."""

from __future__ import annotations

import logging

import aiohttp

from config import get_config
from services.errors import BotError
from services.models import SOURCE_JAMENDO, Track

log = logging.getLogger(__name__)

_API_URL = "https://api.jamendo.com/v3.0/tracks/"
_TIMEOUT = aiohttp.ClientTimeout(total=15)


def is_configured() -> bool:
    return bool(get_config().jamendo_client_id)


async def search(query: str, limit: int = 5) -> list[Track]:
    client_id = get_config().jamendo_client_id
    if not client_id:
        raise BotError(
            "Music search is not configured on this bot. "
            "You can still play a direct audio link or reply to an audio file with /play."
        )

    params = {
        "client_id": client_id,
        "format": "json",
        "limit": str(limit),
        "search": query[:100],
        "audioformat": "mp32",
        "imagesize": "200",
        "order": "relevance",
    }
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(_API_URL, params=params) as response:
                if response.status != 200:
                    log.warning("Jamendo returned HTTP %s", response.status)
                    raise BotError("The music catalogue is unavailable right now. Please try again later.")
                data = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError):
        log.warning("Jamendo request failed", exc_info=True)
        raise BotError("The music catalogue is unavailable right now. Please try again later.") from None

    tracks: list[Track] = []
    for item in data.get("results", []):
        stream_url = item.get("audio")
        if not stream_url:
            continue
        tracks.append(
            Track(
                title=str(item.get("name") or "Unknown title")[:200],
                artist=str(item.get("artist_name") or "")[:200],
                duration=int(item.get("duration") or 0),
                source=SOURCE_JAMENDO,
                location=stream_url,
                thumb=item.get("image") or None,
                license_url=item.get("license_ccurl") or None,
            )
        )
    return tracks
