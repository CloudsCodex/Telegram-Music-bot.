# Developer by : Mr_Manas_Op
"""/settings, /admincache and /reload."""

from __future__ import annotations

import time

from pyrogram import filters

from database import db
from helpers.decorators import guarded, guarded_callback
from helpers.permissions import is_admin, refresh_admins
from keyboards.settings import settings_markup, settings_text
from services.clients import bot
from services.errors import BotError
from services.player import players

_ADMINCACHE_COOLDOWN = 30
_last_refresh: dict[int, float] = {}


@bot.on_message(filters.command("settings"))
@guarded()
async def settings_cmd(client, message):
    settings = await db.get_chat_settings(message.chat.id)
    await message.reply_text(settings_text(settings), reply_markup=settings_markup(settings))


@bot.on_callback_query(filters.regex(r"^st\|"))
@guarded_callback(admin=True)
async def settings_callback(client, callback):
    chat_id = callback.message.chat.id
    action = callback.data.split("|", 1)[1]

    if action == "close":
        await callback.message.delete()
        await callback.answer()
        return

    settings = await db.get_chat_settings(chat_id)
    if action == "ctl":
        new_mode = "everyone" if settings["controls_mode"] == "admins" else "admins"
        await db.set_chat_setting(chat_id, "controls_mode", new_mode)
    elif action in ("vup", "vdn"):
        step = 10 if action == "vup" else -10
        volume = max(1, min(200, int(settings["volume"]) + step))
        await players.set_volume(chat_id, volume)
    elif action == "loop":
        await players.cycle_loop(chat_id)
    elif action == "ann":
        await db.set_chat_setting(chat_id, "announce", 0 if settings["announce"] else 1)
    else:
        await callback.answer()
        return

    settings = await db.get_chat_settings(chat_id)
    await callback.message.edit_text(settings_text(settings), reply_markup=settings_markup(settings))
    await callback.answer("Saved")


@bot.on_message(filters.command("admincache"))
@guarded()
async def admincache_cmd(client, message):
    chat_id = message.chat.id
    now = time.monotonic()
    if now - _last_refresh.get(chat_id, 0.0) < _ADMINCACHE_COOLDOWN:
        raise BotError(f"The admin list was refreshed moments ago. Try again in {_ADMINCACHE_COOLDOWN} seconds.")
    _last_refresh[chat_id] = now
    admins = await refresh_admins(chat_id)
    await message.reply_text(f"✅ Admin list refreshed — {len(admins)} admin(s) recognised.")


@bot.on_message(filters.command("reload"))
@guarded()
async def reload_cmd(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    anonymous = message.from_user is None
    if not anonymous and not await is_admin(chat_id, user_id):
        raise BotError("Only group admins can reload the settings.")
    await players.reload_settings(chat_id)
    await refresh_admins(chat_id)
    await message.reply_text("🔄 Settings reloaded.")
