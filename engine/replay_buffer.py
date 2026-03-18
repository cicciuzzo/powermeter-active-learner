# engine/replay_buffer.py
import json
import random
import sqlite3
import time
from pathlib import Path
from typing import Optional

from engine import IDLE, WASHER, DRYER, BOTH

BUFFER_MAX_SIZE = 1000
DB_PATH = Path("replay_buffer.db")
ALL_CLASSES = [IDLE, WASHER, DRYER, BOTH]

# Minimum samples per class to attempt stratified sampling
_STRAT_MIN = 2


class ReplayBuffer:
    """
    Persistent FIFO replay buffer backed by SQLite.

    Each entry stores:
        timestamp  : float   — Unix epoch of the sample
        window     : JSON    — serialised normalised window (list[float])
        label      : int     — class label (IDLE/WASHER/DRYER/BOTH)
        source     : str     — 'proactive' or 'reactive'

    Stratified sampling ensures IDLE does not dominate mini-batches.
    """

    def __init__(
        self,
        max_size: int = BUFFER_MAX_SIZE,
        db_path: Path | str = DB_PATH,
    ) -> None:
        self._max_size = max_size
        self._db_path = Path(db_path)
        self._conn = self._init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, window: list[float], label: int, source: str) -> None:
        """Insert a new sample; evict the oldest entry if over capacity."""
        ts = time.time()
        window_json = json.dumps(window)
        with self._conn:
            self._conn.execute(
                "INSERT INTO samples (timestamp, window, label, source) VALUES (?, ?, ?, ?)",
                (ts, window_json, label, source),
            )
        self._evict_if_needed()

    def sample_batch(self, batch_size: int) -> list[dict]:
        """
        Return up to batch_size samples using stratified sampling.

        The batch tries to draw an equal number of samples from each class
        that has entries in the buffer.  If a class has fewer samples than
        the per-class quota, all its samples are included and the remainder
        is filled from the global pool.
        """
        cur = self._conn.cursor()

        # Determine which classes have data
        cur.execute("SELECT DISTINCT label FROM samples")
        present_classes = [row[0] for row in cur.fetchall()]
        if not present_classes:
            return []

        per_class = max(1, batch_size // len(present_classes))
        collected: list[dict] = []

        for cls in present_classes:
            cur.execute(
                "SELECT id, timestamp, window, label, source FROM samples "
                "WHERE label = ? ORDER BY RANDOM() LIMIT ?",
                (cls, per_class),
            )
            rows = cur.fetchall()
            collected.extend(self._rows_to_dicts(rows))

        # If we haven't reached batch_size, top up randomly
        if len(collected) < batch_size:
            already_ids = {s["id"] for s in collected}
            placeholders = ",".join("?" for _ in already_ids) if already_ids else "NULL"
            remaining = batch_size - len(collected)
            query = (
                f"SELECT id, timestamp, window, label, source FROM samples "
                f"WHERE id NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT ?"
            )
            params = list(already_ids) + [remaining]
            cur.execute(query, params)
            collected.extend(self._rows_to_dicts(cur.fetchall()))

        random.shuffle(collected)
        return collected[:batch_size]

    def size(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM samples")
        return cur.fetchone()[0]

    def class_counts(self) -> dict[int, int]:
        """Return count of samples per class in the buffer."""
        cur = self._conn.execute("SELECT label, COUNT(*) FROM samples GROUP BY label")
        return dict(cur.fetchall())

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS samples (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL    NOT NULL,
                window    TEXT    NOT NULL,
                label     INTEGER NOT NULL,
                source    TEXT    NOT NULL
            )
            """
        )
        conn.commit()
        return conn

    def _evict_if_needed(self) -> None:
        current = self.size()
        if current > self._max_size:
            excess = current - self._max_size
            with self._conn:
                self._conn.execute(
                    "DELETE FROM samples WHERE id IN "
                    "(SELECT id FROM samples ORDER BY timestamp ASC LIMIT ?)",
                    (excess,),
                )

    @staticmethod
    def _rows_to_dicts(rows: list) -> list[dict]:
        result = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "timestamp": row[1],
                    "window": json.loads(row[2]),
                    "label": row[3],
                    "source": row[4],
                }
            )
        return result
