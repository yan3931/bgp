from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from database import record_modernart_game, get_modernart_leaderboard
from ModernArt.engine import GameState, ModernArtEngine

router = APIRouter(prefix="/modernart", tags=["ModernArt"])
templates = Jinja2Templates(directory=["ModernArt/", "templates"])

# ---------------------------------------------------------------------------
# 状态 & 引擎实例
# ---------------------------------------------------------------------------
global_state = GameState()
engine = ModernArtEngine()

# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# API 端点 — 接入层
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/api/join")
async def join_game(req: JoinRoomRequest):
    result = engine.join_game(global_state, req.player_name)
    if result.get("msg"):
        raise HTTPException(status_code=400, detail=result["msg"])
    return result

@router.post("/api/start")
async def start_game(req: StartGameRequest):
    error = engine.start_game(global_state, req.player_name)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"status": "success", "state": engine.get_state_for_player(global_state, req.player_name)}

@router.post("/api/reset")
async def reset_game():
    global global_state
    global_state = GameState()
    return {"status": "success"}

@router.post("/api/play_again")
async def play_again():
    engine.play_again(global_state)
    return {"status": "success"}

@router.get("/api/state")
async def get_state_endpoint(player_name: str = ""):
    return engine.get_state_for_player(global_state, player_name)

@router.post("/api/transaction")
async def transaction(req: TransactionRequest):
    error = engine.validate_transaction(global_state, req.player_name, req.buyer, req.artist)
    if error:
        raise HTTPException(status_code=400, detail=error)

    trigger_end = engine.execute_transaction(
        global_state, req.player_name, req.buyer, req.artist, req.price,
    )

    if trigger_end:
        end_data = engine.trigger_end_round(global_state)
        if end_data:
            # 游戏结束，写入数据库
            try:
                await record_modernart_game(end_data["game_id"], end_data["players_data"])
            except Exception as e:
                print(f"Error saving modern art game: {e}")

    return {"status": "success", "state": engine.get_state_for_player(global_state, req.player_name)}

@router.post("/api/end_round")
async def end_round(req: EndRoundRequest):
    if global_state.current_round > 4:
        raise HTTPException(status_code=400, detail="Game already ended")

    end_data = engine.trigger_end_round(global_state)
    if end_data:
        try:
            await record_modernart_game(end_data["game_id"], end_data["players_data"])
        except Exception as e:
            print(f"Error saving modern art game: {e}")

    return {"status": "success", "state": engine.get_state_for_player(global_state, req.player_name)}

@router.post("/api/undo")
async def undo():
    pass

@router.get("/api/leaderboard")
async def get_leaderboard():
    try:
        data = await get_modernart_leaderboard()
        return {"status": "success", "leaderboard": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}
