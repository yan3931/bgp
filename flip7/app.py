import asyncio
import os
from typing import List

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from database import record_flip7_game, get_flip7_leaderboard
from flip7.engine import GameState, Flip7Engine

router = APIRouter(prefix="/flip7", tags=["Flip7"])
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=[base_dir, "templates"])

# ---------------------------------------------------------------------------
# 状态 & 引擎实例
# ---------------------------------------------------------------------------
game_state = GameState()
engine = Flip7Engine()
global_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class NameRequest(BaseModel):
    name: str

class PlayerRoundData(BaseModel):
    name: str
    cards: List[str]

class SubmitRoundRequest(BaseModel):
    players: List[PlayerRoundData]

# ---------------------------------------------------------------------------
# API 端点 — 接入层
# ---------------------------------------------------------------------------

@router.post("/api/reset")
async def reset_game():
    async with global_lock:
        engine.reset(game_state)
    return {"status": "ok"}

@router.post("/api/add_player")
async def add_player(req: NameRequest):
    async with global_lock:
        return engine.add_player(game_state, req.name)

@router.post("/api/remove_player")
async def remove_player(req: NameRequest):
    async with global_lock:
        return engine.remove_player(game_state, req.name)

@router.post("/api/submit_round")
async def submit_round(req: SubmitRoundRequest):
    async with global_lock:
        players_data = [{"name": p.name, "cards": p.cards} for p in req.players]
        result = engine.submit_round(game_state, players_data)

    # 如果游戏结束，写入数据库
    if result.get("status") == "game_over":
        await record_flip7_game(result["game_id"], result["players_db_data"])
        # 返回前端期望的格式（不含内部字段）
        return {
            "status": "game_over",
            "round_scores": result["round_scores"],
            "winner": result["winner"],
        }

    return result

@router.get("/api/status")
async def get_status():
    return engine.get_status(game_state)

@router.get("/api/leaderboard")
async def get_leaderboard():
    return {"leaderboard": await get_flip7_leaderboard()}

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
