from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterable

from schems import IListingRepository
from models import Listing

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    external_id TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    price       TEXT,
    price_eur   INTEGER,
    address     TEXT,
    url         TEXT NOT NULL,
    scraped_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_eur);
"""


class SqliteListingRepository(IListingRepository):
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def save_many(self, listings: Iterable[Listing]) -> int:
        rows = [
            (l.external_id, l.title, l.price, l.price_eur, l.address, l.url, l.scraped_at)
            for l in listings
        ]
        if not rows:
            return 0
        with self._connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            conn.executemany(
                """
                INSERT INTO listings
                    (external_id, title, price, price_eur, address, url, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(external_id) DO UPDATE SET
                    title=excluded.title,
                    price=excluded.price,
                    price_eur=excluded.price_eur,
                    address=excluded.address,
                    url=excluded.url,
                    scraped_at=excluded.scraped_at
                """,
                rows,
            )
            after = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        return after - before

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]