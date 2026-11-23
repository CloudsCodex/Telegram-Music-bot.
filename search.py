# Developer by : Mr_Manas_Op
"""/search and /lyrics."""

from __future__ import annotations

import secrets
import time

from pyrogram import filters

from helpers.cards import duration_label
from helpers.decorators import guarded, guarded_callback
from helpers.formatting import command_args, esc, split_text
from keyboards.search import search_markup
from services import jamendo, lyrics, sources
from services.clients import bot
from services.errors import BotError
from services.models import Track
from services.player import players

_CACHE_TTL = 600
_MAX_LYRIC_MESSAGES = 3
# token -> (chat_id, results, expires_at)
_results: dict[str, tuple[int, list[Track], float]] = {}


def _purge() -> None:
    now = time.monotonic()
    for token in [t for t, (_, _, exp) in _results.items() if exp < now]:
        _results.pop(token, None)


@bot.on_message(filters.command("search"))
@guarded()
async def search_cmd(client, message):
    query = command_args(message)
    if not query:
        raise BotError("Usage: /search <song or artist>")

    tracks = await jamendo.search(query, limit=5)
    if not tracks:
        raise BotError(f"No results found for “{query[:60]}”.")

    _purge()
    token = secrets.token_hex(4)
    _results[token] = (message.chat.id, tracks, time.monotonic() + _CACHE_TTL)

    lines = [f"🔎 <b>Results for</b> “{esc(query[:60])}”", ""]
    for index, track in enumerate(tracks, start=1):
        lines.append(f"{index}. <b>{esc(track.title)}</b> — {esc(track.artist)} [{duration_label(track)}]")
    lines.append("\nTap a number to add it to the queue.")
    await message.reply_text("\n".join(lines), reply_markup=search_markup(token, len(tracks)))


@bot.on_callback_query(filters.regex(r"^sr\|"))
@guarded_callback()
async def search_callback(client, callback):
    try:
        _, token, choice = callback.data.split("|")
    except ValueError:
        await callback.answer()
        return

    entry = _results.get(token)
    if entry is None or entry[2] < time.monotonic() or entry[0] != callback.message.chat.id:
        await callback.answer("These results have expired. Please search again.", show_alert=True)
        return

    if choice == "x":
        _results.pop(token, None)
        await callback.message.delete()
        await callback.answer()
        return

    index = int(choice) if choice.isdigit() else -1
    tracks = entry[1]
    if not 0 <= index < len(tracks):
        await callback.answer()
        return

    chat_id = callback.message.chat.id
    await players.check_room(chat_id)
    user = callback.from_user
    name = " ".join(p for p in (user.first_name, user.last_name) if p)[:64] or "User"
    track = sources.for_requester(tracks[index], user.id, name)
    position, started = await players.add(chat_id, track)

    if started:
        await callback.answer("▶️ Playing now")
        await players.announce(chat_id)
    else:
        await callback.answer(f"✅ Added to the queue (#{position})")
        await bot.send_message(
            chat_id, f"✅ <b>Added to queue</b> — position {position}\n<b>{esc(track.display_name)}</b>"
        )


@bot.on_message(filters.command("lyrics"))
@guarded()
async def lyrics_cmd(client, message):
    arg = command_args(message)
    if arg:
        artist, sep, title = arg.partition(" - ")
        if not sep or not artist.strip() or not title.strip():
            raise BotError("Usage: /lyrics <artist> - <title>\nOr use /lyrics while a track is playing.")
        artist, title = artist.strip(), title.strip()
    else:
        player = players.peek(message.chat.id)
        if not player or player.current is None or not player.current.artist:
            raise BotError("Usage: /lyrics <artist> - <title>\nOr use /lyrics while a track is playing.")
        artist, title = player.current.artist, player.current.title

    status = await message.reply_text("🔎 Looking for lyrics…")
    text = await lyrics.fetch(artist, title)
    if not text:
        await status.edit_text(f"No lyrics found for <b>{esc(artist)} – {esc(title)}</b>.")
        return

    header = f"📝 <b>{esc(artist)} – {esc(title)}</b>\n\n"
    chunks = split_text(esc(text))
    await status.edit_text(header + chunks[0])
    for chunk in chunks[1:_MAX_LYRIC_MESSAGES]:
        await message.reply_text(chunk, quote=False)
    if len(chunks) > _MAX_LYRIC_MESSAGES:
        await message.reply_text("… (lyrics truncated)", quote=False)
