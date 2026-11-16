"""
test_spooler.py — Unit tests for offline alert spooler and network circuit breaker.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibvap.spooler import AlertSpooler, CircuitBreaker, CircuitState


def run_tests():
    passed = 0

    # 1. CircuitBreaker transitions
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.2, half_open_success_threshold=1)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_attempt() is True
    
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED, "One failure under threshold should stay CLOSED"
    
    cb.record_failure()
    assert cb.state == CircuitState.OPEN, "Two failures should trip to OPEN"
    assert cb.can_attempt() is False
    print("  PASS  circuit breaker trips to OPEN upon reaching consecutive failure threshold")
    passed += 1

    # 2. CircuitBreaker recovery to HALF_OPEN and CLOSED
    time.sleep(0.25)
    assert cb.state == CircuitState.HALF_OPEN, "Recovery timeout should transition to HALF_OPEN"
    assert cb.can_attempt() is True
    
    cb.record_success()
    assert cb.state == CircuitState.CLOSED, "Success in HALF_OPEN should reset to CLOSED"
    print("  PASS  circuit breaker transitions from HALF_OPEN to CLOSED upon successful trial")
    passed += 1

    # 3. Spooler Enqueue and stats
    spooler = AlertSpooler(":memory:")
    id1 = spooler.enqueue({"type": "loitering", "cam": "cam1"}, priority=3)
    id2 = spooler.enqueue({"type": "weapon_ready", "cam": "cam2"}, priority=1)
    
    stats = spooler.stats()
    assert stats["pending"] == 2
    assert stats["delivered"] == 0
    print("  PASS  alert spooler correctly enqueues records and reports pending counts")
    passed += 1

    # 4. Spooler drains in priority order (Critical priority 1 first)
    delivered_order = []

    def mock_sink(alert):
        delivered_order.append(alert["type"])
        return True

    deliv_count, fail_count = spooler.drain_batch(mock_sink)
    assert deliv_count == 2
    assert fail_count == 0
    assert delivered_order == ["weapon_ready", "loitering"], "Priority 1 must be delivered before Priority 3"
    
    stats2 = spooler.stats()
    assert stats2["pending"] == 0
    assert stats2["delivered"] == 2
    print("  PASS  alert spooler drains batch strictly according to tactical priority order")
    passed += 1

    # 5. Outage handling and circuit breaker trip
    cb_outage = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
    spooler_outage = AlertSpooler(":memory:", circuit_breaker=cb_outage)
    spooler_outage.enqueue({"type": "breach_1"}, priority=1)
    spooler_outage.enqueue({"type": "breach_2"}, priority=1)
    spooler_outage.enqueue({"type": "breach_3"}, priority=1)

    def failing_sink(alert):
        return False

    deliv_c, fail_c = spooler_outage.drain_batch(failing_sink, batch_size=10)
    assert deliv_c == 0
    assert fail_c == 2  # After 2 failures, circuit opened, so 3rd was not attempted
    assert cb_outage.state == CircuitState.OPEN
    print("  PASS  failing sink trips circuit breaker and halts batch draining early")
    passed += 1

    # 6. Max retry exhaustion
    spooler_exhaust = AlertSpooler(":memory:", circuit_breaker=CircuitBreaker(failure_threshold=100))
    spooler_exhaust.enqueue({"type": "corrupt_event"}, priority=1, max_retries=2)
    spooler_exhaust.drain_batch(failing_sink)
    stats_ex1 = spooler_exhaust.stats()
    assert stats_ex1["pending"] == 1
    
    spooler_exhaust.drain_batch(failing_sink)
    stats_ex2 = spooler_exhaust.stats()
    assert stats_ex2["pending"] == 0
    assert stats_ex2["exhausted"] == 1
    print("  PASS  events reaching max retries are safely marked exhausted")
    passed += 1

    print(f"\n{passed}/{passed} passed")


if __name__ == "__main__":
    run_tests()
