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
                     no_ball_hit: bool = False) -> dict:
        """Process a shot with full foul detection.

        Args:
            potted_balls: list of pocketed balls with {is_solid, is_stripe, is_black, is_cue}
            is_foul: pre-detected foul (e.g. from vision)
            cue_pocketed: cue ball went in pocket
            no_ball_hit: no ball was contacted

        Returns action dict.
        """
        s = self.state

        # Detect all fouls
        fouls = self.detect_fouls(potted_balls, cue_pocketed=cue_pocketed,
                                   no_ball_hit=no_ball_hit)

        s.record_shot(potted_balls, is_foul or len(fouls) > 0)

        # Break shot
        if s.is_break_shot:
            s.is_break_shot = False
            if fouls:
                return self.apply_fouls(fouls)
            if potted_balls:
                return self._handle_break(potted_balls)
            s.switch_player()
            return {"action": "switch_player", "player": s.current_player}

        # Foul handling
        if fouls:
            return self.apply_fouls(fouls)
        if is_foul:
            s.switch_player()
            return {"action": "switch_player", "player": s.current_player,
                    "foul": True}

        # Potted balls
        if potted_balls:
            return self._handle_pot(potted_balls)

        # Miss
        s.switch_player()
        return {"action": "switch_player", "player": s.current_player}

    def _handle_break(self, potted: List[Dict[str, Any]]) -> dict:
        """Assign ball groups based on first pocketed ball after break."""
        s = self.state
        s.table_open = False
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
        return {"action": "assign", "p1": s.player1_balls,
                "p2": s.player2_balls, "player": s.current_player}

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
                     no_ball_hit: bool = False) -> list:
        """Detect all fouls. Returns list of {type, desc, severity}."""
        results = []
        s = self.state
        if cue_pocketed:
            results.append({"type": "cue_pocketed", "desc": "白球进袋", "severity": "foul"})
        if no_ball_hit:
            results.append({"type": "no_hit", "desc": "未命中目标球", "severity": "foul"})
        for b in potted:
            if b.get("is_black") and self._remaining_of_group(s.current_player) > 0:
                results.append({"type": "early_eight", "desc": "黑8提前进袋", "severity": "loss"})
                break
        own_group = s.player1_balls if s.current_player == 1 else s.player2_balls
        if own_group:
            for b in potted:
                is_opp = (own_group == "solids" and b.get("is_stripe")) or \
                         (own_group == "stripes" and b.get("is_solid"))
                if is_opp:
                    results.append({"type": "opponent_ball", "desc": "打进对方球", "severity": "foul"})
                    break
        return results

    def apply_fouls(self, fouls: list) -> dict:
        """Apply foul results: switch, free ball, or loss."""
        s = self.state
        for f in fouls:
            if f.get("severity") == "loss":
                s.winner = 2 if s.current_player == 1 else 1
                s.game_over = True
                return {"action": "lose", "player": s.current_player, "reason": f["desc"]}
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
