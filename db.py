# Developer by : Mr_Manas_Op
"""Async SQLite storage for chat settings, playlists and statistics."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import aiosqlite

from services.models import Track

log = logging.getLogger(__name__)

MAX_PLAYLISTS_PER_USER = 10
MAX_TRACKS_PER_PLAYLIST = 100

DEFAULT_SETTINGS: dict[str, Any] = {
    "volume": 100,
    "loop_mode": "off",
    "controls_mode": "admins",
    "announce": 1,
}
_SETTING_KEYS = frozenset(DEFAULT_SETTINGS)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id       INTEGER PRIMARY KEY,
    volume        INTEGER NOT NULL DEFAULT 100,
    loop_mode     TEXT    NOT NULL DEFAULT 'off',
    controls_mode TEXT    NOT NULL DEFAULT 'admins',
    announce      INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS chats (
    chat_id    INTEGER PRIMARY KEY,
    title      TEXT,
    first_seen INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS stats (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS playlists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    name       TEXT    NOT NULL COLLATE NOCASE,
    created_at INTEGER NOT NULL,
    UNIQUE (user_id, name)
);
CREATE TABLE IF NOT EXISTS playlist_tracks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL,
    artist      TEXT,
    duration    INTEGER NOT NULL DEFAULT 0,
    source      TEXT    NOT NULL,
    location    TEXT    NOT NULL,
    is_video    INTEGER NOT NULL DEFAULT 0,
    thumb       TEXT,
    license_url TEXT,
    added_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tracks_playlist ON playlist_tracks(playlist_id);
"""


class PlaylistExists(Exception):
    """A playlist with that name already exists."""


class LimitReached(Exception):
    """A per-user or per-playlist limit was reached."""


class Database:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._conn: aiosqlite.Connection | None = None
        self._settings_cache: dict[int, dict[str, Any]] = {}

    # ------------------------------------------------------------ lifecycle
    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        log.info("Database ready at %s", self._path)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected.")
        return self._conn

    # -------------------------------------------------------- chat settings
    async def get_chat_settings(self, chat_id: int) -> dict[str, Any]:
        cached = self._settings_cache.get(chat_id)
        if cached is not None:
            return dict(cached)
        async with self.conn.execute(
            "SELECT volume, loop_mode, controls_mode, announce FROM chat_settings WHERE chat_id=?",
            (chat_id,),
        ) as cur:
            row = await cur.fetchone()
        settings = dict(row) if row else dict(DEFAULT_SETTINGS)
        self._settings_cache[chat_id] = settings
        return dict(settings)

    async def set_chat_setting(self, chat_id: int, key: str, value: Any) -> None:
        if key not in _SETTING_KEYS:
            raise ValueError(f"Unknown setting: {key}")
        await self.conn.execute(
            "INSERT INTO chat_settings(chat_id) VALUES(?) ON CONFLICT(chat_id) DO NOTHING",
            (chat_id,),
        )
        # ``key`` is validated against a fixed whitelist above.
        await self.conn.execute(f"UPDATE chat_settings SET {key}=? WHERE chat_id=?", (value, chat_id))
        await self.conn.commit()
        self._settings_cache.pop(chat_id, None)

    def clear_settings_cache(self, chat_id: int | None = None) -> None:
        if chat_id is None:
            self._settings_cache.clear()
        else:
            self._settings_cache.pop(chat_id, None)

    # ----------------------------------------------------- chats & statistics
    async def touch_chat(self, chat_id: int, title: str) -> None:
        now = int(time.time())
        await self.conn.execute(
            "INSERT INTO chats(chat_id, title, first_seen, last_seen) VALUES(?,?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, last_seen=excluded.last_seen",
            (chat_id, title, now, now),
        )
        await self.conn.commit()

    async def incr_stat(self, key: str, amount: int = 1) -> None:
        await self.conn.execute(
            "INSERT INTO stats(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = value + excluded.value",
            (key, amount),
        )
        await self.conn.commit()

    async def get_stats(self) -> dict[str, int]:
        async with self.conn.execute("SELECT value FROM stats WHERE key='tracks_played'") as cur:
            row = await cur.fetchone()
        tracks = int(row[0]) if row else 0
        async with self.conn.execute("SELECT COUNT(*) FROM chats") as cur:
            row = await cur.fetchone()
        return {"tracks_played": tracks, "chats": int(row[0]) if row else 0}

    # -------------------------------------------------------------- playlists
    async def list_playlists(self, user_id: int) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT p.id, p.name, COUNT(t.id) AS tracks FROM playlists p "
            "LEFT JOIN playlist_tracks t ON t.playlist_id = p.id "
            "WHERE p.user_id=? GROUP BY p.id ORDER BY p.name COLLATE NOCASE",
            (user_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def get_playlist(self, user_id: int, name: str) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT id, name FROM playlists WHERE user_id=? AND name=?", (user_id, name)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def create_playlist(self, user_id: int, name: str) -> dict[str, Any]:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM playlists WHERE user_id=?", (user_id,)
        ) as cur:
            count = (await cur.fetchone())[0]
        if count >= MAX_PLAYLISTS_PER_USER:
            raise LimitReached(f"You can have up to {MAX_PLAYLISTS_PER_USER} playlists.")
        try:
            cur = await self.conn.execute(
                "INSERT INTO playlists(user_id, name, created_at) VALUES(?,?,?)",
                (user_id, name, int(time.time())),
            )
        except aiosqlite.IntegrityError:
            raise PlaylistExists(name) from None
        await self.conn.commit()
        return {"id": cur.lastrowid, "name": name}

    async def delete_playlist(self, user_id: int, name: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM playlists WHERE user_id=? AND name=?", (user_id, name)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_tracks(self, playlist_id: int) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT id, title, artist, duration, source, location, is_video, thumb, license_url "
            "FROM playlist_tracks WHERE playlist_id=? ORDER BY id",
            (playlist_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def add_track(self, playlist_id: int, track: Track) -> bool:
        """Add a track. Returns False if it is already in the playlist."""
        async with self.conn.execute(
            "SELECT COUNT(*), SUM(location=?) FROM playlist_tracks WHERE playlist_id=?",
            (track.location, playlist_id),
        ) as cur:
            total, dupes = await cur.fetchone()
        if dupes:
            return False
        if total >= MAX_TRACKS_PER_PLAYLIST:
            raise LimitReached(f"A playlist can hold up to {MAX_TRACKS_PER_PLAYLIST} tracks.")
        await self.conn.execute(
            "INSERT INTO playlist_tracks(playlist_id, title, artist, duration, source, location, "
            "is_video, thumb, license_url, added_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                playlist_id,
                track.title,
                track.artist,
                track.duration,
                track.source,
                track.location,
                int(track.is_video),
                track.thumb,
                track.license_url,
                int(time.time()),
            ),
        )
        await self.conn.commit()
        return True

    async def remove_track(self, playlist_id: int, position: int) -> dict[str, Any] | None:
        tracks = await self.get_tracks(playlist_id)
        if not 1 <= position <= len(tracks):
            return None
        target = tracks[position - 1]
        await self.conn.execute("DELETE FROM playlist_tracks WHERE id=?", (target["id"],))
        await self.conn.commit()
        return target
