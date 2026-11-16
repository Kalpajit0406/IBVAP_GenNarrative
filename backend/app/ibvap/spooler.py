"""
spooler.py — Resilient offline alert spooler with circuit breaker for border backhaul outages.

Ensures zero event loss during satellite/cellular link degradation or total blackout.
Enqueued alerts are persisted in SQLite (WAL mode) and drained in priority order
(Critical priority 1 before nominal events) once connectivity is restored.
Includes an adaptive circuit breaker preventing egress thread starvation or server pounding.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("ibvap.spooler")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"         # Normal operation; forward allowed
    OPEN = "OPEN"             # Tripped; blocking forward attempts
    HALF_OPEN = "HALF_OPEN"   # Probing recovery with limited trials


class CircuitBreaker:
    """Three-state circuit breaker with configurable backoff timeout."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 5.0,
        half_open_success_threshold: int = 2,
    ):
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout = max(0.1, recovery_timeout)
        self.half_open_success_threshold = max(1, half_open_success_threshold)

        self._state: CircuitState = CircuitState.CLOSED
        self._consecutive_failures: int = 0
        self._consecutive_successes: int = 0
        self._last_state_change: float = time.monotonic()
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        now = time.monotonic()
        if self._state == CircuitState.OPEN:
            if (now - self._last_failure_time) >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    def can_attempt(self) -> bool:
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        now = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.half_open_success_threshold:
                self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._last_failure_time = time.monotonic()
        self._consecutive_successes = 0
        self._consecutive_failures += 1

        if self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
            if self._consecutive_failures >= self.failure_threshold or self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        logger.info("Circuit breaker transition: %s -> %s", self._state.value, new_state.value)
        self._state = new_state
        self._last_state_change = time.monotonic()
        if new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0
            self._consecutive_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._consecutive_successes = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
            "recovery_timeout_s": self.recovery_timeout,
        }


class AlertSpooler:
    """Disk-backed SQLite alert spooler with priority ordering and circuit breaking."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        circuit_breaker: Optional[CircuitBreaker] = None,
        keep_history: bool = True,
    ):
        self.db_path = str(db_path)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.keep_history = keep_history
        self._shared_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:")
            self._shared_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        p = Path(self.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_spool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id TEXT UNIQUE NOT NULL,
                    timestamp REAL NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 2,
                    payload TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 10,
                    status TEXT NOT NULL DEFAULT 'pending',
                    last_error TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_spool_status_prio ON alert_spool(status, priority, timestamp);")

    def enqueue(self, alert: Dict[str, Any], priority: int = 2, max_retries: int = 10) -> str:
        alert_id = alert.get("alert_id") or f"alt_{uuid.uuid4().hex[:12]}"
        now = time.time()
        payload_json = json.dumps(alert)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO alert_spool (alert_id, timestamp, priority, payload, retry_count, max_retries, status)
                VALUES (?, ?, ?, ?, 0, ?, 'pending');
                """,
                (alert_id, now, priority, payload_json, max_retries),
            )
        return alert_id

    def drain_batch(
        self,
        forward_fn: Callable[[Dict[str, Any]], bool],
        batch_size: int = 50,
    ) -> Tuple[int, int]:
        """Tries to forward spooled alerts. Returns (delivered_count, failed_count)."""
        if not self.circuit_breaker.can_attempt():
            return 0, 0

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, alert_id, payload, retry_count, max_retries
                FROM alert_spool
                WHERE status = 'pending'
                ORDER BY priority ASC, timestamp ASC
                LIMIT ?;
                """,
                (batch_size,),
            )
            rows = cursor.fetchall()

        if not rows:
            return 0, 0

        delivered = 0
        failed = 0

        for row in rows:
            if not self.circuit_breaker.can_attempt():
                break

            record_id = row["id"]
            retry_count = row["retry_count"]
            max_retries = row["max_retries"]
            
            try:
                payload = json.loads(row["payload"])
                success = forward_fn(payload)
            except Exception as exc:
                success = False
                error_msg = str(exc)
            else:
                error_msg = "Forwarding returned False"

            with self._get_connection() as conn:
                if success:
                    delivered += 1
                    self.circuit_breaker.record_success()
                    if self.keep_history:
                        conn.execute(
                            "UPDATE alert_spool SET status = 'delivered' WHERE id = ?;",
                            (record_id,),
                        )
                    else:
                        conn.execute("DELETE FROM alert_spool WHERE id = ?;", (record_id,))
                else:
                    failed += 1
                    self.circuit_breaker.record_failure()
                    new_retry = retry_count + 1
                    new_status = "exhausted" if new_retry >= max_retries else "pending"
                    conn.execute(
                        """
                        UPDATE alert_spool
                        SET retry_count = ?, status = ?, last_error = ?
                        WHERE id = ?;
                        """,
                        (new_retry, new_status, error_msg, record_id),
                    )

        return delivered, failed

    def stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
                    SUM(CASE WHEN status = 'exhausted' THEN 1 ELSE 0 END) as exhausted,
                    COUNT(*) as total
                FROM alert_spool;
                """
            )
            row = cursor.fetchone()
            
        return {
            "total": row["total"] or 0,
            "pending": row["pending"] or 0,
            "delivered": row["delivered"] or 0,
            "exhausted": row["exhausted"] or 0,
            "circuit": self.circuit_breaker.to_dict(),
        }

    def clear(self) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM alert_spool;")
