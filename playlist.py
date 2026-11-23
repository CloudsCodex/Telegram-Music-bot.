# Developer by : Mr_Manas_Op
"""/playlist, /save and /myplaylist."""

from __future__ import annotations

from pyrogram import filters
from pyrogram.enums import ChatType

from database import db
from database.db import LimitReached, PlaylistExists
from helpers.cards import duration_label
from helpers.decorators import guarded
from helpers.formatting import command_args, esc, split_text
from helpers.permissions import requester
from services.clients import bot
from services.errors import BotError
from services.models import Track
from services.player import players

DEFAULT_PLAYLIST = "Favorites"
_MAX_NAME = 40

USAGE = (
    "📂 <b>Playlists</b>\n\n"
    "/playlist create &lt;name&gt;\n"
    "/playlist view &lt;name&gt;\n"
    "/playlist play &lt;name&gt;\n"
    "/playlist remove &lt;name&gt; &lt;position&gt;\n"
    "/playlist delete &lt;name&gt;\n"
    "/save [name] — save the current track\n"
    "/myplaylist — show all your playlists"
)


def _user(message) -> tuple[int, str]:
    user_id, name = requester(message)
    if not user_id:
        raise BotError("Please send this command from your own account, not as an anonymous admin.")
    return user_id, name


def _valid_name(name: str) -> str:
    name = " ".join(name.split())
    if not name or len(name) > _MAX_NAME:
        raise BotError(f"Playlist names must be 1–{_MAX_NAME} characters.")
    return name


async def _find(user_id: int, name: str) -> dict:
    playlist = await db.get_playlist(user_id, _valid_name(name))
    if playlist is None:
        raise BotError(f"You don't have a playlist called “{name[:40]}”.")
    return playlist


def _track_lines(rows: list[dict], limit: int | None = None) -> list[str]:
    lines = []
    for index, row in enumerate(rows[:limit] if limit else rows, start=1):
        track = Track.from_row(row, 0, "")
        lines.append(f"{index}. {esc(track.display_name)} [{duration_label(track)}]")
    return lines


@bot.on_message(filters.command("playlist"))
@guarded(group_only=False)
async def playlist_cmd(client, message):
    user_id, name = _user(message)
    sub, _, rest = command_args(message).partition(" ")
    sub, rest = sub.lower(), rest.strip()

    if not sub:
        playlists = await db.list_playlists(user_id)
        if playlists:
            listing = "\n".join(f"• <b>{esc(p['name'])}</b> — {p['tracks']} track(s)" for p in playlists)
            await message.reply_text(f"{listing}\n\n{USAGE}")
        else:
            await message.reply_text(f"You don't have any playlists yet.\n\n{USAGE}")
        return

    if sub == "create":
        try:
            await db.create_playlist(user_id, _valid_name(rest))
        except PlaylistExists:
            raise BotError("You already have a playlist with that name.") from None
        except LimitReached as exc:
            raise BotError(str(exc)) from None
        await message.reply_text(f"✅ Playlist <b>{esc(_valid_name(rest))}</b> created.")

    elif sub == "delete":
        if not await db.delete_playlist(user_id, _valid_name(rest)):
            raise BotError("I couldn't find that playlist.")
        await message.reply_text("🗑 Playlist deleted.")

    elif sub == "view":
        playlist = await _find(user_id, rest)
        rows = await db.get_tracks(playlist["id"])
        if not rows:
            await message.reply_text(f"📂 <b>{esc(playlist['name'])}</b> is empty. Use /save to add tracks.")
            return
        text = f"📂 <b>{esc(playlist['name'])}</b> — {len(rows)} track(s)\n\n" + "\n".join(_track_lines(rows))
        for chunk in split_text(text)[:2]:
            await message.reply_text(chunk, quote=False)

    elif sub == "remove":
        name_part, _, position = rest.rpartition(" ")
        if not name_part or not position.isdigit():
            raise BotError("Usage: /playlist remove <name> <position>")
        playlist = await _find(user_id, name_part)
        removed = await db.remove_track(playlist["id"], int(position))
        if removed is None:
            raise BotError("There is no track at that position.")
        await message.reply_text(f"🗑 Removed <b>{esc(removed['title'])}</b> from {esc(playlist['name'])}.")

    elif sub == "play":
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            raise BotError("Use /playlist play inside a group with an active voice chat.")
        playlist = await _find(user_id, rest)
        rows = await db.get_tracks(playlist["id"])
        if not rows:
            raise BotError("That playlist is empty.")

        added = 0
        started_any = False
        for row in rows:
            track = Track.from_row(row, user_id, name)
            try:
                _, started = await players.add(message.chat.id, track)
            except BotError:
                if added == 0:
                    raise
                break
            added += 1
            started_any = started_any or started

        header = f"📂 <b>{esc(playlist['name'])}</b> — {added} track(s) added"
        if started_any:
            await players.announce(
                message.chat.id, header=f"{header}\n\n🎵 <b>Now playing</b>", reply_to=message
            )
        else:
            await message.reply_text(f"✅ {header}.")

    else:
        await message.reply_text(USAGE)


@bot.on_message(filters.command("save"))
@guarded()
async def save_cmd(client, message):
    user_id, _ = _user(message)
    player = players.peek(message.chat.id)
    if not player or player.current is None:
        raise BotError("Nothing is playing right now.")

    name = _valid_name(command_args(message) or DEFAULT_PLAYLIST)
    playlist = await db.get_playlist(user_id, name)
    try:
        if playlist is None:
            playlist = await db.create_playlist(user_id, name)
        added = await db.add_track(playlist["id"], player.current)
    except LimitReached as exc:
        raise BotError(str(exc)) from None

    title = esc(player.current.display_name)
    if added:
        await message.reply_text(f"💾 Saved <b>{title}</b> to <b>{esc(playlist['name'])}</b>.")
    else:
        await message.reply_text(f"That track is already in <b>{esc(playlist['name'])}</b>.")


@bot.on_message(filters.command("myplaylist"))
@guarded(group_only=False)
async def myplaylist_cmd(client, message):
    user_id, _ = _user(message)
    playlists = await db.list_playlists(user_id)
    if not playlists:
        await message.reply_text("You don't have any playlists yet. Use /save while music is playing.")
        return

    blocks = ["🎼 <b>Your playlists</b>"]
    for playlist in playlists:
        rows = await db.get_tracks(playlist["id"])
        lines = [f"\n📂 <b>{esc(playlist['name'])}</b> — {playlist['tracks']} track(s)"]
        lines += _track_lines(rows, limit=5)
        if len(rows) > 5:
            lines.append(f"…and {len(rows) - 5} more")
        blocks.append("\n".join(lines))

    for chunk in split_text("\n".join(blocks))[:2]:
        await message.reply_text(chunk, quote=False)
