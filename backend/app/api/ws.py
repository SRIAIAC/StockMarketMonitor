import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

_connections: list[WebSocket] = []
_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


@router.websocket("/ws/alerts")
async def alerts_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _connections.remove(websocket)


def broadcast_alert(alert: dict) -> None:
    """Thread-safe broadcast, callable from the (non-async) scheduler thread."""
    if _loop is None:
        return
    payload = json.dumps(alert)
    for ws in list(_connections):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, payload), _loop)


async def _safe_send(ws: WebSocket, payload: str) -> None:
    try:
        await ws.send_text(payload)
    except Exception:
        logger.debug("Dropping closed websocket connection")
