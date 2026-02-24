import asyncio
import random
from typing import List, Dict, Optional
from enum import Enum
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os

app = FastAPI(title="Avalon Simple Server")

# Mount assets
base_dir = os.path.dirname(os.path.abspath(__file__))
assets_dir = os.path.join(base_dir, "assets")
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# -----------------------------------------------------------------------------
# 数据模型
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# 角色预设配置 (标准包)
# -----------------------------------------------------------------------------
ROLE_PRESETS = {
    5: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN],
    6: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN],
    7: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN, RoleType.OBERON],
    8: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MINION],
    9: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MORDRED],
    10: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.MORGANA, RoleType.ASSASSIN, RoleType.OBERON, RoleType.MORDRED],
    # 10人兰斯洛特变体：替换忠臣+刺客
    "10_lancelot": [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT,
                     RoleType.LANCELOT_GOOD,
                     RoleType.MORGANA, RoleType.MORDRED, RoleType.OBERON, RoleType.LANCELOT_EVIL],
    12: [RoleType.MERLIN, RoleType.PERCIVAL, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT, RoleType.SERVANT,
         RoleType.LANCELOT_GOOD,
         RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MORDRED, RoleType.OBERON, RoleType.LANCELOT_EVIL],
}

# 每轮任务人数
MISSION_SIZES = {
    5:  [2, 3, 2, 3, 3],
    6:  [2, 3, 4, 3, 4],
    7:  [2, 3, 3, 4, 4],
    8:  [3, 4, 4, 5, 5],
    9:  [3, 4, 4, 5, 5],
    10: [3, 4, 4, 5, 5],
    12: [3, 4, 5, 6, 6],
}

# -----------------------------------------------------------------------------
# 全局游戏状态
# -----------------------------------------------------------------------------
class GlobalGame:
    def __init__(self):
        self.target_count = 6
        self.players: List[Player] = []
        self.missions: List[MissionRecord] = []
        self.status = "empty"  # empty, joining, active, lady_of_lake, assassin, ended
        self.vote_fail_count = 0

        # 投票阶段
        self.vote_team_active = False
        self.team_votes: Dict[str, str] = {}
        self.last_vote_result: Optional[str] = None
        self.last_vote_snapshot: Dict[str, str] = {}  # 上一轮投票快照

        # 任务执行
        self.mission_active = False
        self.current_mission_team: List[str] = []
        self.mission_votes: List[str] = []
        self.mission_voted_players: List[str] = []

        # 队长系统
        self.captain_index = 0
        self.captain_name: Optional[str] = None

        # 刺杀阶段
        self.assassin_target: Optional[str] = None
        self.game_winner: Optional[str] = None  # "good" or "evil"

        # 湖中仙女
        self.lady_of_lake_enabled: bool = False
        self.lady_of_lake_holder: Optional[str] = None
        self.lady_of_lake_history: List[str] = []  # 曾担任过的玩家（不可再次被查验）
        self.lady_of_lake_active: bool = False     # 是否正在查验中
        self.lady_of_lake_result: Optional[dict] = None  # 最近查验结果
        self.lady_of_lake_inspector: Optional[str] = None  # 执行查验的玩家
        self.lady_of_lake_initial_holder: Optional[str] = None

        # 兰斯洛特
        self.lancelot_enabled: bool = False
        self.lancelot_swap_cards: List[bool] = []  # 5张牌, True=转换, False=不变
        self.lancelot_swapped: bool = False         # 当前是否处于转换状态
        self.lancelot_swap_reveal: List[Optional[bool]] = []  # 每轮翻出的牌

        # 王者之剑 (Excalibur)
        self.excalibur_enabled: bool = False
        self.excalibur_holder: Optional[str] = None
        self.excalibur_phase: str = "none"  # none | assign | decide
        self.excalibur_result: Optional[dict] = None  # {target, original_vote}

game_state = GlobalGame()
global_lock = asyncio.Lock()

# -----------------------------------------------------------------------------
# 请求模型
# -----------------------------------------------------------------------------
class CreateRequest(BaseModel):
    player_count: int
    lancelot_enabled: bool = False
    excalibur_enabled: bool = False
    lady_of_lake_enabled: bool = True

class JoinRequest(BaseModel):
    player_name: str

class StartMissionRequest(BaseModel):
    team: List[str]

class TeamVoteRequest(BaseModel):
    player_name: str
    vote: str

class MissionVoteRequest(BaseModel):
    player_name: str
    action: str

class AssassinRequest(BaseModel):
    target: str

class LadyOfLakeRequest(BaseModel):
    target: str

class ExcaliburAssignRequest(BaseModel):
    target: str

class ExcaliburUseRequest(BaseModel):
    target: Optional[str] = None  # None = skip

# -----------------------------------------------------------------------------
# 逻辑函数
# -----------------------------------------------------------------------------
def is_evil(role: RoleType) -> bool:
    """判断角色的原始阵营是否为邪恶"""
    return role in [RoleType.MORGANA, RoleType.ASSASSIN, RoleType.MORDRED,
                    RoleType.OBERON, RoleType.MINION, RoleType.LANCELOT_EVIL]

def is_currently_evil(player: Player) -> bool:
    """判断玩家当前有效阵营是否为邪恶（考虑兰斯洛特转换）"""
    if player.role in (RoleType.LANCELOT_GOOD, RoleType.LANCELOT_EVIL):
        original_evil = (player.role == RoleType.LANCELOT_EVIL)
        if game_state.lancelot_swapped:
            return not original_evil
        return original_evil
    return is_evil(player.role)

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
            # 普通邪恶队员看到同伙（包括红方兰斯洛特）
            if target.role in evil_team_visible or target.role == RoleType.LANCELOT_EVIL:
                seen_identity = "同伙"
        elif viewer.role == RoleType.LANCELOT_EVIL:
            # 红方兰斯洛特不主动看到队友（类似奥伯伦的反向）
            pass

        if viewer.role == RoleType.OBERON:
            seen_identity = None

        if seen_identity:
            vision_info.append({"name": target.name, "identity": seen_identity})
    return vision_info

def assign_roles():
    count = game_state.target_count
    if game_state.lancelot_enabled and count == 10:
        roles = list(ROLE_PRESETS.get("10_lancelot", ROLE_PRESETS[10]))
    else:
        roles = list(ROLE_PRESETS.get(count, ROLE_PRESETS[6]))
    random.shuffle(roles)
    for idx, p in enumerate(game_state.players):
        p.role = roles[idx] if idx < len(roles) else RoleType.SERVANT

def setup_lancelot_cards():
    """准备兰斯洛特阵营转换牌：2张转换 + 5张不变，洗匀后取5张"""
    cards = [True, True] + [False] * 5  # 2转换 + 5不变
    random.shuffle(cards)
    game_state.lancelot_swap_cards = cards[:5]  # 取5张放在进度条上
    game_state.lancelot_swap_reveal = [None] * 5
    game_state.lancelot_swapped = False

def setup_lady_of_lake():
    """初始化湖中仙女：分配给第一任队长右手边的玩家"""
    if game_state.target_count >= 8 and game_state.lady_of_lake_enabled:
        # 队长右手边 = 队长索引 - 1（顺时针中右手边是逆序）
        holder_index = (game_state.captain_index - 1) % len(game_state.players)
        holder_name = game_state.players[holder_index].name
        game_state.lady_of_lake_holder = holder_name
        game_state.lady_of_lake_initial_holder = holder_name
        game_state.lady_of_lake_history = [holder_name]  # 初始持有者也记入历史

def get_current_mission_size() -> int:
    round_idx = len(game_state.missions)
    sizes = MISSION_SIZES.get(game_state.target_count, MISSION_SIZES[6])
    return sizes[round_idx] if round_idx < 5 else sizes[-1]

def get_next_captain():
    if not game_state.players:
        return None
    game_state.captain_index = game_state.captain_index % len(game_state.players)
    game_state.captain_name = game_state.players[game_state.captain_index].name
    return game_state.captain_name

def advance_captain():
    game_state.captain_index = (game_state.captain_index + 1) % len(game_state.players)
    game_state.captain_name = game_state.players[game_state.captain_index].name

def get_assassin_player() -> Optional[Player]:
    """获取执行刺杀的玩家：优先刺客，若无刺客则由莫甘娜执行"""
    assassin = next((p for p in game_state.players if p.role == RoleType.ASSASSIN), None)
    if assassin:
        return assassin
    morgana = next((p for p in game_state.players if p.role == RoleType.MORGANA), None)
    return morgana

def check_game_end():
    """检查游戏是否结束"""
    success_count = sum(1 for m in game_state.missions if m.result == 'success')
    fail_count = sum(1 for m in game_state.missions if m.result == 'fail')

    if success_count >= 3:
        game_state.status = "assassin"
        return True
    if fail_count >= 3:
        game_state.status = "ended"
        game_state.game_winner = "evil"
        record_db_results("evil")
        return True
    if game_state.vote_fail_count >= 5:
        game_state.status = "ended"
        game_state.game_winner = "evil"
        record_db_results("evil")
        return True
    return False

def record_db_results(winner_team: str):
    try:
        import database
        for p in game_state.players:
            is_evil_role = is_currently_evil(p)
            won = (winner_team == "evil" and is_evil_role) or (winner_team == "good" and not is_evil_role)
            database.record_result("Avalon", p.name, won, 0)
    except Exception as e:
        print(f"Error recording Avalon results: {e}")

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------

@app.post("/reset_game")
async def reset_game(req: CreateRequest):
    async with global_lock:
        previous_names = [p.name for p in game_state.players]
        game_state.__init__()
        game_state.target_count = req.player_count
        game_state.lancelot_enabled = req.lancelot_enabled
        game_state.excalibur_enabled = req.excalibur_enabled
        game_state.lady_of_lake_enabled = req.lady_of_lake_enabled
        game_state.status = "joining"
        game_state.previous_players = previous_names
    return {"status": "ok", "previous_players": previous_names}

@app.get("/lobby")
async def get_lobby():
    return {
        "status": game_state.status,
        "current_count": len(game_state.players),
        "target_count": game_state.target_count,
        "players": [p.name for p in game_state.players],
        "previous_players": getattr(game_state, 'previous_players', []),
        "excalibur_enabled": game_state.excalibur_enabled,
        "lancelot_enabled": game_state.lancelot_enabled,
        "lady_of_lake_enabled": game_state.lady_of_lake_enabled,
    }

@app.post("/end_game")
async def end_game():
    async with global_lock:
        game_state.status = "ended"
    return {"status": "ok"}

@app.post("/clear_game")
async def clear_game():
    """清空游戏，返回empty状态"""
    async with global_lock:
        previous_names = [p.name for p in game_state.players]
        game_state.__init__()
        game_state.previous_players = previous_names
    return {"status": "ok"}

@app.post("/join")
async def join_game(req: JoinRequest):
    async with global_lock:
        exists = next((p for p in game_state.players if p.name == req.player_name), None)
        if exists:
            return {"status": "rejoined"}

        if game_state.status != "joining":
            raise HTTPException(status_code=400, detail="游戏已开始或未创建")

        if len(game_state.players) >= game_state.target_count:
            raise HTTPException(status_code=400, detail="房间已满")

        game_state.players.append(Player(name=req.player_name))

        if len(game_state.players) >= game_state.target_count:
            assign_roles()
            game_state.captain_index = random.randint(0, len(game_state.players) - 1)
            get_next_captain()
            # 初始化湖中仙女（8人+）
            setup_lady_of_lake()
            # 初始化兰斯洛特转换牌（12人局或10人兰斯洛特变体）
            has_lancelot = any(p.role in (RoleType.LANCELOT_GOOD, RoleType.LANCELOT_EVIL) for p in game_state.players)
            if has_lancelot:
                game_state.lancelot_enabled = True
                setup_lancelot_cards()
            game_state.status = "active"

    return {"status": "joined"}

@app.post("/propose_team")
async def propose_team(req: StartMissionRequest):
    async with global_lock:
        required_size = get_current_mission_size()
        if len(req.team) != required_size:
            raise HTTPException(status_code=400, detail=f"本轮需要 {required_size} 人")

        game_state.current_mission_team = req.team
        game_state.vote_team_active = True
        game_state.team_votes = {}
        game_state.last_vote_result = None
    return {"status": "ok", "required_size": required_size}

@app.post("/vote_team")
async def vote_team(req: TeamVoteRequest):
    async with global_lock:
        if not game_state.vote_team_active:
            return {"status": "ignored"}

        game_state.team_votes[req.player_name] = req.vote

        if len(game_state.team_votes) >= len(game_state.players):
            approve_count = list(game_state.team_votes.values()).count('approve')
            reject_count = list(game_state.team_votes.values()).count('reject')

            game_state.last_vote_snapshot = dict(game_state.team_votes)

            if approve_count > reject_count:
                game_state.vote_team_active = False
                game_state.last_vote_result = 'approved'
                game_state.vote_fail_count = 0
                # 王者之剑：队长先分配
                if game_state.excalibur_enabled and game_state.target_count >= 8:
                    game_state.excalibur_phase = "assign"
                    game_state.excalibur_holder = None
                    game_state.excalibur_result = None
                else:
                    game_state.mission_active = True
                    game_state.mission_votes = []
                    game_state.mission_voted_players = []
            else:
                game_state.vote_team_active = False
                game_state.mission_active = False
                game_state.current_mission_team = []
                game_state.vote_fail_count += 1
                game_state.last_vote_result = 'rejected'
                advance_captain()
                check_game_end()

    return {"status": "ok"}

@app.post("/start_mission")
async def start_mission(req: StartMissionRequest):
    return await propose_team(req)

@app.post("/vote_mission")
async def vote_mission(req: MissionVoteRequest):
    async with global_lock:
        if not game_state.mission_active:
            return {"status": "ignored"}
        if req.player_name in game_state.mission_voted_players:
            return {"status": "ok"}

        vote_action = req.action
        player = next((p for p in game_state.players if p.name == req.player_name), None)

        if player:
            currently_evil = is_currently_evil(player)
            # 好人（当前有效阵营）只能投成功
            if not currently_evil:
                vote_action = 'success'
            # 当前处于邪恶阵营的兰斯洛特必须投失败
            if currently_evil and player.role in (RoleType.LANCELOT_GOOD, RoleType.LANCELOT_EVIL):
                vote_action = 'fail'

        game_state.mission_votes.append(vote_action)
        game_state.mission_voted_players.append(req.player_name)

        if len(game_state.mission_votes) == len(game_state.current_mission_team):
            # 王者之剑：所有人投完后进入 decide 阶段而不是立刻结算
            if game_state.excalibur_enabled and game_state.excalibur_holder and game_state.excalibur_phase != "done":
                game_state.excalibur_phase = "decide"
                game_state.mission_active = False  # 暂停任务
                return {"status": "ok"}

            _resolve_mission()

    return {"status": "ok"}

def _resolve_mission():
    """结算任务结果（从 vote_mission 和 excalibur 共用）"""
    fail_count = game_state.mission_votes.count('fail')
    round_idx = len(game_state.missions)

    is_fail = fail_count >= 1
    if game_state.target_count >= 7 and round_idx == 3:
        is_fail = fail_count >= 2

    game_state.missions.append(MissionRecord(
        round_num=round_idx + 1,
        team=game_state.current_mission_team,
        fail_count=fail_count,
        result='fail' if is_fail else 'success'
    ))

    game_state.mission_active = False
    game_state.current_mission_team = []
    game_state.excalibur_phase = "none"
    game_state.excalibur_holder = None

    # --- 兰斯洛特阵营转换牌 ---
    if game_state.lancelot_enabled and round_idx < 5:
        card = game_state.lancelot_swap_cards[round_idx]
        game_state.lancelot_swap_reveal[round_idx] = card
        if card:
            game_state.lancelot_swapped = not game_state.lancelot_swapped

    # --- 湖中仙女触发 ---
    completed_rounds = len(game_state.missions)
    if (game_state.lady_of_lake_enabled
            and completed_rounds in (2, 3, 4)
            and not check_game_end()):
        game_state.lady_of_lake_active = True
        game_state.lady_of_lake_result = None
        game_state.lady_of_lake_inspector = None
    else:
        advance_captain()
        check_game_end()

@app.post("/assign_excalibur")
async def assign_excalibur(req: ExcaliburAssignRequest):
    """队长将王者之剑分配给队伍中一名非自己的队员"""
    async with global_lock:
        if game_state.excalibur_phase != "assign":
            raise HTTPException(status_code=400, detail="当前不在王者之剑分配阶段")
        if req.target == game_state.captain_name:
            raise HTTPException(status_code=400, detail="不能将王者之剑交给自己")
        if req.target not in game_state.current_mission_team:
            raise HTTPException(status_code=400, detail="目标必须是本轮队员")

        game_state.excalibur_holder = req.target
        game_state.excalibur_phase = "mission"  # 标记已分配，等任务投票
        game_state.mission_active = True
        game_state.mission_votes = []
        game_state.mission_voted_players = []
    return {"status": "ok"}

@app.post("/use_excalibur")
async def use_excalibur(req: ExcaliburUseRequest):
    """持剑者使用或跳过王者之剑"""
    async with global_lock:
        if game_state.excalibur_phase != "decide":
            raise HTTPException(status_code=400, detail="当前不在王者之剑决策阶段")

        if req.target:
            # 使用：找到目标的投票索引并翻转
            if req.target not in game_state.mission_voted_players:
                raise HTTPException(status_code=400, detail="目标不在任务队伍中")
            idx = game_state.mission_voted_players.index(req.target)
            original_vote = game_state.mission_votes[idx]
            new_vote = 'fail' if original_vote == 'success' else 'success'
            game_state.mission_votes[idx] = new_vote
            game_state.excalibur_result = {"target": req.target, "original_vote": original_vote}
        else:
            game_state.excalibur_result = None

        # 结算任务
        game_state.excalibur_phase = "done"
        _resolve_mission()

    return {"status": "ok", "excalibur_result": game_state.excalibur_result}

@app.post("/lady_of_lake")
async def lady_of_lake(req: LadyOfLakeRequest):
    """湖中仙女查验"""
    async with global_lock:
        if not game_state.lady_of_lake_active:
            raise HTTPException(status_code=400, detail="当前不在湖中仙女阶段")

        # 不能查验曾经持有过湖中仙女的玩家
        if req.target in game_state.lady_of_lake_history:
            raise HTTPException(status_code=400, detail="该玩家曾担任过湖中仙女，不可再次被查验")

        target_player = next((p for p in game_state.players if p.name == req.target), None)
        if not target_player:
            raise HTTPException(status_code=400, detail="找不到该玩家")

        # 判断被验者的当前有效阵营
        target_evil = is_currently_evil(target_player)
        alignment = "evil" if target_evil else "good"

        # 记录查验者
        inspector = game_state.lady_of_lake_holder  # 当前持有者就是查验者
        game_state.lady_of_lake_inspector = inspector

        game_state.lady_of_lake_result = {
            "target": req.target,
            "alignment": alignment
        }

        # 传递湖中仙女给被验者
        game_state.lady_of_lake_history.append(req.target)
        game_state.lady_of_lake_holder = req.target
        game_state.lady_of_lake_active = False

        # 仙女查验完毕，继续正常流程
        advance_captain()
        check_game_end()

    return {"status": "ok", "alignment": alignment}

@app.post("/assassinate")
async def assassinate(req: AssassinRequest):
    async with global_lock:
        if game_state.status != "assassin":
            raise HTTPException(status_code=400, detail="非刺杀阶段")

        game_state.assassin_target = req.target
        target_player = next((p for p in game_state.players if p.name == req.target), None)

        if target_player and target_player.role == RoleType.MERLIN:
            game_state.game_winner = "evil"
        else:
            game_state.game_winner = "good"

        game_state.status = "ended"
        record_db_results(game_state.game_winner)
    return {"status": "ok", "winner": game_state.game_winner}

@app.post("/record_vote_fail")
async def record_vote_fail():
    async with global_lock:
        game_state.vote_fail_count += 1
    return {"status": "ok"}

@app.get("/status/{player_name}")
async def get_status(player_name: str):
    if game_state.status == "empty":
        return {
            "status": "empty", "current_count": 0, "target_count": 0,
            "players_list": [], "mission_history": [], "your_role": "", "vision": [], "revealed_players": [],
            "vote_fail_count": 0, "mission_active": False, "mission_team": [], "has_acted": False,
            "vote_team_active": False, "team_votes": {}, "last_vote_result": None,
            "last_vote_snapshot": {}, "captain": None, "required_team_size": 2,
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

    viewer = next((p for p in game_state.players if p.name == player_name), None)
    round_idx = len(game_state.missions)
    sizes = MISSION_SIZES.get(game_state.target_count, MISSION_SIZES[6])
    required_size = sizes[round_idx] if round_idx < 5 else sizes[-1]

    # 确定执行刺杀的角色
    assassin_player = get_assassin_player()
    assassin_role = assassin_player.role if assassin_player else None

    # 当前玩家有效阵营
    current_alignment = None
    if viewer and viewer.role in (RoleType.LANCELOT_GOOD, RoleType.LANCELOT_EVIL):
        current_alignment = "evil" if is_currently_evil(viewer) else "good"

    resp = {
        "status": game_state.status,
        "current_count": len(game_state.players),
        "target_count": game_state.target_count,
        "players_list": [p.name for p in game_state.players],
        "mission_history": [m.dict() for m in game_state.missions],
        "vote_fail_count": game_state.vote_fail_count,
        "your_role": viewer.role if viewer else "",
        "vision": [],
        "revealed_players": [],

        "mission_active": game_state.mission_active,
        "mission_team": game_state.current_mission_team,
        "has_acted": (player_name in game_state.mission_voted_players),

        "vote_team_active": game_state.vote_team_active,
        "team_votes": game_state.team_votes,
        "last_vote_result": game_state.last_vote_result,
        "last_vote_snapshot": game_state.last_vote_snapshot,

        "captain": game_state.captain_name,
        "required_team_size": required_size,

        "game_winner": game_state.game_winner,
        "assassin_target": game_state.assassin_target,

        # 湖中仙女
        "lady_of_lake_holder": game_state.lady_of_lake_holder,
        "lady_of_lake_active": game_state.lady_of_lake_active,
        "lady_of_lake_result": game_state.lady_of_lake_result if (game_state.lady_of_lake_inspector == player_name) else None,
        "lady_of_lake_inspector": game_state.lady_of_lake_inspector if (game_state.lady_of_lake_inspector == player_name) else None,
        "lady_of_lake_history": game_state.lady_of_lake_history,

        # 兰斯洛特
        "lancelot_enabled": game_state.lancelot_enabled,
        "lancelot_swapped": game_state.lancelot_swapped,
        "lancelot_swap_reveal": game_state.lancelot_swap_reveal,
        "current_alignment": current_alignment,

        # 刺杀角色（用于前端判断谁执行刺杀）
        "assassin_role": assassin_role,

        # 王者之剑
        "excalibur_enabled": game_state.excalibur_enabled,
        "excalibur_holder": game_state.excalibur_holder,
        "excalibur_phase": game_state.excalibur_phase,
        "excalibur_result": game_state.excalibur_result if (game_state.excalibur_holder == player_name) else None,
    }

    if game_state.status in ["active", "assassin", "lady_of_lake"] and viewer:
        resp["vision"] = calculate_vision(viewer, game_state.players)

    if game_state.status == "ended":
        resp["revealed_players"] = [{"name": p.name, "role": p.role} for p in game_state.players]

    return resp

@app.get("/leaderboard")
async def get_avalon_leaderboard():
    try:
        import database
        lb = database.get_leaderboard()
        return {"leaderboard": lb.get("Avalon", [])}
    except Exception:
        return {"leaderboard": []}

@app.get("/", response_class=HTMLResponse)
async def read_root():
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "index.html")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>找不到 index.html</h1>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)