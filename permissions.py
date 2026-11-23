# Developer by : Mr_Manas_Op
"""Admin detection and music-control permission checks."""

from __future__ import annotations

import logging
import time

from pyrogram.enums import ChatMembersFilter

from config import get_config
from database import db
from helpers.formatting import display_name
from services.clients import bot

log = logging.getLogger(__name__)

_ADMIN_TTL = 600  # seconds
_admin_cache: dict[int, tuple[float, set[int]]] = {}


def requester(message) -> tuple[int, str]:
    """Return ``(user_id, display_name)``; ``(0, ...)`` for anonymous admins."""
    if message.from_user:
        return message.from_user.id, display_name(message.from_user)
    return 0, "Anonymous admin"


def is_owner(user_id: int) -> bool:
    return user_id in get_config().owner_ids


async def refresh_admins(chat_id: int) -> set[int]:
    ids: set[int] = set()
    try:
        async for member in bot.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
            if member.user:
                ids.add(member.user.id)
    except Exception:  # noqa: BLE001 - keep the previous list if Telegram refuses
        log.warning("Could not refresh admins for chat %s", chat_id, exc_info=True)
        previous = _admin_cache.get(chat_id)
        return previous[1] if previous else ids
    _admin_cache[chat_id] = (time.monotonic(), ids)
    return ids


async def get_admins(chat_id: int) -> set[int]:
    entry = _admin_cache.get(chat_id)
    if entry and time.monotonic() - entry[0] < _ADMIN_TTL:
        return entry[1]
    return await refresh_admins(chat_id)


async def is_admin(chat_id: int, user_id: int) -> bool:
    if is_owner(user_id):
        return True
    return user_id in await get_admins(chat_id)


async def has_control(chat_id: int, user_id: int, anonymous: bool = False) -> bool:
    """May this user use playback-control commands in this chat?"""
    if anonymous or is_owner(user_id):
        return True
    settings = await db.get_chat_settings(chat_id)
    if settings["controls_mode"] == "everyone":
        return True
    return await is_admin(chat_id, user_id)
