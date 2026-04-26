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


@dataclass
class ShotResult:
    cue_path: List[Vec2]          # Cue ball path points
    target_path: List[Vec2]       # Target ball path points
    target_pocket: Vec2           # Target pocket position
    cue_speed: float              # Cue ball initial speed
    target_speed: float           # Target ball speed after hit
    success: bool                 # Whether shot is physically possible
    cue_final_pos: Optional[Vec2] = None  # Cue ball final position


class PhysicsEngine:
    TABLE_WIDTH: float = 1.0       # normalized width
    TABLE_HEIGHT: float = 0.5      # normalized height
    CUSHION_RESTITUTION: float = 0.78
    BALL_RADIUS: float = 0.015     # normalized ball radius
    POCKET_RADIUS: float = 0.035   # normalized pocket radius

    POCKETS: List[Vec2] = [
        Vec2(0.0, 0.0),            # top-left
        Vec2(0.5, 0.0),            # top-center
        Vec2(1.0, 0.0),            # top-right
        Vec2(0.0, 1.0),            # bottom-left
        Vec2(0.5, 1.0),            # bottom-center
        Vec2(1.0, 1.0),            # bottom-right
    ]

    def calculate_shot(self, cue_pos: Vec2, target_pos: Vec2,
                       pocket_pos: Vec2) -> ShotResult:
        """Calculate the optimal shot to hit target ball into pocket."""
        # Direction from target to pocket
        to_pocket = pocket_pos - target_pos
        to_pocket_n = to_pocket.normalized()

        # Aim point is behind the target ball (in direction of pocket)
        aim_point = Vec2(
            target_pos.x - to_pocket_n.x * self.BALL_RADIUS * 2,
            target_pos.y - to_pocket_n.y * self.BALL_RADIUS * 2,
        )

        # Direction from cue ball to aim point
        to_aim = aim_point - cue_pos
        dist_to_aim = to_aim.length()

        if dist_to_aim < self.BALL_RADIUS * 2:
            return self._no_shot()

        to_aim_n = to_aim.normalized()

        # Check if shot is valid (angle between cue-target and target-pocket)
        cue_to_target = target_pos - cue_pos
        target_to_pocket = pocket_pos - target_pos
        angle = self._angle_between(cue_to_target, target_to_pocket)

        if abs(angle) > math.pi / 3:  # Max 60 degrees
            return self._no_shot()

        # Check for pocket proximity
        dist_to_pocket = (target_pos - pocket_pos).length()
        if dist_to_pocket > 0.6:  # Too far for a reasonable shot
            return self._no_shot()

        cue_path = [cue_pos, aim_point]
        target_path = [target_pos, pocket_pos]

        cue_speed = dist_to_aim * 0.15  # Simple speed calculation
        target_speed = cue_speed * 0.7

        return ShotResult(
            cue_path=cue_path,
            target_path=target_path,
            target_pocket=pocket_pos,
            cue_speed=cue_speed,
            target_speed=target_speed,
            success=True,
            cue_final_pos=Vec2(
                cue_pos.x + to_aim_n.x * dist_to_aim * 0.3,
                cue_pos.y + to_aim_n.y * dist_to_aim * 0.3,
            ),
        )

    def calculate_bank_shot(self, cue_pos: Vec2, target_pos: Vec2,
                            pocket_pos: Vec2) -> ShotResult:
        """Calculate a one-cushion bank shot."""
        # Reflect target across the nearest cushion
        reflected = self._reflect_across_cushion(target_pos, pocket_pos)
        # Now calculate as if the pocket is at the reflected position
        return self.calculate_shot(cue_pos, target_pos, reflected)

    def find_best_shot(self, cue_pos: Vec2, target_pos: Vec2) -> ShotResult:
        """Find the best shot (direct or bank) for a target ball."""
        best_shot: Optional[ShotResult] = None
        best_score = float("inf")

        for pocket in self.POCKETS:
            shot = self.calculate_shot(cue_pos, target_pos, pocket)
            if shot.success:
                dist = (target_pos - pocket).length()
                score = dist
                if best_shot is None or score < best_score:
                    best_shot = shot
                    best_score = score

        return best_shot or self._no_shot()

    def _no_shot(self) -> ShotResult:
        return ShotResult(
            cue_path=[], target_path=[], target_pocket=Vec2(0, 0),
            cue_speed=0, target_speed=0, success=False,
        )

    def _reflect_across_cushion(self, pos: Vec2, pocket: Vec2) -> Vec2:
        """Reflect position across the nearest cushion for bank shot calc."""
        dx = pocket.x - pos.x
        dy = pocket.y - pos.y
        if abs(dx) < abs(dy):
            return Vec2(-pos.x, pos.y)
        else:
            return Vec2(pos.x, -pos.y)

    @staticmethod
    def _angle_between(v1: Vec2, v2: Vec2) -> float:
        dot = v1.x * v2.x + v1.y * v2.y
        norm = math.sqrt(v1.x ** 2 + v1.y ** 2) * math.sqrt(v2.x ** 2 + v2.y ** 2)
        if norm == 0:
            return 0
        cos_a = max(-1, min(1, dot / norm))
        return math.acos(cos_a)
