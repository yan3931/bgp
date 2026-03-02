"""
lasvegas/engine.py - Las Vegas 业务引擎层

纯游戏逻辑：钞票分配、排名计算、赌场场地设置等。
不依赖 FastAPI、Socket.IO 或数据库。
"""

import random
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

VALID_DENOMINATIONS = [30, 40, 50, 60, 70, 80, 90, 100]
BILL_POOL = {
    30: 11, 40: 11, 50: 13, 60: 15,
    70: 13, 80: 11, 90: 9, 100: 7,
}
TILE_GROUPS = {
    "A": ["A1", "A2"], "B": ["B1", "B2"],
    "C": ["C1", "C2"], "D": ["D1", "D2"],
    "E": ["E1", "E2"], "F": ["F1", "F2"],
    "G": ["G1", "G2"], "H": ["H1", "H2"],
}


class Bill(BaseModel):
    id: str
    value: int


class Player(BaseModel):
    name: str
    bills: List[Bill] = []
    total_amount: int = 0
    bill_count: int = 0
    rank: int = 0


class GameState:
    def __init__(self) -> None:
        self.players: List[Player] = []
        self.field_setup: Optional[List[Dict[str, Any]]] = None
        self.status = "active"


# ---------------------------------------------------------------------------
# 引擎类
# ---------------------------------------------------------------------------

class LasVegasEngine:
    """Las Vegas 游戏业务引擎。操作传入的 GameState 对象。"""

    # -- 纯计算函数 --

    @staticmethod
    def recalc_player(player: Player) -> None:
        player.total_amount = sum(b.value for b in player.bills)
        player.bill_count = len(player.bills)

    @staticmethod
    def recalc_ranks(state: GameState) -> None:
        sorted_players = sorted(
            state.players,
            key=lambda p: (-p.total_amount, -p.bill_count),
        )
        for rank, player in enumerate(sorted_players):
            original = next(item for item in state.players if item.name == player.name)
            original.rank = rank + 1

    @staticmethod
    def get_remaining_pool(players: List[Player]) -> Dict[int, int]:
        remaining = dict(BILL_POOL)
        for player in players:
            for bill in player.bills:
                if bill.value in remaining:
                    remaining[bill.value] = max(0, remaining[bill.value] - 1)
        return remaining

    @staticmethod
    def draw_bill_from_pool(pool: Dict[int, int]) -> Optional[int]:
        weighted = [(value, count) for value, count in pool.items() if count > 0]
        if not weighted:
            return None
        total_weight = sum(count for _, count in weighted)
        target = random.uniform(0, total_weight)
        cumulative = 0.0
        for value, count in weighted:
            cumulative += count
            if target <= cumulative:
                pool[value] -= 1
                return value
        value = weighted[-1][0]
        pool[value] -= 1
        return value

    @classmethod
    def distribute_casino_bills(cls, players: List[Player]) -> List[List[int]]:
        pool = cls.get_remaining_pool(players)
        pairs: List[List[int]] = []
        for _ in range(6):
            b1 = cls.draw_bill_from_pool(pool)
            b2 = cls.draw_bill_from_pool(pool)
            bills = sorted([v for v in (b1, b2) if v is not None], reverse=True)
            pairs.append(bills)

        pairs.sort(key=lambda b: (sum(b), b[0] if b else 0), reverse=True)
        result: List[List[int]] = [[] for _ in range(6)]
        for idx, bills in enumerate(pairs):
            result[5 - idx] = bills
        return result

    # -- 业务操作 --

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

    def add_bill(self, state: GameState, player_name: str, value: int) -> Dict[str, str]:
        player = next((p for p in state.players if p.name == player_name), None)
        if not player:
            return {"status": "error", "msg": "Player not found"}
        if value not in VALID_DENOMINATIONS:
            return {"status": "error", "msg": "Invalid denomination"}

        bill = Bill(id=str(uuid.uuid4())[:8], value=value)
        player.bills.append(bill)
        self.recalc_player(player)
        self.recalc_ranks(state)
        return {"status": "ok"}

    def remove_bill(self, state: GameState, player_name: str, bill_id: str) -> Dict[str, str]:
        player = next((p for p in state.players if p.name == player_name), None)
        if not player:
            return {"status": "error", "msg": "Player not found"}
        player.bills = [b for b in player.bills if b.id != bill_id]
        self.recalc_player(player)
        self.recalc_ranks(state)
        return {"status": "ok"}

    def setup_field(self, state: GameState) -> List[Dict[str, Any]]:
        candidates = [random.choice(group_tiles) for group_tiles in TILE_GROUPS.values()]
        random.shuffle(candidates)
        chosen = candidates[:6]
        casino_bills = self.distribute_casino_bills(state.players)
        state.field_setup = [
            {"casino": idx + 1, "tile_id": chosen[idx], "bills": casino_bills[idx]}
            for idx in range(6)
        ]
        return state.field_setup

    def get_status(self, state: GameState) -> Dict[str, Any]:
        all_players = [p.model_dump() for p in state.players]
        ranked = sorted(all_players, key=lambda p: (-p["total_amount"], -p["bill_count"]))
        return {"ranked": ranked, "players": all_players, "field": state.field_setup}

    def validate_end_game(self, state: GameState) -> Optional[Dict[str, str]]:
        """验证是否满足结束条件，返回 None 表示可以结束，返回 dict 表示错误。"""
        if not state.players:
            return {"status": "error", "msg": "No players"}
        if not any(p.bill_count > 0 for p in state.players):
            return {"status": "error", "msg": "No bills recorded"}
        return None
