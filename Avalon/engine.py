"""
Avalon/engine.py - Avalon 业务引擎层

纯游戏逻辑：角色分配、视野计算、任务判定、刺杀、湖中仙女、
兰斯洛特阵营转换、王者之剑等核心状态机逻辑。
不依赖 FastAPI、Socket.IO 或数据库。
"""

import random
from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class RoleType(str, Enum):
    MERLIN = "Merlin"
    PERCIVAL = "Percival"
    SERVANT = "Loyal Servant"
    MORGANA = "Morgana"
    ASSASSIN = "Assassin"
    MORDRED = "Mordred"
    OBERON = "Oberon"
    MINION = "Minion"
    LANCELOT_GOOD = "Lancelot Good"
    LANCELOT_EVIL = "Lancelot Evil"


class Player(BaseModel):
    name: str
    role: RoleType = RoleType.SERVANT


class MissionRecord(BaseModel):
    round_num: int
    team: List[str]
    fail_count: int
    result: str


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ROLE_PRESETS = {
    5: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN],
    6: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN],
    7: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN, RoleType.OBERON],
    8: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MINION],
    9: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MORDRED],
    10: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN, RoleType.OBERON, RoleType.MORDRED],
    "10_lancelot": [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT,
                     RoleType.LANCELOT_GOOD,
                     RoleType.MORGANA, RoleType.MORDRED, RoleType.OBERON, RoleType.LANCELOT_EVIL],
    12: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT,
         RoleType.LANCELOT_GOOD,
         RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MORDRED, RoleType.OBERON, RoleType.LANCELOT_EVIL],
}

MISSION_SIZES = {
    5:  [2, 3, 2, 3, 3],
    6:  [2, 3, 4, 3, 4],
    7:  [2, 3, 3, 4, 4],
    8:  [3, 4, 4, 5, 5],
    9:  [3, 4, 4, 5, 5],
    10: [3, 4, 4, 5, 5],
    12: [3, 4, 5, 6, 6],
}


# ---------------------------------------------------------------------------
# 全局游戏状态
# ---------------------------------------------------------------------------

class GameState:
    def __init__(self) -> None:
        self.target_count = 6
        self.players: List[Player] = []
        self.missions: List[MissionRecord] = []
        self.status = "empty"
        self.vote_fail_count = 0
        self.history: List[dict] = []

        self.vote_team_active = False
        self.team_votes: Dict[str, str] = {}
        self.last_vote_result: Optional[str] = None
        self.last_vote_snapshot: Dict[str, str] = {}

        self.mission_active = False
        self.current_mission_team: List[str] = []
        self.mission_votes: List[str] = []
        self.mission_voted_players: List[str] = []

        self.captain_index = 0
        self.captain_name: Optional[str] = None
        self.team_proposer: Optional[str] = None

        self.assassin_target: Optional[str] = None
        self.game_winner: Optional[str] = None

        self.lady_of_lake_enabled: bool = False
        self.lady_of_lake_holder: Optional[str] = None
        self.lady_of_lake_history: List[str] = []
        self.lady_of_lake_active: bool = False
        self.lady_of_lake_result: Optional[dict] = None
        self.lady_of_lake_inspector: Optional[str] = None
        self.lady_of_lake_initial_holder: Optional[str] = None

        self.lancelot_enabled: bool = False
        self.lancelot_swap_cards: List[bool] = []
        self.lancelot_swapped: bool = False
        self.lancelot_swap_reveal: List[Optional[bool]] = []

        self.excalibur_enabled: bool = False
        self.excalibur_holder: Optional[str] = None
        self.excalibur_phase: str = "none"
        self.excalibur_result: Optional[dict] = None

        # 用于保存上一局玩家名单
        self.previous_players: List[str] = []


# ---------------------------------------------------------------------------
# 引擎类
# ---------------------------------------------------------------------------

class AvalonEngine:
    """Avalon 游戏业务引擎 — 纯状态机逻辑。"""

    # -- 阵营判定 --

    @staticmethod
    def is_evil(role: RoleType) -> bool:
        return role in [RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MORDRED,
                        RoleType.OBERON, RoleType.MINION, RoleType.LANCELOT_EVIL]

    @staticmethod
    def is_currently_evil(player: Player, lancelot_swapped: bool) -> bool:
        if player.role in (RoleType.LANCELOT_GOOD, RoleType.LANCELOT_EVIL):
            original_evil = (player.role == RoleType.LANCELOT_EVIL)
            return not original_evil if lancelot_swapped else original_evil
        return AvalonEngine.is_evil(player.role)

    # -- 视野计算 --

    @staticmethod
    def calculate_vision(viewer: Player, all_players: List[Player]) -> List[Dict[str, str]]:
        vision_info = []
        evil_team_visible = {RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MORDRED, RoleType.MINION}
        merlin_sees = {RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MINION, RoleType.OBERON, RoleType.LANCELOT_EVIL}

        for target in all_players:
            if target.name == viewer.name:
                continue
            seen_identity = None

            if viewer.role == RoleType.MERLIN:
                if target.role in merlin_sees:
                    seen_identity = "坏人"
            elif viewer.role == RoleType.PERCIVAL:
                if target.role in {RoleType.MERLIN, RoleType.MORGANA}:
                    seen_identity = "梅林?"
            elif viewer.role in evil_team_visible:
                if target.role in evil_team_visible:
                    seen_identity = "同伙"
                elif target.role == RoleType.LANCELOT_EVIL:
                    seen_identity = "红方兰斯洛特"
            elif viewer.role == RoleType.LANCELOT_EVIL:
                pass

            if viewer.role == RoleType.OBERON:
                seen_identity = None

            if seen_identity:
                vision_info.append({"name": target.name, "identity": seen_identity})
        return vision_info

    # -- 角色分配 --

    def assign_roles(self, state: GameState) -> None:
        count = state.target_count
        if state.lancelot_enabled and count == 10:
            roles = list(ROLE_PRESETS.get("10_lancelot", ROLE_PRESETS[10]))
        else:
            roles = list(ROLE_PRESETS.get(count, ROLE_PRESETS[6]))
        random.shuffle(roles)
        for idx, p in enumerate(state.players):
            p.role = roles[idx] if idx < len(roles) else RoleType.SERVANT

    def setup_lancelot_cards(self, state: GameState) -> None:
        cards = [True, True] + [False] * 5
        random.shuffle(cards)
        state.lancelot_swap_cards = cards[:5]
        state.lancelot_swap_reveal = [None] * 5
        state.lancelot_swapped = False

    def setup_lady_of_lake(self, state: GameState) -> None:
        if state.target_count >= 8 and state.lady_of_lake_enabled:
            holder_index = (state.captain_index - 1) % len(state.players)
            holder_name = state.players[holder_index].name
            state.lady_of_lake_holder = holder_name
            state.lady_of_lake_initial_holder = holder_name
            state.lady_of_lake_history = [holder_name]

    # -- 队长系统 --

    def get_current_mission_size(self, state: GameState) -> int:
        round_idx = len(state.missions)
        sizes = MISSION_SIZES.get(state.target_count, MISSION_SIZES[6])
        return sizes[round_idx] if round_idx < 5 else sizes[-1]

    def get_next_captain(self, state: GameState) -> Optional[str]:
        if not state.players:
            return None
        state.captain_index = state.captain_index % len(state.players)
        state.captain_name = state.players[state.captain_index].name
        return state.captain_name

    def advance_captain(self, state: GameState) -> None:
        state.captain_index = (state.captain_index + 1) % len(state.players)
        state.captain_name = state.players[state.captain_index].name

    def get_assassin_player(self, state: GameState) -> Optional[Player]:
        assassin = next((p for p in state.players if p.role == RoleType.ASSASSIN), None)
        if assassin:
            return assassin
        return next((p for p in state.players if p.role == RoleType.MORGANA), None)

    # -- 游戏结束检查 --

    def check_game_end(self, state: GameState) -> Optional[str]:
        """
        检查游戏是否结束。
        返回值：
          - None：游戏未结束
          - "assassin"：好人 3 任务成功，进入刺杀阶段
          - "evil"：坏人获胜（3 任务失败 或 5 连续否决）
        """
        success_count = sum(1 for m in state.missions if m.result == 'success')
        fail_count = sum(1 for m in state.missions if m.result == 'fail')

        if success_count >= 3:
            state.status = "assassin"
            return "assassin"
        if fail_count >= 3:
            state.status = "ended"
            state.game_winner = "evil"
            return "evil"
        if state.vote_fail_count >= 5:
            state.status = "ended"
            state.game_winner = "evil"
            return "evil"
        return None

    # -- 核心操作 --

    def reset_game(
        self, state: GameState, player_count: int,
        lancelot_enabled: bool, excalibur_enabled: bool, lady_of_lake_enabled: bool,
    ) -> List[str]:
        previous_names = [p.name for p in state.players]
        state.__init__()
        state.target_count = player_count
        state.lancelot_enabled = lancelot_enabled
        state.excalibur_enabled = excalibur_enabled
        state.lady_of_lake_enabled = lady_of_lake_enabled
        state.status = "joining"
        state.previous_players = previous_names
        return previous_names

    def clear_game(self, state: GameState) -> List[str]:
        previous_names = [p.name for p in state.players]
        state.__init__()
        state.previous_players = previous_names
        return previous_names

    def join_game(self, state: GameState, player_name: str) -> Dict[str, str]:
        exists = next((p for p in state.players if p.name == player_name), None)
        if exists:
            return {"status": "rejoined"}
        if state.status != "joining":
            return {"status": "error", "msg": "游戏已开始或未创建"}
        if len(state.players) >= state.target_count:
            return {"status": "error", "msg": "房间已满"}

        state.players.append(Player(name=player_name))

        if len(state.players) >= state.target_count:
            self.assign_roles(state)
            state.captain_index = random.randint(0, len(state.players) - 1)
            self.get_next_captain(state)
            self.setup_lady_of_lake(state)
            has_lancelot = any(p.role in (RoleType.LANCELOT_GOOD, RoleType.LANCELOT_EVIL) for p in state.players)
            if has_lancelot:
                state.lancelot_enabled = True
                self.setup_lancelot_cards(state)
            state.status = "active"

        return {"status": "joined"}

    def propose_team(self, state: GameState, team: List[str], player_name: Optional[str]) -> Dict:
        required_size = self.get_current_mission_size(state)
        if len(team) != required_size:
            return {"status": "error", "msg": f"本轮需要 {required_size} 人"}

        proposer = player_name or state.captain_name
        if proposer and not any(p.name == proposer for p in state.players):
            return {"status": "error", "msg": "Player not found"}

        state.current_mission_team = team
        state.team_proposer = proposer
        state.vote_team_active = True
        state.team_votes = {}
        state.last_vote_result = None
        return {"status": "ok", "required_size": required_size}

    def vote_team(self, state: GameState, player_name: str, vote: str) -> Dict:
        if not state.vote_team_active:
            return {"status": "ignored"}

        state.team_votes[player_name] = vote

        if len(state.team_votes) >= len(state.players):
            approve_count = list(state.team_votes.values()).count('approve')
            reject_count = list(state.team_votes.values()).count('reject')
            state.last_vote_snapshot = dict(state.team_votes)

            if approve_count > reject_count:
                state.vote_team_active = False
                state.last_vote_result = 'approved'
                state.vote_fail_count = 0
                if state.excalibur_enabled and state.target_count >= 8:
                    state.excalibur_phase = "assign"
                    state.excalibur_holder = None
                    state.excalibur_result = None
                else:
                    state.mission_active = True
                    state.mission_votes = []
                    state.mission_voted_players = []
            else:
                state.history.append({
                    "round_num": len(state.missions) + 1,
                    "proposal_index": state.vote_fail_count + 1,
                    "team": list(state.current_mission_team),
                    "captain": state.captain_name,
                    "votes": dict(state.team_votes),
                    "mission_votes": {},
                    "result": "rejected",
                })
                state.vote_team_active = False
                state.mission_active = False
                state.current_mission_team = []
                state.vote_fail_count += 1
                state.last_vote_result = 'rejected'
                self.advance_captain(state)
                # 返回标识，让调用方检查游戏结束
                end_result = self.check_game_end(state)
                if end_result:
                    return {"status": "ok", "game_end": end_result}

        return {"status": "ok"}

    def vote_mission(self, state: GameState, player_name: str, action: str) -> Dict:
        if not state.mission_active:
            return {"status": "ignored"}
        if player_name in state.mission_voted_players:
            return {"status": "ok"}

        vote_action = action
        player = next((p for p in state.players if p.name == player_name), None)
        if player:
            currently_evil = self.is_currently_evil(player, state.lancelot_swapped)
            if not currently_evil:
                vote_action = 'success'
            if currently_evil and player.role in (RoleType.LANCELOT_GOOD, RoleType.LANCELOT_EVIL):
                vote_action = 'fail'

        state.mission_votes.append(vote_action)
        state.mission_voted_players.append(player_name)

        need_resolve = False
        if len(state.mission_votes) == len(state.current_mission_team):
            if state.excalibur_enabled and state.excalibur_holder and state.excalibur_phase != "done":
                state.excalibur_phase = "decide"
                state.mission_active = False
                return {"status": "ok", "excalibur_decide": True}
            need_resolve = True

        return {"status": "ok", "need_resolve": need_resolve}

    def resolve_mission(self, state: GameState) -> Dict:
        """结算任务结果。返回结果数据。"""
        fail_count = state.mission_votes.count('fail')
        round_idx = len(state.missions)

        is_fail = fail_count >= 1
        if state.target_count >= 7 and round_idx == 3:
            is_fail = fail_count >= 2

        mission_votes_dict = dict(zip(state.mission_voted_players, state.mission_votes))
        state.history.append({
            "round_num": round_idx + 1,
            "proposal_index": state.vote_fail_count + 1,
            "team": list(state.current_mission_team),
            "captain": state.captain_name,
            "votes": dict(state.last_vote_snapshot),
            "mission_votes": mission_votes_dict,
            "result": "approved_fail" if is_fail else "approved_success",
        })

        state.missions.append(MissionRecord(
            round_num=round_idx + 1,
            team=state.current_mission_team,
            fail_count=fail_count,
            result='fail' if is_fail else 'success',
        ))

        state.mission_active = False
        state.current_mission_team = []
        state.excalibur_phase = "none"
        state.excalibur_holder = None

        # 兰斯洛特阵营转换
        if state.lancelot_enabled and round_idx < 5:
            card = state.lancelot_swap_cards[round_idx]
            state.lancelot_swap_reveal[round_idx] = card
            if card:
                state.lancelot_swapped = not state.lancelot_swapped

        # 湖中仙女触发
        completed_rounds = len(state.missions)
        end_result = self.check_game_end(state)
        if (state.lady_of_lake_enabled
                and completed_rounds in (2, 3, 4)
                and end_result is None):
            state.lady_of_lake_active = True
            state.lady_of_lake_result = None
            state.lady_of_lake_inspector = None
            return {"lady_of_lake": True, "game_end": None}
        else:
            if end_result is None:
                self.advance_captain(state)
                end_result = self.check_game_end(state)
            return {"lady_of_lake": False, "game_end": end_result}

    def assign_excalibur(self, state: GameState, target: str) -> Dict:
        if state.excalibur_phase != "assign":
            return {"status": "error", "msg": "当前不在王者之剑分配阶段"}
        proposer = state.team_proposer or state.captain_name
        if target == proposer:
            return {"status": "error", "msg": "不能将王者之剑交给自己"}
        if target not in state.current_mission_team:
            return {"status": "error", "msg": "目标必须是本轮队员"}

        state.excalibur_holder = target
        state.excalibur_phase = "mission"
        state.mission_active = True
        state.mission_votes = []
        state.mission_voted_players = []
        return {"status": "ok"}

    def use_excalibur(self, state: GameState, target: Optional[str]) -> Dict:
        if state.excalibur_phase != "decide":
            return {"status": "error", "msg": "当前不在王者之剑决策阶段"}

        if target:
            if target not in state.mission_voted_players:
                return {"status": "error", "msg": "目标不在任务队伍中"}
            idx = state.mission_voted_players.index(target)
            original_vote = state.mission_votes[idx]
            new_vote = 'fail' if original_vote == 'success' else 'success'
            state.mission_votes[idx] = new_vote
            state.excalibur_result = {"target": target, "original_vote": original_vote}
        else:
            state.excalibur_result = None

        state.excalibur_phase = "done"
        return {"status": "ok"}

    def lady_of_lake(self, state: GameState, target: str) -> Dict:
        if not state.lady_of_lake_active:
            return {"status": "error", "msg": "当前不在湖中仙女阶段"}
        if target in state.lady_of_lake_history:
            return {"status": "error", "msg": "该玩家曾担任过湖中仙女，不可再次被查验"}

        target_player = next((p for p in state.players if p.name == target), None)
        if not target_player:
            return {"status": "error", "msg": "找不到该玩家"}

        target_evil = self.is_currently_evil(target_player, state.lancelot_swapped)
        alignment = "evil" if target_evil else "good"

        inspector = state.lady_of_lake_holder
        state.lady_of_lake_inspector = inspector
        state.lady_of_lake_result = {"target": target, "alignment": alignment}
        state.lady_of_lake_history.append(target)
        state.lady_of_lake_holder = target
        state.lady_of_lake_active = False

        self.advance_captain(state)
        end_result = self.check_game_end(state)

        return {"status": "ok", "alignment": alignment, "game_end": end_result}

    def assassinate(self, state: GameState, target: str) -> Dict:
        if state.status != "assassin":
            return {"status": "error", "msg": "非刺杀阶段"}

        state.assassin_target = target
        target_player = next((p for p in state.players if p.name == target), None)

        if target_player and target_player.role == RoleType.MERLIN:
            state.game_winner = "evil"
        else:
            state.game_winner = "good"

        state.status = "ended"
        return {"status": "ok", "winner": state.game_winner}

    def get_db_results(self, state: GameState, winner_team: str) -> List[Dict]:
        """构建需要写入数据库的结果列表。"""
        results = []
        for p in state.players:
            is_evil_role = self.is_currently_evil(p, state.lancelot_swapped)
            won = (winner_team == "evil" and is_evil_role) or (winner_team == "good" and not is_evil_role)
            results.append({"player_name": p.name, "is_winner": won})
        return results

    def build_status(self, state: GameState, player_name: str) -> Dict:
        """构建给前端的完整状态响应。"""
        if state.status == "empty":
            return {
                "status": "empty", "current_count": 0, "target_count": 0,
                "players_list": [], "mission_history": [], "your_role": "", "vision": [], "revealed_players": [],
                "vote_fail_count": 0, "mission_active": False, "mission_team": [], "has_acted": False,
                "vote_team_active": False, "team_votes": {}, "last_vote_result": None,
                "last_vote_snapshot": {}, "captain": None, "team_proposer": None, "required_team_size": 2,
                "game_winner": None, "assassin_target": None,
                "lady_of_lake_holder": None, "lady_of_lake_active": False,
                "lady_of_lake_result": None, "lady_of_lake_history": [],
                "lady_of_lake_inspector": None,
                "lancelot_enabled": False, "lancelot_swapped": False,
                "lancelot_swap_reveal": [], "current_alignment": None,
                "assassin_role": None,
                "excalibur_enabled": False, "excalibur_holder": None,
                "excalibur_phase": "none", "excalibur_result": None,
            }

        viewer = next((p for p in state.players if p.name == player_name), None)
        round_idx = len(state.missions)
        sizes = MISSION_SIZES.get(state.target_count, MISSION_SIZES[6])
        required_size = sizes[round_idx] if round_idx < 5 else sizes[-1]

        assassin_player = self.get_assassin_player(state)
        assassin_role = assassin_player.role if assassin_player else None

        current_alignment = None
        if viewer and viewer.role in (RoleType.LANCELOT_GOOD, RoleType.LANCELOT_EVIL):
            current_alignment = "evil" if self.is_currently_evil(viewer, state.lancelot_swapped) else "good"

        resp = {
            "status": state.status,
            "current_count": len(state.players),
            "target_count": state.target_count,
            "players_list": [p.name for p in state.players],
            "mission_history": [m.dict() for m in state.missions],
            "vote_fail_count": state.vote_fail_count,
            "your_role": viewer.role if viewer else "",
            "vision": [],
            "revealed_players": [],
            "mission_active": state.mission_active,
            "mission_team": state.current_mission_team,
            "has_acted": (player_name in state.mission_voted_players),
            "vote_team_active": state.vote_team_active,
            "team_votes": state.team_votes,
            "last_vote_result": state.last_vote_result,
            "last_vote_snapshot": state.last_vote_snapshot,
            "captain": state.captain_name,
            "team_proposer": state.team_proposer,
            "required_team_size": required_size,
            "game_winner": state.game_winner,
            "assassin_target": state.assassin_target,
            "lady_of_lake_holder": state.lady_of_lake_holder,
            "lady_of_lake_active": state.lady_of_lake_active,
            "lady_of_lake_result": state.lady_of_lake_result if (state.lady_of_lake_inspector == player_name) else None,
            "lady_of_lake_inspector": state.lady_of_lake_inspector if (state.lady_of_lake_inspector == player_name) else None,
            "lady_of_lake_history": state.lady_of_lake_history,
            "lancelot_enabled": state.lancelot_enabled,
            "lancelot_swapped": state.lancelot_swapped,
            "lancelot_swap_reveal": state.lancelot_swap_reveal,
            "current_alignment": current_alignment,
            "assassin_role": assassin_role,
            "excalibur_enabled": state.excalibur_enabled,
            "excalibur_holder": state.excalibur_holder,
            "excalibur_phase": state.excalibur_phase,
            "excalibur_result": state.excalibur_result if (state.excalibur_holder == player_name) else None,
        }

        if state.status in ["active", "assassin", "lady_of_lake"] and viewer:
            resp["vision"] = self.calculate_vision(viewer, state.players)

        if state.status == "ended":
            resp["revealed_players"] = [{"name": p.name, "role": p.role} for p in state.players]
            resp["history"] = getattr(state, "history", [])

        return resp
