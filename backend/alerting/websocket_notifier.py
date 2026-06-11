"""
==========================================================
MetricGuard — WebSocket Notifier  (websocket_notifier.py)
==========================================================

Phase 14: Real-Time Alerting System
"""

import logging
from typing import List
from fastapi import WebSocket

logger = logging.getLogger("metricguard.alerting.websocket_notifier")


class ConnectionManager:
    """
    Manages active WebSocket connections for broadcasting alerts to dashboard clients.
    """

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept and track a new WebSocket connection.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("[WebSocket Manager] Client connected. Active clients: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Stop tracking a disconnected client.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("[WebSocket Manager] Client disconnected. Active clients: %d", len(self.active_connections))

    async def broadcast(self, payload: dict) -> None:
        """
        Send JSON payload to all active connections.
        Handles disconnects and cleanups automatically on communication errors.
        """
        if not self.active_connections:
            logger.debug("[WebSocket Manager] No active clients connected. Skipping broadcast.")
            return

        logger.info("[WebSocket Manager] Broadcasting alert event to %d clients...", len(self.active_connections))
        
        # Keep track of stale connections to clean up
        stale_connections: List[WebSocket] = []

        for connection in self.active_connections:
            try:
                await connection.send_json(payload)
            except Exception as e:
                logger.warning("[WebSocket Manager] Failed to send to socket. Client might be gone: %s", e)
                stale_connections.append(connection)

        # Cleanup stale connections
        for conn in stale_connections:
            self.disconnect(conn)


# Singleton manager instance
_manager_instance = ConnectionManager()


def get_websocket_manager() -> ConnectionManager:
    """
    Access the singleton WebSocket ConnectionManager.
    """
    return _manager_instance
