"""
cabo/engine.py - Cabo 业务引擎层

纯游戏逻辑：分数计算、Cabo 惩罚、神风特攻、胜负判定等。
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
    history: List[int] = []
    is_safe: bool = True
    rank: int = 1
    reset_used: bool = False


class RoundRecord(BaseModel):
    round_num: int
    scores: Dict[str, int]
    cabo_caller: Optional[str] = None
    fail_penalty: bool = False
    kamikaze_player: Optional[str] = None


class GameState:
    def __init__(self) -> None:
        self.players: List[Player] = []
        self.round_history: List[RoundRecord] = []
        self.status = "active"
        self.game_id = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 引擎类
# ---------------------------------------------------------------------------

class CaboEngine:
    """Cabo 游戏业务引擎。操作传入的 GameState 对象。"""

    def reset(self, state: GameState) -> None:
        state.__init__()

    def add_player(self, state: GameState, name: str) -> Dict[str, str]:
        if any(p.name == name for p in state.players):
            return {"status": "exists", "msg": "Player exists"}
        state.players.append(Player(name=name))
        return {"status": "ok"}

    def remove_player(self, state: GameState, name: str) -> Dict[str, str]:
        state.players = [p for p in state.players if p.name != name]
        return {"status": "ok"}

    def _apply_100_reset(self, player: Player) -> None:
        """规则：恰好 100 分重置为 50 分（每人限一次）。"""
        if player.total_score == 100 and not player.reset_used:
            player.total_score = 50
            player.reset_used = True
        if player.total_score > 100:
            player.is_safe = False

    def _recalc_ranks(self, state: GameState) -> None:
        sorted_players = sorted(state.players, key=lambda x: x.total_score)
        for rank, p in enumerate(sorted_players):
            original = next(pl for pl in state.players if pl.name == p.name)
            original.rank = rank + 1

    def submit_round(
        self,
        state: GameState,
        raw_scores: Dict[str, int],
        cabo_caller: Optional[str],
        kamikaze_player: Optional[str],
    ) -> Dict:
        """
        提交一轮分数。返回结果字典，包含：
        - status: "ok" | "game_over" | "error"
        - 其他上下文信息
        """
        if state.status == "finished":
            return {"status": "error", "msg": "Game already finished"}

        if not kamikaze_player and not raw_scores:
            return {"status": "error", "msg": "No scores"}

        min_val = 0
        if raw_scores:
            try:
                min_val = min(raw_scores.values())
            except ValueError:
                pass

        round_scores_final: Dict[str, int] = {}
        caller_failed = False

        if kamikaze_player:
            # 神风特攻队: 触发者得 0 分，其他所有人各 +50
            kamikaze_valid = any(p.name == kamikaze_player for p in state.players)
            if not kamikaze_valid:
                return {"status": "error", "msg": "Invalid kamikaze player"}

            for p in state.players:
                if p.name == kamikaze_player:
                    round_scores_final[p.name] = 0
                    p.total_score += 0
                    p.history.append(0)
                else:
                    round_scores_final[p.name] = 50
                    p.total_score += 50
                    p.history.append(50)
                self._apply_100_reset(p)
        else:
            # 正常计分
            for p in state.players:
                card_sum = raw_scores.get(p.name, 0)
                final_points = card_sum

                if cabo_caller and p.name == cabo_caller:
                    if card_sum == min_val:
                        final_points = 0
                    else:
                        final_points = card_sum + 10
                        caller_failed = True

                round_scores_final[p.name] = final_points
                p.total_score += final_points
                p.history.append(final_points)
                self._apply_100_reset(p)

        self._recalc_ranks(state)

        state.round_history.append(RoundRecord(
            round_num=len(state.round_history) + 1,
            scores=round_scores_final,
            cabo_caller=cabo_caller,
            fail_penalty=caller_failed,
            kamikaze_player=kamikaze_player,
        ))

        # 检查是否有人超过 100 分
        game_over = any(not p.is_safe for p in state.players)
        if game_over:
            state.status = "finished"
            winner_player = min(state.players, key=lambda x: x.total_score)
            return {
                "status": "game_over",
                "winner": winner_player.name,
                "players": sorted(state.players, key=lambda x: x.total_score),
                "round_count": len(state.round_history),
            }

        return {"status": "ok"}

    def get_status(self, state: GameState) -> Dict:
        return {
            "players": sorted(state.players, key=lambda x: x.total_score),
            "history": state.round_history,
            "round_count": len(state.round_history),
            "game_status": state.status,
        }
