"""进袋检测模块

基于连续帧对比检测进球事件。
使用多帧确认机制避免误报（球被短暂遮挡等）。
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set, Dict
import time
from collections import defaultdict


# 六袋口归一化坐标（中式八球标准位置）
# 四角袋口在角落，中间袋口在长边中点稍偏
POCKETS: List[Tuple[float, float]] = [
    (0.015, 0.015),     # 左上角
    (0.50, 0.010),      # 上中（稍偏上）
    (0.985, 0.015),     # 右上角
    (0.015, 0.985),     # 左下角
    (0.50, 0.990),      # 下中（稍偏下）
    (0.985, 0.985),     # 右下角
]

# 袋口检测半径（归一化坐标）
POCKET_RADIUS_NORM: float = 0.040


@dataclass
class BallState:
    """单颗球在某一帧的状态"""
    x: float; y: float; ball_id: int
    color: str; is_stripe: bool; is_solid: bool
    is_black: bool; is_cue: bool; confidence: float


@dataclass
class PocketEvent:
    """进球事件"""
    ball_id: int; color: str; is_stripe: bool; is_solid: bool
    is_black: bool; is_cue: bool
    pocket_pos: Tuple[float, float]; timestamp: float


class PocketDetector:
    """进袋检测器

    策略：
      1. 每帧传入当前检测到的所有球
      2. 与追踪列表中的球做最近邻匹配（距离+颜色辅助）
      3. 未匹配到的球 → 在袋口附近 → 累计miss帧计数
      4. 连续多帧确认后才判定进球（防止遮挡误报）
      5. 追踪列表独立于当前帧，球消失后仍保留计数
    """

    def __init__(self, match_distance: float = 0.025,
                 confirm_frames: int = 2):
        """
        Args:
            match_distance: 前后帧球匹配的最大距离(归一化坐标)
            confirm_frames: 进球确认所需的连续帧数
        """
        self._match_dist = match_distance
        self._confirm_frames = confirm_frames
        self._tracked: Dict[int, BallState] = {}    # ball_id → BallState
        self._missed: Dict[int, int] = {}            # ball_id → missed frames
        self._next_id: int = 0
        self._events: List[PocketEvent] = []

    def update(self, balls: List) -> List[PocketEvent]:
        """传入当前帧球列表，返回新发生的进球事件"""
        self._events = []
        current = self._build_states(balls)
        matched_curr: Set[int] = set()

        if not self._tracked:
            for b in current:
                b.ball_id = self._next_id
                self._tracked[b.ball_id] = b
                self._next_id += 1
            return []

        # 匹配当前帧球 → 追踪列表
        for j, curr in enumerate(current):
            best_id, best_d = -1, self._match_dist
            for tid, tball in self._tracked.items():
                d = ((curr.x - tball.x) ** 2 + (curr.y - tball.y) ** 2) ** 0.5
                # 颜色辅助惩罚
                if curr.color != tball.color:
                    d += 0.02
                if curr.is_solid != tball.is_solid:
                    d += 0.02
                if curr.is_cue != tball.is_cue:
                    d += 0.02
                if d < best_d:
                    best_d = d
                    best_id = tid
            if best_id >= 0:
                matched_curr.add(j)
                curr.ball_id = best_id
                # 匹配成功 → 更新追踪位置 + 清零miss计数
                self._tracked[best_id] = curr
                self._missed.pop(best_id, None)

        # 未匹配的新球 → 新ID
        for j, curr in enumerate(current):
            if j in matched_curr:
                continue
            curr.ball_id = self._next_id
            self._tracked[curr.ball_id] = curr
            self._next_id += 1

        # 检查所有追踪球：本帧未匹配到的增量miss计数
        to_remove: List[int] = []
        for tid, tball in list(self._tracked.items()):
            # 如果这颗球在本帧被匹配到了，上面已经清零了miss，跳过
            if tid in [c.ball_id for c in current]:
                continue
            missed = self._missed.get(tid, 0) + 1
            self._missed[tid] = missed

            pocket = self._near_pocket((tball.x, tball.y))
            if pocket and missed >= self._confirm_frames:
                self._events.append(PocketEvent(
                    ball_id=tid, color=tball.color,
                    is_stripe=tball.is_stripe, is_solid=tball.is_solid,
                    is_black=tball.is_black, is_cue=tball.is_cue,
                    pocket_pos=pocket, timestamp=time.time(),
                ))
                to_remove.append(tid)
            elif missed > self._confirm_frames + 3:
                # 太多帧未出现且不在袋口附近 → 可能是误检，清理
                if not pocket:
                    to_remove.append(tid)

        for tid in to_remove:
            self._tracked.pop(tid, None)
            self._missed.pop(tid, None)

        return self._events

    def get_pocketed_ball_ids(self) -> Set[int]:
        return {e.ball_id for e in self._events}

    def is_cue_pocketed(self) -> bool:
        return any(e.is_cue for e in self._events)

    def has_events(self) -> bool:
        return len(self._events) > 0

    def clear_events(self) -> None:
        self._events = []
        self._missed.clear()
        self._tracked.clear()

    def reset(self) -> None:
        """重置全部状态（新对局/新训练）"""
        self._tracked.clear()
        self._events.clear()
        self._missed.clear()
        self._next_id = 0

    # ---- internal ----

    def _build_states(self, balls: List) -> List[BallState]:
        return [
            BallState(
                x=b.x, y=b.y, ball_id=-1,
                color=b.color, is_stripe=b.is_stripe,
                is_solid=b.is_solid, is_black=b.is_black,
                is_cue=b.is_cue, confidence=1.0,
            )
            for b in balls
        ]

    @staticmethod
    def _near_pocket(pos: Tuple[float, float]) -> Optional[Tuple[float, float]]:
        """检查位置是否在某个袋口内，返回袋口坐标"""
        x, y = pos
        for px, py in POCKETS:
            d = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            if d < POCKET_RADIUS_NORM:
                return (px, py)
        return None
