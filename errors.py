# Developer by : Mr_Manas_Op
"""Exception types whose message is safe to show to ordinary users."""

from __future__ import annotations


class BotError(Exception):
    """An expected problem. ``message`` is plain text and safe for end users."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
