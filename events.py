# Developer by : Mr_Manas_Op
"""Voice-chat events: advance the queue when a stream ends, clean up when the call closes."""

from __future__ import annotations

import inspect
import logging

from pytgcalls import filters
from pytgcalls.types import ChatUpdate

from services.clients import calls
from services.player import players

log = logging.getLogger(__name__)


def register_call_handlers() -> None:
    """Attach py-tgcalls update handlers. Call once, before ``calls.start()``."""
    stream_end = filters.stream_end
    if inspect.isfunction(stream_end):
        stream_end = stream_end()

    @calls.on_update(stream_end)
    async def _on_stream_end(_, update):
        await players.on_stream_end(update.chat_id)

    try:
        status = ChatUpdate.Status
        closed = status.CLOSED_VOICE_CHAT | status.KICKED | status.LEFT_GROUP

        @calls.on_update(filters.chat_update(closed))
        async def _on_call_closed(_, update):
            await players.on_call_closed(update.chat_id)

    except Exception:  # noqa: BLE001 - optional cleanup hook
        log.warning("Voice-chat close events are not available in this py-tgcalls version.", exc_info=True)
