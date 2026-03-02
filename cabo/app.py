import asyncio
import os
from typing import List, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import database
from cabo.engine import GameState, CaboEngine

router = APIRouter(prefix="/cabo", tags=["Cabo"])
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=[base_dir, "templates"])

# ---------------------------------------------------------------------------
# 状态 & 引擎实例
# ---------------------------------------------------------------------------
game_state = GameState()
engine = CaboEngine()
global_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class AddPlayerRequest(BaseModel):
    name: str

class RoundSubmitRequest(BaseModel):
    raw_scores: Dict[str, int]
    cabo_caller: Optional[str] = None
    kamikaze_player: Optional[str] = None

# ---------------------------------------------------------------------------
# API 端点 — 接入层
# ---------------------------------------------------------------------------

@router.post("/api/reset")
async def reset_game():
    async with global_lock:
        engine.reset(game_state)
    return {"status": "ok"}

@router.post("/api/add_player")
async def add_player(req: AddPlayerRequest):
    async with global_lock:
        return engine.add_player(game_state, req.name)

@router.post("/api/remove_player")
async def remove_player(req: AddPlayerRequest):
    async with global_lock:
        return engine.remove_player(game_state, req.name)

@router.post("/api/submit_round")
async def submit_round(req: RoundSubmitRequest):
    async with global_lock:
        result = engine.submit_round(
            game_state,
            raw_scores=req.raw_scores,
            cabo_caller=req.cabo_caller,
            kamikaze_player=req.kamikaze_player,
        )

    # 如果游戏结束，写入数据库
    if result.get("status") == "game_over":
        try:
            await database.record_cabo_game(
                game_state.game_id,
                [
                    {
                        "name": p.name,
                        "final_score": p.total_score,
                        "is_winner": p.name == result["winner"],
                        "round_count": result["round_count"],
                    }
                    for p in game_state.players
                ],
            )
        except Exception as e:
            print(f"Error saving cabo game: {e}")

    # 保持原有响应格式
    if result.get("status") == "game_over":
        return {
            "status": "game_over",
            "winner": result["winner"],
            "players": sorted(game_state.players, key=lambda x: x.total_score),
        }
    return result

@router.get("/api/status")
async def get_status():
    return engine.get_status(game_state)

@router.get("/api/leaderboard")
async def get_leaderboard():
    try:
        return await database.get_cabo_leaderboard()
    except Exception as e:
        print(f"Error getting cabo leaderboard: {e}")
        return []

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
