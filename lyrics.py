# Developer by : Mr_Manas_Op
"""Lyrics lookup through the public lyrics.ovh API."""

from __future__ import annotations

import logging
from urllib.parse import quote

import aiohttp

from services.errors import BotError

log = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def fetch(artist: str, title: str) -> str | None:
    """Return lyrics text, or None if the provider has no match."""
    url = f"https://api.lyrics.ovh/v1/{quote(artist, safe='')}/{quote(title, safe='')}"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(url) as response:
                if response.status == 404:
                    return None
                if response.status != 200:
                    log.warning("Lyrics provider returned HTTP %s", response.status)
                    raise BotError("The lyrics service is unavailable right now. Please try again later.")
                data = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError):
        log.warning("Lyrics request failed", exc_info=True)
        raise BotError("The lyrics service is unavailable right now. Please try again later.") from None

    text = (data.get("lyrics") or "").replace("\r\n", "\n").strip()
    return text or None
