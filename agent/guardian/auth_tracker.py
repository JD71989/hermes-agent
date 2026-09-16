"""Authentication failure tracking with lockout.

Tracks failed authentication attempts per identity and enforces lockout
after a configurable threshold. Records all attempts (success and failure)
to the Guardian audit log.

Lockout policy:
- After ``max_failures`` consecutive failures, the identity is locked out
  for ``lockout_seconds``.
- A successful authentication resets the failure counter.
- Lockout state is process-local (resets on restart) — this is intentional
  for a personal agent; a persistent lockout store would be appropriate for
  a multi-tenant service.

Integration points:
- ``auth_tracker.record_auth_failure()`` should be called on any failed
  authentication (login, token validation, credential check).
- ``auth_tracker.record_auth_success()`` should be called on successful auth.
- ``auth_tracker.is_locked_out()`` should be called before processing an
  authentication attempt.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from agent.guardian.audit import AuditEvent, audit_log

logger = logging.getLogger(__name__)


@dataclass
class _FailureRecord:
    """Internal tracking for an identity's failure history."""

    count: int = 0
    locked_until: float = 0.0  # monotonic time when lockout expires
    last_failure_reason: Optional[str] = None


class AuthTracker:
    """Per-identity authentication failure tracking with lockout.

    Thread-safe. Process-local state (not persisted across restarts).
    """

    def __init__(
        self,
        max_failures: int = 5,
        lockout_seconds: float = 3600.0,  # 1 hour default
    ) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, _FailureRecord] = {}
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds

    def record_failure(
        self,
        identity: str,
        *,
        reason: Optional[str] = None,
        identity_type: str = "user",
        session_id: Optional[str] = None,
    ) -> None:
        """Record a failed authentication attempt.

        If the failure count reaches ``max_failures``, the identity is
        locked out for ``lockout_seconds``.
        """
        now = time.monotonic()
        with self._lock:
            record = self._records.get(identity)
            if record is None:
                record = _FailureRecord()
                self._records[identity] = record

            # If previously locked out and lockout has expired, reset.
            if record.locked_until > 0 and now >= record.locked_until:
                record.count = 0
                record.locked_until = 0.0

            record.count += 1
            record.last_failure_reason = reason

            # Engage lockout if threshold reached.
            if record.count >= self.max_failures and record.locked_until == 0:
                record.locked_until = now + self.lockout_seconds
                logger.warning(
                    "Auth lockout engaged for '%s' after %d failures "
                    "(lockout for %.0fs)",
                    identity, record.count, self.lockout_seconds,
                )
                audit_log(
                    AuditEvent.AUTH_LOCKOUT,
                    who=identity,
                    what=f"locked out after {record.count} failures",
                    why=reason,
                    result="blocked",
                    failure=f"lockout for {self.lockout_seconds}s",
                    identity_type=identity_type,
                    session_id=session_id,
                )

        # Always audit the failure.
        audit_log(
            AuditEvent.AUTH_FAILURE,
            who=identity,
            what=f"authentication failed ({record.count}/{self.max_failures})",
            why=reason,
            result="denied",
            failure=reason,
            identity_type=identity_type,
            session_id=session_id,
        )

    def record_success(
        self,
        identity: str,
        *,
        identity_type: str = "user",
        session_id: Optional[str] = None,
    ) -> None:
        """Record a successful authentication.

        Resets the failure counter. If the identity was locked out and the
        lockout has expired, clears the lockout.
        """
        with self._lock:
            record = self._records.get(identity)
            now = time.monotonic()
            was_locked = (
                record is not None
                and record.locked_until > 0
                and now < record.locked_until
            )
            if record is not None:
                record.count = 0
                record.locked_until = 0.0
                record.last_failure_reason = None

        if was_locked:
            audit_log(
                AuditEvent.AUTH_RECOVERY,
                who=identity,
                what="authentication succeeded after lockout",
                result="allowed",
                identity_type=identity_type,
                session_id=session_id,
            )
        else:
            audit_log(
                AuditEvent.AUTH_SUCCESS,
                who=identity,
                what="authentication succeeded",
                result="allowed",
                identity_type=identity_type,
                session_id=session_id,
            )

    def is_locked_out(self, identity: str) -> tuple[bool, Optional[float]]:
        """Check if an identity is currently locked out.

        Returns (locked: bool, remaining_seconds: Optional[float]).
        If not locked, remaining_seconds is None.
        """
        now = time.monotonic()
        with self._lock:
            record = self._records.get(identity)
            if record is None:
                return False, None
            if record.locked_until <= 0:
                return False, None
            if now >= record.locked_until:
                # Lockout expired — clear it.
                record.count = 0
                record.locked_until = 0.0
                return False, None
            remaining = record.locked_until - now
            return True, remaining

    def get_failure_count(self, identity: str) -> int:
        """Get the current failure count for an identity (not lockout-adjusted)."""
        with self._lock:
            record = self._records.get(identity)
            if record is None:
                return 0
            return record.count

    def reset(self, identity: str) -> None:
        """Reset an identity's failure tracking (admin override)."""
        with self._lock:
            self._records.pop(identity, None)

    def reset_all(self) -> None:
        """Reset all tracking (test isolation)."""
        with self._lock:
            self._records.clear()


# Module-level singleton with sensible defaults.
auth_tracker = AuthTracker()


def record_auth_failure(
    identity: str,
    *,
    reason: Optional[str] = None,
    identity_type: str = "user",
    session_id: Optional[str] = None,
) -> None:
    """Convenience function: record a failed authentication attempt."""
    auth_tracker.record_failure(
        identity,
        reason=reason,
        identity_type=identity_type,
        session_id=session_id,
    )


def record_auth_success(
    identity: str,
    *,
    identity_type: str = "user",
    session_id: Optional[str] = None,
) -> None:
    """Convenience function: record a successful authentication."""
    auth_tracker.record_success(
        identity,
        identity_type=identity_type,
        session_id=session_id,
    )


def is_locked_out(identity: str) -> tuple[bool, Optional[float]]:
    """Convenience function: check if an identity is locked out."""
    return auth_tracker.is_locked_out(identity)
