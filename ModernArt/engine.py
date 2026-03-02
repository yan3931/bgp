"""
ModernArt/engine.py - Modern Art 业务引擎层

纯游戏逻辑：交易处理、回合结算估值、历史记录等。
不依赖 FastAPI、Socket.IO 或数据库。
"""

import copy
import uuid
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ARTISTS = [
    "Manuel Carvalho (Yellow)", "Sigrid Thaler (Blue)",
    "Daniel Melim (Red)", "Ramon Martins (Green)", "Rafael Silveira (Orange)",
]
ARTIST_KEYS = ["yellow", "blue", "red", "green", "orange"]
COLOR_MAP = {
    "yellow": "黄 (Manuel Carvalho)",
    "blue": "蓝 (Sigrid Thaler)",
    "red": "红 (Daniel Melim)",
    "green": "绿 (Ramon Martins)",
    "orange": "橙 (Rafael Silveira)",
}


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class GameState:
    def __init__(self) -> None:
        self.players: Dict[str, Dict[str, Any]] = {}  # name -> {"money": int, "portfolio": {...}}
        self.current_round = 1
        self.round_paintings = {key: 0 for key in ARTIST_KEYS}
        self.artist_values_history: Dict[str, List[int]] = {key: [] for key in ARTIST_KEYS}
        self.started = False
        self.history_log: List[str] = []

    def reset_round(self) -> None:
        self.round_paintings = {key: 0 for key in ARTIST_KEYS}
        for player in self.players.values():
            player["portfolio"] = {key: 0 for key in ARTIST_KEYS}

    def add_log(self, message: str) -> None:
        self.history_log.append(message)


# ---------------------------------------------------------------------------
# 引擎类
# ---------------------------------------------------------------------------

class ModernArtEngine:
    """Modern Art 游戏业务引擎。"""

    def join_game(self, state: GameState, player_name: str) -> Dict[str, Any]:
        if player_name and player_name in state.players:
            return {"status": "success", "state": self.get_state_for_player(state, player_name)}
        if state.started:
            return {"status": "error", "msg": "Game already started"}
        if player_name and player_name not in state.players:
            state.players[player_name] = {
                "money": 100,
                "portfolio": {key: 0 for key in ARTIST_KEYS},
            }
            state.add_log(f"{player_name} 加入了游戏")
        return {"status": "success", "state": self.get_state_for_player(state, player_name)}

    def start_game(self, state: GameState, player_name: str) -> Optional[str]:
        """尝试开始游戏。返回 None 表示成功，返回错误消息表示失败。"""
        if len(state.players) < 3:
            return "Need at least 3 players"
        state.started = True
        state.add_log(f"{player_name} 开始了游戏！第 1 回合")
        return None

    def reset(self, state: GameState) -> None:
        state.__init__()

    def play_again(self, state: GameState) -> None:
        if state.started:
            for player in state.players.values():
                player["money"] = 100
                player["portfolio"] = {key: 0 for key in ARTIST_KEYS}
            state.current_round = 1
            state.round_paintings = {key: 0 for key in ARTIST_KEYS}
            state.artist_values_history = {key: [] for key in ARTIST_KEYS}
            state.started = False
            state.history_log = ["--- 游戏已由其中一位玩家重启，等待开始 ---"]

    def get_state_for_player(self, state: GameState, current_player: str) -> Dict[str, Any]:
        players_copy = copy.deepcopy(state.players)
        if state.started:
            for p_name, p_data in players_copy.items():
                if p_name != current_player:
                    p_data["money"] = "???"
        return {
            "started": state.started,
            "players": players_copy,
            "current_round": state.current_round,
            "round_paintings": state.round_paintings,
            "artist_values_history": state.artist_values_history,
            "history_log": state.history_log,
        }

    def validate_transaction(
        self,
        state: GameState,
        seller: str,
        buyer: str,
        artist: str,
    ) -> Optional[str]:
        """验证交易合法性。返回 None 表示合法，返回错误消息字符串表示不合法。"""
        if not state.started:
            return "Game not started"
        if artist not in ARTIST_KEYS:
            return "Invalid artist"
        if buyer != "Bank" and buyer not in state.players:
            return "Invalid buyer"
        if seller not in state.players:
            return "Invalid seller"
        return None

    def execute_transaction(
        self,
        state: GameState,
        seller: str,
        buyer: str,
        artist: str,
        price: int,
    ) -> bool:
        """
        执行交易。返回 True 表示触发了回合结算（某画家打出 >= 5 张）。
        """
        # 确定收款方
        payee = "Bank" if (buyer == seller and buyer != "Bank") else seller

        if buyer != "Bank":
            if state.players[buyer]["money"] != "???":
                state.players[buyer]["money"] -= price
        if payee != "Bank":
            if state.players[payee]["money"] != "???":
                state.players[payee]["money"] += price
        if buyer != "Bank":
            state.players[buyer]["portfolio"][artist] += 1

        state.round_paintings[artist] += 1

        # 日志
        if buyer == "Bank":
            state.add_log(f"{seller} 打出了 {COLOR_MAP[artist]} 的画作（流拍/没人买）")
        elif buyer == seller:
            state.add_log(f"{seller} 花 ${price} 购买了自己打出的 {COLOR_MAP[artist]} 画作")
        else:
            state.add_log(f"{seller} 以 ${price} 卖给 {buyer} 一张 {COLOR_MAP[artist]} 画作")

        return state.round_paintings[artist] >= 5

    def trigger_end_round(self, state: GameState) -> Optional[Dict]:
        """
        触发回合结算。返回结束数据（用于数据库存储），或 None（如果未到最终回合）。
        """
        if state.current_round > 4:
            return None

        # 确定前 3 名画家
        artists_with_counts = [
            (state.round_paintings[key], -i, key)
            for i, key in enumerate(ARTIST_KEYS)
        ]
        artists_with_counts.sort(reverse=True)

        round_values = {key: 0 for key in ARTIST_KEYS}
        values = [30, 20, 10]
        placed_count = 0
        for count, _, key in artists_with_counts:
            if count > 0 and placed_count < 3:
                round_values[key] = values[placed_count]
                placed_count += 1

        for key in ARTIST_KEYS:
            state.artist_values_history[key].append(round_values[key])

        state.add_log(f"--- 结算 第 {state.current_round} 回合 ---")

        # 结算分红
        for player_name, player_data in state.players.items():
            player_total_payout = 0
            payouts_msg = []
            for key in ARTIST_KEYS:
                count = player_data["portfolio"][key]
                if count > 0 and round_values[key] > 0:
                    total_value = sum(state.artist_values_history[key])
                    payout = count * total_value
                    if player_data["money"] != "???":
                        player_data["money"] += payout
                    player_total_payout += payout
                    payouts_msg.append(f"{count}张{COLOR_MAP[key].split(' ')[0]}")

            if player_total_payout > 0:
                state.add_log(f"💰 {player_name} 卖出 {', '.join(payouts_msg)}，获得 ${player_total_payout}")
            else:
                state.add_log(f"💰 {player_name} 本回合无分红")

        state.current_round += 1
        if state.current_round <= 4:
            state.reset_round()
            state.add_log(f"--- 开始 第 {state.current_round} 回合 ---")
            return None
        else:
            state.add_log("--- 游戏结束 ---")
            return self._build_game_end_data(state)

    def _build_game_end_data(self, state: GameState) -> Optional[Dict]:
        """构建游戏结束时需要存储到数据库的数据。"""
        if not state.players:
            return None

        max_money = -1
        for p_data in state.players.values():
            if p_data["money"] != "???" and p_data["money"] > max_money:
                max_money = p_data["money"]

        players_data = []
        for p_name, p_data in state.players.items():
            if p_data["money"] != "???":
                players_data.append({
                    "name": p_name,
                    "final_money": p_data["money"],
                    "is_winner": (p_data["money"] == max_money),
                })

        return {
            "game_id": str(uuid.uuid4()),
            "players_data": players_data,
        }
