"""裁判播报系统

集中管理所有语音播报文字生成。后端发送文字，投影仪APP通过TTS朗读。
"""
from typing import Optional


# 球号映射
BALL_NAMES: dict = {
    "yellow": "1号球", "blue": "2号球", "red": "3号球",
    "purple": "4号球", "orange": "5号球", "green": "6号球",
    "brown": "7号球",
    "black": "黑8",
}

# 花色球号映射（颜色名相同，但用 stripe_ 前缀区分）
STRIPE_BALL_NAMES: dict = {
    "yellow": "9号球", "blue": "10号球", "red": "11号球",
    "purple": "12号球", "orange": "13号球", "green": "14号球",
    "brown": "15号球",
}


class Announcer:
    """裁判播报文字生成器

    用法:
        announcer = Announcer("张三", "李四")
        text = announcer.pocket_announce("red", False, False)
        # → "3号球进袋"
    """

    def __init__(self, player1: str = "选手一", player2: str = "选手二"):
        self.p1 = player1
        self.p2 = player2

    def set_players(self, p1: str, p2: str) -> None:
        self.p1 = p1
        self.p2 = p2

    # ─── 进球播报 ────────────────────────────────────────────

    def pocket_announce(self, color: str, is_stripe: bool,
                        is_cue: bool, is_black: bool = False) -> str:
        """球进袋播报"""
        if is_cue:
            return "犯规！白球进袋"
        if is_black:
            return "黑8进袋"
        name = self._ball_name(color, is_stripe)
        return f"{name}进袋"

    def pocket_simple(self, color: str, is_stripe: bool) -> str:
        """简略播报（连续进球时只报球号）"""
        name = self._ball_name(color, is_stripe)
        return name

    # ─── 比赛播报 ────────────────────────────────────────────

    def match_start(self) -> str:
        return f"比赛开始，{self.p1}开球"

    def assign_balls(self, p1_group: str) -> str:
        """球色分配播报 p1_group: "纯色" 或 "花色" """
        p2_group = "花色" if p1_group == "纯色" else "纯色"
        return f"{self.p1}{p1_group}球，{self.p2}{p2_group}球"

    def foul(self, reason: str = "") -> str:
        if reason:
            return f"犯规！{reason}"
        return "犯规"

    def switch_player(self) -> str:
        return f"轮到{self.p2}击球"

    def victory(self, player: int) -> str:
        name = self.p1 if player == 1 else self.p2
        return f"本局{name}获胜！"

    def score_summary(self, s1: int, s2: int) -> str:
        return f"当前比分{self.p1}{s1}比{s2}{self.p2}"

    # ─── 训练播报 ────────────────────────────────────────────

    def placement_ok(self) -> str:
        return "摆球正确"

    def placement_adjust(self, cue_dir: str = "", target_dir: str = "") -> str:
        """摆球位置有偏差，提示调整方向"""
        parts = []
        if cue_dir:
            parts.append(f"白球{cue_dir}")
        if target_dir:
            parts.append(f"目标球{target_dir}")
        return "，".join(parts) if parts else "请调整摆球位置"

    def shot_result(self, pocketed: bool, cue_in_zone: bool,
                    consecutive: int = 0, drill_passed: bool = False) -> str:
        """击球结果播报"""
        if pocketed and cue_in_zone:
            msg = "目标球进袋！母球走位完美"
            if drill_passed:
                msg += "，本题通过"
            elif consecutive >= 2:
                msg += f"，连续成功{consecutive}次"
            return msg
        elif pocketed:
            return "目标球进袋，但母球偏离指定区域"
        else:
            return "未进球"

    def challenge_pass(self) -> str:
        return "恭喜，连续三连成功，进入下一题"

    def level_up(self, level: int) -> str:
        return f"恭喜通关！进入第{level}档"

    def all_clear(self) -> str:
        return "全部通关！你是大师级选手"

    def cue_speed(self, speed: float) -> str:
        """杆速播报"""
        return f"杆速{round(speed, 1)}米每秒"

    # ─── 内部 ────────────────────────────────────────────────

    def _ball_name(self, color: str, is_stripe: bool) -> str:
        if is_stripe:
            return STRIPE_BALL_NAMES.get(color, f"{color}球")
        return BALL_NAMES.get(color, f"{color}球")
