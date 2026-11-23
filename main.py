# Developer by : Mr_Manas_Op
"""Entry point: starts the bot client, the assistant account and the voice engine."""

import asyncio
import logging
import sys

# Pyrogram binds to the current event loop when a Client is created, so make
# sure a loop exists *before* any client module is imported.
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from config import ConfigError, VERSION, get_config  # noqa: E402

try:
    cfg = get_config()
except ConfigError as error:
    print(f"Configuration error: {error}\nCopy .env.example to .env and fill in the values.")
    sys.exit(1)

from utils.logger import setup_logging  # noqa: E402

setup_logging(cfg.log_level, cfg.log_dir)
log = logging.getLogger("main")

from pyrogram import idle  # noqa: E402
from pyrogram.types import BotCommand  # noqa: E402

from database import db  # noqa: E402
from services import media  # noqa: E402
from services.clients import assistant, bot, calls  # noqa: E402
from services.player import players  # noqa: E402
import plugins  # noqa: E402,F401  (registers every command handler)
from plugins.events import register_call_handlers  # noqa: E402

COMMANDS = [
    BotCommand("play", "Play a song, link or replied audio file"),
    BotCommand("vplay", "Play a video link or replied video file"),
    BotCommand("pause", "Pause playback"),
    BotCommand("resume", "Resume playback"),
    BotCommand("skip", "Skip the current track"),
    BotCommand("end", "Stop playback and clear the queue"),
    BotCommand("stop", "Stop the current track"),
    BotCommand("replay", "Replay the current track"),
    BotCommand("seek", "Jump to a timestamp, e.g. /seek 1:30"),
    BotCommand("volume", "Adjust the volume (1-200)"),
    BotCommand("mute", "Mute playback"),
    BotCommand("unmute", "Unmute playback"),
    BotCommand("queue", "Show the queue"),
    BotCommand("shuffle", "Shuffle queued tracks"),
    BotCommand("loop", "Set repeat mode: off, track or queue"),
    BotCommand("remove", "Remove a track from the queue"),
    BotCommand("skipto", "Skip to a queue position"),
    BotCommand("clear", "Clear upcoming tracks"),
    BotCommand("song", "Show details of the current track"),
    BotCommand("current", "Show what is playing"),
    BotCommand("search", "Search for music"),
    BotCommand("lyrics", "Find lyrics"),
    BotCommand("playlist", "Manage your playlists"),
    BotCommand("save", "Save the current track to a playlist"),
    BotCommand("myplaylist", "Show your saved playlists"),
    BotCommand("settings", "Open playback settings"),
    BotCommand("admincache", "Refresh the group admin list"),
    BotCommand("reload", "Reload music settings"),
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show the command list"),
    BotCommand("ping", "Check response time"),
    BotCommand("about", "About this bot"),
]


async def run() -> None:
    log.info("Starting music bot v%s", VERSION)
    await db.connect()
    media.purge_downloads()

    await bot.start()
    await assistant.start()
    register_call_handlers()
    await calls.start()
    await bot.set_bot_commands(COMMANDS)

    cleanup_task = asyncio.create_task(players.cleanup_loop())
    log.info("Bot @%s is online.", bot.me.username)
    try:
        await idle()
    finally:
        log.info("Shutting down…")
        cleanup_task.cancel()
        await players.shutdown()
        await bot.stop()
        await assistant.stop()
        await db.close()


if __name__ == "__main__":
    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        pass
