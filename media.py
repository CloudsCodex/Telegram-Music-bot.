# Developer by : Mr_Manas_Op
"""Media probing, Telegram file downloads and temporary-file cleanup."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from config import get_config
from services.clients import bot
from services.errors import BotError
from services.models import SOURCE_TELEGRAM, Track

log = logging.getLogger(__name__)

_PROBE_TIMEOUT = 25
# Container formats that are playlists/manifests rather than plain media files.
_BLOCKED_FORMATS = {"hls", "applehttp", "dash", "concat", "ffconcat", "sdp", "rtsp", "rtp", "image2"}
_download_slots = asyncio.Semaphore(2)


@dataclass
class ProbeResult:
    duration: float
    has_audio: bool
    has_video: bool
    title: str
    artist: str


async def probe(target: str, *, remote: bool) -> ProbeResult:
    """Inspect a media file or URL with ffprobe and validate that it is playable."""
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams"]
    if remote:
        cmd += ["-protocol_whitelist", "http,https,tcp,tls,crypto"]
    cmd += ["-i", target]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        log.error("ffprobe is not installed")
        raise BotError("Media tools are not installed on the server. Please contact the bot owner.") from None

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_PROBE_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise BotError("Timed out while reading the media.") from None

    unreadable = BotError(
        "I couldn't read that media. Only direct links to audio or video files are supported."
    )
    if proc.returncode != 0:
        raise unreadable
    try:
        data = json.loads(stdout or b"{}")
    except json.JSONDecodeError:
        raise unreadable from None

    fmt = data.get("format") or {}
    if _BLOCKED_FORMATS & set(str(fmt.get("format_name", "")).split(",")):
        raise unreadable

    has_audio = has_video = False
    for stream in data.get("streams", []):
        kind = stream.get("codec_type")
        if kind == "audio":
            has_audio = True
        elif kind == "video" and not (stream.get("disposition") or {}).get("attached_pic"):
            has_video = True
    if not (has_audio or has_video):
        raise unreadable

    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    tags = {str(k).lower(): str(v) for k, v in (fmt.get("tags") or {}).items()}
    return ProbeResult(duration, has_audio, has_video, tags.get("title", ""), tags.get("artist", ""))


def ensure_duration_ok(track: Track) -> None:
    limit = get_config().max_duration_minutes * 60
    if track.duration and track.duration > limit:
        raise BotError(f"That track is too long. The limit is {get_config().max_duration_minutes} minutes.")


async def resolve(track: Track) -> str:
    """Return what py-tgcalls should open: a URL, or a local file for Telegram uploads."""
    if track.source != SOURCE_TELEGRAM:
        return track.location

    if track.local_path and Path(track.local_path).is_file():
        return track.local_path

    cfg = get_config()
    cfg.download_dir.mkdir(parents=True, exist_ok=True)
    target = cfg.download_dir / f"{uuid.uuid4().hex}.media"

    async with _download_slots:
        try:
            downloaded = await bot.download_media(track.location, file_name=str(target))
        except Exception:  # noqa: BLE001
            log.warning("Telegram download failed", exc_info=True)
            raise BotError("I couldn't download that file from Telegram.") from None
    if not downloaded:
        raise BotError("I couldn't download that file from Telegram.")

    path = str(downloaded)
    try:
        info = await probe(path, remote=False)
        if not track.duration:
            track.duration = int(info.duration)
        if track.is_video and not info.has_video:
            track.is_video = False
        ensure_duration_ok(track)
    except BotError:
        _remove(path)
        raise
    track.local_path = path
    return path


def _remove(path: str | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        log.debug("Could not remove %s", path, exc_info=True)


def release(track: Track) -> None:
    """Delete the downloaded copy of a track, if any."""
    if track.local_path:
        _remove(track.local_path)
        track.local_path = None


def purge_downloads() -> None:
    """Remove leftovers from a previous run (the queue is memory-only)."""
    directory = get_config().download_dir
    if not directory.is_dir():
        return
    for path in directory.iterdir():
        if path.is_file():
            _remove(str(path))


def cleanup_old_files(in_use: set[str], max_age_seconds: int) -> int:
    """Delete stale downloads that are not referenced by any queue."""
    directory = get_config().download_dir
    if not directory.is_dir():
        return 0
    removed = 0
    now = time.time()
    for path in directory.iterdir():
        try:
            if path.is_file() and str(path) not in in_use and now - path.stat().st_mtime > max_age_seconds:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
