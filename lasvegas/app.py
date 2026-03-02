import asyncio
import os
from typing import List, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from database import get_lasvegas_leaderboard, record_lasvegas_game
from state_store import get_store
from lasvegas.engine import GameState, LasVegasEngine

router = APIRouter(prefix="/lasvegas", tags=["LasVegas"])
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=[base_dir, "templates"])

# ---------------------------------------------------------------------------
# 状态 & 引擎实例
# ---------------------------------------------------------------------------
game_state = GameState()
engine = LasVegasEngine()
global_lock = asyncio.Lock()


async def _publish(event: str) -> None:
    """通过 state_store 发布状态变更事件（由推送网关自动广播）。"""
    await get_store().publish("game:lasvegas", {"game": "lasvegas", "event": event})


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class NameRequest(BaseModel):
    name: str


class AddBillRequest(BaseModel):
    player_name: str
    value: int


class RemoveBillRequest(BaseModel):
    player_name: str
    bill_id: str


# ---------------------------------------------------------------------------
# API 端点 — 接入层（仅负责解析请求 → 调用引擎 → 返回结果）
# ---------------------------------------------------------------------------

@router.post("/api/reset")
async def reset_game():
    async with global_lock:
        engine.reset(game_state)
    await _publish("reset")
    return {"status": "ok"}


@router.post("/api/add_player")
async def add_player(req: NameRequest):
    async with global_lock:
        result = engine.add_player(game_state, req.name)
    if result["status"] == "ok":
        await _publish("add_player")
    return result


@router.post("/api/remove_player")
async def remove_player(req: NameRequest):
    async with global_lock:
        result = engine.remove_player(game_state, req.name)
    await _publish("remove_player")
    return result


@router.post("/api/add_bill")
async def add_bill(req: AddBillRequest):
    async with global_lock:
        result = engine.add_bill(game_state, req.player_name, req.value)
    if result["status"] == "ok":
        await _publish("add_bill")
    return result


@router.post("/api/remove_bill")
async def remove_bill(req: RemoveBillRequest):
    async with global_lock:
        result = engine.remove_bill(game_state, req.player_name, req.bill_id)
    if result["status"] == "ok":
        await _publish("remove_bill")
    return result


@router.post("/api/setup_field")
async def setup_field():
    async with global_lock:
        field = engine.setup_field(game_state)
    await _publish("setup_field")
    return {"status": "ok", "field": field}


@router.get("/api/field")
async def get_field():
    return {"field": game_state.field_setup}


@router.post("/api/end_game")
async def end_game():
    async with global_lock:
        error = engine.validate_end_game(game_state)
        if error:
            return error
        for player in game_state.players:
            await record_lasvegas_game(player.name, player.total_amount, player.bill_count)
        engine.reset(game_state)
    await _publish("end_game")
    return {"status": "ok"}


@router.get("/api/status")
async def get_status():
    return engine.get_status(game_state)


@router.get("/api/leaderboard")
async def get_leaderboard():
    return {"leaderboard": await get_lasvegas_leaderboard()}


@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
