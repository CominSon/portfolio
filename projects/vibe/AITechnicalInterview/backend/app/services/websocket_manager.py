import json
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    """In-memory room registry for MVP."""

    def __init__(self) -> None:
        self.rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, interview_id: str, websocket: WebSocket) -> None:
        """Добавить уже принятое соединение (accept вызывается в handler)."""
        self.rooms.setdefault(interview_id, []).append(websocket)

    def disconnect(self, interview_id: str, websocket: WebSocket) -> None:
        conns = self.rooms.get(interview_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self.rooms.pop(interview_id, None)

    async def broadcast(self, interview_id: str, message: dict[str, Any], exclude: WebSocket | None = None) -> None:
        payload = json.dumps(message, default=str)
        for ws in list(self.rooms.get(interview_id, [])):
            if ws is exclude:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(interview_id, ws)
