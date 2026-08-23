import json
from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket


class ConnectionManager:
    """
    Tracks active WebSocket connections per show_id ("room"). Feature 4 (seat
    hold) and Feature 6 (waitlist) call broadcast_seat_update() whenever a
    ShowSeat's status changes, so every connected client's seat map updates
    live without polling.
    """

    def __init__(self):
        self._rooms: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, show_id: str, websocket: WebSocket):
        await websocket.accept()
        self._rooms[show_id].add(websocket)

    def disconnect(self, show_id: str, websocket: WebSocket):
        self._rooms[show_id].discard(websocket)
        if not self._rooms[show_id]:
            del self._rooms[show_id]

    async def broadcast_seat_update(self, show_id: str, seats: list[dict]):
        """seats: [{"seat_id": str, "status": "available"|"held"|"booked"}, ...]"""
        payload = json.dumps({"type": "seat:update", "seats": seats})
        dead = []
        for ws in self._rooms.get(show_id, set()):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._rooms[show_id].discard(ws)


manager = ConnectionManager()
