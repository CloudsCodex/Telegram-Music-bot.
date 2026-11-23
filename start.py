# Developer by : Mr_Manas_Op
"""Keyboard for the /start message."""

from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def start_markup(bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add me to your group", url=f"https://t.me/{bot_username}?startgroup=true")],
            [InlineKeyboardButton("📖 Commands", callback_data="basic|help")],
        ]
    )
