import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from typing import Set
from .routes import system_state


class ConnectionManager:
    def __init__(self):
        self._phone_clients: Set[WebSocket] = set()
        self._projector_clients: Set[WebSocket] = set()
        self._camera_preview_clients: Set[WebSocket] = set()

    async def connect_phone(self, ws: WebSocket) -> None:
        await ws.accept()
        self._phone_clients.add(ws)

    async def connect_projector(self, ws: WebSocket) -> None:
        await ws.accept()
        self._projector_clients.add(ws)

    async def connect_camera_preview(self, ws: WebSocket) -> None:
        await ws.accept()
        self._camera_preview_clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._phone_clients.discard(ws)
        self._projector_clients.discard(ws)
        self._camera_preview_clients.discard(ws)

    def has_projector_clients(self) -> bool:
        return len(self._projector_clients) > 0

    def has_camera_preview_clients(self) -> bool:
        return len(self._camera_preview_clients) > 0

    async def broadcast_table_state(self) -> None:
        data = json.dumps({
            "type": "table_state",
            "data": system_state["table_state"],
        })
        dead = set()
        for ws in self._phone_clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self._phone_clients -= dead

    async def broadcast_projection(self, image_data: str) -> None:
        data = json.dumps({
            "type": "projection",
            "image": image_data,
        })
        dead = set()
        for ws in self._projector_clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self._projector_clients -= dead

    async def broadcast_camera_preview(self, image_data: str) -> None:
        data = json.dumps({
            "type": "camera_preview",
            "image": image_data,
        })
        dead = set()
        for ws in self._camera_preview_clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self._camera_preview_clients -= dead

    async def broadcast_score(self) -> None:
        mm = system_state.get("match_mode")
        if not mm:
            return
        s = mm.state
        data = json.dumps({
            "type": "score_update",
            "score": {
                "player1_score": s.player1_score,
                "player2_score": s.player2_score,
                "current_player": s.current_player,
                "game_over": s.game_over,
                "winner": s.winner,
            },
        })
        for ws in list(self._phone_clients):
            try:
                await ws.send_text(data)
            except Exception:
                self._phone_clients.discard(ws)


manager = ConnectionManager()
