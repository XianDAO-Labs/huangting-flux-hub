"""
app/core/websocket_manager.py
==============================
WebSocket connection manager for real-time signal broadcasting.
Manages all connected clients and broadcasts live network events.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages all active WebSocket connections.
    Broadcasts live network signals to all connected clients.
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, event: dict):
        """Broadcast a JSON event to all connected clients."""
        if not self.active_connections:
            return

        message = json.dumps(event, default=str)
        dead_connections = set()

        async with self._lock:
            connections = set(self.active_connections)

        for websocket in connections:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.add(websocket)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                self.active_connections -= dead_connections

    async def broadcast_signal(self, signal_data: dict):
        """Broadcast a new network signal event."""
        event = {
            "event_type": "signal",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **signal_data
        }
        await self.broadcast(event)

    async def broadcast_stats_update(self, stats: dict):
        """Broadcast updated network statistics."""
        event = {
            "event_type": "stats_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **stats
        }
        await self.broadcast(event)

    async def send_heartbeat(self, websocket: WebSocket):
        """Send a heartbeat to a specific client."""
        try:
            await websocket.send_json({
                "event_type": "heartbeat",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception:
            await self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


# Global singleton instance
ws_manager = ConnectionManager()
