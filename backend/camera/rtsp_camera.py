import cv2
import threading
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class Frame:
    data: Optional[cv2.Mat]
    timestamp: float
    valid: bool


class RtspCamera:
    def __init__(self, rtsp_url: str, fps: int = 10):
        self._url = rtsp_url
        self._target_interval = 1.0 / fps
        self._cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[Frame] = None
        self._running = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._cap = cv2.VideoCapture(self._url)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open RTSP stream: {self._url}")
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()

    def get_frame(self) -> Optional[Frame]:
        with self._lock:
            return self._latest_frame

    def is_running(self) -> bool:
        return self._running

    def _capture_loop(self) -> None:
        while self._running:
            loop_start = time.time()
            ret, frame = self._cap.read() if self._cap else (False, None)
            with self._lock:
                self._latest_frame = Frame(
                    data=frame if ret else None,
                    timestamp=time.time(),
                    valid=ret,
                )
            elapsed = time.time() - loop_start
            sleep_time = self._target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            elif not ret:
                time.sleep(1.0)  # wait before retry on failure
