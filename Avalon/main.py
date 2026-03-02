import asyncio
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import database
from Avalon.engine import GameState, AvalonEngine

router = APIRouter(prefix="/avalon", tags=["Avalon"])
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=[base_dir, "templates"])

# ---------------------------------------------------------------------------
# 状态 & 引擎实例
# ---------------------------------------------------------------------------
game_state = GameState()
engine = AvalonEngine()
global_lock = asyncio.Lock()


async def _record_db(winner_team: str) -> None:
    """将对局结果写入数据库。"""
    try:
        results = engine.get_db_results(game_state, winner_team)
        for r in results:
            await database.record_result("Avalon", r["player_name"], r["is_winner"], 0)
    except Exception as e:
        print(f"Error recording Avalon results: {e}")


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class CreateRequest(BaseModel):
    player_count: int
    lancelot_enabled: bool = False
    excalibur_enabled: bool = False
    lady_of_lake_enabled: bool = True

class JoinRequest(BaseModel):
    player_name: str

class StartMissionRequest(BaseModel):
    player_name: Optional[str] = None
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
    target: Optional[str] = None

# ---------------------------------------------------------------------------
# API 端点 — 接入层
# ---------------------------------------------------------------------------

@router.post("/reset_game")
async def reset_game(req: CreateRequest):
    async with global_lock:
        previous_names = engine.reset_game(
            game_state, req.player_count,
            req.lancelot_enabled, req.excalibur_enabled, req.lady_of_lake_enabled,
        )
    return {"status": "ok", "previous_players": previous_names}

@router.get("/lobby")
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

@router.post("/end_game")
async def end_game():
    async with global_lock:
        game_state.status = "ended"
    return {"status": "ok"}

@router.post("/clear_game")
async def clear_game():
    async with global_lock:
        engine.clear_game(game_state)
    return {"status": "ok"}

@router.post("/join")
async def join_game(req: JoinRequest):
    async with global_lock:
        result = engine.join_game(game_state, req.player_name)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["msg"])
    return result

@router.post("/propose_team")
async def propose_team(req: StartMissionRequest):
    async with global_lock:
        result = engine.propose_team(game_state, req.team, req.player_name)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["msg"])
    return result

@router.post("/vote_team")
async def vote_team(req: TeamVoteRequest):
    async with global_lock:
        result = engine.vote_team(game_state, req.player_name, req.vote)
        # 如果游戏因 5 次否决而结束
        if result.get("game_end") == "evil":
            await _record_db("evil")
    return {"status": "ok"}

@router.post("/start_mission")
async def start_mission(req: StartMissionRequest):
    return await propose_team(req)

@router.post("/vote_mission")
async def vote_mission(req: MissionVoteRequest):
    async with global_lock:
        result = engine.vote_mission(game_state, req.player_name, req.action)

        if result.get("need_resolve"):
            resolve_result = engine.resolve_mission(game_state)
            # 检查数据库写入
            if resolve_result.get("game_end") == "evil":
                await _record_db("evil")

    return {"status": "ok"}

@router.post("/assign_excalibur")
async def assign_excalibur(req: ExcaliburAssignRequest):
    async with global_lock:
        result = engine.assign_excalibur(game_state, req.target)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["msg"])
    return result

@router.post("/use_excalibur")
async def use_excalibur(req: ExcaliburUseRequest):
    async with global_lock:
        result = engine.use_excalibur(game_state, req.target)
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result["msg"])
        # 结算任务
        resolve_result = engine.resolve_mission(game_state)
        if resolve_result.get("game_end") == "evil":
            await _record_db("evil")
    return {"status": "ok", "excalibur_result": game_state.excalibur_result}

@router.post("/lady_of_lake")
async def lady_of_lake(req: LadyOfLakeRequest):
    async with global_lock:
        result = engine.lady_of_lake(game_state, req.target)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["msg"])
    return {"status": "ok", "alignment": result["alignment"]}

@router.post("/assassinate")
async def assassinate(req: AssassinRequest):
    async with global_lock:
        result = engine.assassinate(game_state, req.target)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["msg"])
    await _record_db(game_state.game_winner)
    return result

@router.post("/record_vote_fail")
async def record_vote_fail():
    async with global_lock:
        game_state.vote_fail_count += 1
    return {"status": "ok"}

@router.get("/status/{player_name}")
async def get_status(player_name: str):
    return engine.build_status(game_state, player_name)

@router.get("/leaderboard")
async def get_avalon_leaderboard():
    try:
        lb = await database.get_leaderboard()
        return {"leaderboard": lb.get("Avalon", [])}
    except Exception:
        return {"leaderboard": []}

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
