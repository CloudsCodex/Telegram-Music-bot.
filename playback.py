# Developer by : Mr_Manas_Op
"""Playback commands and the inline player controls."""

from __future__ import annotations

import logging

from pyrogram import filters

from helpers.cards import loop_label
from helpers.decorators import guarded, guarded_callback
from helpers.formatting import command_args, esc, fmt_time, parse_timestamp
from helpers.permissions import requester
from services import sources
from services.clients import bot
from services.errors import BotError
from services.player import players

log = logging.getLogger(__name__)


async def _play(message, *, video: bool) -> None:
    chat_id = message.chat.id
    await players.check_room(chat_id)
    user_id, name = requester(message)
    status = await message.reply_text("🔎 Processing your request…")
    try:
        track = await sources.build_track(message, command_args(message), video, user_id, name)
        position, started = await players.add(chat_id, track)
    except BotError as exc:
        await status.edit_text(f"⚠️ {esc(exc.message)}")
        return
    except Exception:
        try:
            await status.delete()
        except Exception:  # noqa: BLE001
            pass
        raise

    if started:
        text, markup = players.build_card(chat_id, "🎵 <b>Now playing</b>")
        await status.edit_text(text, reply_markup=markup)
        await players.adopt(chat_id, status)
    else:
        await status.edit_text(
            f"✅ <b>Added to queue</b> — position {position}\n\n"
            f"<b>{esc(track.display_name)}</b>\n"
            f"⏱ {fmt_time(track.duration) if track.duration else 'Unknown'}"
        )


@bot.on_message(filters.command("play"))
@guarded()
async def play_cmd(client, message):
    await _play(message, video=False)


@bot.on_message(filters.command("vplay"))
@guarded()
async def vplay_cmd(client, message):
    await _play(message, video=True)


@bot.on_message(filters.command("pause"))
@guarded(control=True)
async def pause_cmd(client, message):
    await players.pause(message.chat.id)
    await message.reply_text("⏸ Playback paused.")


@bot.on_message(filters.command("resume"))
@guarded(control=True)
async def resume_cmd(client, message):
    started = await players.resume(message.chat.id)
    if started:
        await players.announce(message.chat.id, header="▶️ <b>Now playing</b>", reply_to=message)
    else:
        await message.reply_text("▶️ Playback resumed.")


@bot.on_message(filters.command("skip"))
@guarded(control=True, allow_requester=True)
async def skip_cmd(client, message):
    track = await players.skip(message.chat.id)
    if track:
        await players.announce(message.chat.id, header="⏭ <b>Skipped — now playing</b>", reply_to=message)
    else:
        await message.reply_text("⏭ Skipped. The queue is now empty.")


@bot.on_message(filters.command("stop"))
@guarded(control=True)
async def stop_cmd(client, message):
    remaining = await players.stop(message.chat.id)
    note = (
        f" {remaining} track(s) are still queued — use /resume to continue with the next one."
        if remaining
        else ""
    )
    await message.reply_text(f"⏹ Playback stopped.{note}")


@bot.on_message(filters.command("end"))
@guarded(control=True)
async def end_cmd(client, message):
    await players.end(message.chat.id)
    await message.reply_text("⏹ Playback ended and the queue was cleared.")


@bot.on_message(filters.command("replay"))
@guarded(control=True)
async def replay_cmd(client, message):
    await players.replay(message.chat.id)
    await message.reply_text("🔂 Replaying the current track.")


@bot.on_message(filters.command("seek"))
@guarded(control=True)
async def seek_cmd(client, message):
    seconds = parse_timestamp(command_args(message))
    if seconds is None:
        raise BotError("Usage: /seek <time> — for example /seek 90 or /seek 1:30")
    await players.seek(message.chat.id, seconds)
    await message.reply_text(f"⏩ Jumped to {fmt_time(seconds)}.")


@bot.on_message(filters.command("volume"))
@guarded(control=True)
async def volume_cmd(client, message):
    chat_id = message.chat.id
    arg = command_args(message).rstrip("%").strip()
    if not arg:
        player = await players.get(chat_id)
        await message.reply_text(f"🔊 Current volume: {player.volume}%\nUsage: /volume <1-200>")
        return
    if not arg.isdigit() or not 1 <= int(arg) <= 200:
        raise BotError("Volume must be a number between 1 and 200.")
    live = await players.set_volume(chat_id, int(arg))
    if live:
        await message.reply_text(f"🔊 Volume set to {int(arg)}%.")
    else:
        await message.reply_text(f"🔊 Default volume set to {int(arg)}%. It will apply to the next track.")


@bot.on_message(filters.command("mute"))
@guarded(control=True)
async def mute_cmd(client, message):
    await players.mute(message.chat.id)
    await message.reply_text("🔇 Playback muted.")


@bot.on_message(filters.command("unmute"))
@guarded(control=True)
async def unmute_cmd(client, message):
    await players.unmute(message.chat.id)
    await message.reply_text("🔊 Playback unmuted.")


# ------------------------------------------------------------------ buttons
@bot.on_callback_query(filters.regex(r"^mc\|"))
@guarded_callback(control=True, allow_requester=True)
async def controls_callback(client, callback):
    try:
        _, action, raw_chat = callback.data.split("|")
        chat_id = int(raw_chat)
    except ValueError:
        await callback.answer()
        return
    if chat_id != callback.message.chat.id:
        await callback.answer()
        return

    if action == "pp":
        paused = await players.toggle_pause(chat_id)
        await callback.answer("⏸ Paused" if paused else "▶️ Resumed")
    elif action == "skip":
        track = await players.skip(chat_id)
        if track:
            await callback.answer("⏭ Skipped")
            await players.announce(chat_id, header="⏭ <b>Skipped — now playing</b>")
        else:
            await callback.answer("⏭ Skipped — the queue is empty", show_alert=True)
    elif action == "end":
        await players.end(chat_id)
        await callback.answer("⏹ Playback ended")
        await bot.send_message(chat_id, "⏹ Playback ended and the queue was cleared.")
    elif action == "loop":
        mode = await players.cycle_loop(chat_id)
        await callback.answer(f"🔁 Loop: {loop_label(mode)}")
    elif action == "shuffle":
        count = await players.shuffle(chat_id)
        await callback.answer(f"🔀 Shuffled {count} track(s)")
    elif action == "queue":
        from helpers.cards import queue_text

        player = await players.get(chat_id)
        current, queue = players.snapshot(chat_id)
        await bot.send_message(chat_id, queue_text(current, queue, player.loop))
        await callback.answer()
    else:
        await callback.answer()
