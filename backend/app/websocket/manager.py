"""
WebSocket Connection Manager — tracks connected clients and
provides a simple broadcast mechanism for realtime updates.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for realtime folder updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        logger.info(
            "WebSocket client connected (total: %d)",
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            "WebSocket client disconnected (total: %d)",
            len(self.active_connections),
        )

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Send *message* to every connected client."""
        if not self.active_connections:
            return
        raw = json.dumps(message, default=str)
        dead: List[WebSocket] = []
        for ws in self.active_connections:
            try:
                await ws.send_text(raw)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_personal(self, websocket: WebSocket, message: Dict[str, Any]) -> None:
        raw = json.dumps(message, default=str)
        await websocket.send_text(raw)

    def broadcast_background(self, message: Dict[str, Any]) -> None:
        """
        Schedule a broadcast from any thread, including background
        threads that run outside the main event loop.

        Uses ``asyncio.run_coroutine_threadsafe`` so the coroutine is
        executed on the correct (main) event loop that owns the
        WebSocket connections.
        """
        if self._loop is None:
            logger.warning("Cannot broadcast: no event loop registered yet.")
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.broadcast(message), self._loop
            )
        except RuntimeError as exc:
            logger.warning("Broadcast scheduling failed: %s", exc)


ws_manager = ConnectionManager()
