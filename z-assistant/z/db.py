"""Deterministic SQLite persistence for proposals and the immutable audit log.

The schema is created and migrated with the standard-library ``sqlite3`` module.
Migrations are an ordered list applied inside a transaction and tracked with the
``PRAGMA user_version`` counter, so initialisation is deterministic and
idempotent. Audit rows are append-only; only retention purging removes them.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Each migration is (version, list-of-statements). Applying them in order on a
# fresh database yields the current schema; re-running is a no-op.
MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            """
            CREATE TABLE action_proposals (
                id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                preview_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                approved_at TEXT,
                executed_at TEXT,
                result_json TEXT
            )
            """,
            """
            CREATE TABLE action_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                event TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_proposals_owner ON action_proposals (user_id, session_id)",
            "CREATE INDEX idx_audit_owner ON action_audit (user_id, session_id)",
        ],
    ),
    (
        2,
        [
            """
            CREATE TRIGGER action_audit_no_update
            BEFORE UPDATE ON action_audit
            BEGIN
                SELECT RAISE(ABORT, 'action audit rows are immutable');
            END
            """,
        ],
    ),
]

LATEST_VERSION = MIGRATIONS[-1][0]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


class Database:
    """Thin wrapper around a SQLite file with deterministic migrations."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        if self.path.parent and not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        # A generous busy timeout lets concurrent requests (e.g. rapid double
        # clicks in two tabs) wait briefly for a writer instead of raising
        # ``sqlite3.OperationalError: database is locked`` under contention.
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self) -> int:
        with closing(self.connect()) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            for target, statements in MIGRATIONS:
                if version >= target:
                    continue
                for statement in statements:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {target}")
                version = target
            connection.commit()
            return version

    def schema_version(self) -> int:
        with closing(self.connect()) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def purge_expired_and_old(self, retention_days: int) -> dict[str, int]:
        """Expire stale proposals and purge audit rows past the retention window."""

        now = utc_now()
        cutoff = (now - timedelta(days=retention_days)).isoformat()
        with closing(self.connect()) as connection:
            expired = connection.execute(
                """
                UPDATE action_proposals SET status = 'expired'
                WHERE status IN ('proposed', 'approved') AND expires_at < ?
                """,
                (now.isoformat(),),
            ).rowcount
            purged_proposals = connection.execute(
                "DELETE FROM action_proposals WHERE created_at < ?",
                (cutoff,),
            ).rowcount
            purged_audit = connection.execute(
                "DELETE FROM action_audit WHERE created_at < ?",
                (cutoff,),
            ).rowcount
            connection.commit()
        return {
            "expired": expired,
            "purged_proposals": purged_proposals,
            "purged_audit": purged_audit,
        }
