from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MatchState:
    player1_score: int = 0
    player2_score: int = 0
    current_player: int = 1       # 1 or 2
    player1_balls: str = ""       # "solids" or "stripes"
    player2_balls: str = ""
    is_break_shot: bool = True
    game_over: bool = False
    winner: Optional[int] = None
    foul: bool = False
    shots_this_turn: int = 0
    history: List[dict] = field(default_factory=list)

    def switch_player(self) -> None:
        self.current_player = 2 if self.current_player == 1 else 1
        self.shots_this_turn = 0

    def record_shot(self, potted: List[str], foul: bool = False) -> None:
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
        self._assignment_locked = False

    def start_new_match(self) -> None:
        self.state = MatchState()

    def process_shot(self, potted_balls: List[str],
                     is_foul: bool = False) -> dict:
        s = self.state
        s.record_shot(potted_balls, is_foul)

        # Handle break shot - ball type assignment
        if s.is_break_shot:
            return self._handle_break(potted_balls)

        # Handle foul
        if is_foul:
            s.switch_player()
            return {"action": "switch_player", "player": s.current_player}

        # Handle potting
        if potted_balls:
            self._handle_pot(potted_balls)
            return {"action": "continue", "player": s.current_player}

        # No ball potted - switch player
        s.switch_player()
        return {"action": "switch_player", "player": s.current_player}

    def get_recommended_targets(self, balls: List[dict]) -> List[dict]:
        """Get recommended target balls for current player."""
        s = self.state
        player_balls = self._get_player_balls(balls, s.current_player)
        if not player_balls:
            return []
        return sorted(player_balls, key=lambda b: b.get("difficulty", 0))

    def _handle_break(self, potted: List[str]) -> dict:
        s = self.state
        s.is_break_shot = False
        if potted:
            first = potted[0]
            if first in self._solids():
                s.player1_balls = "solids"
                s.player2_balls = "stripes"
            else:
                s.player1_balls = "stripes"
                s.player2_balls = "solids"
            return {"action": "assign", "p1": s.player1_balls,
                    "p2": s.player2_balls, "player": 1}
        return {"action": "open_table", "player": 1}

    def _handle_pot(self, potted: List[str]) -> None:
        s = self.state
        has_black = "black" in potted
        if has_black:
            player_balls_remaining = self._remaining_of_group(
                s.current_player)
            if player_balls_remaining == 0:
                s.winner = s.current_player
                s.game_over = True

    def _get_player_balls(self, balls: List[dict],
                          player: int) -> List[dict]:
        s = self.state
        group = s.player1_balls if player == 1 else s.player2_balls
        if group == "solids":
            return [b for b in balls if b.get("is_solid")]
        elif group == "stripes":
            return [b for b in balls if b.get("is_stripe")]
        return []

    def _remaining_of_group(self, player: int) -> int:
        return 7

    @staticmethod
    def _solids() -> List[str]:
        return ["yellow", "blue", "red", "purple", "orange", "green", "brown"]

    @staticmethod
    def _stripes() -> List[str]:
        return ["yellow", "blue", "red", "purple", "orange", "green", "brown"]

