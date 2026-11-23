# Developer by : Mr_Manas_Op
"""Turns a /play request into a Track.

Supported sources (all legitimate and non-circumventing):
  * Jamendo catalogue search (Creative Commons licensed music).
  * Direct http(s) links to audio/video files.
  * Audio/video files that a user uploads to Telegram and replies to.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from config import get_config
from services import jamendo, media
from services.errors import BotError
from services.models import SOURCE_TELEGRAM, SOURCE_URL, Track
from utils.security import is_public_url

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_MEDIA_ATTRS = ("audio", "voice", "video", "video_note", "animation", "document")
_VIDEO_ATTRS = {"video", "video_note", "animation"}

PLAY_USAGE = (
    "Usage: /play <song name or direct link>\n"
    "You can also reply to an audio file with /play."
)
VPLAY_USAGE = (
    "Usage: /vplay <direct video link>\n"
    "You can also reply to a video file with /vplay."
)


def for_requester(track: Track, user_id: int, name: str) -> Track:
    return dataclasses.replace(track, requested_by_id=user_id, requested_by_name=name, local_path=None)


def _from_telegram(reply, video: bool, user_id: int, name: str) -> Track | None:
    for attr in _MEDIA_ATTRS:
        item = getattr(reply, attr, None)
        if not item:
            continue
        mime = getattr(item, "mime_type", None) or ""
        if attr == "document" and not mime.startswith(("audio/", "video/")):
            continue

        cfg = get_config()
        size = getattr(item, "file_size", 0) or 0
        if size > cfg.max_file_mb * 1024 * 1024:
            raise BotError(f"That file is too large. The limit is {cfg.max_file_mb} MB.")

        file_name = getattr(item, "file_name", None) or ""
        title = getattr(item, "title", None) or PurePosixPath(file_name).stem or "Telegram file"
        track = Track(
            title=str(title)[:200],
            artist=str(getattr(item, "performer", None) or "")[:200],
            duration=int(getattr(item, "duration", 0) or 0),
            source=SOURCE_TELEGRAM,
            location=item.file_id,
            is_video=video and (attr in _VIDEO_ATTRS or mime.startswith("video/")),
            requested_by_id=user_id,
            requested_by_name=name,
        )
        media.ensure_duration_ok(track)
        return track
    return None


async def _from_url(url: str, video: bool, user_id: int, name: str) -> Track:
    if not get_config().allow_direct_urls:
        raise BotError("Playing links is disabled by the bot administrator.")
    if not await is_public_url(url):
        raise BotError("That link can't be used.")

    info = await media.probe(url, remote=True)
    parsed = urlparse(url)
    fallback = PurePosixPath(unquote(parsed.path)).stem or parsed.hostname or "Audio stream"
    track = Track(
        title=(info.title or fallback)[:200],
        artist=info.artist[:200],
        duration=int(info.duration),
        source=SOURCE_URL,
        location=url,
        is_video=video and info.has_video,
        requested_by_id=user_id,
        requested_by_name=name,
    )
    media.ensure_duration_ok(track)
    return track


async def build_track(message, query: str, video: bool, user_id: int, name: str) -> Track:
    reply = message.reply_to_message
    if reply:
        track = _from_telegram(reply, video, user_id, name)
        if track:
            # Download now so problems are reported immediately.
            await media.resolve(track)
            return track

    if not query:
        raise BotError(VPLAY_USAGE if video else PLAY_USAGE)

    if _URL_RE.match(query):
        return await _from_url(query, video, user_id, name)

    if video:
        raise BotError("/vplay works with direct video links or a replied video file.")

    results = await jamendo.search(query, limit=1)
    if not results:
        raise BotError(f"No results found for “{query[:60]}”.")
    return for_requester(results[0], user_id, name)
