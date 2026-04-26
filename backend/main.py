import asyncio
import base64
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
from renderer.projector_renderer import ProjectorRenderer, ProjectionOverlay
from vision.table_detector import TableDetector


class PoolARSystem:
    def __init__(self):
        self.camera: Optional[RtspCamera] = None
        self.table_detector = TableDetector()
        self.physics = PhysicsEngine()
        self.match_mode = MatchMode()
        self.training_mode = TrainingMode()
        self.renderer = ProjectorRenderer()
        self._running = False
        self._vision_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_table_corners = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start(self) -> None:
        print("[System] Starting Pool AR System...")
        system_state["match_mode"] = self.match_mode
        system_state["training_mode"] = self.training_mode
        system_state["table_detector"] = self.table_detector
        system_state["calibration"] = {"active": False, "markers": []}

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

    def _process_camera_frame(self, frame) -> Optional[bytes]:
        """Detect table, warp perspective, crop, return JPEG bytes."""
        import cv2
        import numpy as np
        try:
            corners = self.table_detector.find_table(frame.data)
            if corners is not None:
                self._last_table_corners = corners
                warped = self.table_detector.warp(frame.data, corners)
                _, buf = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 70])
                return buf.tobytes()
        except Exception:
            pass
        return None

    def _do_calibration(self) -> None:
        """Run calibration: project markers, detect them in camera feed."""
        cal = system_state["calibration"]
        if not cal["active"]:
            return
        if not self.camera or not self.camera.is_running():
            return

        # Define markers at key positions (normalized coords)
        markers = [
            (0.1, 0.1), (0.5, 0.1), (0.9, 0.1),
            (0.1, 0.5), (0.5, 0.5), (0.9, 0.5),
            (0.1, 0.9), (0.5, 0.9), (0.9, 0.9),
        ]
        cal["markers"] = markers

        # Send calibration image to projector
        cal_b64 = self.renderer.render_calibration_to_base64(markers)
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast_projection(cal_b64), self._loop,
            )

        # Check alignment: detect table corners in camera feed
        frame = self.camera.get_frame()
        if frame and frame.valid and self._last_table_corners is not None:
            cal["table_detected"] = True
            cal["status"] = "Calibration image projected. Check alignment."
        else:
            cal["table_detected"] = False
            cal["status"] = "Waiting for camera..."

    def _vision_loop(self) -> None:
        while self._running:
            has_projector = self._loop and manager.has_projector_clients()
            has_preview = self._loop and manager.has_camera_preview_clients()

            # Process camera frame if needed
            if (has_preview or has_projector) and self.camera and self.camera.is_running():
                frame = self.camera.get_frame()
                if frame and frame.valid:
                    system_state["table_state"]["detected"] = True

                    # Camera preview for phone app (warped + cropped)
                    if has_preview:
                        jpeg_bytes = self._process_camera_frame(frame)
                        if jpeg_bytes:
                            b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
                            asyncio.run_coroutine_threadsafe(
                                manager.broadcast_camera_preview(b64), self._loop,
                            )

            # Check calibration mode
            if system_state["calibration"]["active"]:
                self._do_calibration()
                time.sleep(1.0)
                continue

            # Render projection image (route lines on dark bg)
            if has_projector:
                try:
                    overlay = None  # TODO: wire up physics engine output
                    image_b64 = self.renderer.render_to_base64(overlay)
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast_projection(image_b64), self._loop,
                    )
                except Exception:
                    pass
                time.sleep(0.5)
            else:
                time.sleep(0.1)

    @staticmethod
    def _get_local_ip() -> str:
        """Get the actual LAN IP address reliably."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return socket.gethostbyname(socket.gethostname())

    @staticmethod
    def start_discovery_service() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 8001))

        local_ip = PoolARSystem._get_local_ip()
        print(f"[Discovery] Service started on {local_ip}:8001")

        while True:
            try:
                data, addr = sock.recvfrom(256)
                if data.decode().startswith("POOL_AR_DISCOVER"):
                    response = f"POOL_AR_SERVER:{local_ip}"
                    sock.sendto(response.encode(), addr)
                    print(f"[Discovery] Responded to {addr} -> {local_ip}")
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


async def main() -> None:
    system = PoolARSystem()
    system.start()

    disc_thread = threading.Thread(
        target=PoolARSystem.start_discovery_service, daemon=True)
    disc_thread.start()

    system.set_loop(asyncio.get_running_loop())

    app = create_app(system)
    print(f"\n[Server] Starting API at http://0.0.0.0:{settings.API_PORT}")
    print("[Server] Scoreboard at http://<ip>:{}/scoreboard".format(
        settings.API_PORT))
    print("[Server] Phone app can now discover and connect\n")

    config = uvicorn.Config(app, host=settings.API_HOST,
                            port=settings.API_PORT)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
