# 数据持久化增强实现计划

> **For agentic workers:** Use inline execution. 5 files, minimal changes.

**Goal:** 修复5个数据持久化缺口：比赛/训练历史加载、击球数据/物理参数增量保存、AI模型自动加载

---

### Task 1: MatchMode + TrainingMode load + main.py 启动恢复

**Files:** `game/match_mode.py`, `game/training_mode.py`, `main.py`

#### match_mode.py — 新增 load_history()

在 `save_history()` 方法之后新增：

```python
    def load_history(self) -> bool:
        """Load match history from disk. Returns True if history was loaded."""
        try:
            path = os.path.join(os.path.dirname(__file__), "..", "learning", "match_history.json")
            if not os.path.exists(path):
                return False
            with open(path, "r") as f:
                data = json.load(f)
            self.player1_name = data.get("player1_name", "选手一")
            self.player2_name = data.get("player2_name", "选手二")
            self.state.player1_score = data.get("player1_score", 0)
            self.state.player2_score = data.get("player2_score", 0)
            self.state.player1_balls = data.get("player1_balls", "")
            self.state.player2_balls = data.get("player2_balls", "")
            self.state.game_over = data.get("game_over", False)
            self.state.winner = data.get("winner", 0)
            return True
        except Exception:
            return False
```

确保文件顶部有 `import os` 和 `import json`。

#### training_mode.py — 新增 load_history()

在 `save_history()` 方法之后新增：

```python
    def load_history(self) -> bool:
        """Load training history from disk. Returns True if history was loaded."""
        try:
            path = os.path.join(os.path.dirname(__file__), "..", "learning", "training_history.json")
            if not os.path.exists(path):
                return False
            with open(path, "r") as f:
                data = json.load(f)
            self.current_level = data.get("current_level", 1)
            self.current_drill_index = data.get("current_drill_index", 0)
            self.consecutive_successes = data.get("consecutive_successes", 0)
            self.total_attempts = data.get("total_attempts", 0)
            self.total_successes = data.get("total_successes", 0)
            self.completed_levels = set(data.get("completed_levels", []))
            self.unlocked_levels = set(data.get("unlocked_levels", [1]))
            self.challenge_mode = data.get("challenge_mode", False)
            return True
        except Exception:
            return False
```

#### main.py — 启动时调用 load

在 `start()` 方法中，MatchMode/TrainingMode 初始化之后添加：

```python
        # 恢复持久化的比赛/训练状态
        if self.match_mode.load_history():
            print("[System] Restored match state from history")
        if self.training_mode.load_history():
            print("[System] Restored training state from history")
        # 自动加载AI修正模型
        if self.correction_model.load(
            os.path.join(os.path.dirname(__file__), "learning", "correction_model.pt")):
            print("[System] Correction model loaded")
```

- [ ] 执行 + 验证 + 提交

---

### Task 2: DataCollector + PhysicsAdapter 增量保存

**Files:** `learning/data_collector.py`, `learning/physics_adapter.py`

#### data_collector.py — record_shot 末尾加 save

在 `record_shot()` 方法的最后（return 之前）添加：

```python
        self.save()  # incremental save after each shot
```

#### physics_adapter.py — update_from_observation 末尾加 save

在 `update_from_observation()` 方法的最后添加：

```python
        self.save()  # incremental save after each update
```

- [ ] 执行 + 验证 + 提交

---

### Task 3: 集成验证

运行测试并验证所有文件正确加载：

```bash
cd D:\daima\backend && python test_pipeline.py
```

验证启动流程：
```bash
cd D:\daima\backend && python -c "
from main import PoolARSystem
s = PoolARSystem()
s.start()
print('Startup complete — all persistence loaded')
s.stop()
"
```

- [ ] 执行 + 提交
