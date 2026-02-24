from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict, Optional
import copy
import uuid
import sys
import os

# Ensure database is accessible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import record_modernart_game, get_modernart_leaderboard

app = FastAPI(title="Modern Art Game Helper")
templates = Jinja2Templates(directory="ModernArt/templates")

# Constants
ARTISTS = ["Manuel Carvalho (Yellow)", "Sigrid Thaler (Blue)", "Daniel Melim (Red)", "Ramon Martins (Green)", "Rafael Silveira (Orange)"]
ARTIST_KEYS = ["yellow", "blue", "red", "green", "orange"]
COLOR_MAP = {
    "yellow": "黄 (Manuel Carvalho)",
    "blue": "蓝 (Sigrid Thaler)",
    "red": "红 (Daniel Melim)",
    "green": "绿 (Ramon Martins)",
    "orange": "橙 (Rafael Silveira)"
}

# Initial Game State
class GameState:
    def __init__(self):
        self.players = {} # name -> {"money": int, "portfolio": {"yellow": int, ...}}
        self.current_round = 1
        self.round_paintings = {key: 0 for key in ARTIST_KEYS}
        self.artist_values_history = {key: [] for key in ARTIST_KEYS} # history of values per round
        self.started = False
        self.history_log = []
        
    def reset_round(self):
        self.round_paintings = {key: 0 for key in ARTIST_KEYS}
        for player in self.players.values():
            player["portfolio"] = {key: 0 for key in ARTIST_KEYS}
            
    def add_log(self, message: str):
        self.history_log.append(message)

global_state = GameState()

class JoinRoomRequest(BaseModel):
    player_name: str

class StartGameRequest(BaseModel):
    player_name: str

class TransactionRequest(BaseModel):
    player_name: str
    buyer: str
    artist: str
    price: int
    is_bank_paint: bool = False

class EndRoundRequest(BaseModel):
    player_name: str

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/join")
async def join_game(req: JoinRoomRequest):
    if req.player_name and req.player_name in global_state.players:
        return {"status": "success", "state": get_state_for_player(req.player_name)}
        
    if global_state.started:
        raise HTTPException(status_code=400, detail="Game already started")
    if req.player_name and req.player_name not in global_state.players:
        global_state.players[req.player_name] = {
            "money": 100,
            "portfolio": {key: 0 for key in ARTIST_KEYS}
        }
        global_state.add_log(f"{req.player_name} 加入了游戏")
    return {"status": "success", "state": get_state_for_player(req.player_name)}

@app.post("/api/start")
async def start_game(req: StartGameRequest):
    if len(global_state.players) < 3:
        raise HTTPException(status_code=400, detail="Need at least 3 players")
    global_state.started = True
    global_state.add_log(f"{req.player_name} 开始了游戏！第 1 回合")
    return {"status": "success", "state": get_state_for_player(req.player_name)}

@app.post("/api/reset")
async def reset_game():
    global global_state
    global_state = GameState()
    return {"status": "success"}

@app.post("/api/play_again")
async def play_again():
    if global_state.started:
        for player in global_state.players.values():
            player["money"] = 100
            player["portfolio"] = {key: 0 for key in ARTIST_KEYS}
        global_state.current_round = 1
        global_state.round_paintings = {key: 0 for key in ARTIST_KEYS}
        global_state.artist_values_history = {key: [] for key in ARTIST_KEYS}
        global_state.started = False
        global_state.history_log = ["--- 游戏已由其中一位玩家重启，等待开始 ---"]
    return {"status": "success"}

def get_state_for_player(current_player: str):
    players_copy = copy.deepcopy(global_state.players)
    if global_state.started:
        for p_name, p_data in players_copy.items():
            if p_name != current_player:
                p_data["money"] = "???"

    return {
        "started": global_state.started,
        "players": players_copy,
        "current_round": global_state.current_round,
        "round_paintings": global_state.round_paintings,
        "artist_values_history": global_state.artist_values_history,
        "history_log": global_state.history_log
    }

@app.get("/api/state")
async def get_state_endpoint(player_name: str = ""):
    return get_state_for_player(player_name)

@app.post("/api/transaction")
async def transaction(req: TransactionRequest):
    if not global_state.started:
        raise HTTPException(status_code=400, detail="Game not started")

    if req.artist not in ARTIST_KEYS:
        raise HTTPException(status_code=400, detail="Invalid artist")
        
    buyer = req.buyer
    seller = req.player_name
    price = req.price

    if buyer != "Bank" and buyer not in global_state.players:
        raise HTTPException(status_code=400, detail="Invalid buyer")
    if seller not in global_state.players:
        raise HTTPException(status_code=400, detail="Invalid seller")

    # If player buys from themselves, money goes to bank
    if buyer == seller and buyer != "Bank":
        payee = "Bank"
    else:
        payee = seller

    # Deduct money from buyer
    if buyer != "Bank":
        if global_state.players[buyer]["money"] != "???":
            global_state.players[buyer]["money"] -= price
        
    # Add money to payee
    if payee != "Bank":
        if global_state.players[payee]["money"] != "???":
            global_state.players[payee]["money"] += price

    # Add painting to buyer's portfolio
    if buyer != "Bank":
        global_state.players[buyer]["portfolio"][req.artist] += 1
        
    # Increment round artist count
    global_state.round_paintings[req.artist] += 1
    
    if buyer == "Bank":
        global_state.add_log(f"{seller} 打出了 {COLOR_MAP[req.artist]} 的画作（流拍/没人买）")
    elif buyer == seller:
        global_state.add_log(f"{seller} 花 ${price} 购买了自己打出的 {COLOR_MAP[req.artist]} 画作")
    else:
        global_state.add_log(f"{seller} 以 ${price} 卖给 {buyer} 一张 {COLOR_MAP[req.artist]} 画作")

    if global_state.round_paintings[req.artist] >= 5:
        _trigger_end_round()

    return {"status": "success", "state": get_state_for_player(req.player_name)}

def _trigger_end_round():
    if global_state.current_round > 4:
        return

    # Determine top 3 artists
    artists_with_counts = []
    for i, key in enumerate(ARTIST_KEYS):
        artists_with_counts.append((global_state.round_paintings[key], -i, key))
        
    artists_with_counts.sort(reverse=True)
    
    # Assign values for this round: 30, 20, 10
    round_values = {key: 0 for key in ARTIST_KEYS}
    
    placed_count = 0
    values = [30, 20, 10]
    for count, neg_idx, key in artists_with_counts:
        if count > 0 and placed_count < 3:
            round_values[key] = values[placed_count]
            placed_count += 1
            
    # Record history
    for key in ARTIST_KEYS:
        global_state.artist_values_history[key].append(round_values[key])
        
    global_state.add_log(f"--- 结算 第 {global_state.current_round} 回合 ---")

    # Calculate payout
    for player_name, player_data in global_state.players.items():
        player_total_payout = 0
        payouts_msg = []
        for key in ARTIST_KEYS:
            count = player_data["portfolio"][key]
            if count > 0:
                if round_values[key] > 0:
                    total_value = sum(global_state.artist_values_history[key])
                    payout = count * total_value
                    if player_data["money"] != "???":
                        player_data["money"] += payout
                    player_total_payout += payout
                    payouts_msg.append(f"{count}张{COLOR_MAP[key].split(' ')[0]}")
                    
        if player_total_payout > 0:
            global_state.add_log(f"💰 {player_name} 卖出 {', '.join(payouts_msg)}，获得 ${player_total_payout}")
        else:
            global_state.add_log(f"💰 {player_name} 本回合无分红")

    global_state.current_round += 1
    if global_state.current_round <= 4:
        global_state.reset_round()
        global_state.add_log(f"--- 开始 第 {global_state.current_round} 回合 ---")
    else:
        global_state.add_log(f"--- 游戏结束 ---")
        
        # Save game to database
        if len(global_state.players) > 0:
            max_money = -1
            for p_data in global_state.players.values():
                if p_data["money"] != "???" and p_data["money"] > max_money:
                    max_money = p_data["money"]

            players_data = []
            for p_name, p_data in global_state.players.items():
                if p_data["money"] != "???":
                    is_winner = (p_data["money"] == max_money)
                    players_data.append({
                        "name": p_name,
                        "final_money": p_data["money"],
                        "is_winner": is_winner
                    })

            game_id = str(uuid.uuid4())
            try:
                record_modernart_game(game_id, players_data)
            except Exception as e:
                print(f"Error saving modern art game: {e}")

@app.post("/api/end_round")
async def end_round(req: EndRoundRequest):
    if global_state.current_round > 4:
        raise HTTPException(status_code=400, detail="Game already ended")

    _trigger_end_round()
        
    return {"status": "success", "state": get_state_for_player(req.player_name)}

@app.post("/api/undo")
async def undo():
    pass

@app.get("/api/leaderboard")
async def get_leaderboard():
    try:
        data = get_modernart_leaderboard()
        return {"status": "success", "leaderboard": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}
