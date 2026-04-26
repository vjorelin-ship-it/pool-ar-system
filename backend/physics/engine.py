import math
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Vec2:
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    def length(self) -> float:
        return math.sqrt(self.x ** 2 + self.y ** 2)

    def normalized(self) -> "Vec2":
        l = self.length()
        if l == 0:
            return Vec2(0, 0)
        return Vec2(self.x / l, self.y / l)

    def dot(self, other: "Vec2") -> float:
        return self.x * other.x + self.y * other.y

    def dist_to(self, other: "Vec2") -> float:
        return (self - other).length()


@dataclass
class ShotResult:
    cue_path: List[Vec2]          # Cue ball path points
    target_path: List[Vec2]       # Target ball path points
    target_pocket: Vec2           # Target pocket position
    cue_speed: float              # Cue ball initial speed (m/s normalized)
    target_speed: float           # Target ball speed after hit
    success: bool                 # Whether shot is physically possible
    cue_final_pos: Optional[Vec2] = None
    is_bank_shot: bool = False    # Whether this is a bank shot
    bounce_point: Optional[Vec2] = None  # Cushion bounce point (bank shots)


class PhysicsEngine:
    BALL_RADIUS: float = 0.015      # normalized ball radius
    POCKET_RADIUS: float = 0.035    # normalized pocket radius
    CUSHION_RESTITUTION: float = 0.78
    BALL_FRICTION: float = 0.03
    MAX_ANGLE_DIRECT: float = math.pi / 3     # 60° for direct shots
    MAX_ANGLE_BANK: float = math.pi / 2       # 90° for bank shots
    MAX_DIST_DIRECT: float = 0.6
    MAX_DIST_BANK: float = 0.5
    AIM_OFFSET: float = BALL_RADIUS * 2.0     # 幽灵球法：母球在接触点位置

    POCKETS: List[Vec2] = [
        Vec2(0.0, 0.0), Vec2(0.5, 0.0), Vec2(1.0, 0.0),
        Vec2(0.0, 1.0), Vec2(0.5, 1.0), Vec2(1.0, 1.0),
    ]

    # ─── 直接球 ────────────────────────────────────────────────────

    def calculate_shot(self, cue_pos: Vec2, target_pos: Vec2,
                       pocket_pos: Vec2) -> ShotResult:
        """计算直接进球路线

        1. 在目标球后方计算瞄准点（沿目标球→袋口方向偏移2倍球半径）
        2. 验证母球→瞄准点是否与目标球相交（碰撞检测）
        3. 验证角度和距离约束
        """
        to_pocket = pocket_pos - target_pos
        to_pocket_n = to_pocket.normalized()
        dist_target_pocket = target_pos.dist_to(pocket_pos)

        if dist_target_pocket > self.MAX_DIST_DIRECT:
            return self._no_shot()

        # 瞄准点：在目标球后方沿袋口方向偏移2.1倍球半径
        aim_point = target_pos + to_pocket_n * (-self.AIM_OFFSET)

        # 碰撞检测：母球→瞄准点方向是否命中目标球
        if not self._will_hit_target(cue_pos, aim_point, target_pos):
            return self._no_shot()

        # 角度校验：母球→目标球 与 目标球→袋口 夹角
        cue_to_target = target_pos - cue_pos
        angle = self._angle_between(cue_to_target, to_pocket)
        if abs(angle) > self.MAX_ANGLE_DIRECT:
            return self._no_shot()

        # 计算速度
        dist_to_aim = cue_pos.dist_to(aim_point)
        cue_speed = self._speed_from_distance(dist_to_aim)

        # 目标球速度（基于动量传递）
        target_speed = cue_speed * (0.9 - 0.3 * abs(angle) / self.MAX_ANGLE_DIRECT)

        # 母球停点（基于摩擦减速估算）
        cue_final = self._estimate_cue_stop(cue_pos, aim_point, cue_speed)

        return ShotResult(
            cue_path=[cue_pos, aim_point],
            target_path=[target_pos, pocket_pos],
            target_pocket=pocket_pos,
            cue_speed=cue_speed,
            target_speed=target_speed,
            success=True,
            cue_final_pos=cue_final,
        )

    # ─── 一库翻袋 ──────────────────────────────────────────────────

    def calculate_bank_shot(self, cue_pos: Vec2, target_pos: Vec2,
                            pocket_pos: Vec2) -> ShotResult:
        """计算一库翻袋路线

        将袋口沿四条库边镜像 → 得到幻影袋口 →
        目标球→幻影袋口方向瞄准 → 计算与库边的交点为反弹点
        """
        reflections = [
            ("top",    Vec2(pocket_pos.x, -pocket_pos.y),            0.0),
            ("bottom", Vec2(pocket_pos.x, 2.0 - pocket_pos.y),       1.0),
            ("left",   Vec2(-pocket_pos.x, pocket_pos.y),            0.0),
            ("right",  Vec2(2.0 - pocket_pos.x, pocket_pos.y),       1.0),
        ]

        best_shot = self._no_shot()
        best_score = float("inf")

        for side_name, phantom, edge_val in reflections:
            # 方向向量：目标球 → 幻影袋口
            to_phantom = phantom - target_pos
            to_phantom_n = to_phantom.normalized()

            # 瞄准点
            aim_point = target_pos + to_phantom_n * (-self.AIM_OFFSET)

            # 碰撞检测
            if not self._will_hit_target(cue_pos, aim_point, target_pos):
                continue

            # 角度校验（放宽到90°）
            cue_to_target = target_pos - cue_pos
            angle = self._angle_between(cue_to_target, to_phantom)
            if abs(angle) > self.MAX_ANGLE_BANK:
                continue

            # 距离校验
            dist_target_pocket = target_pos.dist_to(pocket_pos)
            if dist_target_pocket > self.MAX_DIST_BANK:
                continue

            # 计算反弹点：线 target_pos → phantom 与库边的交点
            bounce = self._line_edge_intersect(target_pos, phantom, side_name, edge_val)
            if bounce is None:
                continue

            # 验证反弹点在库边范围内
            if not self._on_cushion_edge(bounce, side_name):
                continue

            # 速度计算（翻袋需更大力度）
            dist_to_aim = cue_pos.dist_to(aim_point)
            cue_speed = self._speed_from_distance(dist_to_aim) * 1.2
            target_speed = cue_speed * 0.5

            # 母球停点
            cue_final = self._estimate_cue_stop(cue_pos, aim_point, cue_speed)

            # 正确的路径：目标球 → 库边反弹点 → 袋口
            target_path = [target_pos, bounce, pocket_pos]

            shot = ShotResult(
                cue_path=[cue_pos, aim_point],
                target_path=target_path,
                target_pocket=pocket_pos,
                cue_speed=cue_speed,
                target_speed=target_speed,
                success=True,
                cue_final_pos=cue_final,
                is_bank_shot=True,
                bounce_point=bounce,
            )

            score = dist_target_pocket
            if score < best_score:
                best_score = score
                best_shot = shot

        return best_shot

    # ─── 最佳球袋选择 ─────────────────────────────────────────────

    def find_best_shot(self, cue_pos: Vec2, target_pos: Vec2) -> ShotResult:
        """选择最佳球袋 + 最佳击球方式"""
        best: Optional[ShotResult] = None
        best_score = float("inf")

        for pocket in self.POCKETS:
            # 尝试直接球
            direct = self.calculate_shot(cue_pos, target_pos, pocket)
            if direct.success:
                dist = target_pos.dist_to(pocket)
                if dist < best_score:
                    best = direct
                    best_score = dist

            # 尝试翻袋
            bank = self.calculate_bank_shot(cue_pos, target_pos, pocket)
            if bank.success:
                dist = target_pos.dist_to(pocket)
                # 翻袋评分加权（翻袋比直接球难，加权优先）
                score = dist * 1.15
                if score < best_score:
                    best = bank
                    best_score = score

        return best or self._no_shot()

    # ─── 内部方法 ─────────────────────────────────────────────────

    def _will_hit_target(self, cue_pos: Vec2, aim_point: Vec2,
                         target_pos: Vec2) -> bool:
        """碰撞检测：幽灵球法验证母球是否能命中目标球

        aim_point是母球撞击目标球时母球球心的位置（幽灵球位置）。
        幽灵球法保证：只要母球能运动到aim_point，且到目标球的距离≈2倍球半径，
        则必然命中。验证方式是检查到无限直线的垂线距离。
        """
        cue_dir = aim_point - cue_pos
        line_len = cue_dir.length()
        if line_len < 1e-8:
            return False
        # 目标球到母球路径起点的向量
        to_target = target_pos - cue_pos
        # 目标球在母球路径直线上的投影
        proj_len = to_target.dot(cue_dir) / line_len
        # 垂线距离（使用无限直线，不限线段范围）
        proj_vec = cue_dir * (proj_len / line_len)
        perp = (to_target - proj_vec).length()
        # 若垂线距离 ≤ 两球半径之和 → 命中
        # 宽松阈值：允许aim_point到target的距离略大于2倍半径
        return perp <= self.BALL_RADIUS * 2.5

    @staticmethod
    def _line_edge_intersect(p1: Vec2, p2: Vec2, side: str,
                             edge_val: float) -> Optional[Vec2]:
        """计算线段 p1→p2 与库边的交点

        side: top/bottom (y=edge_val), left/right (x=edge_val)
        """
        dx = p2.x - p1.x
        dy = p2.y - p1.y

        if side in ("top", "bottom"):
            if abs(dy) < 1e-8:
                return None
            t = (edge_val - p1.y) / dy
        else:
            if abs(dx) < 1e-8:
                return None
            t = (edge_val - p1.x) / dx

        if t <= 0 or t >= 1:
            return None

        return Vec2(p1.x + t * dx, p1.y + t * dy)

    @staticmethod
    def _on_cushion_edge(point: Vec2, side: str) -> bool:
        """验证点是否在库边的有效范围内"""
        margin = 0.03  # 不包含袋口区域
        if side == "top":
            return margin <= point.x <= 1.0 - margin
        elif side == "bottom":
            return margin <= point.x <= 1.0 - margin
        elif side == "left":
            return margin <= point.y <= 1.0 - margin
        elif side == "right":
            return margin <= point.y <= 1.0 - margin
        return False

    def _estimate_cue_stop(self, cue_start: Vec2, aim_point: Vec2,
                           speed: float) -> Vec2:
        """估算母球停点（基于摩擦减速）

        停点距离 ≈ v² / (2 * friction * g)
        摩擦减速: a = friction * g (其中 g 归一化为 1)
        """
        if speed < 0.01:
            return cue_start
        dir_n = (aim_point - cue_start).normalized()
        stop_dist = speed ** 2 / (2 * self.BALL_FRICTION * 1.0)
        stop_dist = min(stop_dist, 0.5)  # 限制最大走位距离
        return cue_start + dir_n * stop_dist

    @staticmethod
    def _speed_from_distance(dist: float) -> float:
        """力度-距离映射（非线性）

        短距离用低速度，长距离用高速度，但非线性增长。
        v = k * sqrt(dist) 更真实（动能与力度平方成正比）
        """
        return 0.08 + math.sqrt(dist) * 0.25

    def find_best_shot_for_mode(self, cue_pos: Vec2, targets: List[Vec2]) -> ShotResult:
        """从多个目标球中选择最佳击球方案"""
        best = self._no_shot()
        best_score = float("inf")
        for t in targets:
            shot = self.find_best_shot(cue_pos, t)
            if shot.success:
                score = cue_pos.dist_to(t)
                if score < best_score:
                    best_score = score
                    best = shot
        return best

    def _no_shot(self) -> ShotResult:
        return ShotResult(
            cue_path=[], target_path=[], target_pocket=Vec2(0, 0),
            cue_speed=0, target_speed=0, success=False,
        )

    @staticmethod
    def _angle_between(v1: Vec2, v2: Vec2) -> float:
        dot = v1.x * v2.x + v1.y * v2.y
        norm = math.sqrt(v1.x ** 2 + v1.y ** 2) * math.sqrt(v2.x ** 2 + v2.y ** 2)
        if norm == 0:
            return 0
        cos_a = max(-1, min(1, dot / norm))
        return math.acos(cos_a)
