import asyncio
import os
import random
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from database import get_lasvegas_leaderboard, record_lasvegas_game
from sio_server import sio

router = APIRouter(prefix="/lasvegas", tags=["LasVegas"])
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=[base_dir, "templates"])

VALID_DENOMINATIONS = [30, 40, 50, 60, 70, 80, 90, 100]
BILL_POOL = {
    30: 11,
    40: 11,
    50: 13,
    60: 15,
    70: 13,
    80: 11,
    90: 9,
    100: 7,
}
TILE_GROUPS = {
    "A": ["A1", "A2"],
    "B": ["B1", "B2"],
    "C": ["C1", "C2"],
    "D": ["D1", "D2"],
    "E": ["E1", "E2"],
    "F": ["F1", "F2"],
    "G": ["G1", "G2"],
    "H": ["H1", "H2"],
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


class GlobalGame:
    def __init__(self):
        self.players: List[Player] = []
        self.field_setup: Optional[List[Dict[str, Any]]] = None
        self.status = "active"


game_state = GlobalGame()
global_lock = asyncio.Lock()


def recalc_player(player: Player):
    player.total_amount = sum(b.value for b in player.bills)
    player.bill_count = len(player.bills)


def recalc_ranks():
    sorted_players = sorted(
        game_state.players,
        key=lambda p: (-p.total_amount, -p.bill_count),
    )
    for rank, player in enumerate(sorted_players):
        original = next(item for item in game_state.players if item.name == player.name)
        original.rank = rank + 1


def get_remaining_pool(players: List[Player]) -> Dict[int, int]:
    remaining = dict(BILL_POOL)
    for player in players:
        for bill in player.bills:
            if bill.value in remaining:
                remaining[bill.value] = max(0, remaining[bill.value] - 1)
    return remaining


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


def distribute_casino_bills(players: List[Player]) -> List[List[int]]:
    pool = get_remaining_pool(players)
    pairs: List[List[int]] = []
    for _ in range(6):
        b1 = draw_bill_from_pool(pool)
        b2 = draw_bill_from_pool(pool)
        bills = sorted([value for value in (b1, b2) if value is not None], reverse=True)
        pairs.append(bills)

    pairs.sort(
        key=lambda bills: (sum(bills), bills[0] if bills else 0),
        reverse=True,
    )
    result = [[] for _ in range(6)]
    for idx, bills in enumerate(pairs):
        result[5 - idx] = bills
    return result


async def broadcast_state_update(event: str):
    await sio.emit(
        "state_update",
        {"game": "lasvegas", "event": event},
        namespace="/",
    )


class NameRequest(BaseModel):
    name: str


class AddBillRequest(BaseModel):
    player_name: str
    value: int


class RemoveBillRequest(BaseModel):
    player_name: str
    bill_id: str


@router.post("/api/reset")
async def reset_game():
    async with global_lock:
        game_state.__init__()
    await broadcast_state_update("reset")
    return {"status": "ok"}


@router.post("/api/add_player")
async def add_player(req: NameRequest):
    async with global_lock:
        if any(p.name == req.name for p in game_state.players):
            return {"status": "exists", "msg": "Player already exists"}
        game_state.players.append(Player(name=req.name))
        recalc_ranks()
    await broadcast_state_update("add_player")
    return {"status": "ok"}


@router.post("/api/remove_player")
async def remove_player(req: NameRequest):
    async with global_lock:
        game_state.players = [p for p in game_state.players if p.name != req.name]
        recalc_ranks()
    await broadcast_state_update("remove_player")
    return {"status": "ok"}


@router.post("/api/add_bill")
async def add_bill(req: AddBillRequest):
    async with global_lock:
        player = next((p for p in game_state.players if p.name == req.player_name), None)
        if not player:
            return {"status": "error", "msg": "Player not found"}
        if req.value not in VALID_DENOMINATIONS:
            return {"status": "error", "msg": "Invalid denomination"}

        bill = Bill(id=str(uuid.uuid4())[:8], value=req.value)
        player.bills.append(bill)
        recalc_player(player)
        recalc_ranks()
    await broadcast_state_update("add_bill")
    return {"status": "ok"}


@router.post("/api/remove_bill")
async def remove_bill(req: RemoveBillRequest):
    async with global_lock:
        player = next((p for p in game_state.players if p.name == req.player_name), None)
        if not player:
            return {"status": "error", "msg": "Player not found"}

        player.bills = [b for b in player.bills if b.id != req.bill_id]
        recalc_player(player)
        recalc_ranks()
    await broadcast_state_update("remove_bill")
    return {"status": "ok"}


@router.post("/api/setup_field")
async def setup_field():
    async with global_lock:
        candidates = [random.choice(group_tiles) for group_tiles in TILE_GROUPS.values()]
        random.shuffle(candidates)
        chosen = candidates[:6]
        casino_bills = distribute_casino_bills(game_state.players)
        game_state.field_setup = [
            {"casino": idx + 1, "tile_id": chosen[idx], "bills": casino_bills[idx]}
            for idx in range(6)
        ]
        field = game_state.field_setup
    await broadcast_state_update("setup_field")
    return {"status": "ok", "field": field}


@router.get("/api/field")
async def get_field():
    return {"field": game_state.field_setup}


@router.post("/api/end_game")
async def end_game():
    async with global_lock:
        if not game_state.players:
            return {"status": "error", "msg": "No players"}
        if not any(p.bill_count > 0 for p in game_state.players):
            return {"status": "error", "msg": "No bills recorded"}

        for player in game_state.players:
            await record_lasvegas_game(player.name, player.total_amount, player.bill_count)

        game_state.__init__()
    await broadcast_state_update("end_game")
    return {"status": "ok"}


@router.get("/api/status")
async def get_status():
    all_players = [p.model_dump() for p in game_state.players]
    ranked = sorted(
        all_players,
        key=lambda p: (-p["total_amount"], -p["bill_count"]),
    )
    return {"ranked": ranked, "players": all_players, "field": game_state.field_setup}


@router.get("/api/leaderboard")
async def get_leaderboard():
    return {"leaderboard": await get_lasvegas_leaderboard()}


@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
