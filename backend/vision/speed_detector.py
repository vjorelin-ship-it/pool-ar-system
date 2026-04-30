"""杆速检测模块

通过连续帧分析测量母球被击打后的初速度，反推出杆速。

原理:
  母球从静止到运动的第一帧(t0) →
  测量t0, t1, t2帧的位置变化 →
  位移/时间 = 母球初速度(m/s) →
  杆速 ≈ 母球初速度 × 1.2 (动量传递系数)
"""
from typing import List, Optional, Tuple
import time
from collections import deque


# 台球桌面物理尺寸(mm)
TABLE_WIDTH_MM = 2540
TABLE_HEIGHT_MM = 1270

# 杆速 = 母球初速度 × 动量系数 (经验值)
MOMENTUM_FACTOR = 1.2


class SpeedDetector:
    """杆速检测器

    通过跟踪母球的连续帧位置变化计算击球杆速。
    使用滑动窗口缓存母球历史位置，检测"静止→运动"的突变。
    """

    def __init__(self, window_size: int = 10,
                 motion_threshold: float = 0.003):
        """
        Args:
            window_size: 历史位置缓存帧数
            motion_threshold: 判定为运动的最小位移(归一化坐标)
        """
        self._window_size = window_size
        self._motion_threshold = motion_threshold
        self._history: deque = deque(maxlen=window_size)
        self._last_speed: float = 0.0
        self._was_moving = False
        self._stationary_frames = 0
        self._stationary_count = 0
        self._recording = False
        self._record_buffer: List[Tuple[float, float, float]] = []  # (x, y, t)

    def update(self, cue_ball_x: float, cue_ball_y: float) -> Optional[float]:
        """传入母球位置，返回杆速(m/s)，无击球时返回None

        需要在每帧传入母球位置，内部维护状态机。
        """
        now = time.time()
        self._history.append((cue_ball_x, cue_ball_y, now))

        if len(self._history) < 3:
            return None

        # 计算当前帧与上一帧的位移
        px, py, _ = self._history[-2]
        dx = cue_ball_x - px
        dy = cue_ball_y - py
        displacement = (dx ** 2 + dy ** 2) ** 0.5

        is_moving = displacement > self._motion_threshold

        # 状态机: 静止→运动→记录→静止
        if not self._was_moving and is_moving:
            # 检测到击球：母球从静止变运动
            self._recording = True
            self._record_buffer = [(cue_ball_x, cue_ball_y, now)]
            self._was_moving = True
            self._stationary_frames = 0
            self._stationary_count = 0

        elif self._was_moving and is_moving and self._recording:
            # 运动中：记录轨迹
            self._record_buffer.append((cue_ball_x, cue_ball_y, now))

        elif self._was_moving and not is_moving:
            # 运动结束：需要连续2帧静止才判定停止（避免检测抖动）
            self._stationary_count += 1
            if self._stationary_count >= 2:
                self._was_moving = False
                self._stationary_count = 0
                if self._recording and len(self._record_buffer) >= 2:
                    speed = self._compute_speed()
                    self._recording = False
                    self._last_speed = speed
                    return speed
                self._recording = False

        elif not self._was_moving and not is_moving:
            self._stationary_frames += 1

        return None

    def update_with_balls(self, balls: List) -> Optional[float]:
        """从球列表中提取母球位置并更新"""
        for b in balls:
            if hasattr(b, 'is_cue') and b.is_cue:
                return self.update(b.x, b.y)
            if isinstance(b, dict) and b.get('is_cue'):
                return self.update(b['x'], b['y'])
        return None

    def get_last_speed(self) -> float:
        """上次检测到的杆速(m/s)"""
        return self._last_speed

    def reset(self) -> None:
        """重置状态"""
        self._history.clear()
        self._record_buffer.clear()
        self._was_moving = False
        self._recording = False
        self._stationary_frames = 0
        self._stationary_count = 0

    def _compute_speed(self) -> float:
        """从记录缓冲计算母球初速度"""
        if len(self._record_buffer) < 2:
            return 0.0

        # 取前N帧计算平均速度
        n_samples = min(3, len(self._record_buffer))

        # 总位移
        x0, y0, t0 = self._record_buffer[0]
        xn, yn, tn = self._record_buffer[n_samples - 1]

        dx_norm = xn - x0
        dy_norm = yn - y0
        dt = tn - t0

        if dt <= 0:
            return 0.0

        # 归一化位移 → 实际毫米
        dx_mm = dx_norm * TABLE_WIDTH_MM
        dy_mm = dy_norm * TABLE_HEIGHT_MM
        dist_mm = (dx_mm ** 2 + dy_mm ** 2) ** 0.5

        # 母球速度 m/s
        cue_ball_speed = (dist_mm / 1000.0) / dt

        # 杆速 ≈ 母球初速度 × 动量传递系数
        cue_speed = cue_ball_speed * MOMENTUM_FACTOR

        return round(cue_speed, 2)
