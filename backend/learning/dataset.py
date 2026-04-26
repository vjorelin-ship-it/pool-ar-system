"""训练数据集管理

管理和准备用于AI修正模型训练的数据集。
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import random
import json
import os


@dataclass
class Sample:
    """一条训练样本"""
    features: List[float]          # 12维输入
    residual: List[float]          # 6维残差输出


class ShotDataset:
    """击球数据集，管理训练样本的增删查改和持久化"""

    def __init__(self, save_path: str = ""):
        self._samples: List[Sample] = []
        self._save_path = save_path or os.path.join(
            os.path.dirname(__file__), "training_samples.json")

    def add(self, features: List[float], residual: List[float]) -> None:
        self._samples.append(Sample(features=features, residual=residual))

    def __len__(self) -> int:
        return len(self._samples)

    def get_all(self) -> List[Sample]:
        return list(self._samples)

    def get_training_batches(self, batch_size: int = 32) -> List[List[Sample]]:
        batches = []
        shuffled = list(self._samples)
        random.shuffle(shuffled)
        for i in range(0, len(shuffled), batch_size):
            batches.append(shuffled[i:i + batch_size])
        return batches

    def split(self, train_ratio: float = 0.8
              ) -> Tuple[List[Sample], List[Sample]]:
        n = int(len(self._samples) * train_ratio)
        return self._samples[:n], self._samples[n:]

    def save(self, path: str = "") -> None:
        path = path or self._save_path
        data = [{"features": s.features, "residual": s.residual}
                for s in self._samples]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str = "") -> int:
        path = path or self._save_path
        if not os.path.exists(path):
            return 0
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            self._samples.append(Sample(
                features=item["features"],
                residual=item["residual"],
            ))
        return len(data)
