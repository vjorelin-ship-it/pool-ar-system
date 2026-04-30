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
        self._projector_preview_clients: Set[WebSocket] = set()

    async def connect_phone(self, ws: WebSocket) -> None:
        await ws.accept()
        self._phone_clients.add(ws)

    async def connect_projector(self, ws: WebSocket) -> None:
        await ws.accept()
        self._projector_clients.add(ws)

    async def connect_camera_preview(self, ws: WebSocket) -> None:
        await ws.accept()
        self._camera_preview_clients.add(ws)

    async def connect_projector_preview(self, ws: WebSocket) -> None:
        await ws.accept()
        self._projector_preview_clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._phone_clients.discard(ws)
        self._projector_clients.discard(ws)
        self._camera_preview_clients.discard(ws)
        self._projector_preview_clients.discard(ws)

    def has_projector_clients(self) -> bool:
        return len(self._projector_clients) > 0

    def has_camera_preview_clients(self) -> bool:
        return len(self._camera_preview_clients) > 0

    async def broadcast_pocket_event(self, pocket_event: dict) -> None:
        """Send pocket event to phone clients for live updates."""
        data = json.dumps({
            "type": "pocket_event",
            "data": pocket_event,
        })
        for ws in list(self._phone_clients):
            try:
                await ws.send_text(data)
            except Exception:
                self._phone_clients.discard(ws)

    async def broadcast_announce(self, text: str) -> None:
        """Send announcement text to projector (for TTS) and projector-preview clients."""
        data = json.dumps({
            "type": "announce",
            "text": text,
        })
        for ws in list(self._projector_clients):
            try:
                await ws.send_text(data)
            except Exception:
                self._projector_clients.discard(ws)
        for ws in list(self._projector_preview_clients):
            try:
                await ws.send_text(data)
            except Exception:
                self._projector_preview_clients.discard(ws)

    async def broadcast_table_state(self) -> None:
        data = json.dumps({
            "type": "table_state",
            "data": system_state["table_state"],
        })
        dead = set()
        for ws in list(self._phone_clients):
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
        for ws in list(self._projector_clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self._projector_clients -= dead
        # Also send to phone projector preview clients
        preview_dead = set()
        for ws in list(self._projector_preview_clients):
            try:
                await ws.send_text(data)
            except Exception:
                preview_dead.add(ws)
        self._projector_preview_clients -= preview_dead

    async def broadcast_camera_preview(self, image_data: str) -> None:
        data = json.dumps({
            "type": "camera_preview",
            "image": image_data,
        })
        dead = set()
        for ws in list(self._camera_preview_clients):
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
                "player1_balls": s.player1_balls,
                "player2_balls": s.player2_balls,
                "p1_remaining": s.p1_remaining,
                "p2_remaining": s.p2_remaining,
                "game_over": s.game_over,
                "winner": s.winner,
            },
        })
        for ws in list(self._phone_clients):
            try:
                await ws.send_text(data)
            except Exception:
                self._phone_clients.discard(ws)


    async def broadcast_shot_result(self, result: dict) -> None:
        """Send structured shot result to phone clients."""
        data = json.dumps({
            "type": "shot_result",
            "data": result,
        })
        for ws in list(self._phone_clients):
            try:
                await ws.send_text(data)
            except Exception:
                self._phone_clients.discard(ws)

    async def broadcast_drill_info(self, info: dict) -> None:
        """Send current drill info to phone clients."""
        data = json.dumps({
            "type": "drill_info",
            "data": info,
        })
        for ws in list(self._phone_clients):
            try:
                await ws.send_text(data)
            except Exception:
                self._phone_clients.discard(ws)

    # ─── Camera Upload (USB camera frames from Android box) ───

    async def connect_camera_upload(self, ws: WebSocket) -> None:
        await ws.accept()
        if not hasattr(self, '_camera_upload_clients'):
            self._camera_upload_clients = set()
        self._camera_upload_clients.add(ws)
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                    if data.get("type") == "camera_frame":
                        import base64
                        jpeg_bytes = base64.b64decode(data["data"])
                        ts = data.get("timestamp", 0.0)
                        cam = system_state.get("ws_camera")
                        if cam is not None:
                            cam.receive_frame(jpeg_bytes, ts)
                except Exception:
                    pass
        except WebSocketDisconnect:
            self._camera_upload_clients.discard(ws)


manager = ConnectionManager()
