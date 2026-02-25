import asyncio
import uuid
from typing import List, Dict, Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os

import database

router = APIRouter(prefix="/cabo", tags=["Cabo"])
base_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=[base_dir, "templates"])

# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

class Player(BaseModel):
    name: str
    total_score: int = 0
    history: List[int] = [] 
    is_safe: bool = True    # < 100 or reset used
    rank: int = 1
    reset_used: bool = False # 记录是否已经使用过100分重置机会

class RoundRecord(BaseModel):
    round_num: int
    scores: Dict[str, int]
    cabo_caller: Optional[str] = None
    fail_penalty: bool = False
    kamikaze_player: Optional[str] = None

class GlobalGame:
    def __init__(self):
        self.players: List[Player] = []
        self.round_history: List[RoundRecord] = []
        self.status = "active"
        self.game_id = str(uuid.uuid4())

game_state = GlobalGame()
global_lock = asyncio.Lock()

# -----------------------------------------------------------------------------
# Request Models
# -----------------------------------------------------------------------------
class AddPlayerRequest(BaseModel):
    name: str

class RoundSubmitRequest(BaseModel):
    raw_scores: Dict[str, int]
    cabo_caller: Optional[str] = None
    kamikaze_player: Optional[str] = None  # 神风特攻队触发者

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------

@router.post("/api/reset")
async def reset_game():
    async with global_lock:
        game_state.__init__()
    return {"status": "ok"}

@router.post("/api/add_player")
async def add_player(req: AddPlayerRequest):
    async with global_lock:
        # Check duplicate
        if any(p.name == req.name for p in game_state.players):
             return {"status": "exists", "msg": "Player exists"}
        game_state.players.append(Player(name=req.name))
    return {"status": "ok"}

@router.post("/api/remove_player")
async def remove_player(req: AddPlayerRequest):
    async with global_lock:
        game_state.players = [p for p in game_state.players if p.name != req.name]
    return {"status": "ok"}

@router.post("/api/submit_round")
async def submit_round(req: RoundSubmitRequest):
    async with global_lock:
        if game_state.status == "finished":
            return {"status": "error", "msg": "Game already finished"}

        raw_scores = req.raw_scores
        caller = req.cabo_caller
        kamikaze = req.kamikaze_player
        
        if not kamikaze and not raw_scores:
             return {"status": "error", "msg": "No scores"}

        min_val = 0
        if raw_scores:
            try:
                min_val = min(raw_scores.values())
            except ValueError:
                pass

        round_scores_final = {}
        caller_failed = False

        # --- Kamikaze Check ---
        # 神风特攻队: 手牌恰好 2×12 + 2×13 = 50 点
        # 触发者得 0 分，其他所有人各 +50
        if kamikaze:
            kamikaze_valid = False
            for p in game_state.players:
                if p.name == kamikaze:
                    kamikaze_valid = True
                    break
            
            if kamikaze_valid:
                for p in game_state.players:
                    if p.name == kamikaze:
                        round_scores_final[p.name] = 0
                        p.total_score += 0
                        p.history.append(0)
                    else:
                        round_scores_final[p.name] = 50
                        p.total_score += 50
                        p.history.append(50)
                    
                    # 规则：恰好100分重置为50分（每人限一次）
                    if p.total_score == 100 and not p.reset_used:
                        p.total_score = 50
                        p.reset_used = True
                    
                    if p.total_score > 100:
                        p.is_safe = False
            else:
                return {"status": "error", "msg": "Invalid kamikaze player"}
        else:
            # --- Normal scoring ---
            for p in game_state.players:
                p_name = p.name
                if p_name not in raw_scores:
                    card_sum = 0
                else:
                    card_sum = raw_scores[p_name]
                
                final_points = card_sum

                # Cabo Logic
                if caller:
                    if p_name == caller:
                        if card_sum == min_val:
                            final_points = 0
                        else:
                            final_points = card_sum + 10
                            caller_failed = True
                
                round_scores_final[p_name] = final_points
                p.total_score += final_points
                p.history.append(final_points)
                
                # 规则：恰好100分重置为50分（每人限一次）
                if p.total_score == 100 and not p.reset_used:
                    p.total_score = 50
                    p.reset_used = True
                
                if p.total_score > 100:
                    p.is_safe = False
        
        # Rank
        sorted_players = sorted(game_state.players, key=lambda x: x.total_score)
        for rank, p in enumerate(sorted_players):
            original = next(pl for pl in game_state.players if pl.name == p.name)
            original.rank = rank + 1

        game_state.round_history.append(RoundRecord(
            round_num=len(game_state.round_history) + 1,
            scores=round_scores_final,
            cabo_caller=caller,
            fail_penalty=caller_failed,
            kamikaze_player=kamikaze
        ))

        # --- Auto-settlement: check if anyone > 100 ---
        game_over = any(not p.is_safe for p in game_state.players)
        winner = None
        
        if game_over:
            game_state.status = "finished"
            # Winner is the player with the lowest total score
            winner_player = min(game_state.players, key=lambda x: x.total_score)
            winner = winner_player.name
            
            # Save to database
            round_count = len(game_state.round_history)
            players_data = []
            for p in game_state.players:
                players_data.append({
                    "name": p.name,
                    "final_score": p.total_score,
                    "is_winner": p.name == winner,
                    "round_count": round_count
                })
            
            try:
                await database.record_cabo_game(game_state.game_id, players_data)
            except Exception as e:
                print(f"Error saving cabo game: {e}")

    if game_over:
        return {
            "status": "game_over",
            "winner": winner,
            "players": sorted(game_state.players, key=lambda x: x.total_score)
        }
    return {"status": "ok"}

@router.get("/api/status")
async def get_status():
    return {
        "players": sorted(game_state.players, key=lambda x: x.total_score),
        "history": game_state.round_history,
        "round_count": len(game_state.round_history),
        "game_status": game_state.status
    }

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
