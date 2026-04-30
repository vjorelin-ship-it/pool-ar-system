# 物理引擎增强实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已有的两库翻袋、组合球、旋转球算法接入主流程，修复问题，补充测试。

**Architecture:** `main.py` 调用 `find_best_shot_with_context()`（替代 `find_best_shot()`），后者对每个目标球尝试全部5种打法，按加权得分排序。修正评分不一致、组合球无中间球限制、缺少旋转尝试三个缺口。

**Tech Stack:** Python 3.11+, OpenCV, NumPy

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/test_pipeline.py:31-47` | 扩展 | 新增4个测试 |
| `backend/physics/engine.py:387-416` | 修改 | 修复 find_best_shot_with_context |
| `backend/physics/engine.py:293-357` | 修改 | 组合球限制中间球数 |
| `backend/main.py:380-450` | 修改 | 集成 find_best_shot_with_context |
| `backend/main.py:500-529` | 修改 | 补充翻袋/两库/传球标注 |

---

### Task 1: 补充测试

**Files:**
- Modify: `backend/test_pipeline.py` 在 `test_physics()` 之后追加

- [ ] **Step 1: 添加两库翻袋、组合球、旋转、集成测试**

在 `test_physics()` 函数末尾（第46行之后）追加以下测试代码：

```python
    # 两库翻袋
    result_db = phy.calculate_double_bank_shot(
        Vec2(0.2, 0.3), Vec2(0.15, 0.4), Vec2(1.0, 0.5))
    print(f"  [OK] 两库翻袋: {'可行' if result_db.success else '不可行'}")
    if result_db.success:
        assert len(result_db.target_path) == 4, "两库翻袋应有4段路径(cue→aim, target→b1→b2→pocket)"
        assert result_db.is_bank_shot, "应标记为翻袋"
        assert result_db.bounce_point is not None, "应有反弹点"

    # 组合球传球
    result_combo = phy.calculate_combo_shot(
        Vec2(0.3, 0.3), Vec2(0.4, 0.4), Vec2(0.5, 0.5), Vec2(1.0, 0.5))
    print(f"  [OK] 组合球: {'可行' if result_combo.success else '不可行'}")
    if result_combo.success:
        assert len(result_combo.target_path) >= 3, "组合球应有≥3段路径"

    # 旋转球
    result_spin = phy.calculate_shot_with_spin(
        Vec2(0.2, 0.3), Vec2(0.5, 0.25), Vec2(1.0, 0.5),
        spin_x=0.0, spin_y=0.5)  # 高杆
    print(f"  [OK] 旋转球(高杆): {'可行' if result_spin.success else '不可行'}")
    if result_spin.success:
        assert result_spin.spin_y == 0.5, "应保留spin_y参数"
        assert result_spin.cue_final_pos is not None, "应有母球最终位置"

    result_spin2 = phy.calculate_shot_with_spin(
        Vec2(0.2, 0.3), Vec2(0.5, 0.25), Vec2(1.0, 0.5),
        spin_x=1.0, spin_y=-0.5)  # 右塞+低杆
    print(f"  [OK] 旋转球(右塞低杆): {'可行' if result_spin2.success else '不可行'}")
    if result_spin2.success:
        assert abs(result_spin2.english_deflection) > 0.01, "右塞应有偏移"

    # 集成: find_best_shot_with_context
    all_balls = [Vec2(0.35, 0.45), Vec2(0.6, 0.5), Vec2(0.7, 0.7)]
    best = phy.find_best_shot_with_context(Vec2(0.3, 0.35), Vec2(0.5, 0.25), all_balls)
    assert best.success, f"find_best_shot_with_context应找到可行路线"
    print(f"  [OK] find_best_shot_with_context: 成功, 目标袋({best.target_pocket.x:.2f},{best.target_pocket.y:.2f})")
```

- [ ] **Step 2: 运行测试 验证测试存在**

```bash
cd D:\daima\backend && python -c "
from test_pipeline import test_physics
test_physics()
print('All physics tests ran')
"
```

Expected: 所有测试运行（不一定全部通过，组合球/两库可能返回不可行）

- [ ] **Step 3: Commit**

```bash
git add backend/test_pipeline.py
git commit -m "test: add physics tests for double bank, combo, spin, and find_best_shot_with_context"
```

---

### Task 2: 修复 find_best_shot_with_context + 组合球限制

**Files:**
- Modify: `backend/physics/engine.py:387-416` (find_best_shot_with_context)
- Modify: `backend/physics/engine.py:293-357` (calculate_combo_shot — 保持不变，限制在调用侧)

发现的问题：
1. 没有尝试旋转球
2. 组合球遍历所有中间球，无限制
3. `best_score` 初始值是未加权的距离，后续比较用加权距离，不一致

- [ ] **Step 1: 修改 find_best_shot_with_context**

读取 `engine.py` 第387-416行的现有代码，替换为：

```python
    def find_best_shot_with_context(self, cue_pos: Vec2, target_pos: Vec2,
                                     all_balls: List[Vec2]) -> ShotResult:
        """Find best shot considering all 5 types: direct, bank, double-bank, combo, spin."""
        best: Optional[ShotResult] = None
        best_score = float("inf")
        WEIGHTS = {
            "direct": 1.0,
            "bank": 1.15,
            "double_bank": 1.3,
            "combo": 1.4,
            "spin": 1.15,  # weighted same as bank — spin is an enhancement, not a harder shot
        }

        for pocket in self.POCKETS:
            # 直接球
            direct = self.calculate_shot(cue_pos, target_pos, pocket)
            if direct.success:
                score = target_pos.dist_to(pocket) * WEIGHTS["direct"]
                if score < best_score:
                    best, best_score = direct, score

            # 一库翻袋
            bank = self.calculate_bank_shot(cue_pos, target_pos, pocket)
            if bank.success:
                score = target_pos.dist_to(pocket) * WEIGHTS["bank"]
                if score < best_score:
                    best, best_score = bank, score

            # 两库翻袋
            db = self.calculate_double_bank_shot(cue_pos, target_pos, pocket)
            if db.success:
                score = target_pos.dist_to(pocket) * WEIGHTS["double_bank"]
                if score < best_score:
                    best, best_score = db, score

            # 旋转球：当直接球可行时，计算旋转修正
            if direct.success and direct.cue_final_pos:
                for spin_x, spin_y in [(0, 0.5), (0, -0.5), (0.5, 0), (-0.5, 0), (0, 0)]:
                    spin_shot = self.calculate_shot_with_spin(
                        cue_pos, target_pos, pocket, spin_x=spin_x, spin_y=spin_y)
                    if spin_shot.success:
                        score = target_pos.dist_to(pocket) * WEIGHTS["spin"]
                        if score < best_score:
                            best, best_score = spin_shot, score

        # 组合球：限制最近邻3个中间球
        if all_balls:
            sorted_mids = sorted(
                [(m, m.dist_to(cue_pos) + m.dist_to(target_pos)) for m in all_balls
                 if m.dist_to(cue_pos) > 0.02 and m.dist_to(target_pos) > 0.02],
                key=lambda x: x[1])
            for mid, _ in sorted_mids[:3]:
                for pocket in self.POCKETS:
                    combo = self.calculate_combo_shot(cue_pos, mid, target_pos, pocket)
                    if combo.success:
                        score = target_pos.dist_to(pocket) * WEIGHTS["combo"]
                        if score < best_score:
                            best, best_score = combo, score

        return best if best is not None and best.success else self._no_shot()
```

- [ ] **Step 2: 运行测试验证**

```bash
cd D:\daima\backend && python -c "
from test_pipeline import test_physics
test_physics()
"
```

Expected: 所有测试运行，`find_best_shot_with_context` 应成功找到路线

- [ ] **Step 3: Commit**

```bash
git add backend/physics/engine.py
git commit -m "fix: rewrite find_best_shot_with_context — add spin attempts, limit combo to 3 nearest balls, fix scoring consistency"
```

---

### Task 3: 集成到 main.py + 补充技术标注

**Files:**
- Modify: `backend/main.py:413-421` (替换 find_best_shot 调用)
- Modify: `backend/main.py:500-529` (补充翻袋/两库/传球标注)

- [ ] **Step 1: 修改 _compute_and_render_shot 中的调用**

将 `main.py` 第420行的：
```python
            result = self.physics.find_best_shot(cue_vec, t_vec)
```

替换为：
```python
            result = self.physics.find_best_shot_with_context(
                cue_vec, t_vec,
                [Vec2(b.x, b.y) for b in balls if b is not cue_ball and b is not t])
```

- [ ] **Step 2: 修改 _recommend_technique 补充标注**

将 `main.py` 第500-529行的 `_recommend_technique` 替换为：

```python
    @staticmethod
    def _recommend_technique(result) -> str:
        """根据物理引擎结果推荐杆法"""
        if not result.success or not result.cue_final_pos:
            return "中杆"
        # 翻袋/两库标注
        suffix = ""
        if getattr(result, 'is_bank_shot', False):
            # 区分一库/两库
            tp = result.target_path
            if len(tp) == 4:  # target→b1→b2→pocket = 两库
                suffix = "两库翻袋"
            else:
                suffix = "翻袋"
        # 组合球检测：看target_path是否包含目标球以外的球
        if len(result.target_path) >= 3 and not result.is_bank_shot:
            suffix = "传球"
        # 旋转/杆法
        if hasattr(result, 'spin_y') and result.spin_y != 0:
            sy = result.spin_y
            sx = abs(result.spin_x) if hasattr(result, 'spin_x') else 0
            if sy > 0.2:
                tech = "高杆" + ("加塞" if sx > 0.3 else "")
            elif sy < -0.2:
                tech = "低杆" + ("加塞" if sx > 0.3 else "")
            else:
                tech = "定杆" + ("加塞" if sx > 0.3 else "")
            if suffix:
                tech = tech + "·" + suffix
            return tech
        # Fallback
        if suffix:
            # 有翻袋/传球但没有旋转信息
            dx = result.cue_final_pos.x - result.cue_path[0].x
            dy = result.cue_final_pos.y - result.cue_path[0].y
            fdx = result.cue_path[-1].x - result.cue_path[0].x
            fdy = result.cue_path[-1].y - result.cue_path[0].y
            dot = dx * fdx + dy * fdy
            if dot > 0.01:
                return "高杆·" + suffix
            elif dot < -0.01:
                return "低杆·" + suffix
            return "中杆·" + suffix
        # 默认
        dx = result.cue_final_pos.x - result.cue_path[0].x
        dy = result.cue_final_pos.y - result.cue_path[0].y
        fdx = result.cue_path[-1].x - result.cue_path[0].x
        fdy = result.cue_path[-1].y - result.cue_path[0].y
        dot = dx * fdx + dy * fdy
        power_norm = result.cue_speed / 0.5
        if dot > 0.01:
            return "高杆" if power_norm > 0.6 else "中高杆"
        elif dot < -0.01:
            return "低杆" if power_norm > 0.6 else "中低杆"
        return "中杆"
```

- [ ] **Step 2: 运行完整测试套件**

```bash
cd D:\daima\backend && python test_pipeline.py
```

Expected: 所有已有测试和新测试通过

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: integrate find_best_shot_with_context into main flow with enhanced technique labels"
```

---

### Task 4: 集成验证

**Files:** 无需改动 — 验证全部通过

- [ ] **Step 1: 运行完整测试**

```bash
cd D:\daima\backend && python test_pipeline.py
```

Expected: 所有测试通过，无报错

- [ ] **Step 2: 验证导入完整性**

```bash
cd D:\daima\backend && python -c "
from physics.engine import PhysicsEngine, Vec2, ShotResult
ph = PhysicsEngine()
# 验证所有5种方法存在且可调用
assert callable(ph.calculate_shot)
assert callable(ph.calculate_bank_shot)
assert callable(ph.calculate_double_bank_shot)
assert callable(ph.calculate_combo_shot)
assert callable(ph.calculate_shot_with_spin)
assert callable(ph.find_best_shot_with_context)
print('All methods present and callable')
"
```

**Step 2b: 集成调用验证 — 模拟主流程：**

```bash
cd D:\daima\backend && python -c "
from physics.engine import PhysicsEngine, Vec2
ph = PhysicsEngine()

# 模拟主流程: 对每个目标球调用 find_best_shot_with_context
cue = Vec2(0.3, 0.35)

# 场景1: 简单直接球
t1 = Vec2(0.5, 0.25)
result1 = ph.find_best_shot_with_context(cue, t1, [Vec2(0.7, 0.6), Vec2(0.4, 0.5)])
assert result1.success, '场景1应成功'
print(f'场景1(直接球): 成功, 路线段数={len(result1.target_path)}')

# 场景2: 靠台边球 (应触发翻袋)
t2 = Vec2(0.05, 0.4)
result2 = ph.find_best_shot_with_context(cue, t2, [Vec2(0.7, 0.6), Vec2(0.4, 0.5)])
print(f'场景2(台边球): 成功={result2.success}, 翻袋={result2.is_bank_shot}')

# 场景3: 有可用中间球 (组合球)
t3 = Vec2(0.9, 0.5)
mid = Vec2(0.7, 0.45)
result3 = ph.find_best_shot_with_context(cue, t3, [mid])
print(f'场景3(有中间球): 成功={result3.success}')

print('Integration simulation complete')
"
```

Expected: 所有3个场景运行正常

- [ ] **Step 3: Commit (如有遗留文件)**

```bash
git status
# 如有未提交修改，add并commit
```

---

## 实现顺序

```
Task 1 (测试) → Task 2 (修复engine.py) → Task 3 (集成main.py) → Task 4 (验证)
```

3个Task顺序执行，每个都依赖前一个。
