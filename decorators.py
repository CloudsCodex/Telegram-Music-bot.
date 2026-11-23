# Developer by : Mr_Manas_Op
"""Decorators that add rate limiting, permission checks and error handling."""

from __future__ import annotations

import asyncio
import functools
import logging
import time

from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait, MessageNotModified

from config import get_config
from database import db
from helpers.errors import notify_owners
from helpers.formatting import esc
from helpers.permissions import has_control, is_admin, requester
from services.errors import BotError
from services.player import players
from utils.ratelimit import ALLOWED, FIRST_BLOCK, RateLimiter

log = logging.getLogger(__name__)

_cfg = get_config()
limiter = RateLimiter(_cfg.rate_limit_count, _cfg.rate_limit_window)

DENIED_TEXT = "🚫 Only group admins can use this command."
GENERIC_ERROR = "⚠️ Something went wrong while processing your request. Please try again later."

_GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)
_seen_chats: dict[int, float] = {}


async def _safe_reply(message, text: str) -> None:
    try:
        await message.reply_text(text)
    except Exception:  # noqa: BLE001
        log.debug("Could not send reply", exc_info=True)


async def _remember_chat(chat) -> None:
    now = time.monotonic()
    if now - _seen_chats.get(chat.id, 0.0) < 600:
        return
    _seen_chats[chat.id] = now
    try:
        await db.touch_chat(chat.id, chat.title or "")
    except Exception:  # noqa: BLE001
        log.debug("touch_chat failed", exc_info=True)


def guarded(*, group_only: bool = True, control: bool = False, allow_requester: bool = False):
    """Wrap a command handler.

    group_only       -- refuse use outside groups.
    control          -- require playback-control permission.
    allow_requester  -- also allow the person who requested the current track.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(client, message):
            user = message.from_user
            anonymous = (
                user is None
                and message.sender_chat is not None
                and message.sender_chat.id == message.chat.id
            )
            if user is None and not anonymous:
                return

            user_id, _ = requester(message)
            state = limiter.check(user_id or message.chat.id)
            if state != ALLOWED:
                if state == FIRST_BLOCK:
                    await _safe_reply(message, "⏳ Please slow down a little.")
                return

            is_group = message.chat.type in _GROUP_TYPES
            if group_only and not is_group:
                await _safe_reply(message, "ℹ️ This command can only be used in groups.")
                return
            if is_group:
                await _remember_chat(message.chat)

            if control:
                allowed = await has_control(message.chat.id, user_id, anonymous)
                if not allowed and allow_requester and user_id:
                    player = players.peek(message.chat.id)
                    allowed = bool(
                        player and player.current and player.current.requested_by_id == user_id
                    )
                if not allowed:
                    await _safe_reply(message, DENIED_TEXT)
                    return

            try:
                await func(client, message)
            except BotError as exc:
                await _safe_reply(message, f"⚠️ {esc(exc.message)}")
            except MessageNotModified:
                pass
            except FloodWait as exc:
                log.warning("FloodWait of %ss in %s", exc.value, func.__name__)
                await asyncio.sleep(min(exc.value, 30))
            except Exception as exc:  # noqa: BLE001
                log.exception("Unhandled error in %s", func.__name__)
                await notify_owners(func.__name__, exc)
                await _safe_reply(message, GENERIC_ERROR)

        return wrapper

    return decorator


def guarded_callback(*, control: bool = False, admin: bool = False, allow_requester: bool = False):
    """Wrap an inline-button handler with the same safety net."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(client, callback):
            user_id = callback.from_user.id
            if limiter.check(user_id) != ALLOWED:
                await callback.answer("⏳ Please slow down a little.")
                return
            if callback.message is None:
                await callback.answer()
                return
            chat_id = callback.message.chat.id

            if admin:
                allowed = await is_admin(chat_id, user_id)
            elif control:
                allowed = await has_control(chat_id, user_id)
                if not allowed and allow_requester:
                    player = players.peek(chat_id)
                    allowed = bool(
                        player and player.current and player.current.requested_by_id == user_id
                    )
            else:
                allowed = True
            if not allowed:
                await callback.answer(DENIED_TEXT.replace("🚫 ", ""), show_alert=True)
                return

            try:
                await func(client, callback)
            except BotError as exc:
                await callback.answer(exc.message[:190], show_alert=True)
            except MessageNotModified:
                await callback.answer()
            except FloodWait as exc:
                log.warning("FloodWait of %ss in %s", exc.value, func.__name__)
            except Exception as exc:  # noqa: BLE001
                log.exception("Unhandled error in %s", func.__name__)
                await notify_owners(func.__name__, exc)
                try:
                    await callback.answer("Something went wrong. Please try again.", show_alert=True)
                except Exception:  # noqa: BLE001
                    pass

        return wrapper

    return decorator
