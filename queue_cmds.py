# Developer by : Mr_Manas_Op
"""Queue management and track information commands."""

from __future__ import annotations

from pyrogram import filters

from helpers.cards import now_playing_text, queue_text, track_info_text
from helpers.decorators import guarded
from helpers.formatting import command_args, esc
from keyboards.player import player_markup
from services.clients import bot
from services.errors import BotError
from services.player import players

_LOOP_ALIASES = {
    "off": "off", "disable": "off", "none": "off", "0": "off",
    "track": "track", "song": "track", "one": "track", "1": "track",
    "queue": "queue", "all": "queue", "on": "queue", "enable": "queue",
}


def _parse_position(message, usage: str) -> int:
    arg = command_args(message)
    if not arg.isdigit() or int(arg) < 1:
        raise BotError(usage)
    return int(arg)


@bot.on_message(filters.command("queue"))
@guarded()
async def queue_cmd(client, message):
    chat_id = message.chat.id
    current, queue = players.snapshot(chat_id)
    if current is None and not queue:
        await message.reply_text("📭 The queue is empty. Use /play to add music.")
        return
    player = await players.get(chat_id)
    await message.reply_text(queue_text(current, queue, player.loop))


@bot.on_message(filters.command("shuffle"))
@guarded(control=True)
async def shuffle_cmd(client, message):
    count = await players.shuffle(message.chat.id)
    await message.reply_text(f"🔀 Shuffled {count} queued track(s).")


@bot.on_message(filters.command("loop"))
@guarded(control=True)
async def loop_cmd(client, message):
    chat_id = message.chat.id
    arg = command_args(message).lower()
    if arg:
        mode = _LOOP_ALIASES.get(arg)
        if mode is None:
            raise BotError("Usage: /loop [off|track|queue]")
        await players.set_loop(chat_id, mode)
    else:
        mode = await players.cycle_loop(chat_id)
    texts = {
        "off": "➡️ Repeat is off.",
        "track": "🔂 Repeating the current track.",
        "queue": "🔁 Repeating the whole queue.",
    }
    await message.reply_text(texts[mode])


@bot.on_message(filters.command("remove"))
@guarded(control=True)
async def remove_cmd(client, message):
    position = _parse_position(message, "Usage: /remove <position> — see /queue for positions.")
    track = await players.remove(message.chat.id, position)
    await message.reply_text(f"🗑 Removed <b>{esc(track.display_name)}</b> from the queue.")


@bot.on_message(filters.command("skipto"))
@guarded(control=True)
async def skipto_cmd(client, message):
    position = _parse_position(message, "Usage: /skipto <position> — see /queue for positions.")
    track = await players.skipto(message.chat.id, position)
    if track:
        await players.announce(message.chat.id, header="⏭ <b>Skipped ahead — now playing</b>", reply_to=message)
    else:
        await message.reply_text("⏭ None of the remaining tracks could be played.")


@bot.on_message(filters.command("clear"))
@guarded(control=True)
async def clear_cmd(client, message):
    count = await players.clear(message.chat.id)
    await message.reply_text(f"🧹 Cleared {count} upcoming track(s). The current track keeps playing.")


@bot.on_message(filters.command("song"))
@guarded()
async def song_cmd(client, message):
    player = players.peek(message.chat.id)
    if not player or player.current is None:
        raise BotError("Nothing is playing right now.")
    await message.reply_text(
        track_info_text(player.current, player.position(), player.loop, player.volume),
        disable_web_page_preview=True,
    )


@bot.on_message(filters.command("current"))
@guarded()
async def current_cmd(client, message):
    player = players.peek(message.chat.id)
    if not player or player.current is None:
        raise BotError("Nothing is playing right now.")
    header = "⏸ <b>Paused</b>" if player.paused else "🎵 <b>Now playing</b>"
    text = now_playing_text(
        player.current,
        header=header,
        loop=player.loop,
        volume=player.volume,
        position=player.position(),
    )
    sent = await message.reply_text(text, reply_markup=player_markup(message.chat.id))
    await players.adopt(message.chat.id, sent)
