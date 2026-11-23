# Developer by : Mr_Manas_Op
"""Telegram clients.

``bot``       -- the bot account that receives commands.
``assistant`` -- a dedicated user account that joins voice chats and streams audio.
``calls``     -- py-tgcalls controller attached to the assistant account.
"""

from __future__ import annotations

from pyrogram import Client
from pyrogram.enums import ParseMode
from pytgcalls import PyTgCalls

from config import get_config

_cfg = get_config()
_cfg.data_dir.mkdir(parents=True, exist_ok=True)

bot = Client(
    "music_bot",
    api_id=_cfg.api_id,
    api_hash=_cfg.api_hash,
    bot_token=_cfg.bot_token,
    workdir=str(_cfg.data_dir),
    parse_mode=ParseMode.HTML,
)

assistant = Client(
    "assistant",
    api_id=_cfg.api_id,
    api_hash=_cfg.api_hash,
    session_string=_cfg.session_string,
    in_memory=True,
    parse_mode=ParseMode.HTML,
)

calls = PyTgCalls(assistant)
