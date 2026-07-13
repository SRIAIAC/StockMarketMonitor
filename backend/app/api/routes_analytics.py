import threading
from fastapi import APIRouter
from app.api import analytics_data

router = APIRouter(prefix="/api/analytics")


@router.get("/mutual-funds")
def get_mutual_funds():
    data = analytics_data.get("mutual_funds") or []
    grouped: dict[str, list] = {}
    for fund in data:
        cat = fund["category"]
        grouped.setdefault(cat, []).append(fund)
    return grouped


@router.get("/gold")
def get_gold():
    return analytics_data.get("gold")


@router.get("/fd-rates")
def get_fd_rates():
    rates = analytics_data.get("fd_rates") or []
    return sorted(rates, key=lambda x: x["max_rate"], reverse=True)


@router.get("/ipos")
def get_ipos():
    return analytics_data.get("ipos") or []


@router.get("/gov-bonds")
def get_gov_bonds():
    return analytics_data.get("gov_bonds") or []


@router.get("/commodities")
def get_commodities():
    analytics_data.wait_for_fresh()
    return analytics_data.get("commodities") or []


@router.get("/currencies")
def get_currencies():
    analytics_data.wait_for_fresh()
    return analytics_data.get("currencies") or []


@router.post("/refresh")
def trigger_refresh():
    threading.Thread(target=analytics_data._do_refresh, daemon=True, name="analytics-manual-refresh").start()
    return {"status": "refresh started"}


@router.get("/status")
def get_status():
    """Return the analytics cached refresh timestamp for frontend polling."""
    return {"refreshed_at": analytics_data.get("refreshed_at")}
