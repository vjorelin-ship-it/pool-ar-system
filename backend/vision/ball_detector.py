import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple, Any


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

    def __init__(self, min_radius: int = 8, max_radius: int = 20,
                 stripe_white_threshold: int = 180):
        self._min_r = min_radius
        self._max_r = max_radius
        self._stripe_white_threshold = stripe_white_threshold

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
            ball = self._classify_ball(
                frame=warped, cx=int(cx), cy=int(cy), radius=int(r),
                x=cx / w, y=cy / h,
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

    def _classify_ball(self, frame: cv2.Mat, cx: int, cy: int, radius: int,
                       x: float, y: float) -> Optional[Ball]:
        """分类球：检测是否为白球/黑8，否则区分纯色/花色+识别颜色"""
        mask = self._create_ball_mask(frame, cx, cy, radius)
        ball_pixels = frame[mask > 0]
        if len(ball_pixels) < 10:
            return None

        avg_bgr = cv2.mean(frame, mask)[:3]

        # 用HSV检测白球和黑8（更抗偏色）
        hsv_ball = cv2.cvtColor(ball_pixels.reshape(1, -1, 3), cv2.COLOR_BGR2HSV)[0]
        mean_sat = np.mean(hsv_ball[:, 1])
        mean_val = np.mean(hsv_ball[:, 2])

        # 白球 (母球)
        if mean_sat < 35 and mean_val > 180:
            return Ball(x=x, y=y, radius=float(radius), color="white",
                        is_stripe=False, is_solid=False,
                        is_black=False, is_cue=True)

        # 黑8
        if mean_val < 40 and mean_sat < 80:
            return Ball(x=x, y=y, radius=float(radius), color="black",
                        is_stripe=False, is_solid=False,
                        is_black=True, is_cue=False)

        # 识别基色（转换到HSV做颜色匹配，更符合人眼感知）
        hsv_mean = cv2.cvtColor(
            np.uint8([[avg_bgr]]), cv2.COLOR_BGR2HSV)[0][0]
        base_color = self._find_closest_color_hsv(hsv_mean)
        if not base_color:
            return None

        # 纯色/花色判定
        is_solid = self._is_solid_ball(frame, cx, cy, radius)

        return Ball(
            x=x, y=y, radius=float(radius), color=base_color,
            is_stripe=not is_solid,
            is_solid=is_solid,
            is_black=False, is_cue=False,
        )

    def _is_solid_ball(self, frame: cv2.Mat, cx: int, cy: int,
                       r: int) -> bool:
        """通过像素分布分析判断纯色还是花色

        纯色球: 球面大部分被一种基色覆盖
        花色球: 球面有大量白色区域（顶部和底部白色条纹）
        使用圆形遮罩确保只分析球内像素，避免台面污染。
        """
        # 用圆形遮罩取球内像素
        mask = self._create_ball_mask(frame, cx, cy, int(r * 0.85))
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # 只分析遮罩内像素
        ball_pixels = hsv[mask > 0]

        if len(ball_pixels) < 10:
            return True  # 默认纯色

        saturation = ball_pixels[:, 1].astype(np.float32)
        value = ball_pixels[:, 2].astype(np.float32)

        # 统计白色像素（低饱和度 + 高亮度）
        white_mask_px = (saturation < 40) & (value > 150)
        white_ratio = np.mean(white_mask_px)

        # 花色球通常有大量白色区域（>30%）
        if white_ratio > 0.30:
            return False
        # 纯色球几乎全部被基色覆盖（白色区域<15%）
        elif white_ratio < 0.15:
            return True

        # 中间地带：分析球面上半vs下半的饱和度差异
        # 花色球下半部（彩色横带）饱和度高，上半部（白色）饱和度低
        h, w = frame.shape[:2]
        top_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.ellipse(top_mask, (cx, cy), (int(r*0.7), int(r*0.35)), 0, 180, 360, 255, -1)
        top_mask = top_mask & (mask > 0)

        bot_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.ellipse(bot_mask, (cx, cy), (int(r*0.7), int(r*0.35)), 0, 0, 180, 255, -1)
        bot_mask = bot_mask & (mask > 0)

        top_sat = np.mean(hsv[:, :, 1][top_mask > 0]) if np.any(top_mask > 0) else 0
        bot_sat = np.mean(hsv[:, :, 1][bot_mask > 0]) if np.any(bot_mask > 0) else 0

        # 下半部饱和度 > 上半部饱和度 + 15 → 花色（彩色横带在下方）
        # 上下饱和度接近 → 纯色（均匀覆盖）
        return bot_sat - top_sat < 15

    @staticmethod
    def _hsv_to_color_map() -> dict:
        """标准台球颜色在HSV空间中的近似值（Hue主导）"""
        return {
            "red":     (0,   200, 200),    # H≈0
            "orange":  (10,  200, 200),    # H≈10
            "yellow":  (30,  200, 200),    # H≈30
            "green":   (80,  150, 150),    # H≈80
            "blue":    (115, 200, 200),    # H≈115
            "purple":  (140, 150, 180),    # H≈140
            "brown":   (15,  100, 100),    # 暗橙
        }

    @staticmethod
    def _find_closest_color_hsv(hsv: Tuple) -> Optional[str]:
        """HSV空间颜色匹配（以色相H为主，饱和度和亮度为辅）"""
        h, s, v = hsv
        # 低饱和度 → 灰白，不匹配任何彩色
        if s < 30 or v < 30:
            return None
        best_name = None
        best_score = float("inf")
        for name, (th, ts, tv) in BallDetector._hsv_to_color_map().items():
            # Hue距离（处理环状0-180）
            dh = min(abs(h - th), 180 - abs(h - th))
            # 饱和度+亮度距离作为辅助
            ds = abs(s - ts) * 0.3
            dv = abs(v - tv) * 0.3
            score = dh + ds + dv
            if score < best_score:
                best_score = score
                best_name = name
        return best_name if best_score < 40 else None
