# Diffusion Trajectory Model 实现计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐条实现。步骤使用 `- [ ]` checkbox 语法追踪。

**目标:** 用 Diffusion 模型替代简化的几何物理引擎，直接从球状态预测完整轨迹

**架构:** 213M 参数 Diffusion 模型 — Condition Encoder(28M) 编码桌面+球+击球信息 → Denoising U-Net(175M) 在条件引导下迭代去噪 → Trajectory Head(10M) 输出 16球×300帧 的位置/速度/事件序列

**技术栈:** Python + PyTorch + diffusers + torchvision，硬性依赖 torch >= 2.1（DirectML 支持 7900 XTX），推理 < 50ms

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/learning/synthetic_data.py` | 新建 | 物理引擎扰动生成合成轨迹 |
| `backend/learning/diffusion_condition.py` | 新建 | 4路条件编码器 |
| `backend/learning/diffusion_unet.py` | 新建 | 6级去噪 U-Net |
| `backend/learning/diffusion_trainer.py` | 新建 | 训练循环（预训练/微调） |
| `backend/learning/diffusion_model.py` | 新建 | DiffusionTrajectoryModel 主类 |
| `backend/learning/trajectory_collector.py` | 新建 | 轨迹数据后台采集 |
| `backend/physics/engine.py` | 修改 | 新增 `generate_trajectory()` |
| `backend/learning/__init__.py` | 修改 | 导出新增模块 |
| `backend/main.py` | 修改 | 集成模型 + 采集器 |
| `backend/api/routes.py` | 修改 | 新增 7 个 REST 端点 |
| `backend/api/websocket.py` | 修改 | 新增 model_status 消息 |
| `backend/learning/test_diffusion.py` | 新建 | 模型单元测试 |

---

### Task 1: Synthetic Data Generator

**文件:**
- 新建: `backend/learning/synthetic_data.py`
- 新建测试: `backend/learning/test_diffusion.py`（首测函数）

**职责:** 用 PhysicsEngine 生成 50K 条带参数扰动的合成轨迹，输出训练数据集

- [ ] **Step 1: 写测试 — 验证单条轨迹的形状和范围**

```python
# backend/learning/test_diffusion.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import torch
import numpy as np


def test_synthetic_trajectory_shape():
    """单条合成轨迹的 shapes 正确"""
    from learning.synthetic_data import SyntheticDataGenerator

    gen = SyntheticDataGenerator(num_frames=300)
    sample = gen.generate_one()

    # 初始球状态
    assert sample["initial_balls"].shape == (16, 8)  # [x,y,vx,vy,4类型]
    # 轨迹
    assert sample["trajectory"].shape == (16, 300, 2)
    # 事件
    assert sample["events"].shape == (300, 4)
    # 击球参数
    assert len(sample["shot_params"]) == 3
    # 物理路径（条件）
    assert sample["physics_path"].shape == (2, 8, 2)  # 母球+目标球，各8点
    # 值域检查
    assert 0 <= sample["trajectory"].min() <= sample["trajectory"].max() <= 1


def test_synthetic_dataset_size():
    """生成的数据集大小正确"""
    from learning.synthetic_data import SyntheticDataGenerator
    gen = SyntheticDataGenerator(num_frames=300)
    dataset = gen.generate(num_samples=100)
    assert len(dataset) == 100


def test_trajectory_perturbation():
    """扰动后的轨迹与基准不同"""
    from learning.synthetic_data import SyntheticDataGenerator
    gen = SyntheticDataGenerator(num_frames=300)
    s1 = gen.generate_one()
    s2 = gen.generate_one()
    # 两次生成的轨迹不应完全相同（随机扰动）
    diff = (s1["trajectory"] - s2["trajectory"]).abs().sum()
    assert diff > 0.01
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest learning/test_diffusion.py -v 2>&1 | tail -5
# Expected: ModuleNotFoundError / ImportError
```

- [ ] **Step 3: 实现 SyntheticDataGenerator**

```python
# backend/learning/synthetic_data.py
"""合成数据生成器 — 用物理引擎 + 参数扰动生成训练用轨迹"""
import random
import math
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass
class SyntheticConfig:
    num_frames: int = 300
    ball_types: List[str] = field(default_factory=lambda: [
        "cue", "solid", "solid", "solid", "solid", "solid", "solid", "solid",
        "black", "stripe", "stripe", "stripe", "stripe", "stripe", "stripe", "stripe",
    ])
    # 扰动范围
    power_noise: float = 0.15      # 力度 ±15%
    cushion_noise: float = 0.10    # 弹性 ±10%
    pocket_noise: float = 0.08     # 袋口半径 ±8%
    angle_noise_deg: float = 3.0   # 角度 ±3°
    friction_noise: float = 0.15   # 摩擦 ±15%


class SyntheticDataGenerator:
    """合成数据生成器 — 物理引擎扰动"""

    def __init__(self, num_frames: int = 300, seed: int = 42):
        self.config = SyntheticConfig(num_frames=num_frames)
        self._rng = np.random.RandomState(seed)
        self._physics = None  # lazy init

    def _get_physics(self):
        if self._physics is None:
            from physics.engine import PhysicsEngine
            self._physics = PhysicsEngine()
        return self._physics

    def generate(self, num_samples: int = 50000) -> List[Dict]:
        """生成 num_samples 条合成轨迹"""
        samples = []
        for i in range(num_samples):
            s = self.generate_one()
            if s is not None:
                samples.append(s)
            if (i + 1) % 5000 == 0:
                print(f"[Synth] Generated {i + 1}/{num_samples}")
        return samples

    def generate_one(self) -> Optional[Dict]:
        """生成单条随机合成轨迹 — 返回数据字典或 None（无效生成时）"""
        physics = self._get_physics()
        from physics.engine import Vec2
        r = self._rng

        # 1. 随机生成球分布
        balls = self._random_ball_positions(r)

        # 2. 随机选母球和目标球
        cue_ball = balls[0]  # 第0个总是母球
        target_idx = r.randint(1, 15)
        target_ball = balls[target_idx]

        # 3. 随机选袋口
        pocket_idx = r.randint(0, 5)
        pocket = physics.POCKETS[pocket_idx]

        # 4. 物理引擎计算基准路线
        cue_vec = Vec2(cue_ball[0], cue_ball[1])
        target_vec = Vec2(target_ball[0], target_ball[1])
        result = physics.find_best_shot(cue_vec, target_vec)
        if not result.success:
            return None  # 不可行组合，跳过

        # 5. 随机参数扰动
        power = r.uniform(0.2, 1.0)
        spin_x = r.uniform(-1.0, 1.0)
        spin_y = r.uniform(-1.0, 1.0)
        shot_params = np.array([power, spin_x, spin_y], dtype=np.float32)

        # 6. 生成扰动轨迹（分段线性插值 + 噪声）
        trajectory = self._build_perturbed_trajectory(
            balls, result, power, r, physics)

        # 7. 构建事件序列
        events = self._build_events(trajectory, target_idx, pocket, r)

        # 8. 物理路径（条件引导用）
        physics_path = self._build_physics_path(result)

        # 9. 初始球状态编码
        initial_balls = np.zeros((16, 8), dtype=np.float32)
        for i, b in enumerate(balls):
            initial_balls[i, 0] = b[0]           # x
            initial_balls[i, 1] = b[1]           # y
            initial_balls[i, 2] = 0.0            # vx
            initial_balls[i, 3] = 0.0            # vy
            bt = self.config.ball_types[i]
            initial_balls[i, 4] = 1.0 if bt == "cue" else 0.0
            initial_balls[i, 5] = 1.0 if bt == "black" else 0.0
            initial_balls[i, 6] = 1.0 if bt == "solid" else 0.0
            initial_balls[i, 7] = 1.0 if bt == "stripe" else 0.0

        return {
            "initial_balls": initial_balls,
            "trajectory": trajectory,
            "events": events,
            "shot_params": shot_params,
            "physics_path": physics_path,
            "target_idx": target_idx,
            "pocket_idx": pocket_idx,
        }

    def _random_ball_positions(self, rng) -> List[Tuple[float, float]]:
        """在桌面内随机放置球，避免重叠"""
        MIN_DIST = 0.04  # 球心最小距离（归一化）
        positions = []
        attempts = 0
        while len(positions) < 16 and attempts < 1000:
            x = rng.uniform(0.08, 0.92)
            y = rng.uniform(0.08, 0.92)
            ok = True
            for px, py in positions:
                if ((x - px) ** 2 + (y - py) ** 2) ** 0.5 < MIN_DIST:
                    ok = False
                    break
            if ok:
                positions.append((x, y))
            attempts += 1
        # 不够16颗用随机补
        while len(positions) < 16:
            positions.append((rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9)))
        return positions

    def _build_perturbed_trajectory(self, balls, result, power,
                                     rng, physics) -> np.ndarray:
        """生成带扰动的 16×300×2 轨迹"""
        F = self.config.num_frames
        traj = np.zeros((16, F, 2), dtype=np.float32)

        # 所有球初始位置
        for i, b in enumerate(balls):
            traj[i, 0, 0] = b[0]
            traj[i, 0, 1] = b[1]

        # 模拟母球轨迹
        cue_path = [(p.x, p.y) for p in result.cue_path]
        target_path = [(p.x, p.y) for p in result.target_path]

        # 母球：沿 cue_path 插值
        cue_start = cue_path[0]
        cue_end = cue_path[-1] if len(cue_path) > 1 else cue_start
        # 扰动力度 → 速度变化
        speed_scale = power * (1.0 + rng.uniform(-self.config.power_noise,
                                                  self.config.power_noise))
        # 分段：加速→匀速→减速
        accel_frames = max(1, int(F * 0.05))   # 前5%加速
        coast_frames = int(F * (0.4 + speed_scale * 0.3))  # 中段匀速
        decel_frames = F - accel_frames - coast_frames

        # 角度扰动
        angle_noise = rng.uniform(-self.config.angle_noise_deg,
                                   self.config.angle_noise_deg) * math.pi / 180
        dx = cue_end[0] - cue_start[0]
        dy = cue_end[1] - cue_start[1]
        cos_a, sin_a = math.cos(angle_noise), math.sin(angle_noise)
        dx_n = dx * cos_a - dy * sin_a
        dy_n = dx * sin_a + dy * cos_a

        # 摩擦扰动
        friction = physics.BALL_FRICTION * (1.0 + rng.uniform(
            -self.config.friction_noise, self.config.friction_noise))

        # 逐帧填充母球轨迹
        for t in range(1, F):
            progress = min(t / F, 1.0)
            if t <= accel_frames:
                alpha = t / accel_frames * 0.5
            elif t <= accel_frames + coast_frames:
                alpha = 0.5 + (t - accel_frames) / coast_frames * 0.5
            else:
                # 减速段：摩擦减速
                remain = F - t
                decel_progress = remain / decel_frames
                alpha = 1.0 - 0.5 * decel_progress * decel_progress

            # 目标球：碰撞后移动
            tgt_start_frame = max(1, int(F * 0.15))
            tgt_end_frame = min(F, tgt_start_frame + int(F * 0.35))

            # 母球新位置
            nx = cue_start[0] + dx_n * alpha
            ny = cue_start[1] + dy_n * alpha
            npx = nx + rng.normal(0, 0.001)
            npy = ny + rng.normal(0, 0.001)
            traj[0, t, 0] = float(np.clip(npx, 0.01, 0.99))
            traj[0, t, 1] = float(np.clip(npy, 0.01, 0.99))

            # 目标球：母球碰到之后才开始动
            target_idx = int(np.argmax([traj[i, 0, 0] for i in range(1, 16)])) + 1
            # 简化：目标球在碰撞帧后开始沿 target_path 移动
            for i in range(1, 16):
                if i == target_idx:
                    if t >= tgt_start_frame:
                        tp = min(1.0, (t - tgt_start_frame) / (tgt_end_frame - tgt_start_frame))
                        tx0, ty0 = target_path[0]
                        if len(target_path) > 1:
                            tx1, ty1 = target_path[-1]
                            traj[i, t, 0] = tx0 + (tx1 - tx0) * tp + rng.normal(0, 0.001)
                            traj[i, t, 1] = ty0 + (ty1 - ty0) * tp + rng.normal(0, 0.001)
                        else:
                            traj[i, t, 0] = tx0
                            traj[i, t, 1] = ty0
                else:
                    # 其他球不动
                    traj[i, t, 0] = traj[i, t - 1, 0]
                    traj[i, t, 1] = traj[i, t - 1, 1]

        return traj

    def _build_events(self, traj: np.ndarray, target_idx: int,
                       pocket: 'Vec2', rng) -> np.ndarray:
        """构建 300×4 事件序列：0=无,1=碰撞,2=进袋,3=停止"""
        F = self.config.num_frames
        events = np.zeros((F, 4), dtype=np.float32)
        events[:, 0] = 1.0  # 默认无事件

        # 碰撞帧（~第 15% 处）
        collision_f = int(F * 0.15) + rng.randint(-3, 4)
        collision_f = max(2, min(F - 10, collision_f))
        events[collision_f, 0] = 0.0
        events[collision_f, 1] = 1.0  # 碰撞

        # 入袋帧（~第 50% 处）
        pocket_f = int(F * 0.50) + rng.randint(-5, 5)
        pocket_f = max(collision_f + 5, min(F - 5, pocket_f))
        events[pocket_f, 0] = 0.0
        events[pocket_f, 2] = 1.0  # 进袋

        # 停止帧（~第 80% 处）
        stop_f = int(F * 0.85) + rng.randint(-10, 10)
        stop_f = max(pocket_f + 5, min(F - 2, stop_f))
        events[stop_f, 0] = 0.0
        events[stop_f, 3] = 1.0  # 全部停止
        events[stop_f:, 3] = 1.0
        events[stop_f:, 0] = 0.0

        return events

    def _build_physics_path(self, result) -> np.ndarray:
        """构建物理引擎路线作为条件 (2球 × 8点 × 2坐标)"""
        path = np.zeros((2, 8, 2), dtype=np.float32)
        cue_pts = [(p.x, p.y) for p in result.cue_path]
        target_pts = [(p.x, p.y) for p in result.target_path]

        for j, (x, y) in enumerate(cue_pts[:8]):
            path[0, j, 0] = x
            path[0, j, 1] = y
        for j, (x, y) in enumerate(target_pts[:8]):
            path[1, j, 0] = x
            path[1, j, 1] = y
        return path

    def to_tensors(self, samples: List[Dict]) -> Dict[str, 'torch.Tensor']:
        """将样本列表转为训练用张量"""
        if not HAS_TORCH:
            raise RuntimeError("PyTorch required")
        import torch
        N = len(samples)
        traj = torch.zeros(N, 16, self.config.num_frames, 2)
        init_balls = torch.zeros(N, 16, 8)
        events = torch.zeros(N, self.config.num_frames, 4, dtype=torch.long)
        shot_params = torch.zeros(N, 3)
        phys_path = torch.zeros(N, 2, 8, 2)

        for i, s in enumerate(samples):
            traj[i] = torch.from_numpy(s["trajectory"])
            init_balls[i] = torch.from_numpy(s["initial_balls"])
            events[i] = torch.from_numpy(s["events"]).argmax(dim=-1)
            shot_params[i] = torch.from_numpy(s["shot_params"])
            phys_path[i] = torch.from_numpy(s["physics_path"])

        return {
            "trajectory": traj,
            "initial_balls": init_balls,
            "events": events,
            "shot_params": shot_params,
            "physics_path": phys_path,
        }
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest learning/test_diffusion.py -v
# Expected: 3 tests PASS
```

- [ ] **Step 5: Commit**

```bash
git add backend/learning/synthetic_data.py backend/learning/test_diffusion.py
git commit -m "feat: add synthetic trajectory data generator with physics engine perturbation"
```

---

### Task 2: Condition Encoder

**文件:**
- 新建: `backend/learning/diffusion_condition.py`
- 追加测试: `backend/learning/test_diffusion.py`

**职责:** 将桌面图像、球状态、击球参数、物理路线 4 路编码融合为条件嵌入

- [ ] **Step 1: 写测试 — 验证输出形状**

```python
# 追加到 backend/learning/test_diffusion.py

def test_condition_encoder_output_shape():
    """条件编码器输出形状正确 (1, 32, 512)"""
    import torch
    from learning.diffusion_condition import ConditionEncoder, ConditionInput

    encoder = ConditionEncoder(condition_dim=512, spatial_tokens=32)
    # 构造假输入
    table_image = torch.randn(1, 3, 600, 1200)          # 1×3×600×1200
    ball_states = torch.randn(1, 16, 8)                  # 1×16×8
    shot_params = torch.randn(1, 3)                       # 1×3
    physics_path = torch.randn(1, 2, 8, 2)                # 1×2×8×2

    cond = encoder(table_image, ball_states, shot_params, physics_path)
    assert cond.shape == (1, 32, 512), f"Expected (1,32,512), got {cond.shape}"


def test_condition_encoder_no_physics():
    """不传入物理路线时不出错"""
    import torch
    from learning.diffusion_condition import ConditionEncoder
    encoder = ConditionEncoder()
    cond = encoder(
        torch.randn(1, 3, 600, 1200),
        torch.randn(1, 16, 8),
        torch.randn(1, 3),
        None  # no physics path
    )
    assert cond.shape == (1, 32, 512)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest learning/test_diffusion.py::test_condition_encoder_output_shape -v
# Expected: ImportError / ModuleNotFoundError
```

- [ ] **Step 3: 实现 ConditionEncoder**

```python
# backend/learning/diffusion_condition.py
"""条件编码器 — 将桌面图像+球状态+击球参数+物理路线融合为条件嵌入"""
from typing import Optional
import torch
import torch.nn as nn
import torch.nn.functional as F


class ConditionEncoder(nn.Module):
    """4 路条件融合编码器

    输入:
      - 桌面俯视图 (B, 3, 600, 1200)
      - 球状态     (B, 16, 8)
      - 击球参数   (B, 3)
      - 物理路线   (B, 2, 8, 2) | None

    输出:
      - 条件嵌入   (B, 32, 512)
    """

    def __init__(self, condition_dim: int = 512,
                 spatial_tokens: int = 32,
                 ball_hidden: int = 128,
                 num_attn_heads: int = 8):
        super().__init__()
        self.condition_dim = condition_dim
        self.spatial_tokens = spatial_tokens

        # ── 桌面编码器: ResNet50 截断 ──
        try:
            import torchvision.models as tvm
            resnet = tvm.resnet50(weights=None)
            self.table_encoder = nn.Sequential(
                resnet.conv1,     # 64ch, /2
                resnet.bn1,
                resnet.relu,
                resnet.maxpool,   # /4
                resnet.layer1,    # 256ch, /4
                resnet.layer2,    # 512ch, /8
            )
            table_out_ch = 512
        except ImportError:
            # Fallback: simple conv stack
            self.table_encoder = nn.Sequential(
                nn.Conv2d(3, 64, 7, stride=2, padding=3),
                nn.BatchNorm2d(64), nn.ReLU(),
                nn.MaxPool2d(3, stride=2, padding=1),
                nn.Conv2d(64, 128, 3, stride=2, padding=1),
                nn.BatchNorm2d(128), nn.ReLU(),
                nn.Conv2d(128, 256, 3, stride=2, padding=1),
                nn.BatchNorm2d(256), nn.ReLU(),
                nn.Conv2d(256, 512, 3, stride=2, padding=1),
                nn.BatchNorm2d(512), nn.ReLU(),
            )
            table_out_ch = 512

        # ResNet layer2 输出: (B, 512, H/8, W/8) = (B, 512, 75, 150)
        # 自适应池化到 (B, 512, 4, 8) = 32 tokens
        self.table_pool = nn.AdaptiveAvgPool2d((4, 8))
        self.table_proj = nn.Linear(table_out_ch, condition_dim)  # 512→512

        # ── 球状态编码器: Self-Attention ──
        self.ball_proj = nn.Linear(8, ball_hidden)
        self.ball_ln = nn.LayerNorm(ball_hidden)
        ball_encoder_layer = nn.TransformerEncoderLayer(
            d_model=ball_hidden, nhead=num_attn_heads,
            dim_feedforward=ball_hidden * 2, batch_first=True,
            dropout=0.1)
        self.ball_encoder = nn.TransformerEncoder(
            ball_encoder_layer, num_layers=2)
        # 汇聚 16 球 → 1 tokens，广播到 32
        self.ball_to_cond = nn.Sequential(
            nn.Linear(ball_hidden, condition_dim),
            nn.LayerNorm(condition_dim),
        )

        # ── 击球参数编码器 ──
        self.shot_proj = nn.Sequential(
            nn.Linear(3, 64),
            nn.SiLU(),
            nn.Linear(64, condition_dim),
        )

        # ── 物理路线编码器 ──
        self.physics_proj = nn.Sequential(
            nn.Linear(2 * 8 * 2, 64),   # 2球×8点×2坐标
            nn.SiLU(),
            nn.Linear(64, condition_dim),
        )

        # ── 融合投影 ──
        self.fusion = nn.Sequential(
            nn.Linear(condition_dim * 4, condition_dim * 2),
            nn.LayerNorm(condition_dim * 2),
            nn.SiLU(),
            nn.Linear(condition_dim * 2, condition_dim),
            nn.LayerNorm(condition_dim),
        )

    def forward(self, table_image: torch.Tensor,
                ball_states: torch.Tensor,
                shot_params: torch.Tensor,
                physics_path: Optional[torch.Tensor] = None
                ) -> torch.Tensor:
        B = table_image.shape[0]

        # 1. 桌面特征 (B, 32, condition_dim)
        table_feat = self.table_encoder(table_image)
        table_feat = self.table_pool(table_feat)          # (B, 512, 4, 8)
        table_feat = table_feat.flatten(2).transpose(1, 2)  # (B, 32, 512)
        table_feat = self.table_proj(table_feat)           # (B, 32, condition_dim)

        # 2. 球状态 (B, 16, ball_hidden) → 汇聚 (B, condition_dim)
        ball_feat = self.ball_proj(ball_states)
        ball_feat = self.ball_ln(ball_feat)
        ball_feat = self.ball_encoder(ball_feat)
        ball_feat = ball_feat.mean(dim=1)                  # (B, ball_hidden)
        ball_feat = self.ball_to_cond(ball_feat)           # (B, condition_dim)
        ball_feat = ball_feat.unsqueeze(1).expand(-1, self.spatial_tokens, -1)

        # 3. 击球参数 (B, condition_dim) → 广播
        shot_feat = self.shot_proj(shot_params)             # (B, condition_dim)
        shot_feat = shot_feat.unsqueeze(1).expand(-1, self.spatial_tokens, -1)

        # 4. 物理路线 (B, condition_dim) → 广播，无则填零
        if physics_path is not None:
            phys_flat = physics_path.reshape(B, -1)
            phys_feat = self.physics_proj(phys_flat)
        else:
            phys_feat = torch.zeros(B, self.condition_dim,
                                    device=table_image.device)
        phys_feat = phys_feat.unsqueeze(1).expand(-1, self.spatial_tokens, -1)

        # 5. 融合
        fused = torch.cat([table_feat, ball_feat, shot_feat, phys_feat], dim=-1)
        condition = self.fusion(fused)  # (B, 32, condition_dim)

        return condition
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest learning/test_diffusion.py -v
# Expected: all tests PASS (including previous 3)
```

- [ ] **Step 5: Commit**

```bash
git add backend/learning/diffusion_condition.py backend/learning/test_diffusion.py
git commit -m "feat: add 4-way condition encoder (table+balls+shot+physics)"
```

---

### Task 3: Denoising U-Net

**文件:**
- 新建: `backend/learning/diffusion_unet.py`
- 追加测试: `backend/learning/test_diffusion.py`

**职责:** 6级编解码 U-Net，Cross-Attention 接收条件嵌入，逐级去噪

- [ ] **Step 1: 写测试 — 验证输入输出形状和对噪声的响应**

```python
# 追加到 backend/learning/test_diffusion.py

def test_unet_forward_shape():
    """U-Net 输出形状 = 输入形状"""
    import torch
    from learning.diffusion_unet import TrajectoryUNet

    B, N_BALLS, N_FRAMES, COORD = 2, 16, 300, 2
    unet = TrajectoryUNet(
        n_balls=N_BALLS, n_frames=N_FRAMES, coord_dim=COORD,
        condition_dim=512, spatial_tokens=32,
    )
    x = torch.randn(B, N_BALLS, N_FRAMES, COORD)
    t = torch.randint(0, 1000, (B,))
    condition = torch.randn(B, 32, 512)

    out = unet(x, t, condition)
    assert out.shape == x.shape, f"Expected {x.shape}, got {out.shape}"


def test_unet_denoising_behavior():
    """U-Net 对噪声输入能给出非零输出（即模型在工作）"""
    import torch
    from learning.diffusion_unet import TrajectoryUNet
    unet = TrajectoryUNet(n_balls=16, n_frames=300)
    unet.train()
    x_noisy = torch.randn(1, 16, 300, 2)
    t = torch.tensor([500], dtype=torch.long)
    cond = torch.randn(1, 32, 512)
    out = unet(x_noisy, t, cond)
    # 非零输出 — 模型确实做了预测
    assert out.abs().sum() > 0.01
    # 输出不应等于输入（做了变换）
    assert not torch.allclose(out, x_noisy, atol=1e-3)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest learning/test_diffusion.py::test_unet_forward_shape -v
# Expected: ImportError / ModuleNotFoundError
```

- [ ] **Step 3: 实现 TrajectoryUNet**

```python
# backend/learning/diffusion_unet.py
"""Denoising U-Net — 6级编解码器，Cross-Attention 连接条件嵌入"""
import math
import torch
import torch.nn as nn
import torch.nn.functional as F


def get_timestep_embedding(timesteps: torch.Tensor, dim: int,
                           max_period: int = 10000) -> torch.Tensor:
    """Sinusoidal 时间步嵌入 (与 DDPM 一致)"""
    half = dim // 2
    freqs = torch.exp(-math.log(max_period) *
                      torch.arange(0, half, dtype=torch.float32) / half)
    freqs = freqs.to(timesteps.device)
    args = timesteps.float().unsqueeze(1) * freqs.unsqueeze(0)
    emb = torch.cat([torch.cos(args), torch.sin(args)], dim=-1)
    if dim % 2:
        emb = F.pad(emb, (0, 1))
    return emb


class TimeEmbed(nn.Module):
    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim
        self.mlp = nn.Sequential(
            nn.Linear(dim, dim * 4),
            nn.SiLU(),
            nn.Linear(dim * 4, dim),
        )

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        emb = get_timestep_embedding(t, self.dim)
        return self.mlp(emb)


class ResBlock1D(nn.Module):
    """1D 残差块 + 时间嵌入 + GroupNorm"""

    def __init__(self, ch: int, time_dim: int, dropout: float = 0.1):
        super().__init__()
        self.norm1 = nn.GroupNorm(8, ch)
        self.conv1 = nn.Conv1d(ch, ch, kernel_size=3, padding=1)
        self.norm2 = nn.GroupNorm(8, ch)
        self.conv2 = nn.Conv1d(ch, ch, kernel_size=3, padding=1)
        self.time_proj = nn.Linear(time_dim, ch)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor, t_emb: torch.Tensor) -> torch.Tensor:
        # x: (B*N_balls, C, N_frames)
        h = self.norm1(x)
        h = F.silu(h)
        h = self.conv1(h)
        # 注入时间嵌入
        h = h + self.time_proj(t_emb)[:, :, None]
        h = self.norm2(h)
        h = F.silu(h)
        h = self.dropout(h)
        h = self.conv2(h)
        return x + h


class SelfAttention1D(nn.Module):
    """1D Self-Attention over time dimension"""

    def __init__(self, ch: int, n_heads: int = 8):
        super().__init__()
        self.norm = nn.LayerNorm(ch)
        self.attn = nn.MultiheadAttention(ch, n_heads, batch_first=True,
                                          dropout=0.1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, C, L) → (B, L, C) → attn → (B, L, C) → (B, C, L)
        B, C, L = x.shape
        x_t = x.transpose(1, 2)
        x_norm = self.norm(x_t)
        x_attn, _ = self.attn(x_norm, x_norm, x_norm)
        return (x_t + x_attn).transpose(1, 2)


class CrossAttention1D(nn.Module):
    """Cross-Attention to condition embedding"""

    def __init__(self, ch: int, cond_dim: int, n_heads: int = 8):
        super().__init__()
        self.norm_q = nn.LayerNorm(ch)
        self.norm_kv = nn.LayerNorm(cond_dim)
        self.attn = nn.MultiheadAttention(ch, n_heads, batch_first=True,
                                          dropout=0.1, kdim=cond_dim, vdim=cond_dim)

    def forward(self, x: torch.Tensor, condition: torch.Tensor) -> torch.Tensor:
        # x: (B*N_balls, C, L), condition: (B, 32, cond_dim)
        Bn, C, L = x.shape
        # Expand condition per ball
        n_balls = Bn // condition.shape[0]
        cond_expanded = condition.repeat_interleave(n_balls, dim=0)  # (B*N, 32, cond_dim)
        x_t = x.transpose(1, 2)  # (B*N, L, C)
        q = self.norm_q(x_t)
        kv = self.norm_kv(cond_expanded)
        x_attn, _ = self.attn(q, kv, kv)
        return (x_t + x_attn).transpose(1, 2)


class DownBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, time_dim: int,
                 cond_dim: int, n_heads: int = 8, has_cross: bool = False):
        super().__init__()
        self.res = ResBlock1D(in_ch, time_dim)
        self.attn = SelfAttention1D(in_ch, n_heads)
        self.cross = CrossAttention1D(in_ch, cond_dim, n_heads) if has_cross else None
        self.down = nn.Conv1d(in_ch, out_ch, kernel_size=3, stride=2, padding=1)

    def forward(self, x: torch.Tensor, t_emb: torch.Tensor,
                condition: torch.Tensor) -> torch.Tensor:
        x = self.res(x, t_emb)
        x = self.attn(x)
        if self.cross is not None:
            x = self.cross(x, condition)
        skip = x
        x = self.down(x)
        return x, skip


class UpBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, skip_ch: int,
                 time_dim: int, cond_dim: int, n_heads: int = 8,
                 has_cross: bool = False):
        super().__init__()
        # Upsample then conv to match skip
        self.upsample = nn.ConvTranspose1d(in_ch, out_ch,
                                            kernel_size=4, stride=2, padding=1)
        # Input channels after concat with skip
        self.res = ResBlock1D(out_ch + skip_ch, time_dim)
        self.attn = SelfAttention1D(out_ch + skip_ch, n_heads)
        self.cross = CrossAttention1D(out_ch + skip_ch, cond_dim,
                                       n_heads) if has_cross else None
        self.out_conv = nn.Conv1d(out_ch + skip_ch, out_ch, kernel_size=3, padding=1)

    def forward(self, x: torch.Tensor, skip: torch.Tensor,
                t_emb: torch.Tensor, condition: torch.Tensor) -> torch.Tensor:
        x = self.upsample(x)
        # Align lengths (upsample may be off by 1)
        if x.shape[-1] != skip.shape[-1]:
            x = F.interpolate(x, size=skip.shape[-1], mode='linear')
        x = torch.cat([x, skip], dim=1)
        x = self.res(x, t_emb)
        x = self.attn(x)
        if self.cross is not None:
            x = self.cross(x, condition)
        x = self.out_conv(x)
        return x


class TrajectoryUNet(nn.Module):
    """6级编解码 U-Net — 轨迹去噪主干

    输入: (B, 16, 300, 2) 噪声轨迹 → 输出: (B, 16, 300, 2) 预测噪声/轨迹
    """

    def __init__(self, n_balls: int = 16, n_frames: int = 300,
                 coord_dim: int = 2, condition_dim: int = 512,
                 spatial_tokens: int = 32,
                 base_ch: int = 64, time_dim: int = 256):
        super().__init__()
        self.n_balls = n_balls
        self.n_frames = n_frames
        self.coord_dim = coord_dim

        self.time_embed = TimeEmbed(time_dim)

        # 输入投影
        self.input_proj = nn.Conv1d(coord_dim, base_ch, kernel_size=3, padding=1)

        ch_mult = [1, 2, 4, 4, 6, 8]
        self.down_blocks = nn.ModuleList()
        in_ch = base_ch
        ch_list = []
        for i, mult in enumerate(ch_mult):
            out_ch = base_ch * mult
            has_cross = (i >= 2)  # L2 onwards: cross-attention to condition
            self.down_blocks.append(
                DownBlock(in_ch, out_ch, time_dim, condition_dim,
                          n_heads=8 if i < 4 else 12, has_cross=has_cross))
            ch_list.append(in_ch)
            in_ch = out_ch

        # Bottleneck
        self.bottleneck_res = ResBlock1D(in_ch, time_dim)
        self.bottleneck_cross = CrossAttention1D(in_ch, condition_dim, n_heads=16)
        self.bottleneck_ffn = nn.Sequential(
            nn.Conv1d(in_ch, in_ch * 2, 1),
            nn.GELU(),
            nn.Conv1d(in_ch * 2, in_ch, 1),
        )

        self.up_blocks = nn.ModuleList()
        for i, mult in enumerate(reversed(ch_mult)):
            out_ch = base_ch * mult
            skip_ch = ch_list[-(i + 1)]
            has_cross = (len(ch_mult) - 1 - i >= 2)
            self.up_blocks.append(
                UpBlock(in_ch, out_ch, skip_ch, time_dim, condition_dim,
                        n_heads=8, has_cross=has_cross))
            in_ch = out_ch

        self.output_conv = nn.Sequential(
            nn.GroupNorm(8, base_ch),
            nn.SiLU(),
            nn.Conv1d(base_ch, base_ch // 2, kernel_size=3, padding=1),
            nn.GroupNorm(4, base_ch // 2),
            nn.SiLU(),
            nn.Conv1d(base_ch // 2, coord_dim, kernel_size=3, padding=1),
        )

    def forward(self, x: torch.Tensor, t: torch.Tensor,
                condition: torch.Tensor) -> torch.Tensor:
        """
        x: (B, N_balls, N_frames, 2) — 噪声轨迹
        t: (B,) — 时间步
        condition: (B, spatial_tokens, cond_dim) — 条件嵌入
        returns: (B, N_balls, N_frames, 2) — 预测噪声
        """
        B = x.shape[0]

        # Flatten balls into batch dimension: (B*N, C, L)
        x = x.reshape(B * self.n_balls, self.coord_dim, self.n_frames)

        t_emb = self.time_embed(t)  # (B, time_dim)
        # Expand time embedding per ball
        t_exp = t_emb.repeat_interleave(self.n_balls, dim=0)

        x = self.input_proj(x)

        skips = []
        for block in self.down_blocks:
            x, skip = block(x, t_exp, condition)
            skips.append(skip)

        x = self.bottleneck_res(x, t_exp)
        x = self.bottleneck_cross(x, condition)
        x = x + self.bottleneck_ffn(x)

        for block in self.up_blocks:
            x = block(x, skips.pop(), t_exp, condition)

        x = self.output_conv(x)

        # Reshape back: (B*N, 2, L) → (B, N, L, 2)
        x = x.reshape(B, self.n_balls, self.coord_dim, self.n_frames)
        x = x.permute(0, 1, 3, 2)  # (B, N, L, 2)
        return x
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest learning/test_diffusion.py -v
# Expected: all 7 tests PASS
```

- [ ] **Step 5: Commit**

```bash
git add backend/learning/diffusion_unet.py backend/learning/test_diffusion.py
git commit -m "feat: add 6-level denoising U-Net with cross-attention"
```

---

### Task 4: Trajectory Head & Training Loop

**文件:**
- 新建: `backend/learning/diffusion_trainer.py`
- 追加测试: `backend/learning/test_diffusion.py`

**职责:** 三路输出头 + DDPM 噪声调度 + 训练循环（含 Loss 计算）

- [ ] **Step 1: 写测试 — Loss 下降、checkpoint 可存可读**

```python
# 追加到 backend/learning/test_diffusion.py

def test_training_loss_decreases():
    """单步训练后 loss 非 NaN 且小于初始值"""
    import torch
    from learning.diffusion_unet import TrajectoryUNet
    from learning.diffusion_condition import ConditionEncoder
    from learning.diffusion_trainer import DiffusionTrainer, TrajectoryHeads

    heads = TrajectoryHeads(coord_dim=2, base_ch=64)
    unet = TrajectoryUNet(n_balls=16, n_frames=100)  # 100帧加速测试
    encoder = ConditionEncoder()
    trainer = DiffusionTrainer(
        unet=unet, heads=heads, condition_encoder=encoder,
        n_frames=100, lr=1e-3,
    )
    # Fake batch
    batch = {
        "trajectory": torch.randn(2, 16, 100, 2),
        "initial_balls": torch.randn(2, 16, 8),
        "events": torch.randint(0, 4, (2, 100)),
        "shot_params": torch.randn(2, 3),
        "physics_path": torch.randn(2, 2, 8, 2),
    }
    table = torch.randn(2, 3, 600, 1200)

    losses = []
    for _ in range(5):
        loss_dict = trainer.train_step(batch, table)
        losses.append(loss_dict["total"].item())

    assert losses[-1] <= losses[0], "Loss should decrease"
    for l in losses:
        assert not torch.isnan(torch.tensor(l)), "Loss should not be NaN"


def test_checkpoint_save_load(tmp_path):
    """Checkpoint 保存和加载往返一致"""
    import torch
    from learning.diffusion_trainer import save_checkpoint, load_checkpoint
    from learning.diffusion_unet import TrajectoryUNet
    from learning.diffusion_condition import ConditionEncoder
    from learning.diffusion_trainer import TrajectoryHeads

    unet = TrajectoryUNet()
    heads = TrajectoryHeads()
    encoder = ConditionEncoder()

    path = str(tmp_path / "test_ckpt.pt")
    save_checkpoint(path, unet, heads, encoder, epoch=5, loss=0.123)

    state = load_checkpoint(path, unet, heads, encoder)
    assert state["epoch"] == 5
    assert abs(state["loss"] - 0.123) < 0.001
```

- [ ] **Step 2: 实现 TrajectoryHeads + DiffusionTrainer + checkpoint 工具**

```python
# backend/learning/diffusion_trainer.py
"""Diffusion 训练器 — DDPM 噪声调度 + 三路输出 + 训练循环"""
import os
import math
from typing import Dict, Optional, Tuple
import torch
import torch.nn as nn
import torch.nn.functional as F


class TrajectoryHeads(nn.Module):
    """三路输出头：位置、速度、事件"""

    def __init__(self, coord_dim: int = 2, base_ch: int = 64):
        super().__init__()
        self.pos_head = nn.Sequential(
            nn.Conv1d(base_ch, base_ch // 2, 3, padding=1),
            nn.SiLU(),
            nn.Conv1d(base_ch // 2, coord_dim, 3, padding=1),
        )
        self.vel_head = nn.Sequential(
            nn.Conv1d(base_ch, base_ch // 2, 3, padding=1),
            nn.SiLU(),
            nn.Conv1d(base_ch // 2, coord_dim, 3, padding=1),
        )
        self.event_head = nn.Sequential(
            nn.Conv1d(base_ch, base_ch // 2, 3, padding=1),
            nn.SiLU(),
            nn.Conv1d(base_ch // 2, 4, 3, padding=1),  # 4 classes
        )

    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """x: (B*N, base_ch, n_frames) from U-Net output (before last conv)"""
        return {
            "positions": self.pos_head(x),
            "velocities": self.vel_head(x),
            "events": self.event_head(x),  # logits
        }


def linear_beta_schedule(timesteps: int, beta_start: float = 1e-4,
                          beta_end: float = 0.02) -> torch.Tensor:
    return torch.linspace(beta_start, beta_end, timesteps)


def cosine_beta_schedule(timesteps: int, s: float = 0.008) -> torch.Tensor:
    """Cosine schedule (improved DDPM)"""
    steps = timesteps + 1
    x = torch.linspace(0, timesteps, steps)
    alphas_cumprod = torch.cos(((x / timesteps) + s) /
                                (1 + s) * math.pi * 0.5) ** 2
    alphas_cumprod = alphas_cumprod / alphas_cumprod[0]
    betas = 1 - (alphas_cumprod[1:] / alphas_cumprod[:-1])
    return torch.clamp(betas, 0.0001, 0.02)


class DiffusionTrainer:
    """DDPM 训练器 — 负责噪声添加 + Loss 计算 + 参数更新"""

    def __init__(self, unet: nn.Module, heads: 'TrajectoryHeads',
                 condition_encoder: nn.Module,
                 n_frames: int = 300, timesteps: int = 1000,
                 lr: float = 1e-4, device: str = "cpu"):
        self.unet = unet
        self.heads = heads
        self.condition_encoder = condition_encoder

        self.n_frames = n_frames
        self.timesteps = timesteps

        # 噪声调度 (cosine)
        betas = cosine_beta_schedule(timesteps)
        alphas = 1.0 - betas
        self.register_buffer("betas", betas)
        self.register_buffer("alphas", alphas)
        self.register_buffer("alphas_cumprod", torch.cumprod(alphas, dim=0))
        self.register_buffer("sqrt_alphas_cumprod",
                              torch.sqrt(self.alphas_cumprod))
        self.register_buffer("sqrt_one_minus_alphas_cumprod",
                              torch.sqrt(1.0 - self.alphas_cumprod))

        self.optimizer = torch.optim.AdamW(
            list(unet.parameters()) +
            list(heads.parameters()) +
            list(condition_encoder.parameters()),
            lr=lr, weight_decay=1e-5,
        )
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=200,
        )
        self.device = device

    def register_buffer(self, name: str, tensor: torch.Tensor):
        """模拟 nn.Module.register_buffer"""
        setattr(self, name, tensor)

    def to(self, device: str):
        self.device = device
        self.unet.to(device)
        self.heads.to(device)
        self.condition_encoder.to(device)
        for name in ["betas", "alphas", "alphas_cumprod",
                      "sqrt_alphas_cumprod",
                      "sqrt_one_minus_alphas_cumprod"]:
            if hasattr(self, name):
                setattr(self, name, getattr(self, name).to(device))
        return self

    @torch.no_grad()
    def add_noise(self, x0: torch.Tensor, t: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Forward diffusion: x0 + noise → xt"""
        sqrt_ac = self.sqrt_alphas_cumprod.to(x0.device)[t]
        sqrt_1m_ac = self.sqrt_one_minus_alphas_cumprod.to(x0.device)[t]
        # 广播到 (B, 1, 1, 1)
        sqrt_ac = sqrt_ac[:, None, None, None]
        sqrt_1m_ac = sqrt_1m_ac[:, None, None, None]
        noise = torch.randn_like(x0)
        xt = sqrt_ac * x0 + sqrt_1m_ac * noise
        return xt, noise

    def train_step(self, batch: Dict[str, torch.Tensor],
                   table_image: torch.Tensor) -> Dict[str, torch.Tensor]:
        """单步训练"""
        B = table_image.shape[0]
        device = self.device

        x0 = batch["trajectory"].to(device)            # (B, 16, 300, 2)
        ball_states = batch["initial_balls"].to(device)  # (B, 16, 8)
        shot_params = batch["shot_params"].to(device)    # (B, 3)
        phys_path = batch.get("physics_path")
        if phys_path is not None:
            phys_path = phys_path.to(device)
        events_gt = batch["events"].to(device)           # (B, 300) class indices
        table_image = table_image.to(device)

        # 随机时间步
        t = torch.randint(0, self.timesteps, (B,), device=device)
        xt, noise = self.add_noise(x0, t)

        # 条件编码
        condition = self.condition_encoder(
            table_image, ball_states, shot_params, phys_path)

        # U-Net 预测噪声
        noise_pred = self.unet(xt, t, condition)

        # Loss: 预测噪声 vs 真实噪声 (DDPM 原始 loss)
        loss_diffusion = F.mse_loss(noise_pred, noise)

        # 额外: 事件预测 loss（在部分去噪后的结果上）
        # 简化: 用预测的噪声反推 x0，再过 event head
        # alpha_cumprod 用于 x0 估计
        x0_pred = (xt - self.sqrt_one_minus_alphas_cumprod.to(device)[t][:, None, None, None] * noise_pred) / \
                   self.sqrt_alphas_cumprod.to(device)[t][:, None, None, None]

        # Reshape for heads: (B, 16, 300, 2) → (B*16, 2, 300)
        Bn, N, L, C = x0_pred.shape
        x_for_heads = x0_pred.permute(0, 1, 3, 2).reshape(B * N, C, L)

        # Use a simple conv projection to get to base_ch
        # Since U-Net output IS the denoised trajectory, we attach heads directly
        # as post-processing — requiring heads to accept coord_dim inputs
        # Simplified: compute event loss on a subset of frames
        event_logits = torch.nn.Sequential(
            torch.nn.Conv1d(C * N, 64, 3, padding=1),
            torch.nn.SiLU(),
            torch.nn.Conv1d(64, 4, 3, padding=1),
        ).to(device)(x0_pred.reshape(B, N * C, L))
        # (B, 4, 300)
        event_logits = event_logits.permute(0, 2, 1)  # (B, 300, 4)
        loss_event = F.cross_entropy(
            event_logits.reshape(-1, 4), events_gt.reshape(-1),
            ignore_index=-1,
        )

        # 平滑约束：相邻帧加速度
        vel = x0_pred[:, :, 1:, :] - x0_pred[:, :, :-1, :]  # (B, N, L-1, 2)
        acc = vel[:, :, 1:, :] - vel[:, :, :-1, :]            # (B, N, L-2, 2)
        loss_smooth = acc.abs().mean()

        total = loss_diffusion + 0.1 * loss_event + 0.05 * loss_smooth

        self.optimizer.zero_grad()
        total.backward()
        torch.nn.utils.clip_grad_norm_(
            list(self.unet.parameters()) +
            list(self.heads.parameters()) +
            list(self.condition_encoder.parameters()),
            max_norm=1.0,
        )
        self.optimizer.step()

        return {
            "total": total,
            "diffusion": loss_diffusion,
            "event": loss_event,
            "smooth": loss_smooth,
        }

    def train_epoch(self, dataloader, table_fn=None) -> Dict[str, float]:
        """训练一个 epoch"""
        self.unet.train()
        self.heads.train()
        self.condition_encoder.train()

        total_losses = {"total": 0.0, "diffusion": 0.0,
                         "event": 0.0, "smooth": 0.0}
        n_batches = 0

        for batch in dataloader:
            if table_fn is not None:
                table = table_fn(batch)
            else:
                # 无真实桌面图，用全黑图
                table = torch.zeros(
                    len(batch["trajectory"]), 3, 600, 1200,
                    device=self.device)
            losses = self.train_step(batch, table)
            for k in total_losses:
                total_losses[k] += losses[k].item()
            n_batches += 1

        self.scheduler.step()
        return {k: v / max(n_batches, 1) for k, v in total_losses.items()}


def save_checkpoint(path: str, unet: nn.Module, heads: 'TrajectoryHeads',
                    encoder: nn.Module, epoch: int = 0,
                    loss: float = 0.0, extra: Optional[Dict] = None):
    """保存完整 checkpoint"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    checkpoint = {
        "unet": unet.state_dict(),
        "heads": heads.state_dict(),
        "encoder": encoder.state_dict(),
        "epoch": epoch,
        "loss": loss,
    }
    if extra:
        checkpoint.update(extra)
    torch.save(checkpoint, path)


def load_checkpoint(path: str, unet: nn.Module, heads: 'TrajectoryHeads',
                    encoder: nn.Module) -> Dict:
    """加载 checkpoint 并恢复模型权重"""
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    unet.load_state_dict(checkpoint["unet"])
    heads.load_state_dict(checkpoint["heads"])
    encoder.load_state_dict(checkpoint["encoder"])
    return {"epoch": checkpoint.get("epoch", 0),
            "loss": checkpoint.get("loss", 0.0)}
```

- [ ] **Step 3: 运行测试确认训练循环工作**

```bash
cd backend && python -m pytest learning/test_diffusion.py -v
# Expected: all 9 tests PASS
```

- [ ] **Step 4: Commit**

```bash
git add backend/learning/diffusion_trainer.py backend/learning/test_diffusion.py
git commit -m "feat: add DDPM trainer with triple-head output and checkpoint utils"
```

---

### Task 5: DiffusionTrajectoryModel 主类

**文件:**
- 新建: `backend/learning/diffusion_model.py`

**职责:** 模型生命周期管理 — 加载/保存/训练/推理/状态查询

- [ ] **Step 1: 实现完整主类**

```python
# backend/learning/diffusion_model.py
"""DiffusionTrajectoryModel — 模型生命周期管理

训练: pretrain() / finetune() / train_async()
推理: predict()
状态: is_trained() / get_status()
"""
import os
import json
import threading
import time
from typing import Dict, List, Optional, Tuple
import numpy as np

try:
    import torch
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from .diffusion_condition import ConditionEncoder
from .diffusion_unet import TrajectoryUNet
from .diffusion_trainer import (
    TrajectoryHeads, DiffusionTrainer, save_checkpoint, load_checkpoint,
    cosine_beta_schedule,
)

TRAJECTORY_CONFIG = {
    "n_balls": 16,
    "n_frames": 300,
    "coord_dim": 2,
    "condition_dim": 512,
    "spatial_tokens": 32,
    "base_ch": 64,
    "timesteps": 1000,
    "ddim_steps": 60,
}


class DiffusionTrajectoryModel:
    """Diffusion 轨迹预测模型"""

    def __init__(self, model_dir: str = "",
                 config: Optional[Dict] = None):
        self.config = {**TRAJECTORY_CONFIG, **(config or {})}
        self._model_dir = model_dir or os.path.dirname(__file__)
        self._ckpt_path = os.path.join(self._model_dir, "trajectory_checkpoint.pt")
        self._base_path = os.path.join(self._model_dir, "trajectory_base.pt")
        self._config_path = os.path.join(self._model_dir, "trajectory_config.json")

        self._device = "cpu"
        self._is_trained = False
        self._train_count = 0
        self._total_count = 0  # total real shots used for training

        self.unet: Optional[TrajectoryUNet] = None
        self.heads: Optional[TrajectoryHeads] = None
        self.encoder: Optional[ConditionEncoder] = None
        self._trainer: Optional[DiffusionTrainer] = None

        if HAS_TORCH:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            self._init_models()

    def _init_models(self):
        cfg = self.config
        self.encoder = ConditionEncoder(
            condition_dim=cfg["condition_dim"],
            spatial_tokens=cfg["spatial_tokens"],
        ).to(self._device)
        self.unet = TrajectoryUNet(
            n_balls=cfg["n_balls"], n_frames=cfg["n_frames"],
            coord_dim=cfg["coord_dim"],
            condition_dim=cfg["condition_dim"],
            spatial_tokens=cfg["spatial_tokens"],
            base_ch=cfg["base_ch"],
        ).to(self._device)
        self.heads = TrajectoryHeads(
            coord_dim=cfg["coord_dim"], base_ch=cfg["base_ch"],
        ).to(self._device)

    # ─── 推理 ────────────────────────────────────────────────

    @torch.no_grad()
    def predict(self, table_image: np.ndarray,
                initial_balls: np.ndarray,
                shot_params: np.ndarray,
                physics_path: Optional[np.ndarray] = None,
                condition_physics: bool = True,
                ddim_steps: Optional[int] = None,
                ) -> np.ndarray:
        """预测轨迹

        Args:
            table_image: (600, 1200, 3) 俯视图
            initial_balls: (16, 8) 球状态
            shot_params: (3,) [力度, 左右塞, 高低杆]
            physics_path: (2, 8, 2) 物理路线 | None
            condition_physics: 是否用物理路线作为条件
            ddim_steps: DDIM 采样步数

        Returns:
            trajectory: (16, 300, 2) 预测位置序列
        """
        if not self._is_trained:
            raise RuntimeError("Model not trained")

        steps = ddim_steps or self.config["ddim_steps"]

        # 准备输入
        table_t = torch.from_numpy(table_image).float().permute(2, 0, 1).unsqueeze(0)
        balls_t = torch.from_numpy(initial_balls).float().unsqueeze(0)
        shot_t = torch.from_numpy(shot_params).float().unsqueeze(0)
        phys_t = None
        if condition_physics and physics_path is not None:
            phys_t = torch.from_numpy(physics_path).float().unsqueeze(0)

        table_t = table_t.to(self._device)
        balls_t = balls_t.to(self._device)
        shot_t = shot_t.to(self._device)
        if phys_t is not None:
            phys_t = phys_t.to(self._device)

        # 条件编码
        condition = self.encoder(table_t, balls_t, shot_t, phys_t)

        # DDIM 采样
        trajectory = self._ddim_sample(condition, steps)

        return trajectory.cpu().numpy()

    @torch.no_grad()
    def _ddim_sample(self, condition: torch.Tensor,
                     steps: int) -> torch.Tensor:
        """DDIM 加速采样"""
        B = condition.shape[0]
        device = self._device
        cfg = self.config

        # DDIM time steps
        total = self.config["timesteps"]
        step_ratio = total // steps
        times = list(reversed(range(0, total, step_ratio)))

        x = torch.randn(B, cfg["n_balls"], cfg["n_frames"],
                         cfg["coord_dim"], device=device)

        betas = cosine_beta_schedule(total)
        alphas = 1.0 - betas
        alphas_cumprod = torch.cumprod(alphas, dim=0).to(device)

        for i, t in enumerate(times):
            t_tensor = torch.full((B,), t, dtype=torch.long, device=device)
            noise_pred = self.unet(x, t_tensor, condition)

            # DDIM 更新公式
            alpha_t = alphas_cumprod[t]
            alpha_prev = alphas_cumprod[times[i + 1]] if i + 1 < len(times) \
                else torch.tensor(1.0, device=device)

            # 预测 x0
            x0_pred = (x - (1 - alpha_t).sqrt() * noise_pred) / alpha_t.sqrt()

            # 方向指向 x0
            dir_xt = (1 - alpha_prev).sqrt() * noise_pred
            x = alpha_prev.sqrt() * x0_pred + dir_xt

        return x

    # ─── 训练 ────────────────────────────────────────────────

    def pretrain(self, synthetic_dataset: List[Dict],
                 epochs: int = 200, batch_size: int = 16,
                 callback=None) -> Dict:
        """合成数据预训练"""
        from .synthetic_data import SyntheticDataGenerator
        gen = SyntheticDataGenerator(num_frames=self.config["n_frames"])

        if not isinstance(synthetic_dataset, list):
            raise ValueError("Expected list of dicts from SyntheticDataGenerator")

        tensors = gen.to_tensors(synthetic_dataset)
        N = tensors["trajectory"].shape[0]

        trainer = DiffusionTrainer(
            unet=self.unet, heads=self.heads,
            condition_encoder=self.encoder,
            n_frames=self.config["n_frames"],
            timesteps=self.config["timesteps"],
            lr=1e-4, device=self._device,
        )

        for epoch in range(epochs):
            perm = torch.randperm(N)
            epoch_losses = {"total": 0.0, "diffusion": 0.0,
                             "event": 0.0, "smooth": 0.0}
            n_batches = 0

            for i in range(0, N, batch_size):
                idx = perm[i:i + batch_size]
                batch = {k: v[idx] for k, v in tensors.items()}
                table = torch.zeros(len(idx), 3, 600, 1200,
                                    device=self._device)
                losses = trainer.train_step(batch, table)
                for k in epoch_losses:
                    epoch_losses[k] += losses[k].item()
                n_batches += 1

            for k in epoch_losses:
                epoch_losses[k] /= max(n_batches, 1)

            if (epoch + 1) % 10 == 0 or epoch == 0:
                print(f"[Pretrain] Epoch {epoch + 1}/{epochs}: "
                      f"loss={epoch_losses['total']:.6f}, "
                      f"diff={epoch_losses['diffusion']:.6f}")

            if callback:
                callback(epoch, epoch_losses)

        self._is_trained = True
        self._total_count = N
        save_checkpoint(self._base_path, self.unet, self.heads, self.encoder,
                         epoch=epochs, loss=epoch_losses["total"])
        self._save_config()

        return {"epochs": epochs, "samples": N,
                "final_loss": epoch_losses["total"]}

    def finetune(self, real_dataset: List[Dict],
                 epochs: int = 50, batch_size: int = 8,
                 lr: float = 1e-5) -> Dict:
        """真实数据增量微调"""
        # 冻结底层
        for name, param in self.unet.named_parameters():
            if "down_blocks." in name and \
               any(f"down_blocks.{i}" in name for i in [2, 3, 4, 5]):
                param.requires_grad = False

        trainer = DiffusionTrainer(
            unet=self.unet, heads=self.heads,
            condition_encoder=self.encoder,
            n_frames=self.config["n_frames"],
            timesteps=self.config["timesteps"],
            lr=lr, device=self._device,
        )

        N = len(real_dataset)
        for epoch in range(epochs):
            perm = torch.randperm(N)
            total_loss = 0.0
            n_batches = 0
            for i in range(0, N, batch_size):
                idx = perm[i:i + batch_size]
                batch = {k: torch.stack([real_dataset[j][k]
                                         for j in idx])
                         for k in ["trajectory", "initial_balls",
                                    "events", "shot_params", "physics_path"]}
                table = torch.zeros(len(idx), 3, 600, 1200,
                                    device=self._device)
                losses = trainer.train_step(batch, table)
                total_loss += losses["total"].item()
                n_batches += 1
            avg_loss = total_loss / max(n_batches, 1)
            if (epoch + 1) % 10 == 0:
                print(f"[Finetune] Epoch {epoch + 1}/{epochs}: loss={avg_loss:.6f}")

        # 解冻
        for param in self.unet.parameters():
            param.requires_grad = True

        self._train_count += N
        self._total_count += N
        save_checkpoint(self._ckpt_path, self.unet, self.heads, self.encoder,
                         loss=avg_loss, extra={"train_count": self._train_count})
        self._save_config()
        return {"epochs": epochs, "new_samples": N, "loss": avg_loss}

    def train_async(self, dataset, **kwargs):
        """后台线程训练"""
        def _run():
            print(f"[Model] Async training started ({len(dataset)} samples)")
            t0 = time.time()
            if not self._is_trained:
                result = self.pretrain(dataset, **kwargs)
            else:
                result = self.finetune(dataset, **kwargs)
            elapsed = time.time() - t0
            print(f"[Model] Async training done in {elapsed:.0f}s: {result}")
        t = threading.Thread(target=_run, daemon=True)
        t.start()

    # ─── 状态 ────────────────────────────────────────────────

    def is_trained(self) -> bool:
        return self._is_trained

    def get_param_count(self) -> int:
        if self.unet is None:
            return 0
        return (sum(p.numel() for p in self.unet.parameters()) +
                sum(p.numel() for p in self.encoder.parameters()) +
                sum(p.numel() for p in self.heads.parameters()))

    def get_status(self) -> Dict:
        return {
            "is_trained": self._is_trained,
            "train_count": self._train_count,
            "total_samples": self._total_count,
            "param_count": self.get_param_count(),
            "device": self._device,
            "config": self.config,
        }

    # ─── 持久化 ────────────────────────────────────────────────

    def save(self, path: str = ""):
        path = path or self._ckpt_path
        if not self._is_trained:
            return
        save_checkpoint(path, self.unet, self.heads, self.encoder,
                         extra={"train_count": self._train_count,
                                "total_count": self._total_count})

    def load(self, path: str = "") -> bool:
        """加载模型，优先最新 checkpoint，其次基座模型"""
        if not HAS_TORCH:
            return False

        self._init_models()

        # 优先尝试 checkpoint
        ckpt_path = path or self._ckpt_path
        base_path = path or self._base_path

        for p in [ckpt_path, base_path]:
            if os.path.exists(p):
                state = load_checkpoint(p, self.unet, self.heads, self.encoder)
                self._is_trained = True
                self._train_count = state.get("train_count", 0)
                self._total_count = state.get("total_count", 0)
                print(f"[Model] Loaded from {os.path.basename(p)} "
                      f"(epoch={state['epoch']}, loss={state['loss']:.6f})")
                return True

        print("[Model] No checkpoint found")
        return False

    def _save_config(self):
        with open(self._config_path, "w") as f:
            json.dump({
                "config": self.config,
                "train_count": self._train_count,
                "total_count": self._total_count,
                "is_trained": self._is_trained,
            }, f, indent=2)
```

- [ ] **Step 2: 确认文件可导入**

```bash
cd backend && python -c "from learning.diffusion_model import DiffusionTrajectoryModel; print('OK')"
# Expected: "OK" (or "PyTorch not installed" if no torch — acceptable)
```

- [ ] **Step 3: Commit**

```bash
git add backend/learning/diffusion_model.py
git commit -m "feat: add DiffusionTrajectoryModel main class with lifecycle management"
```

---

### Task 6: Trajectory Collector (数据采集)

**文件:**
- 新建: `backend/learning/trajectory_collector.py`

**职责:** 后台静默采集击球轨迹，环形缓存+触发+录制+保存

- [ ] **Step 1: 实现 TrajectoryCollector**

```python
# backend/learning/trajectory_collector.py
"""轨迹数据采集器 — 后台静默运行，环形缓冲 + 相对变化触发"""
import os
import json
import time
import threading
from typing import Dict, List, Optional, Tuple
import numpy as np


class TrajectoryCollector:
    """轨迹数据采集器"""

    def __init__(self, save_dir: str = "", ring_size: int = 30,
                 stop_frames: int = 10, trigger_sigma: float = 3.0):
        self._save_dir = save_dir or os.path.join(
            os.path.dirname(__file__), "collected_shots")
        os.makedirs(self._save_dir, exist_ok=True)

        self._ring_size = ring_size           # 击球前保留帧数
        self._stop_frames = stop_frames       # 静止判定连续帧数
        self._trigger_sigma = trigger_sigma   # 触发阈值（sigma倍数）

        self._collecting = False              # 总开关
        self._recording = False               # 正在录制中
        self._ring_buffer: List[List[Dict]] = []  # 最近 N 帧球列表
        self._cue_history: List[Tuple[float, float]] = []  # 母球历史位置
        self._recorded_frames: List[Dict] = []     # 当前录制的帧
        self._shot_id = 0
        self._still_count = 0
        self._miss_count = 0                   # 连续丢母球计数

        self._total_collected = 0
        self._lock = threading.Lock()

        # 自动恢复 shot_id
        self._init_shot_id()

    def _init_shot_id(self):
        """从已有文件恢复 shot_id"""
        max_id = 0
        for f in os.listdir(self._save_dir):
            if f.startswith("shot_") and f.endswith(".json"):
                try:
                    sid = int(f.split("_")[1].split(".")[0])
                    max_id = max(max_id, sid)
                except ValueError:
                    pass
        self._shot_id = max_id + 1

    @property
    def is_collecting(self) -> bool:
        return self._collecting

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self):
        self._collecting = True
        self._ring_buffer.clear()
        self._cue_history.clear()
        self._recorded_frames.clear()
        self._recording = False
        self._still_count = 0
        print(f"[Collector] Started (shot_id={self._shot_id})")

    def stop(self):
        self._collecting = False
        if self._recording:
            self._save_recording()
        print(f"[Collector] Stopped ({self._total_collected} shots)")

    def count(self) -> int:
        return self._total_collected

    def feed_frame(self, balls: List) -> None:
        """每帧喂入球列表 (Ball 对象)"""
        if not self._collecting:
            return

        with self._lock:
            # 提取球位置
            ball_dicts = [{"x": float(b.x), "y": float(b.y),
                           "is_cue": bool(b.is_cue),
                           "is_solid": bool(b.is_solid),
                           "is_stripe": bool(b.is_stripe),
                           "is_black": bool(b.is_black),
                           "color": b.color}
                          for b in balls]

            # 更新环形缓冲
            self._ring_buffer.append(ball_dicts)
            if len(self._ring_buffer) > self._ring_size + 50:
                self._ring_buffer = self._ring_buffer[-self._ring_size - 50:]

            # 找母球
            cue = None
            for b in ball_dicts:
                if b["is_cue"]:
                    cue = b
                    break

            if cue is None:
                if self._recording:
                    self._miss_count += 1
                    if self._miss_count >= 5:
                        # 母球丢失太久，丢弃本次采集
                        self._recording = False
                        self._recorded_frames.clear()
                        self._miss_count = 0
                return
            self._miss_count = 0

            cue_pos = (cue["x"], cue["y"])
            self._cue_history.append(cue_pos)
            if len(self._cue_history) > 30:
                self._cue_history = self._cue_history[-30:]

            if self._recording:
                self._recorded_frames.append(ball_dicts)
                self._check_stop(ball_dicts)
            else:
                self._check_trigger()

    def _check_trigger(self):
        """检测是否触发击球"""
        if len(self._cue_history) < 20:
            return

        # 计算窗口内标准差
        recent = np.array(self._cue_history[-20:])
        sigma = float(np.std(recent))

        if sigma < 1e-6:
            return  # 完全静止

        # 当前位移
        if len(self._cue_history) < 2:
            return
        dx = self._cue_history[-1][0] - self._cue_history[-2][0]
        dy = self._cue_history[-1][1] - self._cue_history[-2][1]
        displacement = (dx ** 2 + dy ** 2) ** 0.5

        # 触发：位移超过 3x 标准差（在归一化坐标下）
        if displacement > self._trigger_sigma * sigma and sigma > 0:
            self._recording = True
            self._still_count = 0
            # 从环形缓冲拿触发前的帧
            pre_frames = max(0, len(self._ring_buffer) - len(self._recorded_frames) - 1)
            ring_start = max(0, pre_frames - self._ring_size)
            self._recorded_frames = []
            for i in range(ring_start, len(self._ring_buffer)):
                self._recorded_frames.append(self._ring_buffer[i])

    def _check_stop(self, ball_dicts: List[Dict]):
        """检测是否全部静止"""
        # 跳过母球的检查
        positions = [(b["x"], b["y"]) for b in ball_dicts]
        if len(self._recorded_frames) < 5:
            self._still_count = 0
            return

        prev = None
        for f in self._recorded_frames[-5:]:
            curr = [(b["x"], b["y"]) for b in f]
            if prev is not None:
                max_disp = max(
                    ((c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2) ** 0.5
                    for c, p in zip(curr, prev) if len(curr) == len(prev))
                if max_disp > 0.002:  # 2px @ 1080p
                    self._still_count = 0
                    return
            prev = curr

        self._still_count += 1
        if self._still_count >= self._stop_frames:
            self._save_recording()

    def _save_recording(self):
        """保存本次采集的轨迹"""
        if len(self._recorded_frames) < 10:
            self._recording = False
            self._recorded_frames.clear()
            self._still_count = 0
            return

        # 构建优化后的事件标注
        events = []
        prev_balls = self._recorded_frames[0]
        for fi, frame in enumerate(self._recorded_frames):
            # 检测状态变化
            for bi, b in enumerate(frame):
                if bi < len(prev_balls):
                    pb = prev_balls[bi]
                    # 碰撞：突然加速
                    if fi > 1 and bi < len(self._recorded_frames[fi - 2]):
                        bb = self._recorded_frames[fi - 2][bi]
                        dx = b["x"] - bb["x"]
                        dy = b["y"] - bb["y"]
                        if (dx ** 2 + dy ** 2) ** 0.5 > 0.01 and \
                           (pb["x"] - bb["x"]) ** 2 + (pb["y"] - bb["y"]) ** 2 < 0.0001:
                            events.append({"frame": fi, "type": "collision",
                                            "ball": bi})
            prev_balls = frame

        shot_data = {
            "shot_id": self._shot_id,
            "timestamp": time.time(),
            "frames": self._recorded_frames,
            "events": events,
        }

        fname = f"shot_{self._shot_id:06d}.json"
        fpath = os.path.join(self._save_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(shot_data, f, ensure_ascii=False)

        self._shot_id += 1
        self._total_collected += 1
        print(f"[Collector] Saved {fname} ({len(self._recorded_frames)} frames, "
              f"{len(events)} events, total={self._total_collected})")

        # 重置
        self._recording = False
        self._recorded_frames.clear()
        self._still_count = 0
```

- [ ] **Step 2: 确认可导入**

```bash
cd backend && python -c "from learning.trajectory_collector import TrajectoryCollector; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/learning/trajectory_collector.py
git commit -m "feat: add trajectory collector with ring buffer and adaptive trigger"
```

---

### Task 7: Physics Engine — 合成轨迹生成方法

**文件:**
- 修改: `backend/physics/engine.py` — 新增 `generate_trajectory_frames()`

- [ ] **Step 1: 在 PhysicsEngine 追加方法**

在 `engine.py` 的 `find_best_shot` 方法后追加：

```python
    def generate_trajectory_frames(self, cue_pos: Vec2, target_pos: Vec2,
                                    pocket_pos: Vec2, num_frames: int = 100,
                                    power: float = 0.5,
                                    spin_x: float = 0.0,
                                    spin_y: float = 0.0,
                                    ) -> Tuple[List[Tuple[float, float]],
                                               List[Tuple[float, float]]]:
        """生成模拟轨迹帧序列（用于合成数据/物理引导）

        Returns:
            cue_path: 母球逐帧位置 [(x,y), ...] length=num_frames
            target_path: 目标球逐帧位置 [(x,y), ...] length=num_frames
        """
        shot = self.calculate_shot(cue_pos, target_pos, pocket_pos)
        if not shot.success:
            # Try bank shot
            shot = self.calculate_bank_shot(cue_pos, target_pos, pocket_pos)
        if not shot.success:
            # Generate simple straight-line fallback
            return ([(cue_pos.x + (target_pos.x - cue_pos.x) * i / num_frames,
                      cue_pos.y + (target_pos.y - cue_pos.y) * i / num_frames)
                     for i in range(num_frames)],
                    [(target_pos.x, target_pos.y) for _ in range(num_frames)])

        # Interpolate physics path into frame sequence
        cue_pts = [(p.x, p.y) for p in shot.cue_path]
        target_pts = [(p.x, p.y) for p in shot.target_path]
        cue_final = (shot.cue_final_pos.x, shot.cue_final_pos.y) \
            if shot.cue_final_pos else cue_pts[-1]

        # Cue path: move → collision → decelerate → stop
        collide_frac = 0.15
        stop_frac = 0.80
        n_collide = max(1, int(num_frames * collide_frac))
        n_stop = min(num_frames, int(num_frames * stop_frac))

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

        # Target path: stay → collision → move to pocket
        target_frames = []
        target_final = target_pts[-1] if len(target_pts) > 1 else target_pts[0]
        for i in range(num_frames):
            if i < n_collide:
                tx, ty = target_pts[0]
            else:
                alpha = min(1.0, (i - n_collide) / (n_stop - n_collide))
                tx = target_pts[0][0] + (target_final[0] - target_pts[0][0]) * alpha
                ty = target_pts[0][1] + (target_final[1] - target_pts[0][1]) * alpha
            target_frames.append((tx, ty))

        return cue_frames, target_frames
```

- [ ] **Step 2: 验证方法可调用**

```bash
cd backend && python -c "
from physics.engine import PhysicsEngine, Vec2
p = PhysicsEngine()
cue, target = p.generate_trajectory_frames(Vec2(0.3,0.4), Vec2(0.5,0.35), Vec2(1.0,0.5), 100)
assert len(cue) == 100 and len(target) == 100
print(f'OK: cue {cue[0]} -> {cue[-1]}, target {target[0]} -> {target[-1]}')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/physics/engine.py
git commit -m "feat: add generate_trajectory_frames() to PhysicsEngine"
```

---

### Task 8: 学习模块导出更新

**文件:**
- 修改: `backend/learning/__init__.py`

- [ ] **Step 1: 更新 exports**

```python
# backend/learning/__init__.py
from .data_collector import DataCollector, ShotRecord
from .physics_adapter import PhysicsAdapter, PhysicsParams
from .diffusion_model import DiffusionTrajectoryModel
from .trajectory_collector import TrajectoryCollector
from .synthetic_data import SyntheticDataGenerator
from .diffusion_trainer import save_checkpoint, load_checkpoint

__all__ = [
    "DataCollector", "ShotRecord",
    "PhysicsAdapter", "PhysicsParams",
    "DiffusionTrajectoryModel",
    "TrajectoryCollector",
    "SyntheticDataGenerator",
    "save_checkpoint", "load_checkpoint",
]
```

- [ ] **Step 2: 验证导入**

```bash
cd backend && python -c "from learning import DiffusionTrajectoryModel, TrajectoryCollector; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/learning/__init__.py
git commit -m "feat: export diffusion model and trajectory collector from learning package"
```

---

### Task 9: System Integration (main.py)

**文件:**
- 修改: `backend/main.py`

- [ ] **Step 1: 修改 PoolARSystem**

在 `__init__` 开头添加导入：

```python
from learning.diffusion_model import DiffusionTrajectoryModel
from learning.trajectory_collector import TrajectoryCollector
```

在 `__init__` 方法中追加模型和采集器初始化（在 `self.physics_adapter = PhysicsAdapter()` 之后）：

```python
        # Diffusion trajectory model
        self.trajectory_model = DiffusionTrajectoryModel()
        self.trajectory_collector = TrajectoryCollector()
        self._use_ai_trajectory = False  # 默认关闭，待模型加载后自动启用
```

在 `start()` 方法中，在 `self.data_collector.load()` 之后追加：

```python
        # Load diffusion model if available
        if self.trajectory_model.load():
            self._use_ai_trajectory = True
            print(f"[Model] Diffusion trajectory model loaded "
                  f"({self.trajectory_model.get_param_count():,} params)")
        else:
            print("[Model] No diffusion model found, using physics engine")
```

在 `stop()` 方法中追加采集器保存：

```python
        if self.trajectory_collector.is_collecting:
            self.trajectory_collector.stop()
```

修改 `_compute_and_render_shot()` 方法签名和逻辑 — 在 `if not cue_ball or not targets:` 之后、物理引擎前插入：

```python
        # 尝试 AI 轨迹预测
        if self._use_ai_trajectory and self.trajectory_model.is_trained():
            try:
                import numpy as np
                # 构造输入
                initial_balls = np.zeros((16, 8), dtype=np.float32)
                for i, b in enumerate(balls[:16]):
                    initial_balls[i, 0] = float(b.x)
                    initial_balls[i, 1] = float(b.y)
                    initial_balls[i, 4] = 1.0 if b.is_cue else 0.0
                    initial_balls[i, 5] = 1.0 if b.is_black else 0.0
                    initial_balls[i, 6] = 1.0 if b.is_solid else 0.0
                    initial_balls[i, 7] = 1.0 if b.is_stripe else 0.0

                shot_params = np.array([0.5, 0.0, 0.0], dtype=np.float32)
                speed_val = system_state["table_state"].get("last_cue_speed", 0)
                if speed_val > 0:
                    shot_params[0] = min(1.0, speed_val / 5.0)

                # 物理路线作为条件
                cue_vec = Vec2(cue_ball.x, cue_ball.y)
                t_vec = Vec2(targets[0].x, targets[0].y)
                phys_result = self.physics.find_best_shot(cue_vec, t_vec)
                physics_path = None
                if phys_result.success:
                    physics_path = np.zeros((2, 8, 2), dtype=np.float32)
                    for j, p in enumerate(phys_result.cue_path[:8]):
                        physics_path[0, j] = [p.x, p.y]
                    for j, p in enumerate(phys_result.target_path[:8]):
                        physics_path[1, j] = [p.x, p.y]

                # 调用模型
                trajectory = self.trajectory_model.predict(
                    np.zeros((600, 1200, 3), dtype=np.uint8),  # placeholder table image
                    initial_balls,
                    shot_params,
                    physics_path,
                    condition_physics=True,
                )

                # 提取母球+目标球轨迹
                target_idx = 0
                for i, b in enumerate(balls[:16]):
                    if not b.is_cue and not b.is_black:
                        target_idx = i
                        break

                cue_path = [(float(trajectory[0, f, 0]),
                              float(trajectory[0, f, 1]))
                             for f in range(300) if trajectory[0, f, 0] != 0 or
                             trajectory[0, f, 1] != 0]
                target_path = [(float(trajectory[target_idx, f, 0]),
                                 float(trajectory[target_idx, f, 1]))
                                for f in range(300) if trajectory[target_idx, f, 0] != 0 or
                                trajectory[target_idx, f, 1] != 0]

                if not cue_path:
                    cue_path = [(cue_ball.x, cue_ball.y)]
                if not target_path:
                    target_path = [(targets[0].x, targets[0].y)]

                cue_final = cue_path[-1] if cue_path else None

                overlay = ProjectionOverlay(
                    cue_path=cue_path,
                    target_path=target_path,
                    pocket=(target_path[-1][0], target_path[-1][1]) if len(target_path) > 0 else (0.5, 0.5),
                    target_pos=(targets[0].x, targets[0].y),
                    cue_pos=(cue_ball.x, cue_ball.y),
                    cue_final_pos=cue_final,
                    label=f"AI: {targets[0].color}",
                )
                return self.renderer.render_to_base64(overlay)
            except Exception as e:
                import traceback
                traceback.print_exc()
                # Fall through to physics engine
```

在 `_vision_loop` 中，在速度检测后追加采集器喂帧：

```python
                        # Feed trajectory collector (silent background)
                        if self.trajectory_collector.is_collecting and balls is not None:
                            self.trajectory_collector.feed_frame(balls)
```

- [ ] **Step 2: 验证启动不报错**

```bash
cd backend && python -c "from main import PoolARSystem; s = PoolARSystem(); print('[OK] System init with model')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: integrate diffusion trajectory model and collector into system"
```

---

### Task 10: REST API 端点

**文件:**
- 修改: `backend/api/routes.py`

- [ ] **Step 1: 追加 8 个 API 端点**

在 `routes.py` 末尾追加：

```python
# ── Model & Collector API ──

@router.get("/model/status")
async def get_model_status():
    """获取 Diffusion 模型状态"""
    from main import PoolARSystem
    import inspect
    # 通过 system_state 拿不到 PoolARSystem 实例，直接用全局
    m = system_state.get("main_system")
    if m is None:
        return {"error": "System not initialized"}
    return m.trajectory_model.get_status()


@router.post("/model/pretrain")
async def trigger_pretrain():
    """触发合成数据预训练（后台）"""
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503, "System not initialized")
    from learning.synthetic_data import SyntheticDataGenerator
    gen = SyntheticDataGenerator(num_frames=m.trajectory_model.config["n_frames"])
    samples = gen.generate(num_samples=50000)
    m.trajectory_model.train_async(samples, epochs=200, batch_size=16)
    return {"status": "started", "samples": len(samples)}


@router.post("/model/finetune")
async def trigger_finetune():
    """触发真实数据微调（后台）"""
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503, "System not initialized")
    # Load collected shots
    from learning.trajectory_collector import TrajectoryCollector
    import os
    data_dir = os.path.join(os.path.dirname(__file__),
                            '..', 'learning', 'collected_shots')
    real_data = []
    if os.path.isdir(data_dir):
        import json
        for f in sorted(os.listdir(data_dir)):
            if f.endswith('.json'):
                with open(os.path.join(data_dir, f)) as fp:
                    real_data.append(json.load(fp))
    if len(real_data) < 50:
        raise HTTPException(400, f"Not enough real data ({len(real_data)} < 50)")
    # 直接传原始数据，模型内部做转换
    m.trajectory_model.train_async(real_data, epochs=50, batch_size=8)
    return {"status": "started", "samples": len(real_data)}


@router.get("/model/config")
async def get_model_config():
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    return {
        "condition_physics": m._use_ai_trajectory,
        "model_config": m.trajectory_model.config,
    }


@router.post("/model/config")
async def set_model_config(req: Request):
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    body = await req.json()
    if "condition_physics" in body:
        m._use_ai_trajectory = bool(body["condition_physics"])
    return {"ok": True}


@router.get("/collector/status")
async def get_collector_status():
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    c = m.trajectory_collector
    return {
        "collecting": c.is_collecting,
        "recording": c.is_recording,
        "total_collected": c.count(),
    }


@router.post("/collector/start")
async def start_collector():
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    m.trajectory_collector.start()
    return {"status": "started"}


@router.post("/collector/stop")
async def stop_collector():
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    m.trajectory_collector.stop()
    return {"status": "stopped",
            "total": m.trajectory_collector.count()}
```

- [ ] **Step 2: 在 main.py 中注入 system 引用**

在 `main.py` 的 `start()` 方法末尾追加：

```python
        system_state["main_system"] = self
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/routes.py backend/main.py
git commit -m "feat: add REST endpoints for model status, training, and collector control"
```

---

### Task 11: WebSocket 消息扩展

**文件:**
- 修改: `backend/api/websocket.py`

- [ ] **Step 1: 追加 model_status 广播方法**

在 `ConnectionManager` 类中追加：

```python
    async def broadcast_model_status(self, status: dict) -> None:
        """Send model training status to phone clients."""
        data = json.dumps({
            "type": "model_status",
            "data": status,
        })
        for ws in list(self._phone_clients):
            try:
                await ws.send_text(data)
            except Exception:
                pass
```

- [ ] **Step 2: Commit**

```bash
git add backend/api/websocket.py
git commit -m "feat: add model_status WebSocket message type"
```

---

### Task 12: 清理测试文件 + 最终验证

- [ ] **Step 1: 运行全部扩散模型测试**

```bash
cd backend && python -m pytest learning/test_diffusion.py -v
# 预期: 9 tests PASS (或 SKIP 如果 torch 未安装)
```

- [ ] **Step 2: 验证整体导入链**

```bash
cd backend && python -c "
from learning import (DiffusionTrajectoryModel, TrajectoryCollector,
                       SyntheticDataGenerator, save_checkpoint, load_checkpoint)
from physics.engine import PhysicsEngine
print('All imports OK')
p = PhysicsEngine()
cue, tgt = p.generate_trajectory_frames(
    p.POCKETS[0], p.POCKETS[3], p.POCKETS[5], 50)
print(f'Physics frames OK: {len(cue)}, {len(tgt)}')
"
```

- [ ] **Step 3: 更新 DEVELOPMENT.md 中的模块状态**

在 `docs/DEVELOPMENT.md` 第 8.1 节表格中更新/新增：

```
| Diffusion轨迹模型 | 90% | 🟡 待数据 | 213M参数，合成预训练+真实微调 |
| 轨迹数据采集 | 100% | ✅ | 环形缓冲+自适应触发+JSON持久化 |
```

- [ ] **Step 4: Final commit**

```bash
git add docs/DEVELOPMENT.md
git commit -m "docs: update module status for diffusion model and collector"
```

---

## 实现顺序

1. Task 1 → 合成数据生成器（无依赖）
2. Task 2 → 条件编码器
3. Task 3 → 去噪 U-Net
4. Task 4 → 训练器 + Output Heads
5. Task 5 → 主模型类（依赖 2,3,4）
6. Task 6 → 轨迹采集器（独立）
7. Task 7 → 物理引擎扩展（独立）
8. Task 8 → 模块导出更新
9. Task 9 → 系统集成
10. Task 10 → REST API
11. Task 11 → WebSocket 扩展
12. Task 12 → 清理 + 最终验证

Tasks 1-4 可并行（相互无运行时依赖），Tasks 5-7 可并行，其余顺序执行。
