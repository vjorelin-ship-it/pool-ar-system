"""碰库检测模块 — 实时检测目标球碰库事件

用于自动执裁：
  - 开球时统计碰库球数（需要≥4颗或进球才合法）
  - 击球后判断是否有球碰库（无碰库+无进球=犯规）
"""

from typing import List, Set
from .ball_detector import Ball


# 库边边界阈值（标准化坐标，离边界多近算碰库）
CUSHION_THRESHOLD = 0.035  # ~ball_radius * 2 在标准化坐标系中

# 六个袋口区域（这些区域不算碰库）
POCKET_REGIONS = [
    (0.0, 0.0, 0.06, 0.06),       # 左上
    (0.47, 0.0, 0.53, 0.04),      # 上中
    (0.94, 0.0, 1.0, 0.06),       # 右上
    (0.0, 0.94, 0.06, 1.0),       # 左下
    (0.47, 0.96, 0.53, 1.0),      # 下中
    (0.94, 0.94, 1.0, 1.0),       # 右下
]


class CushionDetector:
    """碰库检测器"""

    def __init__(self):
        self._shot_hit_balls: Set[int] = set()  # 当前杆碰库的球ID集合
        self._break_cushion_count: int = 0
        self._prev_positions: List[tuple] = []  # 上一帧球位置
        self._shot_active: bool = False

    def new_shot(self) -> None:
        """新一杆开始，重置碰库计数"""
        self._shot_hit_balls.clear()
        self._break_cushion_count = 0
        self._shot_active = True

    def end_shot(self) -> None:
        """击球结束，锁定碰库状态"""
        self._shot_active = False

    def update(self, balls: List[Ball]) -> dict:
        """每帧更新，检测碰库事件。

        Returns:
            dict with:
              - cushion_hit: bool (当前帧是否有球碰库)
              - newly_hit: list of ball indices that just hit cushion
              - total_hit: int (本杆累计碰库球数)
              - break_count: int (开球碰库球数——仅在开球时使用)
        """
        newly_hit = []
        any_hit = False

        for i, b in enumerate(balls):
            if b.is_cue:
                continue  # 忽略母球（母球碰库不算开球碰库要求）
            near_cushion = self._is_near_cushion(b.x, b.y)
            if near_cushion and i not in self._shot_hit_balls:
                self._shot_hit_balls.add(i)
                newly_hit.append(i)
                any_hit = True

        if self._shot_active:
            self._break_cushion_count = max(
                self._break_cushion_count, len(self._shot_hit_balls))

        return {
            "cushion_hit": any_hit,
            "newly_hit": newly_hit,
            "total_hit": len(self._shot_hit_balls),
            "break_count": self._break_cushion_count,
        }

    def get_break_cushion_count(self) -> int:
        """获取开球碰库球数"""
        return self._break_cushion_count

    def has_any_cushion_hit(self) -> bool:
        """本杆是否有球碰库"""
        return len(self._shot_hit_balls) > 0

    def reset(self) -> None:
        """完全重置"""
        self._shot_hit_balls.clear()
        self._break_cushion_count = 0
        self._shot_active = False

    @staticmethod
    def _is_near_cushion(x: float, y: float) -> bool:
        """判断球是否靠近库边（排除袋口区域）"""
        # 检查是否在袋口区域
        for px1, py1, px2, py2 in POCKET_REGIONS:
            if px1 <= x <= px2 and py1 <= y <= py2:
                return False

        # 检查是否靠近四条库边
        near_top = y <= CUSHION_THRESHOLD
        near_bottom = y >= (1.0 - CUSHION_THRESHOLD)
        near_left = x <= CUSHION_THRESHOLD
        near_right = x >= (1.0 - CUSHION_THRESHOLD)

        return near_top or near_bottom or near_left or near_right
