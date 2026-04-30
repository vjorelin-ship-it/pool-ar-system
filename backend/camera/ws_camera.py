"""WebSocket摄像头帧接收器 — 从安卓盒子WebSocket接收USB摄像头帧

接口与RtspCamera完全一致：start() / stop() / get_frame() / is_running()
"""
import threading
import time
import numpy as np
from typing import Optional
from dataclasses import dataclass


@dataclass
class Frame:
    data: Optional['cv2.Mat']  # numpy array (H, W, 3) BGR
    timestamp: float
    valid: bool


class WebSocketCamera:
    """从WebSocket接收摄像头帧"""

    def __init__(self):
        self._latest_frame: Optional[Frame] = None
        self._lock = threading.Lock()
        self._running = False
        self._frame_count = 0
        self._last_receive_time = 0.0

    def start(self) -> None:
        self._running = True
        self._frame_count = 0

    def stop(self) -> None:
        self._running = False
        with self._lock:
            self._latest_frame = None

    def get_frame(self) -> Optional[Frame]:
        with self._lock:
            return self._latest_frame

    def is_running(self) -> bool:
        return self._running

    def receive_frame(self, jpeg_bytes: bytes, timestamp: float) -> None:
        """由WebSocket handler在接收线程调用"""
        if not self._running:
            return
        import cv2
        data = cv2.imdecode(
            np.frombuffer(jpeg_bytes, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if data is None:
            return
        with self._lock:
            self._latest_frame = Frame(
                data=data,
                timestamp=timestamp,
                valid=True,
            )
            self._frame_count += 1
            self._last_receive_time = time.time()

    def stats(self) -> dict:
        with self._lock:
            return {
                "frame_count": self._frame_count,
                "last_receive": self._last_receive_time,
                "running": self._running,
            }
