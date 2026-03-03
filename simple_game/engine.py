"""
simple_game/engine.py - 简单游戏通用引擎层

用于只需记录玩家与胜者的游戏（璀璨宝石、炸弹猫、纸牌帮等）。
纯逻辑，不依赖 FastAPI、Socket.IO 或数据库。
"""

from typing import Dict, List


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class GameState:
    def __init__(self) -> None:
        self.players: List[str] = []


# ---------------------------------------------------------------------------
# 引擎类
# ---------------------------------------------------------------------------

class SimpleGameEngine:
    """简单游戏引擎 — 管理玩家列表与胜者校验。"""

    def reset(self, state: GameState) -> None:
        state.__init__()

    def add_player(self, state: GameState, name: str) -> Dict:
        name = name.strip()
        if not name:
            return {"status": "error", "msg": "玩家名不能为空"}
        if name in state.players:
            return {"status": "error", "msg": "玩家已存在"}
        state.players.append(name)
        return {"status": "ok"}

    def remove_player(self, state: GameState, name: str) -> Dict:
        if name not in state.players:
            return {"status": "error", "msg": "玩家不存在"}
        state.players.remove(name)
        return {"status": "ok"}

    def validate_record(self, state: GameState, winner: str) -> Dict:
        """校验记录合法性：至少 2 名玩家，胜者在列表中。"""
        if len(state.players) < 2:
            return {"status": "error", "msg": "至少需要 2 名玩家"}
        if winner not in state.players:
            return {"status": "error", "msg": "胜者必须在玩家列表中"}
        return {"status": "ok"}

    def get_status(self, state: GameState) -> Dict:
        return {"players": list(state.players)}
