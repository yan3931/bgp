import asyncio
import os
import uuid
from typing import List, Dict, Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from database import record_flip7_game, get_flip7_leaderboard

router = APIRouter(prefix="/flip7", tags=["Flip7"])
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=[base_dir, "templates"])

# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

class Player(BaseModel):
    name: str
    total_score: int = 0
    busts: int = 0
    rank: int = 0

class GlobalGame:
    def __init__(self):
        self.players: List[Player] = []
        self.status = "active"
        self.winning_score = 200

game_state = GlobalGame()
global_lock = asyncio.Lock()

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def recalc_ranks():
    sorted_players = sorted(
        game_state.players,
        key=lambda p: -p.total_score
    )
    for rank, p in enumerate(sorted_players):
        original = next(pl for pl in game_state.players if pl.name == p.name)
        original.rank = rank + 1

def calculate_round_score(cards: List[str]) -> int:
    """
    Calculate round score based on 'cards', a list of drawn cards.
    Cards can be integers (0-12) as strings or modifier cards ('+2' to '+10', 'x2').
    Returns 0 if player busted (duplicate numbers drawn).
    If exactly 7 unique numbers, get a 15 point bonus.
    """
    numbers = []
    modifiers_addition = 0
    multiplier = 1
    
    for c in cards:
        if c == 'x2':
            multiplier *= 2
        elif c.startswith('+'):
            modifiers_addition += int(c[1:])
        else:
            numbers.append(int(c))
            
    # Check for bust
    if len(numbers) != len(set(numbers)):
        return 0 # Bust! Same number drawn twice
        
    base_sum = sum(numbers)
    
    # 7-flip bonus check
    flip_bonus = 15 if len(set(numbers)) == 7 else 0
    
    return (base_sum * multiplier) + modifiers_addition + flip_bonus

# -----------------------------------------------------------------------------
# Request Models
# -----------------------------------------------------------------------------

class NameRequest(BaseModel):
    name: str

class PlayerRoundData(BaseModel):
    name: str
    cards: List[str] # ["1", "5", "x2", "+4"] etc.

class SubmitRoundRequest(BaseModel):
    players: List[PlayerRoundData]

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------

@router.post("/api/reset")
async def reset_game():
    async with global_lock:
        game_state.__init__()
    return {"status": "ok"}

@router.post("/api/add_player")
async def add_player(req: NameRequest):
    async with global_lock:
        if any(p.name == req.name for p in game_state.players):
            return {"status": "exists", "msg": "Player already exists"}
        game_state.players.append(Player(name=req.name))
        recalc_ranks()
    return {"status": "ok"}

@router.post("/api/remove_player")
async def remove_player(req: NameRequest):
    async with global_lock:
        game_state.players = [p for p in game_state.players if p.name != req.name]
        recalc_ranks()
    return {"status": "ok"}

@router.post("/api/submit_round")
async def submit_round(req: SubmitRoundRequest):
    """
    Submit cards drawn by players this round, compute scores, update totals.
    If any player reaches 200 score, the game ends.
    """
    async with global_lock:
        if game_state.status != "active":
            return {"status": "error", "msg": "Game is already over"}

        round_scores = {}
        for p_data in req.players:
            score = calculate_round_score(p_data.cards)
            round_scores[p_data.name] = score
            
            player = next((p for p in game_state.players if p.name == p_data.name), None)
            if player:
                player.total_score += score
                if score == 0 and len(p_data.cards) > 0:
                    player.busts += 1

        recalc_ranks()
        
        # Check game end condition: any player >= 200
        winners = [p for p in game_state.players if p.total_score >= game_state.winning_score]
        
        if winners:
            game_state.status = "finished"
            # Sort winners in case of tie (highest total wins)
            best_player = sorted(winners, key=lambda p: -p.total_score)[0]
            
            # Record in database
            game_id = str(uuid.uuid4())[:8]
            players_db_data = [
                {
                    "name": p.name,
                    "final_score": p.total_score,
                    "is_winner": (p.name == best_player.name),
                    "bust_count": p.busts
                } for p in game_state.players
            ]
            await record_flip7_game(game_id, players_db_data)
            
            return {
                "status": "game_over",
                "round_scores": round_scores,
                "winner": best_player.name
            }
            
    return {"status": "ok", "round_scores": round_scores}

@router.get("/api/status")
async def get_status():
    all_players = [p.model_dump() for p in game_state.players]
    ranked = sorted(
        all_players,
        key=lambda p: -p["total_score"]
    )
    return {
        "status": game_state.status,
        "ranked": ranked,
        "players": all_players
    }

@router.get("/api/leaderboard")
async def get_leaderboard():
    return {"leaderboard": await get_flip7_leaderboard()}

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
