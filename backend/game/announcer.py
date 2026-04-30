"""裁判播报系统 — 基于CTBA中式八球2025最新规则

覆盖完整比赛流程的35种播报场景。
后端生成播报文字 → WebSocket发送 → 投影仪APP通过TTS朗读。
"""

BALL_NAMES: dict = {
    "yellow": "1号球", "blue": "2号球", "red": "3号球",
    "purple": "4号球", "orange": "5号球", "green": "6号球",
    "brown": "7号球", "black": "黑8",
}

STRIPE_NAMES: dict = {
    "yellow": "9号球", "blue": "10号球", "red": "11号球",
    "purple": "12号球", "orange": "13号球", "green": "14号球",
    "brown": "15号球",
}


class Announcer:
    """裁判播报器"""

    def __init__(self, player1: str = "选手一", player2: str = "选手二"):
        self.p1 = player1
        self.p2 = player2
        self._last_foul_desc = ""

    def set_players(self, p1: str, p2: str):
        self.p1 = p1
        self.p2 = p2

    def name(self, player: int) -> str:
        return self.p1 if player == 1 else self.p2

    # ═══ 赛前：比球 ═══════════════════════════════════════

    def lag_start(self) -> str:
        return "请双方准备比球，将母球放在开球线后同时出杆"

    def lag_illegal(self, reason: str = "") -> str:
        base = "非法比球"
        return f"{base}，{reason}，重新比球" if reason else f"{base}，重新比球"

    def lag_result(self, winner: int) -> str:
        return f"{self.name(winner)}比球获胜，获得开球权"

    # ═══ 比赛开始 ═══════════════════════════════════════

    def match_start(self, breaker: int, is_final: bool = False,
                    target_wins: int = 0, p1_wins: int = 0, p2_wins: int = 0) -> str:
        if is_final and target_wins > 0:
            return (f"决胜局！{self.p1}{p1_wins}胜{self.p2}{p2_wins}胜，"
                    f"{self.name(breaker)}开球")
        return f"比赛开始，{self.name(breaker)}开球"

    # ═══ 开球 ═══════════════════════════════════════

    def break_legal(self, potted: bool = False) -> str:
        return "开球进球，台面开放" if potted else "开球有效，台面开放"

    def break_foul(self, opponent: int, reason: str = "") -> str:
        base = f"开球犯规！{self.name(opponent)}可选择"
        opts = "线后自由球、重新摆球自己开球或对方重开"
        return f"{base}：{opts}" if not reason else f"{base}：{opts}（{reason}）"

    def break_8ball_potted(self, player: int, has_foul: bool = False) -> str:
        if has_foul:
            return f"开球黑8入袋同时犯规！对手选择处理方式"
        return f"开球黑8入袋，复位后{self.name(player)}继续击球"

    def break_slip(self) -> str:
        return "开球未触球堆，对手可选择自己开球或对方重开"

    # ═══ 定组 ═══════════════════════════════════════

    def ball_group_assigned(self, player: int, group: str) -> str:
        opp = 2 if player == 1 else 1
        opp_group = "花色球" if group == "纯色球" else "纯色球"
        return f"{self.name(player)}{group}，{self.name(opp)}{opp_group}"

    # ═══ 球权切换 ═══════════════════════════════════════

    def switch_player(self, next_player: int) -> str:
        return f"轮到{self.name(next_player)}击球"

    def continue_player(self, player: int) -> str:
        return f"{self.name(player)}继续击球"

    # ═══ 进球 ═══════════════════════════════════════

    def ball_pocketed(self, color: str, is_stripe: bool = False) -> str:
        name = STRIPE_NAMES.get(color) if is_stripe else BALL_NAMES.get(color)
        if name:
            return f"{name}进袋"
        return f"{color}球进袋"

    # ═══ 犯规 ═══════════════════════════════════════

    def foul_cue_pocketed(self, opponent: int) -> str:
        return f"犯规！白球进袋，{self.name(opponent)}自由球"

    def foul_wrong_ball(self, offender: int, opponent: int) -> str:
        return f"犯规！{self.name(offender)}先碰对方球，{self.name(opponent)}自由球"

    def foul_no_cushion(self, opponent: int) -> str:
        return f"犯规！击球后无球碰库，{self.name(opponent)}自由球"

    def foul_open_8ball(self, opponent: int) -> str:
        return f"犯规！开放球局先碰8号球，{self.name(opponent)}自由球"

    def foul_ball_off_table(self, opponent: int, is_8ball: bool = False) -> str:
        if is_8ball:
            return "犯规！8号球飞出台面，判本局负！"  # 8号飞台直接判负
        return f"犯规！球飞出台面，{self.name(opponent)}自由球"

    def foul_player(self, offender: int, opponent: int, reason: str = "") -> str:
        base = f"犯规！{self.name(offender)}"
        detail = f"{reason}，" if reason else ""
        return f"{base}{detail}{self.name(opponent)}自由球"

    def foul_double_hit(self, opponent: int) -> str:
        return f"连击犯规！{self.name(opponent)}自由球"

    def foul_push_shot(self, opponent: int) -> str:
        return f"推杆犯规！{self.name(opponent)}自由球"

    def foul_wrong_turn(self, offender: int, opponent: int) -> str:
        return f"犯规！{self.name(offender)}轮次错误，{self.name(opponent)}自由球"

    def foul_cue_fly_off(self, opponent: int) -> str:
        return f"犯规！母球飞出台面，{self.name(opponent)}自由球"

    def foul_body_touch(self, opponent: int) -> str:
        return f"犯规！身体触球，{self.name(opponent)}自由球"

    def foul_ball_moving(self, opponent: int) -> str:
        return f"犯规！球未静止击球，{self.name(opponent)}自由球"

    def foul_time(self, opponent: int) -> str:
        return f"超时犯规！{self.name(opponent)}自由球"

    def foul_sportsmanship(self, opponent: int, reason: str = "") -> str:
        base = "违反体育精神"
        return (f"犯规！{base}，{reason}，{self.name(opponent)}自由球"
                if reason else f"犯规！{base}，{self.name(opponent)}自由球")

    def free_ball(self) -> str:
        return "自由球，可将母球放在台面任意位置"

    def behind_line_free_ball(self) -> str:
        return "线后自由球，母球放在开球线后方"

    # ═══ 黑8决胜 ═══════════════════════════════════════

    def black8_on(self, player: int) -> str:
        return f"黑8决胜！{self.name(player)}击球"

    def black8_loss_early(self, offender: int) -> str:
        return f"犯规！{self.name(offender)}未清完己方球，黑8提前进袋，判本局负！"

    def black8_loss_cue_pocketed(self, offender: int) -> str:
        return f"犯规！打黑8白球进袋，{self.name(offender)}判本局负！"

    def black8_loss_off_table(self, offender: int) -> str:
        return f"犯规！黑8飞出台面，{self.name(offender)}判本局负！"

    def black8_loss_foul(self, offender: int, reason: str = "") -> str:
        base = f"犯规！{self.name(offender)}"
        detail = f"{reason}，" if reason else ""
        return f"{base}{detail}黑8进球无效，判本局负！"

    def black8_loss_wrong_pocket(self, offender: int) -> str:
        return f"犯规！黑8进入非指定球袋，{self.name(offender)}判本局负！"

    def black8_foul_but_safe(self, opponent: int) -> str:
        return f"犯规！打黑8存在犯规，但黑8未进，{self.name(opponent)}自由球"

    # ═══ 胜负 ═══════════════════════════════════════

    def game_win(self, winner: int) -> str:
        return f"黑8进袋！本局{self.name(winner)}获胜！"

    def game_win_by_foul(self, winner: int) -> str:
        return f"对手犯规判负！本局{self.name(winner)}获胜！"

    def match_win(self, winner: int, final_score: str = "") -> str:
        base = f"比赛结束！{self.name(winner)}获胜！"
        return f"{base}{final_score}" if final_score else base

    # ═══ 僵局 ═══════════════════════════════════════

    def stalemate_warning(self, count: int) -> str:
        return f"连续{count}杆无进球，注意僵局规则"

    def stalemate(self) -> str:
        return "裁判判定僵局，重新摆球，原开球方开球"

    # ═══ 时限 ═══════════════════════════════════════

    def time_warning(self, seconds: int) -> str:
        return f"还剩{seconds}秒"

    def time_foul(self, opponent: int) -> str:
        return f"超时犯规！{self.name(opponent)}自由球"

    # ═══ 训练模式 ═══════════════════════════════════════

    def placement_ok(self) -> str:
        return "摆球正确"

    def placement_error(self, cue_dir: str = "", target_dir: str = "") -> str:
        parts = []
        if cue_dir:
            parts.append(f"白球偏{cue_dir}")
        if target_dir:
            parts.append(f"目标球偏{target_dir}")
        return "摆球错误，" + "，".join(parts) if parts else "摆球错误"

    def shot_result(self, success: bool, cue_in_zone: bool = False,
                    consecutive: int = 0, drill_passed: bool = False) -> str:
        if success and cue_in_zone:
            msg = "目标球进袋！母球走位完美"
            if drill_passed:
                msg += "，本题通过，进入下一题"
            elif consecutive >= 2:
                msg += f"，连续成功{consecutive}次"
            return msg
        elif success:
            return "目标球进袋，但母球偏离指定区域"
        else:
            return "未进球，继续努力"

    def level_up(self, level_name: str) -> str:
        return f"恭喜晋级！进入{level_name}"

    def all_clear(self) -> str:
        return "全部通关！你是大师级选手！"

    # ═══ 辅助 ═══════════════════════════════════════

    def cue_ball_moving(self) -> str:
        return "球未静止，请等待"

    @staticmethod
    def _ball_name(color: str, is_stripe: bool) -> str:
        if is_stripe:
            return STRIPE_NAMES.get(color, f"{color}球")
        return BALL_NAMES.get(color, f"{color}球")
