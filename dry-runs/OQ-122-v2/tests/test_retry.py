"""Exercises the actual failure/backoff path of scripts/fetch_ecfr.py's
retry() helper - not just the happy path every real fetch_ecfr.py run so
far has taken (the eCFR API responded successfully both times it was
called during this build). A retry helper that has only ever been called
against something that immediately succeeds proves nothing about its
retry logic (FAILURE-CLASSES.md item 6): this simulates real transient and
permanent failures instead.

Run: python -m pytest tests/test_retry.py -v
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fetch_ecfr import retry  # noqa: E402


def test_retry_recovers_after_transient_failures():
    calls = []

    def flaky():
        calls.append(time.monotonic())
        if len(calls) < 3:
            raise ConnectionError("simulated transient network failure")
        return "success"

    result = retry(4, 0.05, flaky)
    assert result == "success"
    assert len(calls) == 3


def test_retry_backoff_doubles_between_attempts():
    calls = []

    def flaky():
        calls.append(time.monotonic())
        if len(calls) < 3:
            raise ConnectionError("simulated transient network failure")
        return "success"

    retry(4, 0.05, flaky)
    gap1 = calls[1] - calls[0]
    gap2 = calls[2] - calls[1]
    # generous scheduling slack; the point being checked is that gap2 is
    # roughly double gap1 (0.05s then 0.1s), not exact timing.
    assert 0.03 < gap1 < 0.3
    assert 0.07 < gap2 < 0.5
    assert gap2 > gap1


def test_retry_gives_up_after_max_attempts_and_raises():
    attempts = []

    def always_fails():
        attempts.append(1)
        raise ConnectionError("permanent failure")

    try:
        retry(3, 0.01, always_fails)
        assert False, "retry() should have raised after exhausting attempts"
    except ConnectionError:
        pass
    assert len(attempts) == 3


def test_retry_returns_immediately_on_first_success():
    calls = []

    def always_succeeds():
        calls.append(1)
        return 42

    assert retry(5, 10, always_succeeds) == 42
    assert len(calls) == 1  # must not sleep/retry when there's no failure
