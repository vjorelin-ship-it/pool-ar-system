"""裁判播报系统 — 生成语音播报文字，后端发送文字，投影仪APP通过TTS朗读。"""

BALL_NAMES: dict = {
    "yellow": "1号球", "blue": "2号球", "red": "3号球",
    "purple": "4号球", "orange": "5号球", "green": "6号球",
    "brown": "7号球", "black": "黑8",
}

STRIPE_BALL_NAMES: dict = {
    "yellow": "9号球", "blue": "10号球", "red": "11号球",
    "purple": "12号球", "orange": "13号球", "green": "14号球",
    "brown": "15号球",
}


class Announcer:
    def __init__(self, player1: str = "选手一", player2: str = "选手二"):
        self.p1 = player1
        self.p2 = player2

    def pocket_announce(self, color: str, is_stripe: bool,
                        is_cue: bool, is_black: bool = False) -> str:
        if is_cue:
            return "犯规！白球进袋"
        if is_black:
            return "黑8进袋"
        name = self._ball_name(color, is_stripe)
        return f"{name}进袋"

    def victory(self, player: int) -> str:
        name = self.p1 if player == 1 else self.p2
        return f"本局{name}获胜！"

    def shot_result(self, pocketed: bool, cue_in_zone: bool,
                    consecutive: int = 0, drill_passed: bool = False) -> str:
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

    def _ball_name(self, color: str, is_stripe: bool) -> str:
        if is_stripe:
            return STRIPE_BALL_NAMES.get(color, f"{color}球")
        return BALL_NAMES.get(color, f"{color}球")
