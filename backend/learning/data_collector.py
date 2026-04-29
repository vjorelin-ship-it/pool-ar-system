"""击球数据采集模块

记录每杆的预测轨迹 vs 实际观察轨迹，为AI修正模型提供训练数据。
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import json
import time
import os


@dataclass
class ShotRecord:
    """单次击球完整记录"""
    shot_id: int
    timestamp: float

    # 输入条件
    cue_x: float
    cue_y: float
    target_x: float
    target_y: float
    pocket_x: float
    pocket_y: float
    power: float          # 1-100
    spin_x: float         # -1.0 ~ 1.0 左右塞
    spin_y: float         # -1.0 ~ 1.0 高杆/低杆

    # 物理引擎预测
    pred_cue_path: List[Tuple[float, float]] = field(default_factory=list)
    pred_target_path: List[Tuple[float, float]] = field(default_factory=list)

    # 实际观察
    obs_cue_path: List[Tuple[float, float]] = field(default_factory=list)
    obs_target_path: List[Tuple[float, float]] = field(default_factory=list)
    obs_target_pocketed: bool = False
    obs_cue_final_x: float = 0.0
    obs_cue_final_y: float = 0.0

    # 推断的残差（计算时填充）
    cue_dx: float = 0.0
    cue_dy: float = 0.0
    angle_error_deg: float = 0.0

    # 训练上下文
    mode: str = ""           # "match", "training", "ai_training"
    level: int = 0           # 训练档位
    drill_id: int = 0        # 训练题号
    outcome: str = ""        # "success", "fail"
    cue_speed: float = 0.0   # 杆速 m/s


class DataCollector:
    """击球数据采集器

    自动记录每杆的[预测路线 vs 实际路线]，用于：
    1. 物理参数自适应 (physics_adapter)
    2. AI残差修正模型训练 (correction_model)
    3. 用户统计和习惯分析
    """

    def __init__(self, save_path: str = ""):
        self._records: List[ShotRecord] = []
        self._next_id: int = 0
        self._save_path = save_path or os.path.join(
            os.path.dirname(__file__), "shot_data.json")

    def record_shot(self, shot: ShotRecord) -> None:
        """记录一次击球"""
        shot.shot_id = self._next_id
        self._next_id += 1
        self._records.append(shot)

    def get_all(self) -> List[ShotRecord]:
        """获取全部记录"""
        return list(self._records)

    def count(self) -> int:
        """总记录数"""
        return len(self._records)

    def get_recent(self, n: int = 50) -> List[ShotRecord]:
        """最近N条记录"""
        return self._records[-n:]

    def save(self, path: str = "") -> None:
        """持久化到JSON文件"""
        path = path or self._save_path
        data = []
        for r in self._records:
            data.append({
                "shot_id": r.shot_id,
                "timestamp": r.timestamp,
                "cue_pos": [r.cue_x, r.cue_y],
                "target_pos": [r.target_x, r.target_y],
                "pocket_pos": [r.pocket_x, r.pocket_y],
                "power": r.power,
                "spin_x": r.spin_x,
                "spin_y": r.spin_y,
                "pred_cue_path": r.pred_cue_path,
                "pred_target_path": r.pred_target_path,
                "obs_cue_path": r.obs_cue_path,
                "obs_target_path": r.obs_target_path,
                "obs_target_pocketed": r.obs_target_pocketed,
                "obs_cue_final": [r.obs_cue_final_x, r.obs_cue_final_y],
                "residual": [r.cue_dx, r.cue_dy, r.angle_error_deg],
                "mode": r.mode,
                "level": r.level,
                "drill_id": r.drill_id,
                "outcome": r.outcome,
                "cue_speed": r.cue_speed,
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str = "") -> int:
        """从JSON文件加载"""
        path = path or self._save_path
        if not os.path.exists(path):
            return 0
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            self._records.append(ShotRecord(
                shot_id=item.get("shot_id", self._next_id),
                timestamp=item.get("timestamp", 0),
                cue_x=item["cue_pos"][0],
                cue_y=item["cue_pos"][1],
                target_x=item["target_pos"][0],
                target_y=item["target_pos"][1],
                pocket_x=item["pocket_pos"][0],
                pocket_y=item["pocket_pos"][1],
                power=item.get("power", 50),
                spin_x=item.get("spin_x", 0),
                spin_y=item.get("spin_y", 0),
                pred_cue_path=[tuple(p) for p in item.get("pred_cue_path", [])],
                pred_target_path=[tuple(p) for p in item.get("pred_target_path", [])],
                obs_cue_path=[tuple(p) for p in item.get("obs_cue_path", [])],
                obs_target_path=[tuple(p) for p in item.get("obs_target_path", [])],
                obs_target_pocketed=item.get("obs_target_pocketed", False),
                obs_cue_final_x=item["obs_cue_final"][0] if "obs_cue_final" in item else 0,
                obs_cue_final_y=item["obs_cue_final"][1] if "obs_cue_final" in item else 0,
                cue_dx=item.get("residual", [0, 0, 0])[0],
                cue_dy=item.get("residual", [0, 0, 0])[1],
                angle_error_deg=item.get("residual", [0, 0, 0])[2],
                mode=item.get("mode", ""),
                level=item.get("level", 0),
                drill_id=item.get("drill_id", 0),
                outcome=item.get("outcome", ""),
                cue_speed=item.get("cue_speed", 0),
            ))
            if item["shot_id"] >= self._next_id:
                self._next_id = item["shot_id"] + 1
        # Ensure _next_id is truly the max + 1 (robust against file ordering)
        max_id = max((item.get("shot_id", -1) for item in data), default=-1)
        self._next_id = max(self._next_id, max_id + 1)
        return len(data)
