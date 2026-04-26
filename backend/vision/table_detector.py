import cv2
import numpy as np
from dataclasses import dataclass


@dataclass
class TableRegion:
    corners: np.ndarray       # 4 corners in source image, shape (4,2)
    warped_size: tuple        # (width, height) of normalized table
    homography: np.ndarray    # perspective transform matrix
    inverse_homography: np.ndarray  # inverse transform


class TableDetector:
    def __init__(self, target_width: int = 800, target_height: int = 400):
        self._target_size = (target_width, target_height)

    def detect(self, frame: cv2.Mat) -> bool:
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100,
                                    minLineLength=100, maxLineGap=50)
            if lines is None or len(lines) < 4:
                return False
            return True
        except Exception:
            return False

    def find_table(self, frame: cv2.Mat) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False
        largest = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
        if len(approx) != 4:
            return False
        corners = approx.reshape(4, 2).astype(np.float32)
        corners = self._order_corners(corners)

        dst = np.array([
            [0, 0],
            [self._target_size[0] - 1, 0],
            [self._target_size[0] - 1, self._target_size[1] - 1],
            [0, self._target_size[1] - 1],
        ], dtype=np.float32)

        self._homography = cv2.getPerspectiveTransform(corners, dst)
        self._inverse_homography = cv2.getPerspectiveTransform(dst, corners)
        self._corners = corners
        return True

    def warp(self, frame: cv2.Mat) -> np.ndarray:
        if not hasattr(self, '_homography'):
            raise RuntimeError("Table not detected, call find_table first")
        return cv2.warpPerspective(frame, self._homography, self._target_size)

    def transform_points(self, points: np.ndarray, inverse: bool = False) -> np.ndarray:
        H = self._inverse_homography if inverse else self._homography
        pts = points.reshape(-1, 1, 2).astype(np.float32)
        transformed = cv2.perspectiveTransform(pts, H)
        return transformed.reshape(-1, 2)

    def get_table_region(self) -> TableRegion:
        return TableRegion(
            corners=self._corners,
            warped_size=self._target_size,
            homography=self._homography,
            inverse_homography=self._inverse_homography,
        )

    @staticmethod
    def _order_corners(pts: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # top-left
        rect[2] = pts[np.argmax(s)]   # bottom-right
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # top-right
        rect[3] = pts[np.argmax(diff)]  # bottom-left
        return rect
