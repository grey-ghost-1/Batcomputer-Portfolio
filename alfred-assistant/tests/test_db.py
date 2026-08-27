"""Database migrations and retention/expiry purging."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from alfred.db import LATEST_VERSION, Database


def test_fresh_database_runs_migrations_to_latest_version(tmp_path):
    db = Database(tmp_path / "fresh.db")
    assert db.schema_version() == LATEST_VERSION
    assert LATEST_VERSION >= 1


def test_database_file_and_parent_directories_are_created(tmp_path):
    nested = tmp_path / "nested" / "dirs" / "alfred.db"
    db = Database(nested)
    assert nested.exists()
    assert db.schema_version() == LATEST_VERSION


def test_reopening_database_is_idempotent(tmp_path):
    path = tmp_path / "reopen.db"
    Database(path)
    second = Database(path)
    assert second.schema_version() == LATEST_VERSION
    # Re-running migrations against an already-migrated file must not error
    # or duplicate schema objects.
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {"action_proposals", "action_audit"} <= tables


def test_expected_tables_and_indexes_exist(tmp_path):
    path = tmp_path / "schema.db"
    Database(path)
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
    assert "action_proposals" in tables
    assert "action_audit" in tables
    assert "idx_proposals_owner" in indexes
    assert "idx_audit_owner" in indexes


def test_action_audit_rows_are_immutable_at_the_database_layer(tmp_path):
    """The append-only audit guarantee is enforced by SQLite itself (a
    BEFORE UPDATE trigger), not only by application code discipline -- even a
    direct SQL UPDATE against action_audit must be rejected."""

    path = tmp_path / "immutable.db"
    Database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO action_audit (proposal_id, action_type, user_id, session_id, event, "
            "detail_json, created_at) VALUES ('p1', 'create_folder', 'u', 's', 'proposed', '{}', 'now')"
        )
        connection.commit()
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("UPDATE action_audit SET event = 'tampered' WHERE proposal_id = 'p1'")


def test_action_audit_rows_can_still_be_deleted_by_retention_purge(tmp_path):
    # The trigger only blocks UPDATE; DELETE (used solely by retention
    # purging) must remain possible.
    path = tmp_path / "purge-ok.db"
    db = Database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO action_audit (proposal_id, action_type, user_id, session_id, event, "
            "detail_json, created_at) VALUES ('p1', 'create_folder', 'u', 's', 'proposed', '{}', '2000-01-01')"
        )
        connection.commit()
    result = db.purge_expired_and_old(retention_days=1)
    assert result["purged_audit"] == 1


def _insert_proposal(path, *, proposal_id, status, created_at, expires_at):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO action_proposals
            (id, action_type, user_id, session_id, payload_json, payload_hash,
             preview_json, status, created_at, expires_at)
            VALUES (?, 'create_folder', 'local-operator', 'session-abc', '{}', 'hash',
                    '{}', ?, ?, ?)
            """,
            (proposal_id, status, created_at, expires_at),
        )
        connection.commit()


def _insert_audit(path, *, proposal_id, created_at):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO action_audit
            (proposal_id, action_type, user_id, session_id, event, detail_json, created_at)
            VALUES (?, 'create_folder', 'local-operator', 'session-abc', 'proposed', '{}', ?)
            """,
            (proposal_id, created_at),
        )
        connection.commit()


def test_purge_expires_stale_proposed_and_approved_rows(tmp_path):
    path = tmp_path / "retention.db"
    db = Database(path)
    now = datetime.now(timezone.utc)
    past = (now - timedelta(seconds=5)).isoformat()
    future = (now + timedelta(hours=1)).isoformat()
    _insert_proposal(path, proposal_id="p1", status="proposed", created_at=now.isoformat(), expires_at=past)
    _insert_proposal(path, proposal_id="p2", status="approved", created_at=now.isoformat(), expires_at=past)
    _insert_proposal(
        path, proposal_id="p3", status="proposed", created_at=now.isoformat(), expires_at=future
    )
    result = db.purge_expired_and_old(retention_days=30)
    assert result["expired"] == 2
    with sqlite3.connect(path) as connection:
        statuses = dict(
            connection.execute("SELECT id, status FROM action_proposals").fetchall()
        )
    assert statuses["p1"] == "expired"
    assert statuses["p2"] == "expired"
    assert statuses["p3"] == "proposed"


def test_purge_deletes_rows_older_than_retention_window(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path)
    now = datetime.now(timezone.utc)
    ancient = (now - timedelta(days=400)).isoformat()
    recent = now.isoformat()
    _insert_proposal(path, proposal_id="old", status="executed", created_at=ancient, expires_at=ancient)
    _insert_proposal(path, proposal_id="new", status="executed", created_at=recent, expires_at=recent)
    _insert_audit(path, proposal_id="old", created_at=ancient)
    _insert_audit(path, proposal_id="new", created_at=recent)

    result = db.purge_expired_and_old(retention_days=30)
    assert result["purged_proposals"] == 1
    assert result["purged_audit"] == 1
    with sqlite3.connect(path) as connection:
        remaining_ids = {row[0] for row in connection.execute("SELECT id FROM action_proposals")}
        remaining_audit = {
            row[0] for row in connection.execute("SELECT proposal_id FROM action_audit")
        }
    assert remaining_ids == {"new"}
    assert remaining_audit == {"new"}


def test_purge_is_a_no_op_when_nothing_is_stale(tmp_path):
    path = tmp_path / "clean.db"
    db = Database(path)
    result = db.purge_expired_and_old(retention_days=30)
    assert result == {"expired": 0, "purged_proposals": 0, "purged_audit": 0}


def test_busy_timeout_pragma_is_configured(tmp_path):
    db = Database(tmp_path / "busy.db")
    with db.connect() as connection:
        value = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    assert value >= 30000
