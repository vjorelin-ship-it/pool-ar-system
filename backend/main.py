import sys
import os
import json
import socket
import threading
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from api.routes import router, system_state
from api.websocket import manager
from web.scoreboard_app import router as scoreboard_router
from camera.rtsp_camera import RtspCamera
from physics.engine import PhysicsEngine, Vec2
from game.match_mode import MatchMode
from game.training_mode import TrainingMode


class PoolARSystem:
    def __init__(self):
        self.camera: Optional[RtspCamera] = None
        self.physics = PhysicsEngine()
        self.match_mode = MatchMode()
        self.training_mode = TrainingMode()
        self._running = False
        self._vision_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        print("[System] Starting Pool AR System...")
        system_state["match_mode"] = self.match_mode
        system_state["training_mode"] = self.training_mode

        try:
            self.camera = RtspCamera(
                settings.CAMERA_RTSP_URL, settings.CAMERA_FPS)
            self.camera.start()
            print(f"[Camera] Connected to {settings.CAMERA_RTSP_URL}")
        except Exception as e:
            print(f"[Camera] Failed: {e}")
            print("[Camera] Running in offline mode (no camera)")

        self._running = True
        self._vision_thread = threading.Thread(
            target=self._vision_loop, daemon=True)
        self._vision_thread.start()
        print("[System] Started")

    def stop(self) -> None:
        self._running = False
        if self.camera:
            self.camera.stop()
        print("[System] Stopped")

    def _vision_loop(self) -> None:
        while self._running:
            if self.camera and self.camera.is_running():
                frame = self.camera.get_frame()
                if frame and frame.valid:
                    system_state["table_state"]["detected"] = True
            time.sleep(0.1)

    @staticmethod
    def start_discovery_service() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 8001))

        while True:
            try:
                data, addr = sock.recvfrom(256)
                if data.decode().startswith("POOL_AR_DISCOVER"):
                    hostname = socket.gethostbyname(socket.gethostname())
                    response = f"POOL_AR_SERVER:{hostname}"
                    sock.sendto(response.encode(), addr)
                    print(f"[Discovery] Responded to {addr}")
            except Exception:
                pass


def create_app(system: PoolARSystem) -> FastAPI:
    app = FastAPI(title="Pool AR System")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(scoreboard_router)

    return app


if __name__ == "__main__":
    system = PoolARSystem()
    system.start()

    disc_thread = threading.Thread(
        target=PoolARSystem.start_discovery_service, daemon=True)
    disc_thread.start()

    app = create_app(system)
    print(f"\n[Server] Starting API at http://0.0.0.0:{settings.API_PORT}")
    print("[Server] Scoreboard at http://<ip>:{}/scoreboard".format(
        settings.API_PORT))
    print("[Server] Phone app can now discover and connect\n")

    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
