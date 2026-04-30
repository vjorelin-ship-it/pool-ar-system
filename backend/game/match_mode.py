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
    current_player: int = 1       # 1 or 2
    player1_balls: str = ""       # "solids" or "stripes"
    player2_balls: str = ""
    is_break_shot: bool = True
    game_over: bool = False
    winner: int | None = None
    foul: bool = False
    shots_this_turn: int = 0
    history: List[dict] = field(default_factory=list)
    # Track remaining balls per group per player (initialized on assignment)
    p1_remaining: int = 0
    p2_remaining: int = 0

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
                     is_foul: bool = False, is_break: bool = False) -> dict:
        """处理击球结果

        Args:
            potted_balls: 进袋的球列表，每颗球包含:
                color, is_solid, is_stripe, is_black, is_cue
            is_foul: 是否犯规

        Returns:
            action: continue / switch_player / assign / win / lose
            player: current_player
        """
        s = self.state

        # Set foul flag before break check so _handle_break sees it
        if is_foul:
            s.foul = True

        s.record_shot(potted_balls, is_foul)

        # 开球处理 - 首颗进球确定球色归属
        if s.is_break_shot:
            return self._handle_break(potted_balls)

        # 犯规处理
        if is_foul:
            s.switch_player()
            return {"action": "switch_player", "player": s.current_player}

        # 有球进袋
        if potted_balls:
            return self._handle_pot(potted_balls)

        # 未进球 - 换手
        s.switch_player()
        return {"action": "switch_player", "player": s.current_player}

    def _handle_break(self, potted: List[Dict[str, Any]]) -> dict:
        """Handle break shot — assign ball groups or handle foul."""
        s = self.state
        # If foul on break, switch player without assigning groups
        if s.foul:
            s.is_break_shot = False
            s.switch_player()
            s.foul = False
            return {"action": "open_table", "player": s.current_player}

        s.is_break_shot = False
        if potted:
            first = potted[0]
            if first.get("is_solid"):
                s.player1_balls = "solids"
                s.player2_balls = "stripes"
                s.p1_remaining = 7
                s.p2_remaining = 7
            elif first.get("is_stripe"):
                s.player1_balls = "stripes"
                s.player2_balls = "solids"
                s.p1_remaining = 7
                s.p2_remaining = 7
            return {"action": "assign", "p1": s.player1_balls,
                    "p2": s.player2_balls, "player": 1}
        return {"action": "open_table", "player": 1}

    def _handle_pot(self, potted: List[Dict[str, Any]]) -> dict:
        s = self.state
        own_group = s.player1_balls if s.current_player == 1 else s.player2_balls
        opp_group = "stripes" if own_group == "solids" else "solids"

        for ball in potted:
            # 黑8进袋
            if ball.get("is_black"):
                remaining = self._remaining_of_group(s.current_player)
                if remaining == 0:
                    s.winner = s.current_player
                    s.game_over = True
                    return {"action": "win", "player": s.current_player}
                else:
                    # 己方球未清完就打黑8 → 判负
                    s.winner = 2 if s.current_player == 1 else 1
                    s.game_over = True
                    return {"action": "lose", "player": s.current_player}

            # 检查是否打进己方球
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

            # 打进对方球 → 犯规换手
            if is_opp:
                s.switch_player()
                return {"action": "switch_player", "player": s.current_player,
                        "reason": "potted_opponent_ball"}

        # 正常打进己方球，继续击球
        return {"action": "continue", "player": s.current_player}

    def _remaining_of_group(self, player: int) -> int:
        s = self.state
        return s.p1_remaining if player == 1 else s.p2_remaining

    def _decrement_remaining(self, player: int) -> None:
        s = self.state
        if player == 1:
            s.p1_remaining = max(0, s.p1_remaining - 1)
        else:
            s.p2_remaining = max(0, s.p2_remaining - 1)

    def detect_break_shot(self, balls_on_table: int) -> bool:
        """Detect if this is a break shot (first shot, all 16 balls present)."""
        if self.state.is_break_shot:
            self.state.is_break_shot = False
            return True
        return False

    def detect_fouls(self, potted: list, cue_pocketed: bool = False,
                     played_wrong_ball: bool = False) -> dict:
        """Detect all foul types from a shot.

        Returns: dict with foul_type and description, or None if no foul.
        """
        results = []

        # Cue ball in pocket = foul
        if cue_pocketed:
            results.append({"type": "cue_pocketed", "desc": "白球进袋"})

        # Wrong ball played (hit opponent's ball first)
        if played_wrong_ball:
            results.append({"type": "wrong_ball", "desc": "击打对方球"})

        # No ball hit cushion after contact (currently not detectable)
        # 8-ball pocketed early
        for b in potted:
            if b.get("is_black") and self.state.p1_remaining > 0 and self.state.p2_remaining > 0:
                results.append({"type": "early_eight", "desc": "黑8提前进袋"})

        return results[0] if results else None

    def save_history(self, path: str = "") -> bool:
        """Save match history to JSON file."""
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
                "history": self.state.history[-50:],  # keep last 50 events
                "last_updated": _dt.now().isoformat(),
            }
            with open(p, 'w', encoding='utf-8') as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
