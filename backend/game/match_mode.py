from dataclasses import dataclass, field
from typing import List, Dict, Any
import json as _json
import os as _os
from datetime import datetime as _dt


@dataclass
class MatchState:
    player1_name: str = ""
    player2_name: str = ""
    player1_score: int = 0
    player2_score: int = 0
    current_player: int = 1
    player1_balls: str = ""
    player2_balls: str = ""
    is_break_shot: bool = True
    game_over: bool = False
    winner: int | None = None
    foul: bool = False
    free_ball: bool = False
    table_open: bool = True
    shots_this_turn: int = 0
    history: List[dict] = field(default_factory=list)
    p1_remaining: int = 0
    p2_remaining: int = 0
    # 僵局计数
    consecutive_misses: int = 0  # 连续无进球杆数
    target_wins: int = 5  # 目标胜局数（先达到此局数者获胜）
    # 阶段追踪（AI裁判8阶段模型）
    phase: str = "init"  # init|lag|break|open|playing|black8|game_over|match_over
    # 8号球规则
    designated_pocket: str = ""  # 指定袋口 (tl|tm|tr|bl|bm|br|"")，空=不指定
    require_designate: bool = False  # 是否需要指定袋口
    # 犯规累计（故意犯规F17/F20）
    intentional_fouls_p1: int = 0  # 选手一故意犯规次数（本场累计）
    intentional_fouls_p2: int = 0  # 选手二故意犯规次数
    # 消极比赛
    passive_warnings_p1: int = 0
    passive_warnings_p2: int = 0
    # 限时
    shot_timer_seconds: int = 45
    extension_used_p1: bool = False
    extension_used_p2: bool = False
    # 开球
    break_8ball_potted: bool = False  # 开球8号入袋
    break_two_colors: bool = False  # 开球两色同时入袋
    break_cushion_count: int = 0  # 开球碰库球数
    # 目标胜局
    player1_match_wins: int = 0
    player2_match_wins: int = 0

    def switch_player(self) -> None:
        self.current_player = 2 if self.current_player == 1 else 1
        self.shots_this_turn = 0

    def record_shot(self, potted: List[Dict[str, Any]], foul: bool = False) -> None:
        self.history.append({
            "player": self.current_player,
            "potted": potted,
            "foul": foul,
        })
        self.shots_this_turn += 1
        self.foul = foul


class MatchMode:
    def __init__(self):
        self.state = MatchState()

    def start_new_match(self, *args) -> None:
        self.state = MatchState()
        if len(args) >= 1:
            self.state.player1_name = str(args[0])
        if len(args) >= 2:
            self.state.player2_name = str(args[1])

    def process_shot(self, potted_balls: List[Dict[str, Any]],
                     is_foul: bool = False, cue_pocketed: bool = False,
                     no_ball_hit: bool = False, no_cushion: bool = False,
                     ball_off_table: bool = False, wrong_player: bool = False) -> dict:
        """Process a shot with full foul detection (CTBA 2025 rules).

        Args:
            potted_balls: list of pocketed balls with {is_solid, is_stripe, is_black, is_cue}
            is_foul: pre-detected foul
            cue_pocketed: cue ball in pocket
            no_ball_hit: no ball contacted
            no_cushion: no ball hit cushion after contact (CTBA rule)
            ball_off_table: ball left the table
            wrong_player: wrong player shooting (from vision)

        Returns action dict with announce tags.
        """
        s = self.state
        prev_player = s.current_player
        prev_game_over = s.game_over

        # Detect all fouls
        fouls = self.detect_fouls(potted_balls, cue_pocketed=cue_pocketed,
                                   no_ball_hit=no_ball_hit, no_cushion=no_cushion,
                                   ball_off_table=ball_off_table, wrong_player=wrong_player)

        s.record_shot(potted_balls, is_foul or len(fouls) > 0)

        # 僵局计数
        has_pocket = bool(potted_balls) and not (len(fouls) > 0 and any(
            f.get("severity") == "loss" for f in fouls))
        if has_pocket:
            s.consecutive_misses = 0
        else:
            s.consecutive_misses += 1

        ann = {}  # announcer tags

        # Break shot
        if s.is_break_shot:
            s.is_break_shot = False
            ann["phase"] = "break"
            if fouls:
                result = self.apply_fouls(fouls)
                result["announce"] = ann
                return result
            if potted_balls:
                ann["break_potted"] = True
                result = self._handle_break(potted_balls)
                result["announce"] = ann
                return result
            s.switch_player()
            ann["switch"] = True
            return {"action": "switch_player", "player": s.current_player,
                    "announce": ann}

        # Foul handling
        if fouls:
            ann["phase"] = "foul"
            ann["foul_types"] = [f["type"] for f in fouls]
            ann["foul_descs"] = [f["desc"] for f in fouls]
            is_loss = any(f.get("severity") == "loss" for f in fouls)
            ann["is_loss"] = is_loss
            # Check if it's black8-related foul
            ann["is_black8"] = any(
                f.get("type") in ("early_eight", "black8_foul") for f in fouls)
            result = self.apply_fouls(fouls)
            result["announce"] = ann
            return result
        if is_foul:
            s.switch_player()
            ann["phase"] = "foul"
            ann["switch"] = True
            return {"action": "switch_player", "player": s.current_player,
                    "foul": True, "announce": ann}

        # Potted balls
        if potted_balls:
            ann["phase"] = "pot"
            result = self._handle_pot(potted_balls)
            if result.get("action") == "continue":
                ann["continue"] = True
            elif result.get("action") == "win":
                ann["game_win"] = True
            elif result.get("action") == "lose":
                ann["game_lose"] = True
                ann["lose_reason"] = result.get("reason", "")
            elif result.get("action") == "switch_player":
                ann["switch"] = True
            result["announce"] = ann
            return result

        # Miss
        s.switch_player()
        ann["phase"] = "miss"
        ann["switch"] = True
        return {"action": "switch_player", "player": s.current_player,
                "announce": ann}

    def _handle_break(self, potted: List[Dict[str, Any]]) -> dict:
        """Assign ball groups based on first pocketed ball after break."""
        s = self.state
        s.table_open = False

        # 检查是否有8号球入袋
        has_8ball = any(b.get("is_black") for b in potted)
        s.break_8ball_potted = has_8ball

        # 检查是否两色同时入袋
        has_solid = any(b.get("is_solid") for b in potted)
        has_stripe = any(b.get("is_stripe") for b in potted)
        s.break_two_colors = has_solid and has_stripe

        # 两色同时入袋 → 选手选择
        if s.break_two_colors:
            s.phase = "open"
            return {"action": "choose_group", "player": s.current_player,
                    "potted_solid": has_solid, "potted_stripe": has_stripe}

        # 8号球入袋（无其他犯规）→ 特殊处理
        if has_8ball:
            s.phase = "open"
            s.break_8ball_potted = True
            return {"action": "break_8ball_choice", "player": s.current_player}

        # 正常定组
        first = potted[0]
        if first.get("is_solid"):
            s.player1_balls = "solids"
            s.player2_balls = "stripes"
        elif first.get("is_stripe"):
            s.player1_balls = "stripes"
            s.player2_balls = "solids"
        else:
            return {"action": "open_table", "player": s.current_player}
        s.p1_remaining = 7
        s.p2_remaining = 7
        s.phase = "playing"
        return {"action": "assign", "p1": s.player1_balls,
                "p2": s.player2_balls, "player": s.current_player}

    def choose_group(self, player: int, group: str) -> dict:
        """选手选择球组（开球两色同时入袋后）"""
        s = self.state
        if group == "solids":
            s.player1_balls = "solids" if player == 1 else "stripes"
            s.player2_balls = "stripes" if player == 1 else "solids"
        else:
            s.player1_balls = "stripes" if player == 1 else "solids"
            s.player2_balls = "solids" if player == 1 else "stripes"
        s.p1_remaining = 7
        s.p2_remaining = 7
        s.phase = "playing"
        return {"action": "assign", "p1": s.player1_balls,
                "p2": s.player2_balls, "player": s.current_player}

    def handle_break_8ball_choice(self, player: int, choice: str) -> dict:
        """处理开球8号入袋后的选择"""
        s = self.state
        if choice == "continue":
            s.break_8ball_potted = False  # 已处理
            return {"action": "continue", "player": player}
        else:
            return {"action": "rebreak", "player": player}

    def _handle_pot(self, potted: List[Dict[str, Any]]) -> dict:
        s = self.state
        own_group = s.player1_balls if s.current_player == 1 else s.player2_balls
        opp_group = "stripes" if own_group == "solids" else "solids"

        # Check 8-ball first
        for ball in potted:
            if ball.get("is_black"):
                remaining = self._remaining_of_group(s.current_player)
                if remaining == 0:
                    s.winner = s.current_player
                    s.game_over = True
                    return {"action": "win", "player": s.current_player}
                else:
                    s.winner = 2 if s.current_player == 1 else 1
                    s.game_over = True
                    return {"action": "lose", "player": s.current_player,
                            "reason": "early_eight"}

        opp_foul = False
        for ball in potted:
            is_own = (own_group == "solids" and ball.get("is_solid")) or \
                     (own_group == "stripes" and ball.get("is_stripe"))
            is_opp = (opp_group == "solids" and ball.get("is_solid")) or \
                     (opp_group == "stripes" and ball.get("is_stripe"))

            if is_own:
                self._decrement_remaining(s.current_player)
                if s.current_player == 1:
                    s.player1_score += 1
                else:
                    s.player2_score += 1
            if is_opp:
                opp_foul = True

        if opp_foul:
            s.switch_player()
            return {"action": "switch_player", "player": s.current_player,
                    "foul": True, "reason": "potted_opponent_ball"}

        return {"action": "continue", "player": s.current_player}

    def _remaining_of_group(self, player: int) -> int:
        return self.state.p1_remaining if player == 1 else self.state.p2_remaining

    def _decrement_remaining(self, player: int) -> None:
        if player == 1:
            self.state.p1_remaining = max(0, self.state.p1_remaining - 1)
        else:
            self.state.p2_remaining = max(0, self.state.p2_remaining - 1)

    def detect_fouls(self, potted: list, cue_pocketed: bool = False,
                     no_ball_hit: bool = False, no_cushion: bool = False,
                     ball_off_table: bool = False, wrong_player: bool = False,
                     is_weak_break: bool = False) -> list:
        """Detect all fouls per CTBA 2025 rules (20 types)."""
        results = []
        s = self.state

        # 白球进袋 / 飞台
        if cue_pocketed:
            results.append({"type": "cue_pocketed", "desc": "白球进袋", "severity": "foul"})

        # 未命中目标球
        if no_ball_hit:
            results.append({"type": "no_hit", "desc": "未命中目标球", "severity": "foul"})

        # 无球碰库
        if no_cushion and not potted:
            results.append({"type": "no_cushion", "desc": "击球后无球碰库", "severity": "foul"})

        # 球飞台
        if ball_off_table:
            for b in potted:
                if b.get("is_black"):
                    results.append({"type": "black8_off_table", "desc": "8号球飞离台面", "severity": "loss"})
                    return results
            results.append({"type": "ball_off_table", "desc": "球飞出台面", "severity": "foul"})

        # 轮次错误
        if wrong_player:
            results.append({"type": "wrong_player", "desc": "轮次错误", "severity": "foul"})

        # F14: 最后一颗目标球+8号球同时入袋
        remaining = self._remaining_of_group(s.current_player)
        has_target = any(b.get("is_solid") or b.get("is_stripe") for b in potted)
        has_black = any(b.get("is_black") for b in potted)
        if remaining == 1 and has_target and has_black:
            results.append({"type": "last_and_8ball", "desc": "最后一颗目标球与8号球同时入袋", "severity": "loss"})
            return results

        # F16: 黑8提前进袋（致命犯规）
        for b in potted:
            if b.get("is_black") and remaining > 0:
                results.append({"type": "early_eight", "desc": "黑8提前进袋", "severity": "loss"})
                break

        # 开放球局打8号
        if s.table_open:
            for b in potted:
                if b.get("is_black"):
                    results.append({"type": "open_8ball", "desc": "开放球局先碰8号", "severity": "foul"})
                    break

        # 打进对方球
        own_group = s.player1_balls if s.current_player == 1 else s.player2_balls
        if own_group:
            for b in potted:
                is_opp = (own_group == "solids" and b.get("is_stripe")) or \
                         (own_group == "stripes" and b.get("is_solid"))
                if is_opp:
                    results.append({"type": "opponent_ball", "desc": "打进对方球", "severity": "foul"})
                    break

        # F19: 8号球入错袋（指定袋口规则下）
        if has_black and remaining == 0 and s.require_designate and s.designated_pocket:
            # 检查是否进入正确袋口——从外部传入或在此检测
            pass  # 由main.py在调用前判定

        # 打黑8时白球进袋 → F13
        if cue_pocketed and remaining == 0:
            results.append({"type": "black8_cue_pocketed", "desc": "8号球入袋同时白球进袋", "severity": "loss"})

        # F20: 开球小力量
        if is_weak_break and s.is_break_shot:
            results.append({"type": "weak_break", "desc": "小力量开球", "severity": "intentional"})

        return results

    def apply_fouls(self, fouls: list) -> dict:
        """Apply foul results: switch, free ball, intentional cumulative, or loss."""
        s = self.state
        # 致命犯规→判负
        for f in fouls:
            if f.get("severity") == "loss":
                s.winner = 2 if s.current_player == 1 else 1
                s.game_over = True
                s.phase = "game_over"
                return {"action": "lose", "player": s.current_player, "reason": f["desc"]}

        # 故意犯规(F17/F20)累计
        for f in fouls:
            if f.get("severity") == "intentional":
                if s.current_player == 1:
                    s.intentional_fouls_p1 += 1
                    count = s.intentional_fouls_p1
                else:
                    s.intentional_fouls_p2 += 1
                    count = s.intentional_fouls_p2
                if count >= 3:
                    s.winner = 2 if s.current_player == 1 else 1
                    s.game_over = True
                    s.phase = "match_over"
                    return {"action": "lose_match", "player": s.current_player,
                            "reason": f"第{count}次故意犯规"}
                elif count >= 2:
                    s.winner = 2 if s.current_player == 1 else 1
                    s.game_over = True
                    s.phase = "game_over"
                    return {"action": "lose", "player": s.current_player,
                            "reason": f"第{count}次故意犯规"}
                else:
                    # 第一次警告
                    s.switch_player()
                    return {"action": "switch_player", "player": s.current_player,
                            "foul": True, "intentional_count": count,
                            "reasons": [f["desc"]]}

        s.switch_player()
        if any(f.get("type") == "cue_pocketed" for f in fouls):
            s.free_ball = True
        return {"action": "switch_player", "player": s.current_player,
                "foul": True, "free_ball": s.free_ball,
                "reasons": [f["desc"] for f in fouls]}

    def clear_free_ball(self) -> None:
        self.state.free_ball = False
        self.state.foul = False

    def save_history(self, path: str = "") -> bool:
        p = path or _os.path.join(_os.path.dirname(__file__), '..', 'learning', 'match_history.json')
        try:
            data = {
                "player1_name": self.state.player1_name,
                "player2_name": self.state.player2_name,
                "player1_score": self.state.player1_score,
                "player2_score": self.state.player2_score,
                "winner": self.state.winner,
                "game_over": self.state.game_over,
                "player1_balls": self.state.player1_balls,
                "player2_balls": self.state.player2_balls,
                "history": self.state.history[-50:],
                "last_updated": _dt.now().isoformat(),
            }
            with open(p, 'w', encoding='utf-8') as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def load_history(self, path: str = "") -> bool:
        """Load match history from disk. Returns True if history was loaded."""
        p = path or _os.path.join(_os.path.dirname(__file__), '..', 'learning', 'match_history.json')
        try:
            if not _os.path.exists(p):
                return False
            with open(p, 'r', encoding='utf-8') as f:
                data = _json.load(f)
            self.state.player1_name = data.get("player1_name", "选手一")
            self.state.player2_name = data.get("player2_name", "选手二")
            self.state.player1_score = data.get("player1_score", 0)
            self.state.player2_score = data.get("player2_score", 0)
            self.state.player1_balls = data.get("player1_balls", "")
            self.state.player2_balls = data.get("player2_balls", "")
            self.state.game_over = data.get("game_over", False)
            self.state.winner = data.get("winner", None)
            return True
        except Exception:
            return False
