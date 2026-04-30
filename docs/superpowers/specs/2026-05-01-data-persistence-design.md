# 数据持久化增强设计 — 全面修复

> 状态: 设计阶段 | 日期: 2026-05-01

## 1. 背景

当前数据持久化有5个缺口：比赛/训练历史从不加载，击球数据和物理参数只在关机时保存，AI修正模型从不自动加载。

## 2. 修复清单

| # | 模块 | 方法 | 文件 |
|---|------|------|------|
| 1 | MatchMode | 新增 `load_history()` | `game/match_mode.py` |
| 2 | TrainingMode | 新增 `load_history()` | `game/training_mode.py` |
| 3 | DataCollector | `record_shot()` 末尾调用 `save()` | `learning/data_collector.py` |
| 4 | PhysicsAdapter | `update_from_observation()` 末尾调用 `save()` | `learning/physics_adapter.py` |
| 5 | CorrectionModel | 启动时自动 `load()` | `main.py` |

## 3. 设计决策

- MatchMode 恢复静态数据（名字/比分/球色），不恢复 volatile 状态（current_player/foul）
- TrainingMode 恢复全部状态，包括 unlocked_levels
- 增量保存重写整个JSON文件（文件小，<10KB，原子性非关键）
- CorrectionModel 加载失败静默降级（旧模型不兼容时跳过）
