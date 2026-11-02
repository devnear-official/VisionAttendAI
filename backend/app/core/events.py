"""Real-time attendance event broadcasting using in-memory WebSockets."""

import json
from typing import List
from fastapi import WebSocket
from app.utils.logger import logger


class AttendanceEventManager:
    """Manages active authenticated WebSocket connections and broadcasts attendance events."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Active listeners: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Active listeners: {len(self.active_connections)}")

    async def broadcast_attendance_event(self, event_data: dict):
        """
        Broadcast an attendance event to all connected dashboard clients.
        Ensures dead connections are safely pruned without crashing the event loop.
        """
        if not self.active_connections:
            return

        message = json.dumps(event_data)
        dead_connections = []

        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket client: {e}")
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)


# Global event manager instance
event_manager = AttendanceEventManager()
