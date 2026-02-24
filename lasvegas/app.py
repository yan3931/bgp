import asyncio
import sys
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import uuid

# Add parent directory to path so we can import the shared database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import init_db, record_lasvegas_game, get_lasvegas_leaderboard

app = FastAPI(title="Las Vegas Money Calculator")
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=[base_dir, "templates"])

# Valid denominations (in 万 units)
VALID_DENOMINATIONS = [30, 40, 50, 60, 70, 80, 90, 100]

# Initialize DB tables on import
init_db()

# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

class Bill(BaseModel):
    id: str
    value: int       # denomination in 万 units: 30, 40, 50, 60, 70, 80, 90, 100

class Player(BaseModel):
    name: str
    bills: List[Bill] = []
    total_amount: int = 0
    bill_count: int = 0
    rank: int = 0

class GlobalGame:
    def __init__(self):
        self.players: List[Player] = []
        self.status = "active"

game_state = GlobalGame()
global_lock = asyncio.Lock()

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def recalc_player(p: Player):
    p.total_amount = sum(b.value for b in p.bills)
    p.bill_count = len(p.bills)

def recalc_ranks():
    sorted_players = sorted(
        game_state.players,
        key=lambda p: (-p.total_amount, -p.bill_count)
    )
    for rank, p in enumerate(sorted_players):
        original = next(pl for pl in game_state.players if pl.name == p.name)
        original.rank = rank + 1

# -----------------------------------------------------------------------------
# Request Models
# -----------------------------------------------------------------------------

class NameRequest(BaseModel):
    name: str

class AddBillRequest(BaseModel):
    player_name: str
    value: int

class RemoveBillRequest(BaseModel):
    player_name: str
    bill_id: str

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------

@app.post("/api/reset")
async def reset_game():
    async with global_lock:
        game_state.__init__()
    return {"status": "ok"}

@app.post("/api/add_player")
async def add_player(req: NameRequest):
    async with global_lock:
        if any(p.name == req.name for p in game_state.players):
            return {"status": "exists", "msg": "Player already exists"}
        game_state.players.append(Player(name=req.name))
        recalc_ranks()
    return {"status": "ok"}

@app.post("/api/remove_player")
async def remove_player(req: NameRequest):
    async with global_lock:
        game_state.players = [p for p in game_state.players if p.name != req.name]
        recalc_ranks()
    return {"status": "ok"}

@app.post("/api/add_bill")
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
    return {"status": "ok"}

@app.post("/api/remove_bill")
async def remove_bill(req: RemoveBillRequest):
    async with global_lock:
        player = next((p for p in game_state.players if p.name == req.player_name), None)
        if not player:
            return {"status": "error", "msg": "Player not found"}
        
        player.bills = [b for b in player.bills if b.id != req.bill_id]
        recalc_player(player)
        recalc_ranks()
    return {"status": "ok"}

@app.post("/api/end_game")
async def end_game():
    """End current game: save each player's result to DB, then reset."""
    async with global_lock:
        if not game_state.players:
            return {"status": "error", "msg": "No players"}
        
        # Check at least one player has bills
        if not any(p.bill_count > 0 for p in game_state.players):
            return {"status": "error", "msg": "No bills recorded"}
        
        # Record each player's result in DB
        for p in game_state.players:
            record_lasvegas_game(p.name, p.total_amount, p.bill_count)
        
        # Reset game state for next round
        game_state.__init__()
    
    return {"status": "ok"}

@app.get("/api/status")
async def get_status():
    all_players = [p.model_dump() for p in game_state.players]
    ranked = sorted(
        all_players,
        key=lambda p: (-p["total_amount"], -p["bill_count"])
    )
    return {
        "ranked": ranked,
        "players": all_players
    }

@app.get("/api/leaderboard")
async def get_leaderboard():
    return {"leaderboard": get_lasvegas_leaderboard()}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
