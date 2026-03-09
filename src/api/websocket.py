"""
WebSocket Routes — Real-time agent status and task progress streaming.

Provides live updates for the monitoring dashboard including
agent health, task progress, and cost tracking.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manage active WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@router.websocket("/agent-status")
async def agent_status_stream(websocket: WebSocket):
    """
    Stream real-time agent status updates to connected clients.

    Sends updates every 2 seconds with:
    - Agent health status
    - Active task count
    - Cost tracking
    - Latency metrics
    """
    await manager.connect(websocket)
    try:
        while True:
            # In production: read from supervisor.get_agent_status()
            supervisor = websocket.app.state.supervisor
            statuses = await supervisor.get_agent_status()

            await websocket.send_json({
                "type": "agent_status",
                "data": statuses,
            })

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.websocket("/task-progress/{session_id}")
async def task_progress_stream(websocket: WebSocket, session_id: str):
    """Stream task execution progress for a specific session."""
    await manager.connect(websocket)
    try:
        while True:
            # In production: subscribe to Redis stream for session events
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
