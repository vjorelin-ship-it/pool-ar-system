"""物理参数自适应模块

从实际击球观察中调优物理引擎参数，让预测越来越准。
"""
from dataclasses import dataclass, field
from typing import List, Optional
import json
import os


@dataclass
class PhysicsParams:
    """可调优的物理参数"""
    cushion_restitution: float = 0.78    # 库边弹性系数
    ball_friction: float = 0.03          # 球与桌面摩擦
    collision_damping: float = 0.95      # 球碰撞阻尼
    pocket_radius_tl: float = 0.035      # 左上袋口(独立调优)
    pocket_radius_tr: float = 0.035      # 右上袋口
    pocket_radius_bl: float = 0.035      # 左下袋口
    pocket_radius_br: float = 0.035      # 右下袋口
    pocket_radius_tm: float = 0.035      # 上中袋口
    pocket_radius_bm: float = 0.035      # 下中袋口

    def to_dict(self) -> dict:
        return {
            "cushion_restitution": self.cushion_restitution,
            "ball_friction": self.ball_friction,
            "collision_damping": self.collision_damping,
            "pocket_radius_tl": self.pocket_radius_tl,
            "pocket_radius_tr": self.pocket_radius_tr,
            "pocket_radius_bl": self.pocket_radius_bl,
            "pocket_radius_br": self.pocket_radius_br,
            "pocket_radius_tm": self.pocket_radius_tm,
            "pocket_radius_bm": self.pocket_radius_bm,
        }


# 参数调整范围
PARAM_CLAMPS = {
    "cushion_restitution": (0.65, 0.90),
    "ball_friction": (0.01, 0.06),
    "collision_damping": (0.85, 0.99),
    "pocket_radius_tl": (0.028, 0.048),
    "pocket_radius_tr": (0.028, 0.048),
    "pocket_radius_bl": (0.028, 0.048),
    "pocket_radius_br": (0.028, 0.048),
    "pocket_radius_tm": (0.028, 0.048),
    "pocket_radius_bm": (0.028, 0.048),
}


class PhysicsAdapter:
    """物理参数自适应

    从击球观察中逐步调优8个物理参数。
    使用 EWMA (指数加权移动平均) 平滑更新，避免单次异常值剧烈抖动。
    """

    def __init__(self, learning_rate: float = 0.05, save_path: str = ""):
        self.params = PhysicsParams()
        self._lr = learning_rate
        self._total_observations = 0
        self._save_path = save_path or os.path.join(
            os.path.dirname(__file__), "physics_params.json")

    def update_from_bank_shot(self, expected_angle: float,
                               actual_angle: float) -> None:
        """从翻袋观察中更新弹性系数

        Args:
            expected_angle: 物理引擎预测的出库角度(度)
            actual_angle: 实际观察到的出库角度(度)
        """
        self._total_observations += 1
        if actual_angle == 0 or expected_angle == 0:
            return
        # 角度比反映弹性系数偏差
        ratio = actual_angle / expected_angle
        error = ratio - 1.0
        adjustment = error * self._lr * 0.3  # 保守更新
        new_val = self.params.cushion_restitution * (1 + adjustment)
        self._clamp_and_set("cushion_restitution", new_val)
        self.save()

    def update_from_roll_distance(self, expected_dist: float,
                                   actual_dist: float) -> None:
        """从白球滚距观察更新摩擦系数"""
        self._total_observations += 1
        if expected_dist == 0:
            return
        ratio = actual_dist / expected_dist
        error = ratio - 1.0
        adjustment = error * self._lr * 0.2
        new_val = self.params.ball_friction * (1 - adjustment)
        self._clamp_and_set("ball_friction", new_val)
        self.save()

    def update_from_pocket(self, pocket_idx: int,
                            is_hit: bool) -> None:
        """从特定袋口的进球/弹出观察更新袋口半径

        Args:
            pocket_idx: 袋口索引 0-5
            is_hit: 是否进球（True=进，False=弹出）
        """
        self._total_observations += 1
        key = ["pocket_radius_tl", "pocket_radius_tm", "pocket_radius_tr",
               "pocket_radius_bl", "pocket_radius_bm", "pocket_radius_br"][pocket_idx]
        current = getattr(self.params, key)
        if is_hit:
            # 球进了→袋口可能比预想大，略增半径
            new_val = current * (1 + self._lr * 0.1)
        else:
            # 球弹出→袋口可能比预想小，略减半径
            new_val = current * (1 - self._lr * 0.1)
        self._clamp_and_set(key, new_val)
        self.save()

    def get_adjusted_params(self) -> PhysicsParams:
        return self.params

    def reset_to_defaults(self) -> None:
        """Reset all physics parameters to default values."""
        self.params = PhysicsParams()
        self._total_observations = 0
        print("[PhysicsAdapter] Reset to defaults")

    def save(self, path: str = "") -> None:
        path = path or self._save_path
        data = self.params.to_dict()
        data["_total_observations"] = self._total_observations
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str = "") -> bool:
        path = path or self._save_path
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in self.params.to_dict():
            if key in data:
                setattr(self.params, key, data[key])
        self._total_observations = data.get("_total_observations", 0)
        return True

    def _clamp_and_set(self, key: str, value: float) -> None:
        lo, hi = PARAM_CLAMPS.get(key, (0, 1))
        setattr(self.params, key, max(lo, min(hi, value)))
