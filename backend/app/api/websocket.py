"""
WebSocket endpoint for realtime updates.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/folders")
async def websocket_endpoint(websocket: WebSocket):
    """
    WS /ws/folders

    Clients connect here to receive realtime notifications about
    folder creation, deletion, rename, and modification events.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Server pushes updates; we keep the connection alive.
            # If the client sends a message, acknowledge it (ping/pong).
            data = await websocket.receive_text()
            logger.debug("Received from WS client: %s", data)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        ws_manager.disconnect(websocket)
        logger.error("WebSocket error: %s", exc)
