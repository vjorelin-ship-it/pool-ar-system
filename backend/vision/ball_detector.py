import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Ball:
    x: float          # normalized 0-1
    y: float          # normalized 0-1
    radius: float     # pixels in warped space
    color: str        # white, black, red, blue, yellow, etc.
    is_stripe: bool   # True if stripe (花色)
    is_solid: bool    # True if solid (纯色)
    is_black: bool    # True if 8-ball
    is_cue: bool      # True if cue ball

    def position(self) -> Tuple[float, float]:
        return (self.x, self.y)


class BallDetector:
    # Pure color (solid) balls in Chinese 8-ball
    SOLID_COLORS_BGR: dict = {
        "yellow": (0, 200, 200),
        "blue": (200, 0, 0),
        "red": (0, 0, 200),
        "purple": (128, 0, 128),
        "orange": (0, 100, 200),
        "green": (0, 128, 0),
        "brown": (0, 50, 100),
    }

    STRIPE_COLORS_BGR: dict = {
        "yellow": (0, 200, 200),
        "blue": (200, 0, 0),
        "red": (0, 0, 200),
        "purple": (128, 0, 128),
        "orange": (0, 100, 200),
        "green": (0, 128, 0),
        "brown": (0, 50, 100),
    }

    def __init__(self, min_radius: int = 8, max_radius: int = 20):
        self._min_r = min_radius
        self._max_r = max_radius

    def detect(self, warped: cv2.Mat) -> List[Ball]:
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
            param1=100, param2=25,
            minRadius=self._min_r, maxRadius=self._max_r,
        )

        balls: List[Ball] = []
        if circles is None:
            return balls

        h, w = warped.shape[:2]
        for (cx, cy, r) in circles[0]:
            # Get ball color from center pixel
            mask = self._create_ball_mask(warped, int(cx), int(cy), int(r))
            avg_color = cv2.mean(warped, mask)[:3]

            ball = self._classify_ball(
                x=cx / w, y=cy / h,
                radius=r,
                avg_color=avg_color,
            )
            if ball:
                balls.append(ball)

        return balls

    def detect_cue_ball(self, warped: cv2.Mat) -> Optional[Ball]:
        balls = self.detect(warped)
        for b in balls:
            if b.is_cue:
                return b
        return None

    @staticmethod
    def _create_ball_mask(frame: cv2.Mat, cx: int, cy: int, r: int) -> cv2.Mat:
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.circle(mask, (cx, cy), r, 255, -1)
        return mask

    def _classify_ball(self, x: float, y: float, radius: float,
                       avg_color: Tuple[float, ...]) -> Optional[Ball]:
        b, g, r = avg_color
        # White ball
        if all(c > 200 for c in (r, g, b)):
            return Ball(x=x, y=y, radius=radius, color="white",
                        is_stripe=False, is_solid=False,
                        is_black=False, is_cue=True)
        # Black ball
        if all(c < 50 for c in (r, g, b)):
            return Ball(x=x, y=y, radius=radius, color="black",
                        is_stripe=False, is_solid=False,
                        is_black=True, is_cue=False)
        # Classify solids
        best_color = self._find_closest_color(avg_color)
        if best_color:
            return Ball(x=x, y=y, radius=radius, color=best_color,
                        is_stripe=False, is_solid=True,
                        is_black=False, is_cue=False)
        return None

    @staticmethod
    def _find_closest_color(avg_color: Tuple[float, ...]) -> Optional[str]:
        color_map: dict = {
            "yellow": (0, 200, 200),
            "blue": (200, 0, 0),
            "red": (0, 0, 200),
            "purple": (128, 0, 128),
            "orange": (0, 100, 200),
            "green": (0, 128, 0),
            "brown": (0, 50, 100),
        }
        best_name = None
        best_dist = float("inf")
        b, g, r = avg_color
        for name, (cb, cg, cr) in color_map.items():
            dist = (b - cb) ** 2 + (g - cg) ** 2 + (r - cr) ** 2
            if dist < best_dist:
                best_dist = dist
                best_name = name
        return best_name if best_dist < 15000 else None
