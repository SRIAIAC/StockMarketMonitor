import datetime as dt
import logging

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


class BaseAgent:
    """Each agent fetches raw data, normalizes it, and stores it in the DB.

    Subclasses implement `run()`. Failures are logged and swallowed so one
    flaky source doesn't take down the scheduler.
    """

    name = "base"

    def run(self) -> None:
        raise NotImplementedError

    def run_safe(self) -> None:
        try:
            self.run()
            _last_ok[self.name] = True
        except Exception:
            logger.exception("Agent %s failed", self.name)
            _last_ok[self.name] = False
        finally:
            _last_run[self.name] = dt.datetime.utcnow()

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
