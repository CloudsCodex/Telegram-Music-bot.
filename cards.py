# Developer by : Mr_Manas_Op
"""Builders for the message texts shown to users."""

from __future__ import annotations

from helpers.formatting import esc, fmt_time, progress_bar
from services.models import SOURCE_JAMENDO, SOURCE_TELEGRAM, SOURCE_URL, Track

LOOP_LABELS = {"off": "Off", "track": "Track", "queue": "Queue"}
_SOURCE_LABELS = {
    SOURCE_JAMENDO: "Jamendo (Creative Commons)",
    SOURCE_URL: "Direct link",
    SOURCE_TELEGRAM: "Telegram file",
}


def loop_label(mode: str) -> str:
    return LOOP_LABELS.get(mode, "Off")


def duration_label(track: Track) -> str:
    return fmt_time(track.duration) if track.duration else "Unknown"


def now_playing_text(
    track: Track,
    *,
    header: str,
    loop: str,
    volume: int,
    position: float | None = None,
) -> str:
    lines = [header, "", f"<b>{esc(track.title)}</b>"]
    if track.artist:
        lines.append(esc(track.artist))
    if position is not None and track.duration:
        lines.append(progress_bar(position, track.duration))
        lines.append(f"{fmt_time(position)} / {fmt_time(track.duration)}")
    else:
        lines.append(f"⏱ {duration_label(track)}")
    if track.is_video:
        lines.append("🎬 Video")
    lines.append(f"👤 {esc(track.requested_by_name or 'Unknown')}")
    lines.append(f"🔁 Loop: {loop_label(loop)}  •  🔊 Volume: {volume}%")
    return "\n".join(lines)


def track_info_text(track: Track, position: float, loop: str, volume: int) -> str:
    lines = [
        "ℹ️ <b>Track information</b>",
        "",
        f"<b>Title:</b> {esc(track.title)}",
        f"<b>Artist:</b> {esc(track.artist) if track.artist else 'Unknown'}",
        f"<b>Duration:</b> {duration_label(track)}",
        f"<b>Position:</b> {fmt_time(position)}",
        f"<b>Source:</b> {_SOURCE_LABELS.get(track.source, track.source)}",
        f"<b>Type:</b> {'Video' if track.is_video else 'Audio'}",
        f"<b>Requested by:</b> {esc(track.requested_by_name or 'Unknown')}",
        f"<b>Loop:</b> {loop_label(loop)}   <b>Volume:</b> {volume}%",
    ]
    if track.license_url:
        lines.append(f"<b>License:</b> {esc(track.license_url)}")
    return "\n".join(lines)


def queue_text(current: Track | None, queue: list[Track], loop: str) -> str:
    lines = ["📜 <b>Queue</b>", ""]
    if current:
        lines.append(f"▶️ <b>{esc(current.display_name)}</b> [{duration_label(current)}]")
        lines.append(f"    👤 {esc(current.requested_by_name or 'Unknown')}")
    else:
        lines.append("Nothing is playing right now.")

    if queue:
        lines.append("")
        lines.append("<b>Up next</b>")
        for index, track in enumerate(queue[:10], start=1):
            lines.append(f"{index}. {esc(track.display_name)} [{duration_label(track)}]")
        if len(queue) > 10:
            lines.append(f"…and {len(queue) - 10} more")
        total = sum(t.duration for t in queue)
        suffix = f" • {fmt_time(total)}" if total else ""
        lines.append("")
        lines.append(f"{len(queue)} track(s) waiting{suffix}")
    lines.append(f"🔁 Loop: {loop_label(loop)}")
    return "\n".join(lines)


HELP_TEXT = (
    "🎵 <b>Music commands</b>\n\n"
    "<b>Playback</b>\n"
    "/play &lt;song or link&gt; — Play music (or reply to an audio file)\n"
    "/vplay &lt;link&gt; — Play a video (or reply to a video file)\n"
    "/pause — Pause playback\n"
    "/resume — Resume playback\n"
    "/skip — Skip the current track\n"
    "/stop — Stop playback (queue is kept)\n"
    "/end — Stop playback and clear the queue\n"
    "/replay — Replay the current track\n"
    "/seek &lt;time&gt; — Jump to a position, e.g. 1:30\n"
    "/volume &lt;1-200&gt; — Adjust the volume\n"
    "/mute · /unmute — Mute or unmute the stream\n\n"
    "<b>Queue</b>\n"
    "/queue — Show the queue\n"
    "/shuffle — Shuffle upcoming tracks\n"
    "/loop [off|track|queue] — Set repeat mode\n"
    "/remove &lt;n&gt; — Remove a queued track\n"
    "/skipto &lt;n&gt; — Jump to a queued track\n"
    "/clear — Clear upcoming tracks\n"
    "/song — Details of the current track\n"
    "/current — Show what is playing\n\n"
    "<b>Search &amp; playlists</b>\n"
    "/search &lt;query&gt; — Search for music\n"
    "/lyrics [artist - title] — Find lyrics\n"
    "/playlist — Manage your playlists\n"
    "/save [name] — Save the current track to a playlist\n"
    "/myplaylist — Show your saved playlists\n\n"
    "<b>Settings</b>\n"
    "/settings — Playback settings\n"
    "/admincache — Refresh the admin list\n"
    "/reload — Reload settings\n\n"
    "<b>General</b>\n"
    "/start · /help · /ping · /about"
)
