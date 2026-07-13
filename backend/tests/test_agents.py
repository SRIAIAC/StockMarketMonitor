import datetime as dt
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import NewsItem, EconomicEvent, FiiDiiFlow, InstitutionalMention
from app.agents.news_agent import NewsAgent
from app.agents.econ_calendar_agent import EconCalendarAgent
from app.agents.fii_dii_agent import FiiDiiAgent


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    monkeypatch.setattr("app.agents.base.SessionLocal", TestSession)
    return TestSession


class FakeEntry(dict):
    """feedparser's real FeedParserDict supports both entry["x"] and
    entry.x — code under test relies on the latter (e.g. `entry.
    published_parsed`), so this fake needs to as well."""

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


def test_news_agent_skips_duplicate_urls(db_session, monkeypatch):
    fake_feed = type(
        "Feed",
        (),
        {
            "entries": [
                FakeEntry({"title": "AAPL surges on earnings", "link": "https://news.example/1", "published_parsed": None}),
            ]
        },
    )()
    monkeypatch.setattr("app.agents.news_agent.feedparser.parse", lambda url: fake_feed)
    monkeypatch.setattr("app.agents.news_agent.settings.watchlist", "AAPL", raising=False)

    agent = NewsAgent()
    agent.run()
    agent.run()  # second run should not duplicate

    session = db_session()
    count = session.query(NewsItem).count()
    session.close()
    # Same URL appears across all 3 configured feeds and across both runs;
    # the url-uniqueness check should dedupe down to a single stored row.
    assert count == 1


_FAKE_CALENDAR_HTML = """
<table id="calendar">
  <thead><tr><th colspan="3">Monday July 13 2026</th></tr></thead>
  <tr data-event="inflation rate yoy" data-category="Inflation Rate" data-symbol="INCPIINY">
    <td class="calendar-item"><a class="calendar-event" href="/india/inflation-cpi">Inflation Rate YoY</a>
      <span class="calendar-reference">JUN</span></td>
    <td><span id="actual"></span></td>
    <td><span id="previous">3.93%</span></td>
    <td><a id="consensus">4.3%</a></td>
    <td><a id="forecast">4.0%</a></td>
  </tr>
  <tr data-event="gdp growth rate" data-category="GDP Growth Rate" data-symbol="INDGDPQOQ">
    <td class="calendar-item"><a class="calendar-event" href="/india/gdp-growth">GDP Growth Rate</a>
      <span class="calendar-reference">Q1</span></td>
    <td><span id="actual">7.4%</span></td>
    <td><span id="previous">6.8%</span></td>
    <td><a id="consensus">7.0%</a></td>
    <td><a id="forecast">7.0%</a></td>
  </tr>
</table>
"""


class _FakeResponse:
    text = _FAKE_CALENDAR_HTML

    def raise_for_status(self):
        return None


def test_econ_agent_parses_and_upserts_india_calendar(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.agents.econ_calendar_agent.httpx.get",
        lambda *a, **k: _FakeResponse(),
    )

    agent = EconCalendarAgent()
    agent.run()
    agent.run()  # second run should upsert in place, not duplicate

    session = db_session()
    rows = session.query(EconomicEvent).order_by(EconomicEvent.series_id).all()
    session.close()

    assert len(rows) == 2
    gdp = next(r for r in rows if r.series_id == "INDGDPQOQ")
    assert gdp.value == 7.4
    assert gdp.detail == "Prev 6.8%"
    assert gdp.importance == "high"

    cpi = next(r for r in rows if r.series_id == "INCPIINY")
    # No actual print yet — falls back to the forecast value, detail shows
    # both previous and forecast since nothing has actually released.
    assert cpi.value == 4.0
    assert "Fcst 4.0%" in cpi.detail
    assert cpi.importance == "high"


_FAKE_FII_DII_PAYLOAD = [
    {"category": "DII", "date": "13-Jul-2026", "buyValue": "17393.46", "sellValue": "15221.76", "netValue": "2171.70"},
    {"category": "FII/FPI", "date": "13-Jul-2026", "buyValue": "10386.48", "sellValue": "13448.75", "netValue": "-3062.27"},
]


def test_fii_dii_agent_stores_flow_and_recent_mentions_only(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.agents.fii_dii_agent.nse_get",
        lambda path, params=None: _FAKE_FII_DII_PAYLOAD,
    )

    now = time.gmtime()
    old = time.gmtime((dt.datetime.utcnow() - dt.timedelta(days=120)).timestamp())

    fresh_mention = FakeEntry({
        "title": "Bharti Airtel sees FII stake increase this quarter",
        "link": "https://news.example/fii-airtel",
        "published_parsed": now,
    })
    stale_mention = FakeEntry({
        "title": "Bharti Airtel FII buying reported months ago",
        "link": "https://news.example/fii-airtel-old",
        "published_parsed": old,
    })
    no_company_mention = FakeEntry({
        "title": "Foreign investors eye Indian bonds broadly",
        "link": "https://news.example/no-company",
        "published_parsed": now,
    })
    fake_feed = type("Feed", (), {"entries": [fresh_mention, stale_mention, no_company_mention]})()
    monkeypatch.setattr("app.agents.fii_dii_agent.feedparser.parse", lambda url: fake_feed)

    agent = FiiDiiAgent()
    agent.run()
    agent.run()  # second run should not duplicate the flow row or the mention

    session = db_session()
    flows = session.query(FiiDiiFlow).all()
    mentions = session.query(InstitutionalMention).all()
    session.close()

    assert len(flows) == 1
    assert flows[0].fii_net_cr == -3062.27
    assert flows[0].dii_net_cr == 2171.70

    # Only the fresh, company-matched headline survives — the >90-day-old
    # one is filtered by the recency cutoff, and the no-mention one never
    # matches any watchlist company.
    assert len(mentions) == 1
    assert mentions[0].ticker == "BHARTIARTL.NS"
    assert mentions[0].url == "https://news.example/fii-airtel"
