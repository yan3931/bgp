"""
flip7/engine.py - Flip 7 业务引擎层

纯游戏逻辑：卡牌分数计算、排名、胜利判定等。
不依赖 FastAPI、Socket.IO 或数据库。
"""

import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class Player(BaseModel):
    name: str
    total_score: int = 0
    busts: int = 0
    rank: int = 0


class GameState:
    def __init__(self) -> None:
        self.players: List[Player] = []
        self.status = "active"
        self.winning_score = 200


# ---------------------------------------------------------------------------
# 引擎类
# ---------------------------------------------------------------------------

class Flip7Engine:
    """Flip 7 游戏业务引擎。"""

    @staticmethod
    def calculate_round_score(cards: List[str]) -> int:
        """
        根据翻到的卡牌计算单轮得分。
        卡牌可以是数字 (0-12) 的字符串或修饰符 ('+2'~'+10', 'x2')。
        如果翻到重复数字则爆牌，返回 0。
        恰好 7 张不重复的数字卡获得 15 分奖励。
        """
        numbers: List[int] = []
        modifiers_addition = 0
        multiplier = 1

        for c in cards:
            if c == 'x2':
                multiplier *= 2
            elif c.startswith('+'):
                modifiers_addition += int(c[1:])
            else:
                numbers.append(int(c))

        # 爆牌检查
        if len(numbers) != len(set(numbers)):
            return 0

        base_sum = sum(numbers)
        flip_bonus = 15 if len(set(numbers)) == 7 else 0
        return (base_sum * multiplier) + modifiers_addition + flip_bonus

    def recalc_ranks(self, state: GameState) -> None:
        sorted_players = sorted(state.players, key=lambda p: -p.total_score)
        for rank, p in enumerate(sorted_players):
            original = next(pl for pl in state.players if pl.name == p.name)
            original.rank = rank + 1

    def reset(self, state: GameState) -> None:
        state.__init__()

    def add_player(self, state: GameState, name: str) -> Dict[str, str]:
        if any(p.name == name for p in state.players):
            return {"status": "exists", "msg": "Player already exists"}
        state.players.append(Player(name=name))
        self.recalc_ranks(state)
        return {"status": "ok"}

    def remove_player(self, state: GameState, name: str) -> Dict[str, str]:
        state.players = [p for p in state.players if p.name != name]
        self.recalc_ranks(state)
        return {"status": "ok"}

    def submit_round(
        self,
        state: GameState,
        players_data: List[Dict[str, object]],
    ) -> Dict:
        """
        提交一轮卡牌数据，计算分数，更新总分。
        players_data: [{"name": str, "cards": List[str]}, ...]
        返回 {"status": "ok"|"game_over"|"error", ...}
        """
        if state.status != "active":
            return {"status": "error", "msg": "Game is already over"}

        round_scores: Dict[str, int] = {}
        for p_data in players_data:
            name = p_data["name"]
            cards = p_data["cards"]
            score = self.calculate_round_score(cards)
            round_scores[name] = score

            player = next((p for p in state.players if p.name == name), None)
            if player:
                player.total_score += score
                if score == 0 and len(cards) > 0:
                    player.busts += 1

        self.recalc_ranks(state)

        # 检查胜利条件
        winners = [p for p in state.players if p.total_score >= state.winning_score]
        if winners:
            state.status = "finished"
            best_player = sorted(winners, key=lambda p: -p.total_score)[0]
            game_id = str(uuid.uuid4())[:8]
            players_db_data = [
                {
                    "name": p.name,
                    "final_score": p.total_score,
                    "is_winner": (p.name == best_player.name),
                    "bust_count": p.busts,
                }
                for p in state.players
            ]
            return {
                "status": "game_over",
                "round_scores": round_scores,
                "winner": best_player.name,
                "game_id": game_id,
                "players_db_data": players_db_data,
            }

        return {"status": "ok", "round_scores": round_scores}

    def get_status(self, state: GameState) -> Dict:
        all_players = [p.model_dump() for p in state.players]
        ranked = sorted(all_players, key=lambda p: -p["total_score"])
        return {"status": state.status, "ranked": ranked, "players": all_players}
