"""Proposal lifecycle: propose -> approve -> execute -> immutable audit.

Every mutating/launching action is bound to an authenticated (user, session)
principal, carries an unguessable id, expires quickly, is approved once and
executed once, and revalidates its canonical payload hash before each transition.
Ownership is enforced on every read and write so no second client — even one
holding the shared token — can approve or execute another session's proposal.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..db import Database, iso_now, utc_now
from ..paths import PathError
from . import registry
from .executors import ActionError, DesktopLauncher


class ProposalError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class Principal:
    user_id: str
    session_id: str


class ProposalStore:
    def __init__(self, db: Database, settings: Settings, launcher: DesktopLauncher | None = None) -> None:
        self.db = db
        self.settings = settings
        self.launcher = launcher or DesktopLauncher()

    # -- lifecycle ---------------------------------------------------------

    def propose(self, principal: Principal, action_type: str, payload: dict) -> dict:
        self._maintenance()
        try:
            registry.get_spec(action_type)
        except KeyError as exc:
            raise ProposalError(404, f"unknown action type '{action_type}'") from exc
        try:
            model = registry.validate_payload(action_type, payload)
            preview = registry.build_preview(self.settings, action_type, model)
        except (ActionError, PathError) as exc:
            raise ProposalError(400, str(exc)) from exc

        canonical = registry.canonical_payload(action_type, model)
        digest = registry.payload_hash(canonical)
        proposal_id = secrets.token_urlsafe(32)
        created = utc_now()
        expires = created.timestamp() + self.settings.proposal_ttl_seconds
        from datetime import datetime, timezone

        expires_at = datetime.fromtimestamp(expires, tz=timezone.utc).isoformat()

        with closing(self.db.connect()) as connection:
            connection.execute(
                """
                INSERT INTO action_proposals
                (id, action_type, user_id, session_id, payload_json, payload_hash,
                 preview_json, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?)
                """,
                (
                    proposal_id,
                    action_type,
                    principal.user_id,
                    principal.session_id,
                    json.dumps(model.model_dump(mode="json"), sort_keys=True),
                    digest,
                    json.dumps(preview, sort_keys=True),
                    created.isoformat(),
                    expires_at,
                ),
            )
            connection.commit()
        self._audit(principal, proposal_id, action_type, "proposed", {"preview": preview})
        return self._view(
            {
                "id": proposal_id,
                "action_type": action_type,
                "status": "proposed",
                "preview_json": json.dumps(preview),
                "payload_hash": digest,
                "created_at": created.isoformat(),
                "expires_at": expires_at,
                "approved_at": None,
                "executed_at": None,
                "result_json": None,
            }
        )

    def approve(self, principal: Principal, proposal_id: str, expected_hash: str) -> dict:
        row = self._owned_row(principal, proposal_id)
        if row["status"] == "executed":
            raise ProposalError(409, "proposal already executed")
        if row["status"] == "approved":
            raise ProposalError(409, "proposal already approved")
        if row["status"] != "proposed":
            raise ProposalError(409, f"proposal cannot be approved from status '{row['status']}'")
        self._verify_integrity(row)
        if not secrets.compare_digest(str(expected_hash), row["payload_hash"]):
            raise ProposalError(409, "payload hash mismatch; approval refers to different content")

        approved_at = iso_now()
        updated = self._execute_write_with_audit(
            "UPDATE action_proposals SET status = 'approved', approved_at = ? "
            "WHERE id = ? AND status = 'proposed'",
            (approved_at, proposal_id),
            principal,
            proposal_id,
            row["action_type"],
            "approved",
            {},
        )
        if updated != 1:
            raise ProposalError(409, "proposal was already decided")
        return self.get(principal, proposal_id)

    def execute(self, principal: Principal, proposal_id: str) -> dict:
        row = self._owned_row(principal, proposal_id)
        if row["status"] == "executed":
            raise ProposalError(409, "proposal already executed")
        if row["status"] != "approved":
            raise ProposalError(409, f"proposal must be approved before execution (status '{row['status']}')")
        self._verify_integrity(row)

        spec = registry.get_spec(row["action_type"])
        if spec.desktop and not self.settings.desktop_actions_enabled:
            self._audit(principal, proposal_id, row["action_type"], "execution_blocked", {})
            raise ProposalError(403, "desktop actions are disabled in this configuration")
        if spec.requires_clipboard and not self.settings.clipboard_enabled:
            raise ProposalError(403, "clipboard actions are disabled in this configuration")

        model = spec.model.model_validate(json.loads(row["payload_json"]))
        try:
            current_preview = registry.build_preview(self.settings, row["action_type"], model)
        except (ActionError, PathError, OSError) as exc:
            raise ProposalError(409, f"execution conditions changed; create a new preview: {exc}") from exc
        stored_preview = json.loads(row["preview_json"])
        if not secrets.compare_digest(
            _effect_fingerprint(current_preview),
            _effect_fingerprint(stored_preview),
        ):
            raise ProposalError(409, "execution effects changed after preview; create a new proposal")

        claimed = self._execute_write(
            "UPDATE action_proposals SET status = 'executing' "
            "WHERE id = ? AND status = 'approved'",
            (proposal_id,),
        )
        if claimed != 1:
            raise ProposalError(409, "proposal was already claimed for execution")

        try:
            result = registry.execute_action(self.settings, row["action_type"], model, self.launcher)
        except (ActionError, PathError, OSError) as exc:
            detail = str(exc)
            self._execute_write(
                "UPDATE action_proposals SET status = 'failed' WHERE id = ? AND status = 'executing'",
                (proposal_id,),
            )
            self._audit(principal, proposal_id, row["action_type"], "execution_failed", {"error": detail})
            raise ProposalError(409, f"execution failed and the proposal is now spent: {detail}") from exc

        executed_at = iso_now()
        result_json = json.dumps(result, sort_keys=True)
        updated = self._execute_write(
            "UPDATE action_proposals SET status = 'executed', executed_at = ?, result_json = ? "
            "WHERE id = ? AND status = 'executing'",
            (executed_at, result_json, proposal_id),
        )
        if updated != 1:
            raise ProposalError(409, "proposal was already executed")
        self._audit(principal, proposal_id, row["action_type"], "executed", {"result": result})
        return self.get(principal, proposal_id)

    def reject(self, principal: Principal, proposal_id: str) -> dict:
        row = self._owned_row(principal, proposal_id)
        if row["status"] in {"executed", "failed"}:
            raise ProposalError(409, f"proposal cannot be rejected from status '{row['status']}'")
        updated = self._execute_write_with_audit(
            "UPDATE action_proposals SET status = 'rejected' WHERE id = ? AND status IN "
            "('proposed', 'approved')",
            (proposal_id,),
            principal,
            proposal_id,
            row["action_type"],
            "rejected",
            {},
        )
        if updated != 1:
            raise ProposalError(409, "proposal was already decided")
        return self.get(principal, proposal_id)

    # -- reads -------------------------------------------------------------

    def get(self, principal: Principal, proposal_id: str) -> dict:
        row = self._owned_row(principal, proposal_id)
        return self._view(row)

    def list_proposals(self, principal: Principal, *, limit: int = 50) -> list[dict]:
        self._maintenance()
        with closing(self.db.connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM action_proposals WHERE user_id = ? AND session_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (principal.user_id, principal.session_id, limit),
            ).fetchall()
        return [self._view(row) for row in rows]

    def audit_log(self, principal: Principal, *, limit: int = 100) -> list[dict]:
        with closing(self.db.connect()) as connection:
            rows = connection.execute(
                "SELECT proposal_id, action_type, event, detail_json, created_at "
                "FROM action_audit WHERE user_id = ? AND session_id = ? "
                "ORDER BY id ASC LIMIT ?",
                (principal.user_id, principal.session_id, limit),
            ).fetchall()
        return [
            {
                "proposal_id": row["proposal_id"],
                "action_type": row["action_type"],
                "event": row["event"],
                "detail": json.loads(row["detail_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # -- internals ---------------------------------------------------------

    def _owned_row(self, principal: Principal, proposal_id: str) -> Any:
        with closing(self.db.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM action_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
        if row is None:
            raise ProposalError(404, "proposal not found")
        # Ownership check with constant-time comparison to avoid leaking which
        # part (user vs session) mismatched.
        owner_ok = secrets.compare_digest(row["user_id"], principal.user_id) & secrets.compare_digest(
            row["session_id"], principal.session_id
        )
        if not owner_ok:
            raise ProposalError(404, "proposal not found")
        row = self._expire_if_needed(row)
        return row

    def _expire_if_needed(self, row: Any) -> Any:
        if row["status"] in {"proposed", "approved"} and row["expires_at"] < iso_now():
            # Rowcount-checked so that two concurrent readers racing an expiry
            # only produce a single "expired" audit entry, not one each.
            claimed = self._execute_write(
                "UPDATE action_proposals SET status = 'expired' WHERE id = ? AND status IN "
                "('proposed', 'approved')",
                (row["id"],),
            )
            if claimed == 1:
                self._audit(
                    Principal(row["user_id"], row["session_id"]),
                    row["id"],
                    row["action_type"],
                    "expired",
                    {},
                )
            with closing(self.db.connect()) as connection:
                row = connection.execute(
                    "SELECT * FROM action_proposals WHERE id = ?", (row["id"],)
                ).fetchone()
        if row["status"] == "expired":
            raise ProposalError(409, "proposal has expired")
        return row

    def _verify_integrity(self, row: Any) -> None:
        spec = registry.get_spec(row["action_type"])
        model = spec.model.model_validate(json.loads(row["payload_json"]))
        canonical = registry.canonical_payload(row["action_type"], model)
        digest = registry.payload_hash(canonical)
        if not secrets.compare_digest(digest, row["payload_hash"]):
            raise ProposalError(409, "stored payload failed integrity verification (tampering)")

    def _execute_write(self, sql: str, params: tuple) -> int:
        """Run one state-transition UPDATE and return its rowcount.

        A rowcount of 0 means another concurrent request already won the race
        (the WHERE clause's prior-status guard no longer matched); callers use
        this to detect and reject the loser side atomically. A locked database
        (possible under heavy concurrent contention despite the busy timeout)
        is translated into a retryable conflict instead of an unhandled crash.
        """

        try:
            with closing(self.db.connect()) as connection:
                rowcount = connection.execute(sql, params).rowcount
                connection.commit()
                return rowcount
        except sqlite3.OperationalError as exc:
            raise ProposalError(409, f"proposal store is temporarily busy; please retry ({exc})") from exc

    def _execute_write_with_audit(
        self,
        sql: str,
        params: tuple,
        principal: Principal,
        proposal_id: str,
        action_type: str,
        event: str,
        detail: dict,
    ) -> int:
        """Commit a state transition and its audit event in one transaction."""

        try:
            with closing(self.db.connect()) as connection:
                rowcount = connection.execute(sql, params).rowcount
                if rowcount == 1:
                    self._insert_audit(
                        connection,
                        principal,
                        proposal_id,
                        action_type,
                        event,
                        detail,
                    )
                connection.commit()
                return rowcount
        except sqlite3.OperationalError as exc:
            raise ProposalError(409, f"proposal store is temporarily busy; please retry ({exc})") from exc

    def _audit(
        self, principal: Principal, proposal_id: str, action_type: str, event: str, detail: dict
    ) -> None:
        with closing(self.db.connect()) as connection:
            self._insert_audit(
                connection,
                principal,
                proposal_id,
                action_type,
                event,
                detail,
            )
            connection.commit()

    @staticmethod
    def _insert_audit(
        connection: sqlite3.Connection,
        principal: Principal,
        proposal_id: str,
        action_type: str,
        event: str,
        detail: dict,
    ) -> None:
        connection.execute(
            "INSERT INTO action_audit (proposal_id, action_type, user_id, session_id, event, "
            "detail_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                proposal_id,
                action_type,
                principal.user_id,
                principal.session_id,
                event,
                json.dumps(detail, sort_keys=True),
                iso_now(),
            ),
        )

    def _maintenance(self) -> None:
        self.db.purge_expired_and_old(self.settings.audit_retention_days)

    def _view(self, row: Any) -> dict:
        preview = json.loads(row["preview_json"]) if row["preview_json"] else {}
        result = json.loads(row["result_json"]) if row["result_json"] else None
        spec = registry.SPECS.get(row["action_type"])
        return {
            "id": row["id"],
            "action_type": row["action_type"],
            "status": row["status"],
            "preview": preview,
            "payload_hash": row["payload_hash"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "approved_at": row["approved_at"] if _has_key(row, "approved_at") else None,
            "executed_at": row["executed_at"] if _has_key(row, "executed_at") else None,
            "result": result,
            "execution_enabled": registry.execution_enabled(self.settings, spec) if spec else False,
        }


def _has_key(row: Any, key: str) -> bool:
    try:
        return key in row.keys()
    except AttributeError:
        return True


def _effect_fingerprint(preview: dict) -> str:
    effect = {
        key: preview.get(key)
        for key in (
            "effects",
            "path_diff",
            "manifest",
            "conflicts",
            "planned_bytes",
            "target",
            "character_count",
        )
        if key in preview
    }
    canonical = json.dumps(effect, sort_keys=True, separators=(",", ":"))
    return registry.payload_hash(canonical)
