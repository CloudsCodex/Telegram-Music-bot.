# Developer by : Mr_Manas_Op
"""Playback engine: per-chat queues and voice-chat control through py-tgcalls."""

from __future__ import annotations

import asyncio
import logging
import random
import time

from pyrogram.errors import (
    InviteRequestSent,
    PeerIdInvalid,
    RPCError,
    UserAlreadyParticipant,
    UserBannedInChannel,
    UserNotParticipant,
    ChannelPrivate,
)
from pytgcalls.types import AudioQuality, MediaStream, VideoQuality

from config import get_config
from database import db
from helpers.cards import now_playing_text
from helpers.formatting import esc
from keyboards.player import player_markup
from services import media
from services.clients import assistant, bot, calls
from services.errors import BotError
from services.models import Track

log = logging.getLogger(__name__)

LOOP_MODES = ("off", "track", "queue")
_STREAM_END_GUARD = 3.0  # ignore "stream ended" events right after a track starts


def _build_stream(source: str, video: bool, offset: float) -> MediaStream:
    ffmpeg_params = f"-ss {int(offset)}" if offset > 0 else None
    if video:
        return MediaStream(
            source,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.SD_480p,
            ffmpeg_parameters=ffmpeg_params,
        )
    return MediaStream(
        source,
        audio_parameters=AudioQuality.HIGH,
        video_flags=MediaStream.Flags.IGNORE,
        ffmpeg_parameters=ffmpeg_params,
    )


class ChatPlayer:
    """State of one chat's voice-chat session."""

    def __init__(self, chat_id: int, volume: int, loop: str) -> None:
        self.chat_id = chat_id
        self.current: Track | None = None
        self.queue: list[Track] = []
        self.loop = loop
        self.volume = volume
        self.paused = False
        self.muted = False
        self.gen = 0
        self.last_end_gen = -1
        self.started_at = 0.0
        self.now_msg_id: int | None = None
        self.lock = asyncio.Lock()
        self._base = 0.0
        self._resumed_at: float | None = None

    def mark_started(self, offset: float) -> None:
        self._base = offset
        self._resumed_at = time.monotonic()
        self.started_at = self._resumed_at
        self.paused = False
        self.gen += 1

    def mark_paused(self) -> None:
        self._base = self.position()
        self._resumed_at = None
        self.paused = True

    def mark_resumed(self) -> None:
        self._resumed_at = time.monotonic()
        self.paused = False

    def position(self) -> float:
        if self.current is None:
            return 0.0
        elapsed = time.monotonic() - self._resumed_at if self._resumed_at is not None else 0.0
        position = self._base + elapsed
        if self.current.duration:
            position = min(position, float(self.current.duration))
        return max(position, 0.0)


class PlayerManager:
    def __init__(self) -> None:
        self.players: dict[int, ChatPlayer] = {}
        self._joined: set[int] = set()
        self._cfg = get_config()

    # ---------------------------------------------------------------- access
    def peek(self, chat_id: int) -> ChatPlayer | None:
        return self.players.get(chat_id)

    async def get(self, chat_id: int) -> ChatPlayer:
        player = self.players.get(chat_id)
        if player is None:
            settings = await db.get_chat_settings(chat_id)
            player = ChatPlayer(chat_id, int(settings["volume"]), str(settings["loop_mode"]))
            self.players[chat_id] = player
        return player

    def active_count(self) -> int:
        return sum(1 for p in self.players.values() if p.current is not None)

    def snapshot(self, chat_id: int) -> tuple[Track | None, list[Track]]:
        player = self.players.get(chat_id)
        if not player:
            return None, []
        return player.current, list(player.queue)

    def in_use_paths(self) -> set[str]:
        paths: set[str] = set()
        for player in self.players.values():
            for track in ([player.current] if player.current else []) + player.queue:
                if track.local_path:
                    paths.add(track.local_path)
        return paths

    async def _require_current(self, chat_id: int) -> ChatPlayer:
        player = self.players.get(chat_id)
        if not player or player.current is None:
            raise BotError("Nothing is playing right now.")
        return player

    async def check_room(self, chat_id: int) -> None:
        player = await self.get(chat_id)
        if len(player.queue) >= self._cfg.max_queue:
            raise BotError(f"The queue is full ({self._cfg.max_queue} tracks).")

    # ----------------------------------------------------------- messaging
    def build_card(self, chat_id: int, header: str) -> tuple[str, object] | None:
        player = self.players.get(chat_id)
        if not player or player.current is None:
            return None
        text = now_playing_text(
            player.current,
            header=header,
            loop=player.loop,
            volume=player.volume,
        )
        return text, player_markup(chat_id)

    async def adopt(self, chat_id: int, message) -> None:
        """Remember ``message`` as the now-playing message and remove the old one."""
        player = self.players.get(chat_id)
        if not player:
            return
        old = player.now_msg_id
        player.now_msg_id = message.id
        if old and old != message.id:
            try:
                await bot.delete_messages(chat_id, old)
            except Exception:  # noqa: BLE001 - missing delete rights are fine
                log.debug("Could not delete old now-playing message", exc_info=True)

    async def announce(self, chat_id: int, *, header: str = "🎵 <b>Now playing</b>", reply_to=None):
        card = self.build_card(chat_id, header)
        if card is None:
            return None
        text, markup = card
        try:
            if reply_to is not None:
                message = await reply_to.reply_text(text, reply_markup=markup)
            else:
                message = await bot.send_message(chat_id, text, reply_markup=markup)
        except Exception:  # noqa: BLE001
            log.warning("Could not send now-playing message", exc_info=True)
            return None
        await self.adopt(chat_id, message)
        return message

    async def _notify(self, chat_id: int, text: str) -> None:
        try:
            await bot.send_message(chat_id, text)
        except Exception:  # noqa: BLE001
            log.debug("Could not send notification", exc_info=True)

    # ------------------------------------------------------------ internals
    @staticmethod
    def _release(track: Track | None) -> None:
        if track is not None:
            media.release(track)

    @staticmethod
    def _map_error(exc: Exception) -> BotError:
        name = type(exc).__name__
        if "NoActiveGroupCall" in name or "GroupCallNotFound" in name:
            return BotError("There is no active voice chat. Please start a voice chat in this group first.")
        if "ChatAdminRequired" in name:
            return BotError("I need admin rights to manage the voice chat.")
        if "NoAudioSourceFound" in name or isinstance(exc, FileNotFoundError):
            return BotError("That media could not be opened.")
        log.exception("Playback error (%s)", name)
        return BotError("I couldn't start playback. Please try again in a moment.")

    async def _ensure_assistant(self, chat_id: int) -> None:
        if chat_id in self._joined:
            return
        try:
            await assistant.get_chat_member(chat_id, "me")
            self._joined.add(chat_id)
            return
        except (UserNotParticipant, PeerIdInvalid, ChannelPrivate):
            pass
        except RPCError:
            log.debug("Membership check failed", exc_info=True)

        try:
            chat = await bot.get_chat(chat_id)
            target = chat.username or await bot.export_chat_invite_link(chat_id)
            await assistant.join_chat(target)
        except UserAlreadyParticipant:
            pass
        except InviteRequestSent:
            raise BotError(
                "A join request was sent for the assistant account. Please approve it and try again."
            ) from None
        except UserBannedInChannel:
            raise BotError("The assistant account is banned in this group. Please unban it and try again.") from None
        except RPCError:
            log.warning("Assistant could not join chat %s", chat_id, exc_info=True)
            raise BotError(
                "I couldn't add the assistant account automatically. Please add it to the group, "
                "or give me the 'Invite users' admin permission."
            ) from None
        self._joined.add(chat_id)

    async def _apply_volume(self, player: ChatPlayer) -> None:
        try:
            await calls.change_volume_call(player.chat_id, player.volume)
        except Exception:  # noqa: BLE001
            log.debug("Could not apply volume", exc_info=True)

    async def _start(self, player: ChatPlayer, track: Track, offset: float = 0.0, count: bool = True) -> None:
        source = await media.resolve(track)
        await self._ensure_assistant(player.chat_id)
        stream = _build_stream(source, track.is_video, offset)
        try:
            await calls.play(player.chat_id, stream)
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc) from exc

        player.current = track
        player.mark_started(offset)
        if player.volume != 100:
            await self._apply_volume(player)
        if count:
            await db.incr_stat("tracks_played")

    async def _leave_call(self, chat_id: int) -> None:
        try:
            await calls.leave_call(chat_id)
        except Exception:  # noqa: BLE001 - not in a call / already left
            log.debug("leave_call failed", exc_info=True)

    async def _advance(self, player: ChatPlayer, *, skipped: bool) -> Track | None:
        """Move to the next track. Returns it, or None when playback has finished."""
        current = player.current
        nxt: Track | None = None
        if current is not None:
            if player.loop == "track" and not skipped:
                nxt = current
            elif player.loop == "queue":
                player.queue.append(current)
            else:
                self._release(current)
        player.current = None

        while nxt is not None or player.queue:
            if nxt is None:
                nxt = player.queue.pop(0)
            try:
                await self._start(player, nxt)
                return nxt
            except BotError as exc:
                self._release(nxt)
                await self._notify(
                    player.chat_id, f"⚠️ Skipped <b>{esc(nxt.title)}</b>: {esc(exc.message)}"
                )
                nxt = None

        player.paused = False
        await self._leave_call(player.chat_id)
        return None

    async def _teardown(self, player: ChatPlayer, *, keep_queue: bool) -> None:
        self._release(player.current)
        player.current = None
        player.paused = False
        if not keep_queue:
            for track in player.queue:
                self._release(track)
            player.queue.clear()
        await self._leave_call(player.chat_id)

    # ------------------------------------------------------------- playback
    async def add(self, chat_id: int, track: Track) -> tuple[int, bool]:
        """Queue a track. Returns ``(position, started)``; position 0 means it started now."""
        player = await self.get(chat_id)
        async with player.lock:
            if player.current is None:
                try:
                    await self._start(player, track)
                except Exception:
                    self._release(track)
                    raise
                return 0, True
            if len(player.queue) >= self._cfg.max_queue:
                self._release(track)
                raise BotError(f"The queue is full ({self._cfg.max_queue} tracks).")
            player.queue.append(track)
            return len(player.queue), False

    async def pause(self, chat_id: int) -> None:
        player = await self._require_current(chat_id)
        async with player.lock:
            if player.paused:
                raise BotError("Playback is already paused.")
            try:
                await calls.pause(chat_id)
            except Exception as exc:  # noqa: BLE001
                raise self._map_error(exc) from exc
            player.mark_paused()

    async def resume(self, chat_id: int) -> Track | None:
        """Resume playback. Returns a Track only if a new queued track was started."""
        player = self.players.get(chat_id)
        if player is None:
            raise BotError("Nothing is playing right now.")
        async with player.lock:
            if player.current is not None:
                if not player.paused:
                    raise BotError("Playback is not paused.")
                try:
                    await calls.resume(chat_id)
                except Exception as exc:  # noqa: BLE001
                    raise self._map_error(exc) from exc
                player.mark_resumed()
                return None
            if player.queue:
                started = await self._advance(player, skipped=True)
                if started is None:
                    raise BotError("None of the queued tracks could be played.")
                return started
        raise BotError("Nothing is playing right now.")

    async def toggle_pause(self, chat_id: int) -> bool:
        """Returns True if playback is now paused."""
        player = await self._require_current(chat_id)
        if player.paused:
            await self.resume(chat_id)
            return False
        await self.pause(chat_id)
        return True

    async def skip(self, chat_id: int) -> Track | None:
        player = await self._require_current(chat_id)
        async with player.lock:
            return await self._advance(player, skipped=True)

    async def stop(self, chat_id: int) -> int:
        """Stop the current track but keep the queue. Returns tracks still queued."""
        player = await self._require_current(chat_id)
        async with player.lock:
            await self._teardown(player, keep_queue=True)
            return len(player.queue)

    async def end(self, chat_id: int) -> None:
        player = self.players.get(chat_id)
        if not player or (player.current is None and not player.queue):
            raise BotError("Nothing is playing right now.")
        async with player.lock:
            await self._teardown(player, keep_queue=False)

    async def replay(self, chat_id: int) -> None:
        player = await self._require_current(chat_id)
        async with player.lock:
            await self._start(player, player.current, offset=0.0, count=False)

    async def seek(self, chat_id: int, seconds: int) -> None:
        player = await self._require_current(chat_id)
        async with player.lock:
            track = player.current
            if track.duration and seconds >= track.duration:
                raise BotError("That position is past the end of the track.")
            await self._start(player, track, offset=float(seconds), count=False)

    async def mute(self, chat_id: int) -> None:
        player = await self._require_current(chat_id)
        async with player.lock:
            if player.muted:
                raise BotError("Playback is already muted.")
            try:
                await calls.mute(chat_id)
            except Exception as exc:  # noqa: BLE001
                raise self._map_error(exc) from exc
            player.muted = True

    async def unmute(self, chat_id: int) -> None:
        player = await self._require_current(chat_id)
        async with player.lock:
            if not player.muted:
                raise BotError("Playback is not muted.")
            try:
                await calls.unmute(chat_id)
            except Exception as exc:  # noqa: BLE001
                raise self._map_error(exc) from exc
            player.muted = False

    async def set_volume(self, chat_id: int, volume: int) -> bool:
        """Set the volume. Returns True if it was applied to a live stream."""
        player = await self.get(chat_id)
        async with player.lock:
            live = player.current is not None
            if live:
                try:
                    await calls.change_volume_call(chat_id, volume)
                except Exception as exc:  # noqa: BLE001
                    raise self._map_error(exc) from exc
            player.volume = volume
        await db.set_chat_setting(chat_id, "volume", volume)
        return live

    # ---------------------------------------------------------------- queue
    async def shuffle(self, chat_id: int) -> int:
        player = self.players.get(chat_id)
        if not player or len(player.queue) < 2:
            raise BotError("I need at least two queued tracks to shuffle.")
        async with player.lock:
            random.shuffle(player.queue)
            return len(player.queue)

    async def set_loop(self, chat_id: int, mode: str) -> None:
        if mode not in LOOP_MODES:
            raise BotError("Loop mode must be off, track or queue.")
        player = await self.get(chat_id)
        player.loop = mode
        await db.set_chat_setting(chat_id, "loop_mode", mode)

    async def cycle_loop(self, chat_id: int) -> str:
        player = await self.get(chat_id)
        mode = LOOP_MODES[(LOOP_MODES.index(player.loop) + 1) % len(LOOP_MODES)]
        await self.set_loop(chat_id, mode)
        return mode

    async def remove(self, chat_id: int, position: int) -> Track:
        player = self.players.get(chat_id)
        if not player or not player.queue:
            raise BotError("The queue is empty.")
        async with player.lock:
            if not 1 <= position <= len(player.queue):
                raise BotError(f"Choose a position between 1 and {len(player.queue)}.")
            track = player.queue.pop(position - 1)
            self._release(track)
            return track

    async def skipto(self, chat_id: int, position: int) -> Track | None:
        player = self.players.get(chat_id)
        if not player or not player.queue:
            raise BotError("The queue is empty.")
        async with player.lock:
            if not 1 <= position <= len(player.queue):
                raise BotError(f"Choose a position between 1 and {len(player.queue)}.")
            skipped = player.queue[: position - 1]
            del player.queue[: position - 1]
            if player.loop == "queue":
                player.queue.extend(skipped)
            else:
                for track in skipped:
                    self._release(track)
            return await self._advance(player, skipped=True)

    async def clear(self, chat_id: int) -> int:
        player = self.players.get(chat_id)
        if not player or not player.queue:
            raise BotError("The queue is already empty.")
        async with player.lock:
            count = len(player.queue)
            for track in player.queue:
                self._release(track)
            player.queue.clear()
            return count

    # --------------------------------------------------------------- events
    async def on_stream_end(self, chat_id: int) -> None:
        player = self.players.get(chat_id)
        if not player:
            return
        async with player.lock:
            if player.current is None or player.last_end_gen == player.gen:
                return
            if time.monotonic() - player.started_at < _STREAM_END_GUARD:
                return
            player.last_end_gen = player.gen
            track = await self._advance(player, skipped=False)

        if track is not None:
            settings = await db.get_chat_settings(chat_id)
            if settings["announce"]:
                await self.announce(chat_id)
        else:
            await self._notify(chat_id, "✅ The queue has finished. Use /play to add more music.")

    async def on_call_closed(self, chat_id: int) -> None:
        """The voice chat ended or the assistant was removed."""
        self._joined.discard(chat_id)
        player = self.players.pop(chat_id, None)
        if player:
            self._release(player.current)
            for track in player.queue:
                self._release(track)

    async def reload_settings(self, chat_id: int) -> None:
        db.clear_settings_cache(chat_id)
        player = self.players.get(chat_id)
        if not player:
            return
        settings = await db.get_chat_settings(chat_id)
        player.loop = str(settings["loop_mode"])
        new_volume = int(settings["volume"])
        if new_volume != player.volume:
            player.volume = new_volume
            if player.current is not None:
                await self._apply_volume(player)

    # --------------------------------------------------------- housekeeping
    async def cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(1800)
            try:
                removed = media.cleanup_old_files(self.in_use_paths(), max_age_seconds=6 * 3600)
                if removed:
                    log.info("Removed %d stale download(s)", removed)
            except Exception:  # noqa: BLE001
                log.exception("Cleanup failed")

    async def shutdown(self) -> None:
        for chat_id, player in list(self.players.items()):
            try:
                await self._teardown(player, keep_queue=False)
            except Exception:  # noqa: BLE001
                log.debug("Shutdown teardown failed for %s", chat_id, exc_info=True)
        self.players.clear()


players = PlayerManager()
