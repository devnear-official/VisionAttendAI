"""Authenticated WebSocket routes for real-time attendance stream."""

import hmac
import hashlib
from typing import Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from app.core.config import get_settings
from app.core.events import event_manager
from app.utils.logger import logger

router = APIRouter(prefix="/ws", tags=["Real-Time WebSockets"])
settings = get_settings()

SESSION_SECRET = settings.__dict__.get("SESSION_SECRET") or "visionattend_local_dev_hmac_secret_key_9876543210123456"


def verify_ws_token(token: Optional[str]) -> bool:
    """Verifies token against ADMIN_API_KEY or signed session ticket."""
    if not token:
        return False

    # 1. Direct match with ADMIN_API_KEY
    if hmac.compare_digest(token, settings.ADMIN_API_KEY):
        return True

    # 2. Verify HMAC session token (format: payload.signature)
    parts = token.split(".")
    if len(parts) == 2:
        payload_str, signature = parts
        try:
            expected = hmac.new(
                SESSION_SECRET.encode("utf-8"),
                payload_str.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(signature, expected)
        except Exception:
            return False

    return False


@router.websocket("/attendance")
async def attendance_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Real-time attendance event stream.
    Requires token in query parameter (?token=...) or 'va_session' cookie.
    Broadcasts verified check-in events when recognized by edge cameras.
    """
    # Check query param first, then fallback to cookie
    auth_token = token or websocket.cookies.get("va_session")

    if not verify_ws_token(auth_token):
        logger.warning("Rejected unauthenticated WebSocket connection attempt.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await event_manager.connect(websocket)
    try:
        while True:
            # Keepalive listener (ignores client pings / heartbeat messages)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"event":"pong"}')
    except WebSocketDisconnect:
        event_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket connection encountered error: {e}")
        event_manager.disconnect(websocket)
