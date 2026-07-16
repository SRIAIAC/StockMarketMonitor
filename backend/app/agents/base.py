import datetime as dt
import logging
import threading

from app.db import SessionLocal

logger = logging.getLogger(__name__)

# In-process liveness tracking, keyed by agent name — the scheduler and the
# FastAPI app share one process (BackgroundScheduler runs in-process, not a
# separate worker), so a module-level dict is sufficient without a DB table.
# Some agents legitimately write zero new rows on a given run (e.g. no new
# corporate action published this cycle), so "last successful run" rather
# than "last DB write" is the honest liveness signal for /api/agents/status.
_last_run: dict[str, dt.datetime] = {}
_last_ok: dict[str, bool] = {}

# One lock per agent name, guarding against two overlapping executions of
# the *same* agent — e.g. a manual /api/refresh firing while that agent's
# own scheduled interval is also mid-run. Found live: both runs independently
# fetch the same item, neither sees the other's uncommitted insert (separate
# sessions), and the second commit dies with sqlite3.IntegrityError: UNIQUE
# constraint failed — which run_safe() then reports as a plain "failed"
# with no hint that overlap was the cause. Non-blocking: a second concurrent
# trigger skips cleanly rather than queueing (the next scheduled/orchestrator
# cycle will pick up whatever the in-progress run doesn't cover) or racing.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(name: str) -> threading.Lock:
    with _locks_guard:
        if name not in _locks:
            _locks[name] = threading.Lock()
        return _locks[name]


class BaseAgent:
    """Each agent fetches raw data, normalizes it, and stores it in the DB.

    Subclasses implement `run()`. Failures are logged and swallowed so one
    flaky source doesn't take down the scheduler.
    """

    name = "base"

    def run(self) -> None:
        raise NotImplementedError

    def run_safe(self) -> None:
        lock = _lock_for(self.name)
        if not lock.acquire(blocking=False):
            logger.info("Agent %s already running — skipping overlapping trigger", self.name)
            return
        try:
            self.run()
            _last_ok[self.name] = True
        except Exception:
            logger.exception("Agent %s failed", self.name)
            _last_ok[self.name] = False
        finally:
            _last_run[self.name] = dt.datetime.utcnow()
            lock.release()

    @staticmethod
    def session():
        return SessionLocal()


def agent_liveness(name: str, stale_after_minutes: int = 90) -> tuple[bool, dt.datetime | None]:
    """(active, last_run) for one agent name. `active` requires both a
    recent run and that run not having raised."""
    last_run = _last_run.get(name)
    if last_run is None:
        return False, None
    fresh = (dt.datetime.utcnow() - last_run) <= dt.timedelta(minutes=stale_after_minutes)
    return bool(_last_ok.get(name)) and fresh, last_run


def agent_last_ok(name: str) -> bool | None:
    """True if the agent's most recent run succeeded, False if it raised,
    None if it has never run at all in this process yet. Deliberately
    distinct from `agent_liveness()`: a slow-cadence agent (e.g. YouTube's
    3h interval) can go "stale" between runs without ever having failed —
    only an explicit False here means something actually broke and is
    worth OrchestratorAgent retrying, not just an agent that hasn't come
    back around to its own schedule yet."""
    return _last_ok.get(name)


def last_run_for(name: str) -> dt.datetime | None:
    """Raw last-run timestamp, no staleness judgment attached — used by
    scheduler.py's watchdog to detect *the scheduler itself* going silent
    (as opposed to agent_liveness()/agent_last_ok(), which judge one
    agent's own health assuming the scheduler is still ticking)."""
    return _last_run.get(name)
