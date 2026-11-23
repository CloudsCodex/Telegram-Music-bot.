# Developer by : Mr_Manas_Op
"""/start, /help, /ping and /about."""

from __future__ import annotations

import time

from pyrogram import filters

from config import VERSION
from database import db
from helpers.cards import HELP_TEXT
from helpers.decorators import guarded, guarded_callback
from helpers.formatting import fmt_uptime
from keyboards.start import start_markup
from services import jamendo
from services.clients import bot
from services.player import players

STARTED_AT = time.monotonic()

START_TEXT = (
    "🎧 <b>Welcome!</b>\n\n"
    "I play music and video in your group's voice chat.\n\n"
    "1. Add me to your group\n"
    "2. Start a voice chat\n"
    "3. Send <code>/play song name</code>\n\n"
    "Tap <b>Commands</b> to see everything I can do."
)


@bot.on_message(filters.command("start"))
@guarded(group_only=False)
async def start_cmd(client, message):
    await message.reply_text(START_TEXT, reply_markup=start_markup(client.me.username))


@bot.on_message(filters.command("help"))
@guarded(group_only=False)
async def help_cmd(client, message):
    await message.reply_text(HELP_TEXT)


@bot.on_callback_query(filters.regex(r"^basic\|help$"))
@guarded_callback()
async def help_callback(client, callback):
    await callback.message.edit_text(HELP_TEXT)
    await callback.answer()


@bot.on_message(filters.command("ping"))
@guarded(group_only=False)
async def ping_cmd(client, message):
    started = time.perf_counter()
    reply = await message.reply_text("🏓 Pinging…")
    latency = (time.perf_counter() - started) * 1000
    await reply.edit_text(f"🏓 <b>Pong!</b> {latency:.0f} ms")


@bot.on_message(filters.command("about"))
@guarded(group_only=False)
async def about_cmd(client, message):
    stats = await db.get_stats()
    sources = ["direct audio/video links", "Telegram files"]
    if jamendo.is_configured():
        sources.insert(0, "Jamendo catalogue")
    text = (
        "🎵 <b>Music Bot</b>\n\n"
        f"<b>Version:</b> {VERSION}\n"
        f"<b>Uptime:</b> {fmt_uptime(time.monotonic() - STARTED_AT)}\n"
        f"<b>Active voice chats:</b> {players.active_count()}\n"
        f"<b>Tracks played:</b> {stats['tracks_played']}\n"
        f"<b>Groups served:</b> {stats['chats']}\n"
        f"<b>Sources:</b> {', '.join(sources)}\n\n"
        "Use /help to see all commands."
    )
    await message.reply_text(text)
