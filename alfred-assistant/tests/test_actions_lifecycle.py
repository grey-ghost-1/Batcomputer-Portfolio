"""Full typed-action lifecycle: propose -> approve -> execute -> audit.

Every mutation is confined to pytest's ``tmp_path`` via an approved root, and
every desktop launch is captured by the ``RecordingLauncher`` double (see
conftest.py) -- no test in this module ever starts a real process, opens a
real browser, or touches the real clipboard.
"""

from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
from alfred.actions import Principal, ProposalError, ProposalStore
from alfred.db import Database

OWNER = Principal(user_id="local-operator", session_id="session-aaaaaaaaaaaaaaaa")
OTHER_SESSION = Principal(user_id="local-operator", session_id="session-bbbbbbbbbbbbbbbb")
OTHER_USER = Principal(user_id="other-user", session_id="session-aaaaaaaaaaaaaaaa")


@pytest.fixture
def stub_exe(tmp_path):
    exe = tmp_path / "stub_app.exe"
    exe.write_bytes(b"not a real executable")
    return exe


@pytest.fixture
def store(settings_factory, approved_root, launcher, stub_exe):
    settings = settings_factory(
        desktop_actions_enabled=True,
        clipboard_enabled=True,
        approved_roots=[approved_root],
        allowed_executables=[stub_exe],
        allowed_url_hosts=["example.com"],
    )
    db = Database(settings.db_path)
    return ProposalStore(db, settings, launcher=launcher)


def make_store(settings_factory, approved_root, launcher, stub_exe, **overrides):
    defaults = dict(
        desktop_actions_enabled=True,
        clipboard_enabled=True,
        approved_roots=[approved_root],
        allowed_executables=[stub_exe],
        allowed_url_hosts=["example.com"],
    )
    defaults.update(overrides)
    settings = settings_factory(**defaults)
    db = Database(settings.db_path)
    return ProposalStore(db, settings, launcher=launcher)


def _force_expired(store, proposal_id):
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    with closing(store.db.connect()) as connection:
        connection.execute("UPDATE action_proposals SET expires_at = ? WHERE id = ?", (past, proposal_id))
        connection.commit()


def _tamper_payload_json(store, proposal_id, new_payload: dict):
    with closing(store.db.connect()) as connection:
        connection.execute(
            "UPDATE action_proposals SET payload_json = ? WHERE id = ?",
            (json.dumps(new_payload), proposal_id),
        )
        connection.commit()


def _row_status(store, proposal_id) -> str:
    with closing(store.db.connect()) as connection:
        row = connection.execute(
            "SELECT status FROM action_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
    return row["status"]


def approve_and_execute(store, owner, proposal_id, payload_hash):
    store.approve(owner, proposal_id, payload_hash)
    return store.execute(owner, proposal_id)


# --- create_folder -----------------------------------------------------------


def test_create_folder_full_lifecycle(store, approved_root, launcher):
    proposal = store.propose(OWNER, "create_folder", {"name": "Reports"})
    assert proposal["status"] == "proposed"
    assert proposal["preview"]["path_diff"][0]["to"] == "Reports"

    approved = store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    assert approved["status"] == "approved"

    executed = store.execute(OWNER, proposal["id"])
    assert executed["status"] == "executed"
    assert executed["result"]["created_directory"] == "Reports"
    assert (approved_root / "Reports").is_dir()
    # No desktop launch of any kind happens for a pure filesystem action.
    assert launcher.executed == []
    assert launcher.opened_urls == []


def test_create_folder_execute_without_approval_is_rejected(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    with pytest.raises(ProposalError) as exc:
        store.execute(OWNER, proposal["id"])
    assert exc.value.status_code == 409


def test_create_folder_collision_is_refused_and_marks_failed(store, approved_root):
    (approved_root / "Existing").mkdir()
    proposal = store.propose(OWNER, "create_folder", {"name": "Existing"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    with pytest.raises(ProposalError, match="already exists"):
        store.execute(OWNER, proposal["id"])
    assert _row_status(store, proposal["id"]) == "failed"
    # A spent (failed) proposal cannot be executed again.
    with pytest.raises(ProposalError):
        store.execute(OWNER, proposal["id"])


def test_create_folder_disabled_when_desktop_actions_off(settings_factory, approved_root, launcher, stub_exe):
    store = make_store(
        settings_factory, approved_root, launcher, stub_exe, desktop_actions_enabled=False
    )
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    # Approval is still allowed (it is not a desktop action by itself).
    approved = store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    assert approved["status"] == "approved"
    assert approved["execution_enabled"] is False
    with pytest.raises(ProposalError, match="disabled") as exc:
        store.execute(OWNER, proposal["id"])
    assert exc.value.status_code == 403
    assert not (approved_root / "X").exists()


def test_create_folder_toctou_new_conflict_after_approval_blocks_execution(store, approved_root):
    proposal = store.propose(OWNER, "create_folder", {"name": "Late"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    # Simulate a filesystem change between approval and execution.
    (approved_root / "Late").mkdir()
    with pytest.raises(ProposalError, match="changed after preview|already exists"):
        store.execute(OWNER, proposal["id"])


# --- move_file -----------------------------------------------------------------


def test_move_file_full_lifecycle(store, approved_root):
    (approved_root / "source.txt").write_text("data", encoding="utf-8")
    proposal = store.propose(OWNER, "move_file", {"source": "source.txt", "destination": "moved.txt"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    executed = store.execute(OWNER, proposal["id"])
    assert executed["result"]["moved_to"] == "moved.txt"
    assert not (approved_root / "source.txt").exists()
    assert (approved_root / "moved.txt").read_text(encoding="utf-8") == "data"


def test_move_file_missing_source_fails_at_execution(store):
    proposal = store.propose(OWNER, "move_file", {"source": "missing.txt", "destination": "out.txt"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    with pytest.raises(ProposalError, match="not an existing regular file"):
        store.execute(OWNER, proposal["id"])


def test_move_file_destination_collision_refused(store, approved_root):
    (approved_root / "a.txt").write_text("a", encoding="utf-8")
    (approved_root / "b.txt").write_text("b", encoding="utf-8")
    proposal = store.propose(OWNER, "move_file", {"source": "a.txt", "destination": "b.txt"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    with pytest.raises(ProposalError, match="already exists"):
        store.execute(OWNER, proposal["id"])
    assert (approved_root / "a.txt").exists()  # nothing was moved


def test_move_file_rejects_traversal_at_propose_time(store):
    with pytest.raises(ProposalError) as exc:
        store.propose(OWNER, "move_file", {"source": "../outside.txt", "destination": "x.txt"})
    assert exc.value.status_code == 400


# --- organize_folder: dry run then execution ------------------------------------


def test_organize_folder_preview_is_a_dry_run_that_moves_nothing(store, approved_root):
    (approved_root / "a.txt").write_text("1", encoding="utf-8")
    (approved_root / "b.log").write_text("2", encoding="utf-8")
    proposal = store.propose(
        OWNER,
        "organize_folder",
        {"rules": [{"extension": ".txt", "subfolder": "text-files"}]},
    )
    assert proposal["preview"]["manifest"][0]["to"] == "text-files/a.txt"
    # Dry run: nothing has actually moved yet.
    assert (approved_root / "a.txt").exists()
    assert not (approved_root / "text-files").exists()


def test_organize_folder_execution_moves_matching_files_and_skips_conflicts(store, approved_root):
    (approved_root / "a.txt").write_text("1", encoding="utf-8")
    (approved_root / "b.txt").write_text("2", encoding="utf-8")
    (approved_root / "c.log").write_text("3", encoding="utf-8")
    proposal = store.propose(
        OWNER, "organize_folder", {"rules": [{"extension": "txt", "subfolder": "text"}]}
    )
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    executed = store.execute(OWNER, proposal["id"])
    assert executed["result"]["moved_count"] == 2
    assert (approved_root / "text" / "a.txt").exists()
    assert (approved_root / "text" / "b.txt").exists()
    assert (approved_root / "c.log").exists()  # unmatched extension untouched


def test_organize_folder_respects_max_files_limit(settings_factory, approved_root, launcher, stub_exe):
    for i in range(3):
        (approved_root / f"f{i}.txt").write_text("x", encoding="utf-8")
    store = make_store(settings_factory, approved_root, launcher, stub_exe, max_organize_files=1)
    with pytest.raises(ProposalError, match="exceeds"):
        store.propose(OWNER, "organize_folder", {"rules": [{"extension": ".txt", "subfolder": "t"}]})


# --- open_app: allow-list, no real launches ------------------------------------


def test_open_app_rejects_non_allowlisted_executable(store):
    with pytest.raises(ProposalError, match="allow-list") as exc:
        store.propose(OWNER, "open_app", {"executable": "not_allowed.exe"})
    assert exc.value.status_code == 400


def test_open_app_full_lifecycle_records_launch_via_fake_launcher_only(store, launcher, stub_exe):
    proposal = store.propose(OWNER, "open_app", {"executable": stub_exe.name})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    executed = store.execute(OWNER, proposal["id"])
    assert executed["result"]["launched"] == stub_exe.name
    assert launcher.executed == [str(stub_exe)]
    assert launcher.opened_urls == []
    assert launcher.clipboard_writes == []


def test_open_app_missing_executable_file_fails_at_execution(settings_factory, approved_root, launcher, tmp_path):
    ghost_exe = tmp_path / "ghost.exe"  # allow-listed but never created on disk
    store = make_store(settings_factory, approved_root, launcher, ghost_exe)
    proposal = store.propose(OWNER, "open_app", {"executable": "ghost.exe"})
    assert proposal["preview"]["warnings"]
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    with pytest.raises(ProposalError, match="does not exist at execution time"):
        store.execute(OWNER, proposal["id"])
    assert launcher.executed == []


# --- open_url: allow-list, scheme/credential/port checks -----------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",  # wrong scheme
        "https://not-allowed.example/",  # not on host allow-list
        "https://user:pass@example.com/",  # embedded credentials
        "https://example.com:8443/",  # nonstandard port
    ],
)
def test_open_url_rejects_unsafe_or_disallowed_urls(store, url):
    with pytest.raises(ProposalError) as exc:
        store.propose(OWNER, "open_url", {"url": url})
    assert exc.value.status_code == 400


def test_open_url_full_lifecycle_records_via_fake_launcher_only(store, launcher):
    proposal = store.propose(OWNER, "open_url", {"url": "https://example.com/page"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    executed = store.execute(OWNER, proposal["id"])
    assert executed["result"]["opened"] == "https://example.com/page"
    assert launcher.opened_urls == ["https://example.com/page"]
    assert launcher.executed == []


# --- set_clipboard: disabled by default; audit never stores the raw text ----


def test_set_clipboard_disabled_is_rejected_at_propose_time(settings_factory, approved_root, launcher, stub_exe):
    store = make_store(settings_factory, approved_root, launcher, stub_exe, clipboard_enabled=False)
    with pytest.raises(ProposalError, match="disabled") as exc:
        store.propose(OWNER, "set_clipboard", {"text": "hello"})
    assert exc.value.status_code == 400


def test_set_clipboard_requires_desktop_actions_even_when_clipboard_enabled(
    settings_factory, approved_root, launcher, stub_exe
):
    store = make_store(
        settings_factory,
        approved_root,
        launcher,
        stub_exe,
        desktop_actions_enabled=False,
        clipboard_enabled=True,
    )
    proposal = store.propose(OWNER, "set_clipboard", {"text": "hello"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    with pytest.raises(ProposalError, match="desktop actions are disabled"):
        store.execute(OWNER, proposal["id"])


def test_set_clipboard_full_lifecycle_and_audit_never_contains_the_text(store, launcher):
    secret_text = "MY-CLIPBOARD-SECRET-1234"
    proposal = store.propose(OWNER, "set_clipboard", {"text": secret_text})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    executed = store.execute(OWNER, proposal["id"])
    assert executed["result"] == {"character_count": len(secret_text)}
    assert launcher.clipboard_writes == [secret_text]

    audit = store.audit_log(OWNER)
    assert len(audit) >= 3  # proposed, approved, executed
    dumped = json.dumps(audit)
    assert secret_text not in dumped


# --- hash tampering / stored payload tampering ---------------------------------


def test_approve_with_wrong_hash_is_rejected(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    with pytest.raises(ProposalError, match="hash mismatch") as exc:
        store.approve(OWNER, proposal["id"], "0" * 64)
    assert exc.value.status_code == 409
    assert _row_status(store, proposal["id"]) == "proposed"


def test_stored_payload_tampering_detected_at_approve(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "Safe"})
    _tamper_payload_json(store, proposal["id"], {"root": 0, "parent": ".", "name": "Tampered"})
    with pytest.raises(ProposalError, match="tampering"):
        store.approve(OWNER, proposal["id"], proposal["payload_hash"])


def test_stored_payload_tampering_detected_at_execute_after_legitimate_approval(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "Safe"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    _tamper_payload_json(store, proposal["id"], {"root": 0, "parent": ".", "name": "Swapped"})
    with pytest.raises(ProposalError, match="tampering"):
        store.execute(OWNER, proposal["id"])


# --- expiry ----------------------------------------------------------------------


def test_expired_proposal_cannot_be_approved(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    _force_expired(store, proposal["id"])
    with pytest.raises(ProposalError, match="expired"):
        store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    assert _row_status(store, proposal["id"]) == "expired"


def test_expiry_produces_exactly_one_audit_entry_even_with_repeated_reads(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    _force_expired(store, proposal["id"])
    for _ in range(3):
        with pytest.raises(ProposalError, match="expired"):
            store.get(OWNER, proposal["id"])
    audit = store.audit_log(OWNER)
    expired_events = [row for row in audit if row["event"] == "expired"]
    assert len(expired_events) == 1


# --- replay / double approval / double execution -------------------------------


def test_double_approval_is_rejected(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    with pytest.raises(ProposalError, match="already approved"):
        store.approve(OWNER, proposal["id"], proposal["payload_hash"])


def test_double_execution_is_rejected(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    store.execute(OWNER, proposal["id"])
    with pytest.raises(ProposalError, match="already executed"):
        store.execute(OWNER, proposal["id"])


def test_reject_then_approve_is_rejected(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    store.reject(OWNER, proposal["id"])
    with pytest.raises(ProposalError):
        store.approve(OWNER, proposal["id"], proposal["payload_hash"])


def test_reject_after_execute_is_rejected(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    store.approve(OWNER, proposal["id"], proposal["payload_hash"])
    store.execute(OWNER, proposal["id"])
    with pytest.raises(ProposalError, match="cannot be rejected"):
        store.reject(OWNER, proposal["id"])


def test_double_reject_is_rejected(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    store.reject(OWNER, proposal["id"])
    with pytest.raises(ProposalError):
        store.reject(OWNER, proposal["id"])


# --- ownership / two-session isolation ------------------------------------------


def test_other_session_cannot_read_the_proposal(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    with pytest.raises(ProposalError) as exc:
        store.get(OTHER_SESSION, proposal["id"])
    assert exc.value.status_code == 404  # not-found, never a 403 that confirms existence


def test_other_user_cannot_approve_or_execute(store):
    proposal = store.propose(OWNER, "create_folder", {"name": "X"})
    with pytest.raises(ProposalError) as exc:
        store.approve(OTHER_USER, proposal["id"], proposal["payload_hash"])
    assert exc.value.status_code == 404
    with pytest.raises(ProposalError):
        store.execute(OTHER_USER, proposal["id"])


def test_two_sessions_have_independent_proposal_lists(store):
    store.propose(OWNER, "create_folder", {"name": "Mine"})
    store.propose(OTHER_SESSION, "create_folder", {"name": "Theirs"})
    mine = store.list_proposals(OWNER)
    theirs = store.list_proposals(OTHER_SESSION)
    assert {p["preview"]["path_diff"][0]["to"] for p in mine} == {"Mine"}
    assert {p["preview"]["path_diff"][0]["to"] for p in theirs} == {"Theirs"}


def test_two_sessions_have_independent_audit_logs(store):
    a = store.propose(OWNER, "create_folder", {"name": "Mine"})
    store.propose(OTHER_SESSION, "create_folder", {"name": "Theirs"})
    audit_mine = store.audit_log(OWNER)
    assert all(row["proposal_id"] == a["id"] for row in audit_mine)


# --- collisions on proposal ids --------------------------------------------------


def test_proposing_the_same_payload_twice_yields_independent_proposals(store):
    first = store.propose(OWNER, "create_folder", {"name": "Dup"})
    second = store.propose(OWNER, "create_folder", {"name": "Dup"})
    assert first["id"] != second["id"]
    assert first["payload_hash"] == second["payload_hash"]
    store.reject(OWNER, first["id"])
    # Rejecting one must not affect the other's independent lifecycle.
    approved = store.approve(OWNER, second["id"], second["payload_hash"])
    assert approved["status"] == "approved"


# --- temp-dir-only mutations / no actual launches (structural check) -------------


def test_full_run_of_all_six_action_types_only_touches_the_approved_root(
    store, approved_root, launcher, stub_exe, tmp_path
):
    canary = tmp_path / "canary-outside-root.txt"
    canary.write_text("must remain untouched", encoding="utf-8")

    (approved_root / "seed.txt").write_text("seed", encoding="utf-8")

    folder_proposal = store.propose(OWNER, "create_folder", {"name": "NewDir"})
    approve_and_execute(store, OWNER, folder_proposal["id"], folder_proposal["payload_hash"])

    move_proposal = store.propose(
        OWNER, "move_file", {"source": "seed.txt", "destination": "NewDir/seed.txt"}
    )
    approve_and_execute(store, OWNER, move_proposal["id"], move_proposal["payload_hash"])

    app_proposal = store.propose(OWNER, "open_app", {"executable": stub_exe.name})
    approve_and_execute(store, OWNER, app_proposal["id"], app_proposal["payload_hash"])

    url_proposal = store.propose(OWNER, "open_url", {"url": "https://example.com/"})
    approve_and_execute(store, OWNER, url_proposal["id"], url_proposal["payload_hash"])

    clip_proposal = store.propose(OWNER, "set_clipboard", {"text": "hello"})
    approve_and_execute(store, OWNER, clip_proposal["id"], clip_proposal["payload_hash"])

    assert canary.read_text(encoding="utf-8") == "must remain untouched"
    assert (approved_root / "NewDir" / "seed.txt").exists()
    assert launcher.executed == [str(stub_exe)]
    assert launcher.opened_urls == ["https://example.com/"]
    assert launcher.clipboard_writes == ["hello"]


def test_no_action_ever_deletes_or_recurses(store, approved_root):
    # There is deliberately no "delete" action type in the registry at all.
    from alfred.actions import registry

    assert "delete" not in " ".join(registry.SPECS.keys()).lower()
    assert "remove" not in " ".join(registry.SPECS.keys()).lower()
