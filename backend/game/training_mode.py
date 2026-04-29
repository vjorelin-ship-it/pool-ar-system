from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from .training_data import TrainingDrill, get_level, get_all_levels


@dataclass
class TrainingSession:
    current_level: int = 1
    current_drill_idx: int = 0
    consecutive_successes: int = 0
    challenge_mode: bool = True
    total_attempts: int = 0
    total_successes: int = 0
    unlocked_levels: List[int] = field(default_factory=lambda: [1])
    completed_levels: List[int] = field(default_factory=list)

    def get_current_drill(self) -> TrainingDrill:
        level = get_level(self.current_level)
        return level.drills[self.current_drill_idx]

    def get_progress(self) -> dict:
        level = get_level(self.current_level)
        return {
            "level": self.current_level,
            "level_name": level.name,
            "drill": self.current_drill_idx + 1,
            "total_drills": len(level.drills),
            "consecutive_successes": self.consecutive_successes,
            "needed_for_pass": 3,
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
        }


class TrainingMode:
    def __init__(self):
        self.session = TrainingSession()
        self._placement_threshold = 0.02

    def start_challenge(self) -> dict:
        self.session = TrainingSession(challenge_mode=True)
        return self._drill_info()

    def select_level(self, level: int) -> dict:
        # Training mode: all levels unlocked; Challenge mode: must progress
        if self.session.challenge_mode and level not in self.session.unlocked_levels:
            return {"error": f"Level {level} not unlocked"}
        self.session.current_level = level
        self.session.current_drill_idx = 0
        self.session.consecutive_successes = 0
        return self._drill_info()

    def verify_placement(self, actual_cue: Tuple[float, float],
                         actual_target: Tuple[float, float]) -> dict:
        drill = self.session.get_current_drill()
        cue_dist = self._distance(actual_cue, drill.cue_pos)
        target_dist = self._distance(actual_target, drill.target_pos)

        return {
            "cue_correct": cue_dist <= self._placement_threshold,
            "target_correct": target_dist <= self._placement_threshold,
            "cue_error": round(cue_dist, 4),
            "target_error": round(target_dist, 4),
            "all_correct": cue_dist <= self._placement_threshold
                           and target_dist <= self._placement_threshold,
        }

    def record_result(self, success: bool,
                      cue_final: Tuple[float, float]) -> dict:
        s = self.session
        s.total_attempts += 1

        drill = s.get_current_drill()
        in_zone = self._is_in_landing_zone(cue_final, drill.cue_landing_zone)

        if success and in_zone:
            s.total_successes += 1
            s.consecutive_successes += 1
            feedback = "成功！目标球进袋，母球在指定区域"
        else:
            s.consecutive_successes = 0
            feedback = "未成功，继续努力"

        passed = False
        if s.challenge_mode and s.consecutive_successes >= 3:
            passed = self._advance_drill_or_level()

        return {
            "success": success and in_zone,
            "cue_in_zone": in_zone,
            "consecutive": s.consecutive_successes,
            "passed": passed,
            "feedback": feedback,
        }

    def process_auto_result(self, target_pocketed: bool,
                             drill: 'TrainingDrill',
                             cue_final: Tuple[float, float]) -> dict:
        """自动处理击球结果（由视觉检测触发）

        Args:
            target_pocketed: 目标球是否进袋
            drill: 当前训练题
            cue_final: 母球最终位置

        Returns:
            同 record_result
        """
        return self.record_result(target_pocketed, cue_final)

    def _advance_drill_or_level(self) -> bool:
        s = self.session
        level = get_level(s.current_level)

        if s.current_drill_idx + 1 < len(level.drills):
            s.current_drill_idx += 1
            s.consecutive_successes = 0
            return True

        if s.current_level < 10:
            s.completed_levels.append(s.current_level)
            s.current_level += 1
            s.current_drill_idx = 0
            s.consecutive_successes = 0
            if s.current_level not in s.unlocked_levels:
                s.unlocked_levels.append(s.current_level)
            return True

        return False

    def _drill_info(self) -> dict:
        drill = self.session.get_current_drill()
        return {
            "level": self.session.current_level,
            "drill": {
                "cue_pos": drill.cue_pos,
                "target_pos": drill.target_pos,
                "pocket_pos": drill.pocket_pos,
                "description": drill.description,
            },
            "progress": self.session.get_progress(),
        }

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    @staticmethod
    def _is_in_landing_zone(pos: Tuple[float, float],
                            zone: Tuple[float, float, float, float]) -> bool:
        x, y = pos
        x1, y1, x2, y2 = zone
        return x1 <= x <= x2 and y1 <= y <= y2
