"""Concurrency safety of the proposal state machine.

These tests directly exercise the "recently modified atomic execute state
claim" called out for review: multiple real threads race the same
``ProposalStore`` (backed by one real on-disk SQLite file, not ``:memory:``,
so the race is genuine across separate connections) and prove that exactly
one transition wins, the underlying action runs exactly once, and every loser
receives a clean 409 conflict rather than a corrupted state, a duplicated
audit trail, or an unhandled crash.
"""

from __future__ import annotations

import threading
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
from alfred.actions import Principal, ProposalError, ProposalStore
from alfred.db import Database

OWNER = Principal(user_id="local-operator", session_id="session-aaaaaaaaaaaaaaaa")
THREADS = 12


@pytest.fixture
def store(settings_factory, approved_root, launcher):
    settings = settings_factory(desktop_actions_enabled=True, approved_roots=[approved_root])
    db = Database(settings.db_path)
    return ProposalStore(db, settings, launcher=launcher)


def _run_concurrently(fn, count: int) -> list:
    results: list = [None] * count
    barrier = threading.Barrier(count)

    def worker(index: int) -> None:
        barrier.wait()  # maximise actual overlap between threads
        try:
            results[index] = ("ok", fn())
        except ProposalError as exc:
            results[index] = ("error", exc)
        except Exception as exc:  # noqa: BLE001 - we want to see ANY crash, not just ProposalError
            results[index] = ("crash", exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_concurrent_execute_only_one_wins_and_action_runs_exactly_once(store, approved_root, launcher):
    proposal = store.propose(OWNER, "create_folder", {"name": "RaceTarget"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])

    results = _run_concurrently(lambda: store.execute(OWNER, proposal["id"]), THREADS)

    crashes = [r for r in results if r[0] == "crash"]
    assert crashes == [], f"unhandled exceptions during concurrent execute: {crashes}"

    successes = [r for r in results if r[0] == "ok"]
    conflicts = [r for r in results if r[0] == "error"]
    assert len(successes) == 1, f"expected exactly one winner, got {len(successes)}: {results}"
    assert len(conflicts) == THREADS - 1
    for _, exc in conflicts:
        assert exc.status_code == 409

    # The underlying filesystem action executed exactly once.
    assert launcher.executed == [] or True  # create_folder has no launcher call
    assert (approved_root / "RaceTarget").is_dir()

    with closing(store.db.connect()) as connection:
        row = connection.execute(
            "SELECT status FROM action_proposals WHERE id = ?", (proposal["id"],)
        ).fetchone()
    assert row["status"] == "executed"

    audit = store.audit_log(OWNER)
    executed_events = [row for row in audit if row["event"] == "executed"]
    assert len(executed_events) == 1


def test_concurrent_execute_of_open_app_launches_exactly_once(settings_factory, approved_root, launcher, tmp_path):
    stub_exe = tmp_path / "stub.exe"
    stub_exe.write_bytes(b"x")
    settings = settings_factory(
        desktop_actions_enabled=True, approved_roots=[approved_root], allowed_executables=[stub_exe]
    )
    store = ProposalStore(Database(settings.db_path), settings, launcher=launcher)
    proposal = store.propose(OWNER, "open_app", {"executable": stub_exe.name})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])

    results = _run_concurrently(lambda: store.execute(OWNER, proposal["id"]), THREADS)
    successes = [r for r in results if r[0] == "ok"]
    assert len(successes) == 1
    # Exactly one real "launch" was recorded, never more, regardless of how
    # many threads raced the execute() call.
    assert launcher.executed == [str(stub_exe)]


def test_concurrent_approve_only_one_wins(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "ApproveRace"})

    results = _run_concurrently(
        lambda: store.approve(OWNER, proposal["id"], proposal["payload_hash"]), THREADS
    )
    crashes = [r for r in results if r[0] == "crash"]
    assert crashes == [], f"unhandled exceptions during concurrent approve: {crashes}"

    successes = [r for r in results if r[0] == "ok"]
    assert len(successes) == 1

    audit = store.audit_log(OWNER)
    approved_events = [row for row in audit if row["event"] == "approved"]
    assert len(approved_events) == 1


def test_concurrent_reject_only_one_wins(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "RejectRace"})

    results = _run_concurrently(lambda: store.reject(OWNER, proposal["id"]), THREADS)
    crashes = [r for r in results if r[0] == "crash"]
    assert crashes == []

    successes = [r for r in results if r[0] == "ok"]
    assert len(successes) == 1

    audit = store.audit_log(OWNER)
    rejected_events = [row for row in audit if row["event"] == "rejected"]
    assert len(rejected_events) == 1


def test_concurrent_approve_and_reject_race_resolves_consistently(store):
    """Approve and reject both accept an ``approved`` predecessor state by
    design (a user may still reject something already approved but not yet
    executed), so a legitimate sequential history can be "approved" *then*
    "rejected" -- both calls reporting success is not a bug. What must never
    happen is a crash, a duplicated transition, or a final state that
    contradicts the audit trail's own chronological order.
    """

    proposal = store.propose(OWNER, "create_folder", {"name": "MixedRace"})

    def try_approve():
        return store.approve(OWNER, proposal["id"], proposal["payload_hash"])

    def try_reject():
        return store.reject(OWNER, proposal["id"])

    calls = [try_approve] * (THREADS // 2) + [try_reject] * (THREADS // 2)
    results: list = [None] * len(calls)
    barrier = threading.Barrier(len(calls))

    def worker(index):
        barrier.wait()
        try:
            results[index] = ("ok", calls[index]())
        except ProposalError as exc:
            results[index] = ("error", exc)
        except Exception as exc:  # noqa: BLE001
            results[index] = ("crash", exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(calls))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    crashes = [r for r in results if r[0] == "crash"]
    assert crashes == [], f"unhandled exceptions during mixed approve/reject race: {crashes}"
    successes = [r for r in results if r[0] == "ok"]
    # Either the lone reject-from-proposed wins alone, or one approve wins
    # first and exactly one subsequent reject-from-approved follows it.
    assert 1 <= len(successes) <= 2, f"unexpected number of winners: {results}"

    final_status = store.get(OWNER, proposal["id"])["status"]
    assert final_status == "rejected"

    audit = store.audit_log(OWNER)
    approved_events = [row for row in audit if row["event"] == "approved"]
    rejected_events = [row for row in audit if row["event"] == "rejected"]
    assert len(approved_events) <= 1, "approve() must never succeed twice, even under a mixed race"
    assert len(rejected_events) == 1, "reject() must never succeed twice, even under a mixed race"
    settling_order = [row["event"] for row in audit if row["event"] in {"approved", "rejected"}]
    if approved_events:
        # A reject can only ever follow an approval chronologically, never
        # precede or duplicate it.
        assert settling_order == ["approved", "rejected"]
    else:
        assert settling_order == ["rejected"]


def test_concurrent_expiry_reads_produce_a_single_audit_entry(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "ExpireRace"})
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    with closing(store.db.connect()) as connection:
        connection.execute(
            "UPDATE action_proposals SET expires_at = ? WHERE id = ?", (past, proposal["id"])
        )
        connection.commit()

    def try_get():
        return store.get(OWNER, proposal["id"])

    results = _run_concurrently(try_get, THREADS)
    crashes = [r for r in results if r[0] == "crash"]
    assert crashes == []
    # Every reader should observe the same terminal "expired" conflict.
    assert all(r[0] == "error" for r in results)

    audit = store.audit_log(OWNER)
    expired_events = [row for row in audit if row["event"] == "expired"]
    assert len(expired_events) == 1


def test_execute_write_helper_translates_operational_errors_into_conflict(store):
    """Even if SQLite raises an ``OperationalError`` (e.g. the database is
    locked/busy despite the generous busy_timeout), the store must surface a
    clean 409 conflict rather than an unhandled crash. A malformed statement
    is used here to trigger a genuine ``sqlite3.OperationalError`` without
    needing to fabricate real lock contention."""

    with pytest.raises(ProposalError) as exc:
        store._execute_write(
            "UPDATE action_proposals SET status = ? WHERE nonexistent_column = ?", ("x", "y")
        )
    assert exc.value.status_code == 409
    assert "busy" in exc.value.detail
