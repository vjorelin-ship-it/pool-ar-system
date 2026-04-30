# 物理引擎增强设计 — 接入+优化已有代码

> 状态: 设计阶段 | 日期: 2026-05-01

## 1. 背景

物理引擎 (`backend/physics/engine.py`) 已经实现了五种击球算法：

| 打法 | 方法 | 状态 |
|------|------|------|
| 直接球 | `calculate_shot()` | ✅ 已接入主流程 |
| 一库翻袋 | `calculate_bank_shot()` | ✅ 已接入主流程 |
| 两库翻袋 | `calculate_double_bank_shot()` | ❌ 未接入 |
| 组合球传球 | `calculate_combo_shot()` | ❌ 未接入 |
| 旋转球 | `calculate_shot_with_spin()` | ❌ 未接入 |

主流程 `_compute_and_render_shot()` 调用的是 `find_best_shot()`，只用了前两种。完整的 `find_best_shot_with_context()` 包含全部五种但未被调用。

## 2. 目标

将 `find_best_shot_with_context()` 接入主流程，审查优化已有算法，补全测试。

## 3. 架构改动

```
当前: main.py → find_best_shot(cue, target) → 直接球 + 一库翻袋

改为: main.py → find_best_shot_with_context(cue, target, all_balls)
       → 直接球 + 一库 + 两库 + 组合(近邻3球) + 旋转
       → 按得分排序选最优
```

## 4. 修改文件

| 文件 | 改动 |
|------|------|
| `backend/main.py:380-450` | `find_best_shot` → `find_best_shot_with_context`，传入全部球 |
| `backend/main.py:500-529` | 补充翻袋/两库/传球的技术标注 |
| `backend/physics/engine.py` | 审查修复两库翻袋、组合球、旋转算法 |
| `backend/test_pipeline.py` | 新增4个测试 |

## 5. 主流程改动

`_compute_and_render_shot()` 中：

```python
# 之前
best = self.physics.find_best_shot(cue_vec, t_vec)

# 之后
all_balls = [(i, Vec2(b.x, b.y)) for i, b in enumerate(balls)]
best = self.physics.find_best_shot_with_context(cue_vec, t_vec, all_balls)
```

`_recommend_technique()` 补充标注：
- `is_bank_shot` + `bounce_point` 为两库时 → "两库翻袋"
- combo_shot 标记 → "传球/组合球"
- 旋转 + 翻袋 → "加塞翻袋"

## 6. 算法审查要点

1. **两库翻袋** — 验证双反射几何，检查 bounce2 在有效台边区域
2. **组合球** — 限制中间球 ≤ 3个最近邻，验证两次碰撞角度
3. **旋转** — 确认 SIDE_DEFLECTION (3°/unit) 合理，走位建议可用
4. **评分权重** — 直接1.0 < 旋转1.15 < 一库1.15 < 两库1.3 < 组合1.4

## 7. 设计决策

| 决策 | 选择 |
|------|------|
| 组合球中间球数量 | ≤3个最近邻 |
| 旋转何时触发 | 直接球可行时计算旋转修正 |
| 性能目标 | 单帧单目标 < 5ms |
| 测试覆盖 | 两库翻袋、组合球、旋转、集成测试 |
