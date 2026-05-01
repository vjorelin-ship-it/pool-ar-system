"""击球限时执裁模块 — CTBA 2025 职业赛规则

每杆限时45秒，剩10秒提醒，剩5秒倒计时。
每局可申请1次30秒延时。
超时未出杆 = 犯规 + 对手自由球。
"""

import time
from typing import Optional, Callable


class ShotTimer:
    """击球限时器"""

    def __init__(self, shot_seconds: int = 45, extension_seconds: int = 30):
        self._shot_seconds = shot_seconds
        self._extension_seconds = extension_seconds
        self._shot_start: float = 0.0
        self._running: bool = False
        self._extension_active: bool = False
        self._extension_used_p1: bool = False
        self._extension_used_p2: bool = False
        self._last_announced_10s: bool = False
        self._last_announced_5s: bool = False
        self._last_announced_4s: bool = False
        self._last_announced_3s: bool = False
        self._last_announced_2s: bool = False
        self._last_announced_1s: bool = False
        self._timed_out: bool = False

    @property
    def shot_seconds(self) -> int:
        return self._shot_seconds

    @property
    def running(self) -> bool:
        return self._running

    @property
    def timed_out(self) -> bool:
        return self._timed_out

    def start_shot(self) -> None:
        """开始新一杆的计时"""
        self._shot_start = time.time()
        self._running = True
        self._extension_active = False
        self._timed_out = False
        self._last_announced_10s = False
        self._last_announced_5s = False
        self._last_announced_4s = False
        self._last_announced_3s = False
        self._last_announced_2s = False
        self._last_announced_1s = False

    def stop(self) -> None:
        """停止计时（击球已发生）"""
        self._running = False

    def reset_game(self) -> None:
        """新一局重置延时使用状态"""
        self._extension_used_p1 = False
        self._extension_used_p2 = False
        self.stop()

    def request_extension(self, player: int) -> bool:
        """申请延时。返回True=批准，False=已用完"""
        used = self._extension_used_p1 if player == 1 else self._extension_used_p2
        if used:
            return False
        if player == 1:
            self._extension_used_p1 = True
        else:
            self._extension_used_p2 = True
        self._shot_start = time.time()  # 重置计时起点
        self._extension_active = True
        self._last_announced_10s = False
        self._last_announced_5s = False
        self._timed_out = False
        return True

    def tick(self) -> Optional[str]:
        """每个视觉帧调用。返回需要播报的文字，或None。

        Returns:
            None: 无事件
            "10s": 剩余10秒提醒
            "5"~"1": 倒计时
            "timeout": 超时犯规
        """
        if not self._running:
            return None
        if self._timed_out:
            return None

        elapsed = time.time() - self._shot_start
        limit = self._extension_seconds if self._extension_active else self._shot_seconds
        remaining = limit - elapsed

        # 超时
        if remaining <= 0:
            self._timed_out = True
            self._running = False
            return "timeout"

        # 10秒提醒
        if remaining <= 10 and not self._last_announced_10s:
            self._last_announced_10s = True
            return "10s"

        # 倒计时
        if remaining <= 5 and not self._last_announced_5s:
            self._last_announced_5s = True
            return "5"
        if remaining <= 4 and not self._last_announced_4s:
            self._last_announced_4s = True
            return "4"
        if remaining <= 3 and not self._last_announced_3s:
            self._last_announced_3s = True
            return "3"
        if remaining <= 2 and not self._last_announced_2s:
            self._last_announced_2s = True
            return "2"
        if remaining <= 1 and not self._last_announced_1s:
            self._last_announced_1s = True
            return "1"

        return None

    def get_remaining_seconds(self) -> float:
        """获取剩余秒数（用于UI显示）"""
        if not self._running:
            return 0
        elapsed = time.time() - self._shot_start
        limit = self._extension_seconds if self._extension_active else self._shot_seconds
        return max(0, limit - elapsed)
