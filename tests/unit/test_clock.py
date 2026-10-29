from datetime import datetime, timedelta, timezone

import pytest

from prism.adapters.system_clock import SystemClock
from prism.ports.clock import Clock
from tests.helpers.fake_clock import FakeClock


def test_system_clock_returns_timezone_aware_utc_time() -> None:
    clock = SystemClock()

    before = datetime.now(timezone.utc)
    actual = clock.now()
    after = datetime.now(timezone.utc)

    assert before <= actual <= after
    assert actual.tzinfo is not None
    assert actual.utcoffset() == timedelta(0)


def test_system_clock_implements_clock_interface() -> None:
    assert isinstance(SystemClock(), Clock)


def test_fake_clock_returns_initial_time() -> None:
    initial_time = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
    clock = FakeClock(initial_time)

    assert clock.now() == initial_time


def test_fake_clock_can_advance_time() -> None:
    initial_time = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
    clock = FakeClock(initial_time)

    clock.advance(300)

    assert clock.now() == initial_time + timedelta(seconds=300)


def test_fake_clock_rejects_naive_datetime() -> None:
    initial_time = datetime(2026, 10, 28, 10, 0)

    with pytest.raises(ValueError, match="timezone-aware"):
        FakeClock(initial_time)


def test_fake_clock_rejects_negative_time_advance() -> None:
    initial_time = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
    clock = FakeClock(initial_time)

    with pytest.raises(ValueError, match="cannot be negative"):
        clock.advance(-1)
