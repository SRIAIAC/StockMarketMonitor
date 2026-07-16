import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.scheduler import start_scheduler, start_watchdog, trigger_immediate_refresh
from app.api import ws, routes_dashboard, routes_alerts, routes_chat, routes_market, routes_analytics, routes_agents
from app.api import web_data, analytics_data

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Stock Market Monitor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws.router)
app.include_router(routes_dashboard.router)
app.include_router(routes_alerts.router)
app.include_router(routes_chat.router)
app.include_router(routes_market.router)
app.include_router(routes_analytics.router)
app.include_router(routes_agents.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    ws.set_event_loop(asyncio.get_event_loop())
    start_scheduler()
    start_watchdog()
    # Immediately import today's data in the background — don't wait for first interval
    trigger_immediate_refresh()
    analytics_data.ensure_fresh()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/refresh")
def manual_refresh():
    """Trigger an immediate full data refresh (market prices, news, alerts)."""
    trigger_immediate_refresh()
    return {"status": "refresh started"}
