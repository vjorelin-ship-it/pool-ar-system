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
    spin_x: float = 0.0        # -1.0 (left) ~ 1.0 (right)
    spin_y: float = 0.0        # -1.0 (draw) ~ 1.0 (follow)
    english_deflection: float = 0.0  # lateral deflection angle from side spin


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
        Vec2(0.015, 0.015), Vec2(0.5, 0.015), Vec2(0.985, 0.015),
        Vec2(0.015, 0.985), Vec2(0.5, 0.985), Vec2(0.985, 0.985),
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

            # Velocity scales with cushion restitution
            dist_to_aim = cue_pos.dist_to(aim_point)
            cue_speed = self._speed_from_distance(dist_to_aim) * (2.0 - self.CUSHION_RESTITUTION)
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

            # Score = total path length (cue→aim + target→phantom)
            # Prefer shorter total paths; differentiates between cushions
            dist_cue_to_aim = cue_pos.dist_to(aim_point)
            dist_target_to_phantom = target_pos.dist_to(phantom)
            score = dist_cue_to_aim + dist_target_to_phantom
            if score < best_score:
                best_score = score
                best_shot = shot

        return best_shot

    # ─── 两库翻袋 ──────────────────────────────────────────────────

    def calculate_double_bank_shot(self, cue_pos: Vec2, target_pos: Vec2,
                                    pocket_pos: Vec2) -> ShotResult:
        """Calculate two-cushion bank shot.

        Mirror the pocket across two cushions to get a double-phantom pocket.
        Valid cushion pairs: (top,left) (top,right) (bottom,left) (bottom,right)
        """
        # Double reflections: first reflect across cushion A, then across cushion B
        double_reflections = [
            # (name, phantom_x, phantom_y, bounce1_side, bounce1_edge, bounce2_side, bounce2_edge)
            # Top → Left
            ("top-left",
             -pocket_pos.x, -pocket_pos.y,
             "top", 0.0, "left", 0.0),
            # Top → Right
            ("top-right",
             2.0 - pocket_pos.x, -pocket_pos.y,
             "top", 0.0, "right", 1.0),
            # Bottom → Left
            ("bottom-left",
             -pocket_pos.x, 2.0 - pocket_pos.y,
             "bottom", 1.0, "left", 0.0),
            # Bottom → Right
            ("bottom-right",
             2.0 - pocket_pos.x, 2.0 - pocket_pos.y,
             "bottom", 1.0, "right", 1.0),
        ]

        best_shot = self._no_shot()
        best_score = float("inf")

        for name, px, py, s1, e1, s2, e2 in double_reflections:
            phantom = Vec2(px, py)
            # Direction from target to double-phantom
            to_phantom = phantom - target_pos
            to_phantom_n = to_phantom.normalized()
            aim_point = target_pos + to_phantom_n * (-self.AIM_OFFSET)

            # Collision check
            if not self._will_hit_target(cue_pos, aim_point, target_pos):
                continue

            # Angle check
            cue_to_target = target_pos - cue_pos
            angle = self._angle_between(cue_to_target, to_phantom)
            if abs(angle) > self.MAX_ANGLE_BANK * 1.3:
                continue

            # Distance check (relax for double bank)
            dist_target_pocket = target_pos.dist_to(pocket_pos)
            if dist_target_pocket > self.MAX_DIST_BANK * 1.5:
                continue

            # Compute two bounce points
            b1 = self._line_edge_intersect(target_pos, phantom, s1, e1)
            if b1 is None or not self._on_cushion_edge(b1, s1):
                continue
            b2 = self._line_edge_intersect(b1, phantom, s2, e2)
            if b2 is None or not self._on_cushion_edge(b2, s2):
                continue

            # Velocity (double bank needs more power)
            dist_to_aim = cue_pos.dist_to(aim_point)
            cue_speed = self._speed_from_distance(dist_to_aim) * 1.5
            target_speed = cue_speed * 0.3

            cue_final = self._estimate_cue_stop(cue_pos, aim_point, cue_speed)

            shot = ShotResult(
                cue_path=[cue_pos, aim_point],
                target_path=[target_pos, b1, b2, pocket_pos],
                target_pocket=pocket_pos,
                cue_speed=cue_speed,
                target_speed=target_speed,
                success=True,
                cue_final_pos=cue_final,
                is_bank_shot=True,
                bounce_point=b1,
            )
            score = target_pos.dist_to(b1) + b1.dist_to(b2) + b2.dist_to(pocket_pos)
            if score < best_score:
                best_score = score
                best_shot = shot

        return best_shot

    # ─── 组合球/传球 ───────────────────────────────────────────────

    def calculate_combo_shot(self, cue_pos: Vec2, intermediate_pos: Vec2,
                              target_pos: Vec2, pocket_pos: Vec2) -> ShotResult:
        """Calculate a combination/passing shot.

        Cue ball → intermediate ball → target ball → pocket.
        The intermediate ball acts as a 'cue ball' for the target.
        """
        # First: intermediate → target → pocket (same as direct shot logic)
        to_pocket = pocket_pos - target_pos
        to_pocket_n = to_pocket.normalized()
        dist_target_pocket = target_pos.dist_to(pocket_pos)

        if dist_target_pocket > self.MAX_DIST_DIRECT:
            return self._no_shot()

        # Aim point for intermediate → target collision
        aim_intermediate = target_pos + to_pocket_n * (-self.AIM_OFFSET)

        # Check if intermediate can hit target
        if not self._will_hit_target(intermediate_pos, aim_intermediate, target_pos):
            return self._no_shot()

        # Angle check: intermediate → target vs target → pocket
        mid_to_target = target_pos - intermediate_pos
        angle1 = self._angle_between(mid_to_target, to_pocket)
        if abs(angle1) > self.MAX_ANGLE_DIRECT:
            return self._no_shot()

        # Second: cue → intermediate
        # Aim point for cue → intermediate collision (intermediate goes toward aim_intermediate)
        dir_intermediate = aim_intermediate - intermediate_pos
        dir_intermediate_n = dir_intermediate.normalized()
        aim_cue = intermediate_pos + dir_intermediate_n * (-self.AIM_OFFSET)

        # Check if cue can hit intermediate
        if not self._will_hit_target(cue_pos, aim_cue, intermediate_pos):
            return self._no_shot()

        # Angle check: cue → intermediate vs intermediate → target
        angle2 = self._angle_between(aim_cue - cue_pos, aim_intermediate - intermediate_pos)
        if abs(angle2) > self.MAX_ANGLE_DIRECT:
            return self._no_shot()

        # Distance
        dist_cue_intermediate = cue_pos.dist_to(intermediate_pos)
        total_dist = dist_cue_intermediate + dist_target_pocket
        if total_dist > self.MAX_DIST_DIRECT * 1.5:
            return self._no_shot()

        # Velocity (combo needs more power due to two collisions)
        cue_speed = self._speed_from_distance(total_dist) * 1.4
        intermediate_speed = cue_speed * 0.7
        target_speed = intermediate_speed * 0.7

        cue_final = self._estimate_cue_stop(cue_pos, aim_cue, cue_speed)

        return ShotResult(
            cue_path=[cue_pos, aim_cue],
            target_path=[intermediate_pos, aim_intermediate, target_pos, pocket_pos],
            target_pocket=pocket_pos,
            cue_speed=cue_speed,
            target_speed=target_speed,
            success=True,
            cue_final_pos=cue_final,
        )

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

    def find_best_shot_with_context(self, cue_pos: Vec2, target_pos: Vec2,
                                     all_balls: List[Vec2]) -> ShotResult:
        """Like find_best_shot but considers combinations with nearby balls."""
        best = self.find_best_shot(cue_pos, target_pos)
        best_score = float("inf")
        if best.success:
            best_score = target_pos.dist_to(best.target_pocket)

        # Try double bank for each pocket
        for pocket in self.POCKETS:
            db = self.calculate_double_bank_shot(cue_pos, target_pos, pocket)
            if db.success:
                dist = target_pos.dist_to(pocket) * 1.3  # weighted, double bank is harder
                if dist < best_score:
                    best = db
                    best_score = dist

        # Try combo shots using other balls as intermediates
        for mid in all_balls:
            if mid.dist_to(cue_pos) < 0.02 or mid.dist_to(target_pos) < 0.02:
                continue
            for pocket in self.POCKETS:
                combo = self.calculate_combo_shot(cue_pos, mid, target_pos, pocket)
                if combo.success:
                    dist = target_pos.dist_to(pocket) * 1.4
                    if dist < best_score:
                        best = combo
                        best_score = dist

        return best if best.success else self._no_shot()

    # ─── 轨迹生成 ─────────────────────────────────────────────────

    def generate_trajectory_frames(self, cue_pos: Vec2, target_pos: Vec2,
                                    pocket_pos: Vec2, num_frames: int = 100,
                                    power: float = 0.5,
                                    spin_x: float = 0.0,
                                    spin_y: float = 0.0,
                                    ) -> Tuple[List[Tuple[float, float]],
                                               List[Tuple[float, float]]]:
        """Generate simulated trajectory frame sequence.

        Used for synthetic data generation and physics-guided conditioning.

        Returns:
            cue_path: list of (x, y) positions, length=num_frames
            target_path: list of (x, y) positions, length=num_frames
        """
        shot = self.calculate_shot(cue_pos, target_pos, pocket_pos)
        if not shot.success:
            shot = self.calculate_bank_shot(cue_pos, target_pos, pocket_pos)
        if not shot.success:
            # Fallback: simple straight-line motion
            return ([(cue_pos.x + (target_pos.x - cue_pos.x) * i / num_frames,
                      cue_pos.y + (target_pos.y - cue_pos.y) * i / num_frames)
                     for i in range(num_frames)],
                    [(target_pos.x, target_pos.y) for _ in range(num_frames)])

        # Extract physics path points
        cue_pts = [(p.x, p.y) for p in shot.cue_path]
        target_pts = [(p.x, p.y) for p in shot.target_path]
        cue_final = (shot.cue_final_pos.x, shot.cue_final_pos.y)             if shot.cue_final_pos else cue_pts[-1]
        target_final = target_pts[-1] if len(target_pts) > 1 else target_pts[0]

        # Phases: 0-15% approach, 15-80% motion+deceleration, 80-100% stopped
        collide_frac = 0.15
        stop_frac = 0.80
        n_collide = max(1, int(num_frames * collide_frac))
        n_stop = min(num_frames, int(num_frames * stop_frac))

        # Cue ball path
        cue_frames = []
        for i in range(num_frames):
            if i <= n_collide:
                alpha = i / n_collide
                cx = cue_pts[0][0] + (cue_pts[-1][0] - cue_pts[0][0]) * alpha
                cy = cue_pts[0][1] + (cue_pts[-1][1] - cue_pts[0][1]) * alpha
            elif i <= n_stop:
                alpha = (i - n_collide) / (n_stop - n_collide)
                decel = 1.0 - alpha * alpha * 0.7
                cx = cue_pts[-1][0] + (cue_final[0] - cue_pts[-1][0]) * (1 - decel)
                cy = cue_pts[-1][1] + (cue_final[1] - cue_pts[-1][1]) * (1 - decel)
            else:
                cx, cy = cue_final
            cue_frames.append((cx, cy))

        # Target ball path
        target_frames = []
        for i in range(num_frames):
            if i < n_collide:
                tx, ty = target_pts[0]
            else:
                alpha = min(1.0, (i - n_collide) / max(n_stop - n_collide, 1))
                tx = target_pts[0][0] + (target_final[0] - target_pts[0][0]) * alpha
                ty = target_pts[0][1] + (target_final[1] - target_pts[0][1]) * alpha
            target_frames.append((tx, ty))

        return cue_frames, target_frames

    # ─── 旋转/杆法 ─────────────────────────────────────────────────

    def calculate_shot_with_spin(self, cue_pos: Vec2, target_pos: Vec2,
                                  pocket_pos: Vec2, spin_x: float = 0.0,
                                  spin_y: float = 0.0) -> ShotResult:
        """Calculate a direct shot with spin effects.

        spin_x: side spin (-1.0 left, +1.0 right)
        spin_y: vertical spin (-1.0 draw, 0.0 stun, +1.0 follow)
        """
        shot = self.calculate_shot(cue_pos, target_pos, pocket_pos)
        if not shot.success:
            return shot

        # Side spin: deflect cue ball path laterally after hitting target
        # A cue ball with side spin curves slightly and deflects differently
        # SIDE_SPIN_DEFLECTION ≈ 3° per unit of spin
        SIDE_DEFLECTION_PER_UNIT = 3.0 * math.pi / 180.0
        english_deflection = spin_x * SIDE_DEFLECTION_PER_UNIT

        # Vertical spin: modifies cue ball final position
        # Draw (spin_y < 0): cue ball pulls BACK after collision
        # Follow (spin_y > 0): cue ball continues FORWARD after collision
        # Stun (spin_y = 0): cue ball stops at the collision point (approximately)

        cue_start = shot.cue_path[0]
        cue_hit_pos = shot.cue_path[-1]  # where cue hits target
        # Direction from cue start to hit position
        approach_dir = Vec2(cue_hit_pos.x - cue_start.x,
                           cue_hit_pos.y - cue_start.y)
        approach_dist = approach_dir.length()
        if approach_dist < 0.001:
            shot.spin_x = spin_x
            shot.spin_y = spin_y
            shot.english_deflection = english_deflection
            return shot
        approach_n = approach_dir.normalized()

        # Vertical spin effect on cue final position
        # Follow: cue goes forward ~30% of approach distance
        # Draw: cue comes back ~40% of approach distance
        # Stun: cue stops near collision point
        if spin_y > 0.1:  # Follow
            follow_dist = approach_dist * 0.3 * spin_y
            final_x = cue_hit_pos.x + approach_n.x * follow_dist
            final_y = cue_hit_pos.y + approach_n.y * follow_dist
        elif spin_y < -0.1:  # Draw
            draw_dist = approach_dist * 0.4 * abs(spin_y)
            final_x = cue_hit_pos.x - approach_n.x * draw_dist
            final_y = cue_hit_pos.y - approach_n.y * draw_dist
        else:  # Stun/stop
            final_x = cue_hit_pos.x + approach_n.x * approach_dist * 0.05
            final_y = cue_hit_pos.y + approach_n.y * approach_dist * 0.05

        # Clamp
        final_x = max(0.01, min(0.99, final_x))
        final_y = max(0.01, min(0.99, final_y))

        # Side spin deflection: rotate the cue path end slightly
        cos_a = math.cos(english_deflection)
        sin_a = math.sin(english_deflection)
        deflected_x = approach_n.x * cos_a - approach_n.y * sin_a
        deflected_y = approach_n.x * sin_a + approach_n.y * cos_a
        deflected_hit = Vec2(
            cue_hit_pos.x + deflected_x * approach_dist * 0.1,
            cue_hit_pos.y + deflected_y * approach_dist * 0.1,
        )

        return ShotResult(
            cue_path=[cue_start, deflected_hit],
            target_path=shot.target_path,
            target_pocket=shot.target_pocket,
            cue_speed=shot.cue_speed * (1.0 + 0.1 * abs(spin_x)),
            target_speed=shot.target_speed,
            success=True,
            cue_final_pos=Vec2(final_x, final_y),
            spin_x=spin_x,
            spin_y=spin_y,
            english_deflection=english_deflection,
        )

    @staticmethod
    def suggest_spin_for_landing(cue_pos: Vec2, target_pos: Vec2,
                                  desired_final: Vec2) -> Tuple[float, float]:
        """Suggest spin values to land the cue ball near desired_final.

        Returns (spin_x, spin_y).
        """
        approach = target_pos - cue_pos
        desired = desired_final - target_pos
        dist = approach.length()
        if dist < 0.001:
            return (0.0, 0.0)
        approach_n = approach.normalized()
        # Project desired offset onto approach direction
        proj = desired.dot(approach_n)
        # Follow if desired is forward, draw if backward
        spin_y = max(-1.0, min(1.0, proj / (dist * 0.3)))
        # Side spin: perpendicular component
        perp_x = desired.x - proj * approach_n.x
        spin_x = max(-1.0, min(1.0, perp_x / (dist * 0.15)))
        return (spin_x, spin_y)

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
        return perp <= self.BALL_RADIUS * 2.0

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
        if speed < 0.01:
            return cue_start
        dir_n = (aim_point - cue_start).normalized()
        # Energy after collision with target ball (momentum transfer)
        post_collision_speed = speed * (1.0 - self.CUSHION_RESTITUTION * 0.6)
        stop_dist = post_collision_speed ** 2 / (2 * self.BALL_FRICTION * 1.0)
        stop_dist = min(stop_dist, 0.5)
        return cue_start + dir_n * stop_dist

    @staticmethod
    def _speed_from_distance(dist: float) -> float:
        """力度-距离映射（非线性）

        短距离用低速度，长距离用高速度，但非线性增长。
        v = k * sqrt(dist) 更真实（动能与力度平方成正比）
        """
        return 0.08 + math.sqrt(dist) * 0.25

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
