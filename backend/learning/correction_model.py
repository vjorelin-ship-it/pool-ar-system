"""AI残差修正模型

轻量神经网络(~13k参数)，预测物理引擎输出与实际轨迹之间的残差。

路线预测 = PhysicsEngine.predict() + CorrectionModel.predict()
"""
from typing import List, Optional, Tuple
import os
import json
import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from .dataset import ShotDataset, Sample


# ─── 网络定义 ────────────────────────────────────────────────────

if HAS_TORCH:
    class ResidualCorrector(nn.Module):
        """残差修正网络

        输入(12维):
          [cue_x, cue_y, target_x, target_y, pocket_x, pocket_y,
           power/100, spin_x, spin_y, cushion_restitution, friction, pocket_radius]

        输出(6维):
          [cue_path_dx, cue_path_dy, target_path_dx, target_path_dy,
           final_pos_dx, final_pos_dy]
        """
        def __init__(self, input_dim: int = 12, hidden: int = 128):
            super().__init__()
            self.fc1 = nn.Linear(input_dim, hidden)
            self.fc2 = nn.Linear(hidden, 64)
            self.fc3 = nn.Linear(64, 32)
            self.out = nn.Linear(32, 6)
            self.dropout = nn.Dropout(0.1)

        def forward(self, x):
            x = F.relu(self.fc1(x))
            x = self.dropout(x)
            x = F.relu(self.fc2(x))
            x = self.dropout(x)
            x = F.relu(self.fc3(x))
            x = self.out(x)
            return x
else:
    # Dummy class when PyTorch not available
    class ResidualCorrector:
        def __init__(self, *args, **kwargs): pass


# ─── 模型管理器 ────────────────────────────────────────────────────

class CorrectionModel:
    """修正模型管理器

    封装训练、推理、保存、加载。
    模型参数量: 12×128 + 128 + 128×64 + 64 + 64×32 + 32 + 32×6 + 6 = 12,966
    """

    def __init__(self, model_dir: str = "", min_samples: int = 50):
        self._min_samples = min_samples
        self._model_dir = model_dir or os.path.dirname(__file__)
        self._model_path = os.path.join(self._model_dir, "correction_model.pt")
        self._stats_path = os.path.join(self._model_dir, "correction_stats.json")

        self._model: Optional[ResidualCorrector] = None
        self._device = "cpu"
        self._is_trained = False
        self._train_count = 0

        if HAS_TORCH:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"

    # ─── 训练 ────────────────────────────────────────────────────

    def train(self, dataset: ShotDataset, epochs: int = 100,
              lr: float = 0.001, verbose: bool = True) -> dict:
        """训练修正模型

        Args:
            dataset: 训练数据集
            epochs: 训练轮数
            lr: 学习率

        Returns:
            训练结果统计
        """
        if not HAS_TORCH:
            return {"error": "PyTorch not available", "samples": len(dataset)}

        if len(dataset) < self._min_samples:
            return {"error": f"Not enough samples ({len(dataset)} < {self._min_samples})",
                    "samples": len(dataset)}

        # 准备数据
        train_set, val_set = dataset.split(0.8)
        X_train = torch.tensor([s.features for s in train_set],
                                dtype=torch.float32, device=self._device)
        y_train = torch.tensor([s.residual for s in train_set],
                                dtype=torch.float32, device=self._device)
        X_val = torch.tensor([s.features for s in val_set],
                              dtype=torch.float32, device=self._device)
        y_val = torch.tensor([s.residual for s in val_set],
                              dtype=torch.float32, device=self._device)

        # 创建/重置模型
        input_dim = X_train.shape[1]
        self._model = ResidualCorrector(input_dim=input_dim).to(self._device)
        optimizer = torch.optim.Adam(self._model.parameters(), lr=lr)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, patience=10, factor=0.5)

        best_val_loss = float("inf")
        best_state = None

        for epoch in range(epochs):
            self._model.train()
            optimizer.zero_grad()
            pred = self._model(X_train)
            loss = F.mse_loss(pred, y_train)
            loss.backward()
            optimizer.step()

            # Validation
            if epoch % 10 == 0 or epoch == epochs - 1:
                self._model.eval()
                with torch.no_grad():
                    val_pred = self._model(X_val)
                    val_loss = F.mse_loss(val_pred, y_val).item()
                scheduler.step(val_loss)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    best_state = self._model.state_dict().copy()

                if verbose:
                    print(f"  Epoch {epoch:3d}: train_loss={loss.item():.6f}, "
                          f"val_loss={val_loss:.6f}")

        # Restore best model
        if best_state:
            self._model.load_state_dict(best_state)

        self._is_trained = True
        self._train_count = len(dataset)

        # Save
        self.save()

        return {
            "samples": len(dataset),
            "train_samples": len(train_set),
            "val_samples": len(val_set),
            "best_val_loss": round(best_val_loss, 6),
            "device": self._device,
        }

    # ─── 推理 ────────────────────────────────────────────────────

    def predict(self, features: List[float]) -> List[float]:
        """预测残差修正量

        Args:
            features: 12维输入特征

        Returns:
            6维残差输出
        """
        if not self._is_trained or not HAS_TORCH or self._model is None:
            return [0.0] * 6

        self._model.eval()
        x = torch.tensor([features], dtype=torch.float32, device=self._device)
        with torch.no_grad():
            y = self._model(x)
        return y[0].cpu().tolist()

    def predict_batch(self, features_batch: List[List[float]]) -> List[List[float]]:
        """批量预测"""
        if not self._is_trained or not HAS_TORCH or self._model is None:
            return [[0.0] * 6 for _ in features_batch]

        self._model.eval()
        x = torch.tensor(features_batch, dtype=torch.float32, device=self._device)
        with torch.no_grad():
            y = self._model(x)
        return y.cpu().tolist()

    # ─── 状态查询 ────────────────────────────────────────────────

    def is_trained(self) -> bool:
        return self._is_trained

    def get_train_count(self) -> int:
        return self._train_count

    def get_param_count(self) -> int:
        """返回模型参数量"""
        if self._model is None:
            return 0
        return sum(p.numel() for p in self._model.parameters())

    # ─── 持久化 ───────────────────────────────────────────────────

    def save(self, path: str = "") -> None:
        """保存模型和训练统计"""
        if self._model is None or not HAS_TORCH:
            return
        path = path or self._model_path
        torch.save(self._model.state_dict(), path)
        with open(self._stats_path, "w") as f:
            json.dump({
                "is_trained": self._is_trained,
                "train_count": self._train_count,
            }, f)

    def load(self, path: str = "") -> bool:
        """加载模型"""
        if not HAS_TORCH:
            return False
        path = path or self._model_path
        if not os.path.exists(path):
            return False

        self._model = ResidualCorrector().to(self._device)
        self._model.load_state_dict(torch.load(path, map_location=self._device))
        self._model.eval()

        if os.path.exists(self._stats_path):
            with open(self._stats_path) as f:
                stats = json.load(f)
                self._is_trained = stats.get("is_trained", True)
                self._train_count = stats.get("train_count", 0)
        else:
            self._is_trained = True

        return True
