import cv2
import logging
import threading
import time
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._stop_event.is_set():
            return  # already started
        self._cap = cv2.VideoCapture(self._url)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open RTSP stream: {self._url}")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._cap:
            self._cap.release()
            self._cap = None

    def get_frame(self) -> Optional[Frame]:
        with self._lock:
            return self._latest_frame

    def is_running(self) -> bool:
        return not self._stop_event.is_set() and self._thread is not None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
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
            if not ret:
                logger.warning("RTSP read failed: %s", self._url)
                time.sleep(1.0)  # backoff on failure
            elif sleep_time > 0:
                time.sleep(sleep_time)
