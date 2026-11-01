"""forge.cards.storage - SQLite WAL persistence for deduplication and card records.

Replaces error-prone flat JSON with ACID-compliant SQLite:
- WAL mode (Write-Ahead Logging) for safe concurrent reads & writes
- Indexed hash lookups O(1)
- Automatic migration from legacy .zbin_state.json
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Optional, Set

from forge.config import DB_PATH, ensure_dirs


class CardStorage:
    def __init__(self, db_path: Optional[Path] = None, migrate_legacy: bool = True):
        ensure_dirs()
        self.db_path = db_path or DB_PATH
        self._init_db()
        if migrate_legacy:
            self._migrate_legacy_json()
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS card_hashes (
                    hash TEXT PRIMARY KEY,
                    pan TEXT,
                    bin TEXT,
                    created_at REAL
                )
            """)
            conn.commit()

    def _migrate_legacy_json(self) -> None:
        """Migrate legacy .zbin_state.json if present in cwd."""
        legacy = Path(".zbin_state.json")
        if legacy.is_file():
            try:
                data = json.loads(legacy.read_text())
                hashes = data.get("generated_hashes", [])
                if hashes:
                    self.record_hashes(hashes)
            except Exception:
                pass

    def has_seen(self, card_hash: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT 1 FROM card_hashes WHERE hash = ? LIMIT 1", (card_hash,))
            return cur.fetchone() is not None

    def get_known_hashes(self) -> set[str]:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT hash FROM card_hashes")
            return {row[0] for row in cur.fetchall()}

    def record_card(self, card_hash: str, pan: str = "", bin_: str = "") -> bool:
        with self._get_conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO card_hashes (hash, pan, bin, created_at) VALUES (?, ?, ?, ?)",
                    (card_hash, pan, bin_, time.time())
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def record_hashes(self, hashes: Iterable[str]) -> None:
        now = time.time()
        with self._get_conn() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO card_hashes (hash, pan, bin, created_at) VALUES (?, '', '', ?)",
                [(h, now) for h in hashes]
            )
            conn.commit()

    def total_count(self) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM card_hashes")
            return cur.fetchone()[0]


# Default singleton instance
storage = CardStorage()
