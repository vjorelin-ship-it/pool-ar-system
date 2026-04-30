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
    def __init__(self, min_radius: int = 8, max_radius: int = 20):
        self._min_r = min_radius
        self._max_r = max_radius

    def detect(self, warped: cv2.Mat) -> List[Ball]:
        balls: List[Ball] = []
        h, w = warped.shape[:2]
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(warped, cv2.COLOR_BGR2HSV)

        # ── Cue ball: direct white blob detection ──
        cue_ball = self._detect_cue_by_blob(warped, gray, hsv)
        if cue_ball:
            balls.append(cue_ball)
        else:
            print("[BallDetect] No cue ball found")

        # ── Colored balls: HoughCircles with strict params ──
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_enh = clahe.apply(gray)
        circles = cv2.HoughCircles(
            gray_enh, cv2.HOUGH_GRADIENT, dp=1.2, minDist=20,
            param1=70, param2=24,
            minRadius=self._min_r, maxRadius=self._max_r,
        )

        if circles is not None:
            positions = [(float(c[0]), float(c[1])) for c in circles[0]]
            for i, (cx, cy, r) in enumerate(circles[0]):
                if cx < r + 5 or cx > w - r - 5 or cy < r + 5 or cy > h - r - 5:
                    continue
                # Skip if too close to cue ball
                if cue_ball:
                    dcx = cx / w - cue_ball.x
                    dcy = cy / h - cue_ball.y
                    if (dcx ** 2 + dcy ** 2) ** 0.5 < 0.05:
                        continue
                # Neighbor density filter — real balls can be near each other
                neighbors = sum(1 for j, (px, py) in enumerate(positions)
                                if i != j and ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 < 35)
                if neighbors > 3:
                    continue

                ball = self._classify_ball(
                    frame=warped, cx=int(cx), cy=int(cy), radius=int(r),
                    x=float(cx) / w, y=float(cy) / h, gray=gray_enh,
                )
                if ball:
                    balls.append(ball)

        if balls:
            cue = sum(1 for b in balls if b.is_cue)
            colored = len(balls) - cue
            if colored > 0:
                print(f"[BallDetect] Found {cue} cue + {colored} colored balls")
        return balls

    def _detect_cue_by_blob(self, frame: cv2.Mat, gray: cv2.Mat,
                            hsv: cv2.Mat) -> Optional[Ball]:
        """Detect cue ball as the brightest, most circular white blob."""
        h, w = frame.shape[:2]
        white_mask = cv2.inRange(hsv, np.array([0, 0, 150]),
                                 np.array([180, 40, 255]))

        # Use findContours for proper circularity measurement
        contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        EXPECTED_R = 16.0  # expected ball radius in 1600px-wide table (2K camera)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 350 or area > 2100:
                continue
            peri = cv2.arcLength(cnt, True)
            if peri < 1:
                continue
            # Circularity: 4*pi*area / perimeter^2 (1.0 = perfect circle)
            circularity = 4 * np.pi * area / (peri * peri)
            if circularity < 0.30:
                continue

            # Bounding box
            xb, yb, bw, bh = cv2.boundingRect(cnt)
            aspect = max(bw, bh) / (min(bw, bh) + 1e-6)
            if aspect > 1.6:
                continue

            cx = xb + bw / 2.0
            cy = yb + bh / 2.0
            radius = max(bw, bh) / 2.0

            if cx < radius + 5 or cx > w - radius - 5 or cy < radius + 5 or cy > h - radius - 5:
                continue

            # Mean HSV under the contour
            mask = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(mask, [cnt], -1, 255, -1)
            mean_v = float(cv2.mean(gray, mask)[0])
            mean_s = float(cv2.mean(hsv[:, :, 1], mask)[0])
            if mean_s > 30:
                continue

            # Score: circularity + close to expected size + brightness
            size_score = 1.0 - min(abs(radius - EXPECTED_R) / EXPECTED_R, 1.0)
            score = circularity * 0.4 + size_score * 0.35 + (mean_v / 255.0) * 0.25
            candidates.append((score, cx, cy, radius, circularity, mean_v))

        if not candidates:
            return None

        candidates.sort(reverse=True)
        best = candidates[0]
        score, cx, cy, radius, circ, v = best
        print(f"[BallDetect] Cue ball at ({cx/w:.3f},{cy/h:.3f}) r={radius:.0f} "
              f"circ={circ:.2f} V={v:.0f} (score={score:.3f}, {len(candidates)} candidates)")
        return Ball(x=float(cx) / w, y=float(cy) / h, radius=float(radius), color="white",
                    is_stripe=False, is_solid=False,
                    is_black=False, is_cue=True)

    @staticmethod
    def _create_ball_mask(frame: cv2.Mat, cx: int, cy: int, r: int) -> cv2.Mat:
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.circle(mask, (cx, cy), r, 255, -1)
        return mask

    def _classify_ball(self, frame: cv2.Mat, cx: int, cy: int, radius: int,
                       x: float, y: float, gray: Optional[cv2.Mat] = None) -> Optional[Ball]:
        """分类球：检测是否为白球/黑8，否则区分纯色/花色+识别颜色"""
        mask = self._create_ball_mask(frame, cx, cy, radius)
        ball_pixels = frame[mask > 0]
        if len(ball_pixels) < 10:
            return None

        avg_bgr = cv2.mean(frame, mask)[:3]

        # Edge strength check: real balls have clear circular edges
        if gray is not None:
            edge_strength = self._circle_edge_strength(gray, cx, cy, radius)
            if edge_strength < 8:
                return None

        # 用HSV检测白球和黑8（更抗偏色）
        hsv_ball = cv2.cvtColor(ball_pixels.reshape(1, -1, 3), cv2.COLOR_BGR2HSV)[0]
        mean_sat = float(np.mean(hsv_ball[:, 1]))
        mean_val = float(np.mean(hsv_ball[:, 2]))

        # 白球 (母球) — must be distinctively bright vs table cloth
        b, g, r = float(avg_bgr[0]), float(avg_bgr[1]), float(avg_bgr[2])
        # BGR channels close to each other (white/gray) and all above threshold
        is_near_white = (b > 150 and g > 150 and r > 150 and
                         max(b, g, r) - min(b, g, r) < 35)
        # Check local contrast: the ball should be brighter than the ring around it
        local_bright = self._local_brightness_ratio(frame, cx, cy, radius)
        if mean_sat < 30 and mean_val > 160 and is_near_white and local_bright > 1.25:
            return Ball(x=float(x), y=float(y), radius=float(radius), color="white",
                        is_stripe=False, is_solid=False,
                        is_black=False, is_cue=True)

        # 黑8 — very dark, low saturation, dark BGR
        is_dark_bgr = (b < 50 and g < 50 and r < 50)
        if mean_val < 50 and mean_sat < 80 and is_dark_bgr:
            return Ball(x=float(x), y=float(y), radius=float(radius), color="black",
                        is_stripe=False, is_solid=False,
                        is_black=True, is_cue=False)

        # Colored ball: must have noticeable saturation (not just cloth texture)
        if mean_sat < 45:
            return None

        # 识别基色（转换到HSV做颜色匹配，更符合人眼感知）
        hsv_mean = cv2.cvtColor(
            np.uint8([[avg_bgr]]), cv2.COLOR_BGR2HSV)[0][0]
        base_color = self._find_closest_color_hsv(hsv_mean)
        if not base_color:
            return None

        # 纯色/花色判定
        is_solid = self._is_solid_ball(frame, cx, cy, radius)

        return Ball(
            x=float(x), y=float(y), radius=float(radius), color=base_color,
            is_stripe=not is_solid,
            is_solid=is_solid,
            is_black=False, is_cue=False,
        )

    @staticmethod
    def _local_brightness_ratio(frame: cv2.Mat, cx: int, cy: int, r: int) -> float:
        """Ratio of ball brightness to surrounding ring brightness.
        A white ball should be >1.25x brighter than the cloth around it.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        inner_mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.circle(inner_mask, (cx, cy), r, 255, -1)
        outer_mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.circle(outer_mask, (cx, cy), r + 8, 255, -1)
        cv2.circle(outer_mask, (cx, cy), r + 2, 0, -1)
        inner_mean = cv2.mean(gray, inner_mask)[0]
        outer_mean = cv2.mean(gray, outer_mask)[0]
        if outer_mean < 1:
            return 1.0
        return float(inner_mean) / float(outer_mean)

    @staticmethod
    def _circle_edge_strength(gray: cv2.Mat, cx: int, cy: int, r: int) -> float:
        """Measure edge strength around the circle boundary."""
        h, w = gray.shape[:2]
        # Sample 16 points around the circle boundary
        angles = np.linspace(0, 2 * np.pi, 16, endpoint=False)
        strengths = []
        for a in angles:
            x1 = int(cx + r * np.cos(a))
            y1 = int(cy + r * np.sin(a))
            x2 = int(cx + (r + 3) * np.cos(a))
            y2 = int(cy + (r + 3) * np.sin(a))
            if 0 <= x1 < w and 0 <= y1 < h and 0 <= x2 < w and 0 <= y2 < h:
                strengths.append(abs(float(gray[y1, x1]) - float(gray[y2, x2])))
        if not strengths:
            return 0.0
        return float(np.median(strengths))

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
        h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
        # 低饱和度 → 灰白，不匹配任何彩色
        if s < 20 or v < 25:
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
        return best_name if best_score < 55 else None
