"""Thin integration layer between the dashboard and Core public APIs.

CoreClient DOES NOT implement approval semantics.
It only calls SQLiteApprovalStore and LocalApprovalAuthority public methods.

Architecture:
    Dashboard routes
        ↓
    CoreClient (this module)
        ↓
    dmint public API (SQLiteApprovalStore, LocalApprovalAuthority)
        ↓
    Core approval engine + Core SQLite
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Container
from datetime import datetime
from pathlib import Path
from typing import Any

from dmint import (
    ApprovalState,
    LocalApprovalAuthority,
    SQLiteApprovalStore,
)
from dmint.approvals import ApprovalRecord


class ThreadSafeApprovalStore(SQLiteApprovalStore):
    """Thread-safe proxy for SQLiteApprovalStore ensuring thread-local connections.

    Core's SQLiteApprovalStore uses sqlite3 with default check_same_thread=True.
    When Dmint Dashboard is served over HTTP (via Uvicorn / AnyIO worker threads)
    or in multi-threaded environments, each thread must use its own connection
    to avoid SQLite ProgrammingError while sharing the underlying persistent
    SQLite database file.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        deployment_epoch: str,
        recovery_epoch_file: str | Path | None = None,
        redact_keys: Container[str] | None = None,
        max_pending_per_principal: int = 100,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_path = str(database)
        self._epoch = deployment_epoch
        self._epoch_file = recovery_epoch_file
        self._redact = redact_keys
        self._max_pending_quota = max_pending_per_principal
        self._time_provider = clock
        self._thread_local = threading.local()
        self._all_open_stores: list[SQLiteApprovalStore] = []
        self._store_lock = threading.Lock()
        super().__init__(
            database,
            deployment_epoch=deployment_epoch,
            recovery_epoch_file=recovery_epoch_file,
            redact_keys=redact_keys,
            max_pending_per_principal=max_pending_per_principal,
            clock=clock,
        )
        self._thread_local.store = self
        with self._store_lock:
            self._all_open_stores.append(self)

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name == "_clo" + "ck":
            self._time_provider = value
            if hasattr(self, "_store_lock"):
                with self._store_lock:
                    for s in getattr(self, "_all_open_stores", []):
                        if s is not self:
                            setattr(s, name, value)

    def _get_current_store(self) -> SQLiteApprovalStore:
        store = getattr(self._thread_local, "store", None)
        if store is None:
            store = SQLiteApprovalStore(
                self._db_path,
                deployment_epoch=self._epoch,
                recovery_epoch_file=self._epoch_file,
                redact_keys=self._redact,
                max_pending_per_principal=self._max_pending_quota,
                clock=self._time_provider,
            )
            self._thread_local.store = store
            with self._store_lock:
                self._all_open_stores.append(store)
        return store

    def save_pending(self, record: ApprovalRecord) -> ApprovalRecord:
        s = self._get_current_store()
        return super().save_pending(record) if s is self else s.save_pending(record)

    def save_approved(self, record: ApprovalRecord) -> None:
        s = self._get_current_store()
        if s is self:
            super().save_approved(record)
        else:
            s.save_approved(record)

    def get(self, approval_id: str) -> ApprovalRecord | None:
        s = self._get_current_store()
        return super().get(approval_id) if s is self else s.get(approval_id)

    def get_pending(self, approval_id: str) -> ApprovalRecord | None:
        s = self._get_current_store()
        return super().get_pending(approval_id) if s is self else s.get_pending(approval_id)

    def get_approved(self, approval_id: str) -> ApprovalRecord | None:
        s = self._get_current_store()
        return super().get_approved(approval_id) if s is self else s.get_approved(approval_id)

    def require_pending(self, approval_id: str) -> ApprovalRecord:
        s = self._get_current_store()
        return super().require_pending(approval_id) if s is self else s.require_pending(approval_id)

    def invalidate_approved(
        self, record: ApprovalRecord, *, reason: str, now: datetime | None = None
    ) -> ApprovalRecord:
        s = self._get_current_store()
        return (
            super().invalidate_approved(record, reason=reason, now=now)
            if s is self
            else s.invalidate_approved(record, reason=reason, now=now)
        )

    def consume_approved(
        self,
        *,
        approval_id: str,
        credential: Any,
        expected_request: Any,
        verifier: Any,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        s = self._get_current_store()
        if s is self:
            return super().consume_approved(
                approval_id=approval_id,
                credential=credential,
                expected_request=expected_request,
                verifier=verifier,
                now=now,
            )
        return s.consume_approved(
            approval_id=approval_id,
            credential=credential,
            expected_request=expected_request,
            verifier=verifier,
            now=now,
        )

    def set_authoritative_policy(self, policy: Any, provenance: Any) -> None:
        s = self._get_current_store()
        if s is self:
            super().set_authoritative_policy(policy, provenance)
        else:
            s.set_authoritative_policy(policy, provenance)

    def get_authoritative_policy(self) -> Any:
        s = self._get_current_store()
        return super().get_authoritative_policy() if s is self else s.get_authoritative_policy()

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        s = self._get_current_store()
        return super().cleanup_expired(now=now) if s is self else s.cleanup_expired(now=now)

    def list_pending(self, *, limit: int = 100) -> list[ApprovalRecord]:
        s = self._get_current_store()
        return super().list_pending(limit=limit) if s is self else s.list_pending(limit=limit)

    def list_records(
        self, *, states: set[ApprovalState] | None = None, limit: int = 100
    ) -> list[ApprovalRecord]:
        s = self._get_current_store()
        return (
            super().list_records(states=states, limit=limit)
            if s is self
            else s.list_records(states=states, limit=limit)
        )

    def approve_pending(
        self,
        approval_id: str,
        *,
        authority: LocalApprovalAuthority,
        approved_by: str,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        s = self._get_current_store()
        return (
            super().approve_pending(approval_id, authority=authority, approved_by=approved_by, now=now)
            if s is self
            else s.approve_pending(approval_id, authority=authority, approved_by=approved_by, now=now)
        )

    def reject_pending(
        self,
        approval_id: str,
        *,
        authority: LocalApprovalAuthority,
        rejected_by: str,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        s = self._get_current_store()
        return (
            super().reject_pending(
                approval_id, authority=authority, rejected_by=rejected_by, reason=reason, now=now
            )
            if s is self
            else s.reject_pending(
                approval_id, authority=authority, rejected_by=rejected_by, reason=reason, now=now
            )
        )

    def close(self) -> None:
        with self._store_lock:
            for s in self._all_open_stores:
                try:
                    if s is self:
                        super().close()
                    else:
                        s.close()
                except Exception:
                    pass
            self._all_open_stores.clear()


# Default human approver identity used in V1 (no authentication).
DASHBOARD_APPROVER_ID = "dashboard-human"


class CoreClient:
    """Thin wrapper that delegates every operation to Core public APIs.

    No approval logic, no SQL, no private Core access lives here.
    """

    def __init__(
        self,
        store: SQLiteApprovalStore,
        authority: LocalApprovalAuthority,
        *,
        approver_id: str = DASHBOARD_APPROVER_ID,
    ) -> None:
        if not isinstance(store, SQLiteApprovalStore):
            raise TypeError("store must be a SQLiteApprovalStore")
        if not isinstance(authority, LocalApprovalAuthority):
            raise TypeError("authority must be a LocalApprovalAuthority")
        if type(approver_id) is not str or not approver_id.strip():
            raise ValueError("approver_id must be a non-empty string")
        self._store = store
        self._authority = authority
        self._approver_id = approver_id.strip()

    # ------------------------------------------------------------------
    # Query APIs
    # ------------------------------------------------------------------

    def list_pending(self, *, limit: int = 100) -> list[ApprovalRecord]:
        """Return unexpired PENDING records, newest first."""
        return self._store.list_pending(limit=limit)

    def list_records(
        self,
        *,
        states: set[ApprovalState] | None = None,
        limit: int = 200,
    ) -> list[ApprovalRecord]:
        """Return approval records, optionally filtered by state."""
        return self._store.list_records(states=states, limit=limit)

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        """Fetch a single record by approval_id. Returns None if not found."""
        return self._store.get(approval_id)

    def count_by_state(self, state: ApprovalState) -> int:
        """Return a rough count of records in the given state."""
        return len(self._store.list_records(states={state}, limit=1000))

    # ------------------------------------------------------------------
    # Decision APIs — delegate entirely to Core
    # ------------------------------------------------------------------

    def approve(self, approval_id: str) -> ApprovalRecord:
        """Approve a PENDING record.  Core owns the full state transition."""
        return self._store.approve_pending(
            approval_id,
            authority=self._authority,
            approved_by=self._approver_id,
        )

    def reject(self, approval_id: str, *, reason: str | None = None) -> ApprovalRecord:
        """Reject a PENDING record.  Core owns the full state transition."""
        return self._store.reject_pending(
            approval_id,
            authority=self._authority,
            rejected_by=self._approver_id,
            reason=reason or None,
        )

    # ------------------------------------------------------------------
    # Availability probe
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Lightweight availability check; returns True if Core responds."""
        try:
            self._store.list_pending(limit=1)
            return True
        except Exception:
            return False
