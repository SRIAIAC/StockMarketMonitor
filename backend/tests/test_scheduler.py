import datetime as dt

import pytest

from app import scheduler
from app.agents import base


@pytest.fixture(autouse=True)
def _clean_last_run():
    """`base._last_run` is a module-level dict shared across the process —
    isolate each test from whatever the others left in it."""
    base._last_run.clear()
    yield
    base._last_run.clear()


def test_watchdog_does_not_fire_when_agents_are_fresh(monkeypatch):
    triggered = []
    monkeypatch.setattr(scheduler, "trigger_immediate_refresh", lambda: triggered.append(True))

    for name in scheduler._CANARY_AGENTS:
        base._last_run[name] = dt.datetime.utcnow() - dt.timedelta(minutes=5)

    scheduler._watchdog_check()

    assert triggered == []


def test_watchdog_fires_when_every_canary_is_stale(monkeypatch):
    triggered = []
    monkeypatch.setattr(scheduler, "trigger_immediate_refresh", lambda: triggered.append(True))

    for name in scheduler._CANARY_AGENTS:
        base._last_run[name] = dt.datetime.utcnow() - dt.timedelta(minutes=61)

    scheduler._watchdog_check()

    assert triggered == [True]


def test_watchdog_does_not_fire_if_any_single_canary_is_recent(monkeypatch):
    """A stalled scheduler means *nothing* fires — one agent having run
    recently (e.g. via a manual /api/refresh or an orchestrator self-heal
    retry) is proof the scheduler is still alive, even if the others
    haven't come around to their own interval yet."""
    triggered = []
    monkeypatch.setattr(scheduler, "trigger_immediate_refresh", lambda: triggered.append(True))

    for name in scheduler._CANARY_AGENTS:
        base._last_run[name] = dt.datetime.utcnow() - dt.timedelta(minutes=61)
    base._last_run["alert"] = dt.datetime.utcnow() - dt.timedelta(minutes=2)

    scheduler._watchdog_check()

    assert triggered == []


def test_watchdog_does_not_fire_before_any_agent_has_ever_run(monkeypatch):
    """Fresh process startup, before trigger_immediate_refresh()'s own
    startup sweep has populated anything yet — must not false-positive."""
    triggered = []
    monkeypatch.setattr(scheduler, "trigger_immediate_refresh", lambda: triggered.append(True))

    scheduler._watchdog_check()

    assert triggered == []
