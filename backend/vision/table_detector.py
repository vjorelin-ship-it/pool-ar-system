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
    GREEN_LOWER = np.array([35, 30, 20])
    GREEN_UPPER = np.array([90, 255, 255])
    BLUE_LOWER = np.array([95, 30, 20])
    BLUE_UPPER = np.array([130, 255, 255])

    def __init__(self, target_width: int = 1600, target_height: int = 800):
        self._target_size = (target_width, target_height)

    def detect(self, frame: cv2.Mat) -> bool:
        """Quick check: enough lines in the frame to suggest a table exists."""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100,
                                    minLineLength=100, maxLineGap=50)
            return lines is not None and len(lines) >= 4
        except Exception:
            return False

    def find_table(self, frame: cv2.Mat) -> bool:
        """Find pool table corners using cloth color detection.

        Strategy order:
        1. HSV cloth color -> bounding box of largest non-edge blob
        2. Line intersection from HoughLines
        3. Fallback: best 4-corner contour from Canny edges
        """
        h, w = frame.shape[:2]
        min_area_pct = 0.03  # table must be at least 3% of frame

        # Strategy 1: Cloth color bounding box
        corners = self._find_by_cloth_color(frame, min_area_pct)
        if corners is not None:
            self._setup_homography(corners)
            return True

        # Strategy 2: Line-based estimation
        corners = self._find_by_lines(frame, min_area_pct)
        if corners is not None:
            self._setup_homography(corners)
            return True

        # Strategy 3: Edge contour
        corners = self._find_by_contours(frame, min_area_pct)
        if corners is not None:
            self._setup_homography(corners)
            return True

        return False

    def _find_by_cloth_color(self, frame: cv2.Mat, min_area_pct: float):
        """Find table by green/blue cloth bounding box."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, w = frame.shape[:2]
        margin = 10

        for lower, upper in [(self.GREEN_LOWER, self.GREEN_UPPER),
                             (self.BLUE_LOWER, self.BLUE_UPPER)]:
            mask = cv2.inRange(hsv, lower, upper)

            kernel_close = np.ones((25, 25), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)
            kernel_open = np.ones((11, 11), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue

            contours = sorted(contours, key=cv2.contourArea, reverse=True)

            for cnt in contours[:10]:
                area = cv2.contourArea(cnt)
                if area < (w * h) * min_area_pct:
                    continue

                x, y, cw, ch = cv2.boundingRect(cnt)
                if x <= margin or y <= margin or x + cw >= w - margin or y + ch >= h - margin:
                    continue

                # Use bounding box directly - the table is a rectangle
                corners = np.array([
                    [x, y], [x + cw, y],
                    [x + cw, y + ch], [x, y + ch]
                ], dtype=np.float32)
                return self._order_corners(corners)

        return None

    def _find_by_lines(self, frame: cv2.Mat, min_area_pct: float):
        """Estimate table boundary from HoughLines clusters."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)

        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 150,
                                minLineLength=200, maxLineGap=100)
        if lines is None or len(lines) < 4:
            return None

        h, w = frame.shape[:2]
        h_lines, v_lines = [], []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            if angle < 30 or angle > 150:
                h_lines.append(line[0])
            elif 60 < angle < 120:
                v_lines.append(line[0])

        if len(h_lines) < 2 or len(v_lines) < 2:
            return None

        h_centers = sorted([np.mean([l[1], l[3]]) for l in h_lines])
        v_centers = sorted([np.mean([l[0], l[2]]) for l in v_lines])

        top_y = int(np.median(h_centers[:3]))
        bot_y = int(np.median(h_centers[-3:]))
        left_x = int(np.median(v_centers[:3]))
        right_x = int(np.median(v_centers[-3:]))

        top_y = max(0, top_y)
        bot_y = min(h - 1, bot_y)
        left_x = max(0, left_x)
        right_x = min(w - 1, right_x)

        area = (right_x - left_x) * (bot_y - top_y)
        if area < (w * h) * min_area_pct:
            return None

        corners = np.array([
            [left_x, top_y], [right_x, top_y],
            [right_x, bot_y], [left_x, bot_y]
        ], dtype=np.float32)
        return corners

    def _find_by_contours(self, frame: cv2.Mat, min_area_pct: float):
        """Fallback: largest 4-corner contour from Canny edges."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        h, w = frame.shape[:2]
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        best_corners = None
        best_score = -1

        for c in contours[:10]:
            area = cv2.contourArea(c)
            if area < (w * h) * min_area_pct:
                continue
            peri = cv2.arcLength(c, True)
            for eps in [0.02, 0.05, 0.1]:
                approx = cv2.approxPolyDP(c, eps * peri, True)
                if len(approx) == 4:
                    corners = self._order_corners(
                        approx.reshape(4, 2).astype(np.float32))
                    w_est = np.linalg.norm(corners[1] - corners[0])
                    h_est = np.linalg.norm(corners[3] - corners[0])
                    ratio = max(w_est, h_est) / (min(w_est, h_est) + 1e-6)
                    score = area * (1.0 if 1.2 < ratio < 3.5 else 0.3)
                    if score > best_score:
                        best_score = score
                        best_corners = corners
                    break

        return best_corners

    def _setup_homography(self, corners: np.ndarray) -> None:
        dst = np.array([
            [0, 0],
            [self._target_size[0] - 1, 0],
            [self._target_size[0] - 1, self._target_size[1] - 1],
            [0, self._target_size[1] - 1],
        ], dtype=np.float32)
        self._homography = cv2.getPerspectiveTransform(corners, dst)
        self._inverse_homography = cv2.getPerspectiveTransform(dst, corners)
        self._corners = corners

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
