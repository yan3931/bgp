import os
import socketio
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/loveletters", tags=["LoveLetters"])

# Setup SocketIO
from sio_server import sio

# Templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=[os.path.join(BASE_DIR, "templates"), "templates"])

# --- Game Logic & State ---
CONFIG_BASIC = {
    "1 - 侍卫 (Guard)": 5, "2 - 牧师 (Priest)": 2, "3 - 男爵 (Baron)": 2,
    "4 - 侍女 (Handmaid)": 2, "5 - 王子 (Prince)": 2, "6 - 国王 (King)": 1,
    "7 - 女伯爵 (Countess)": 1, "8 - 公主 (Princess)": 1
}

CONFIG_EXTENSION = {
    "0 - 刺客 (Assassin)": 1, "1 - 侍卫 (Guard)": 8, "0 - 弄臣 (Jester)": 1,
    "2 - 牧师 (Priest)": 2, "2 - 红衣主教 (Cardinal)": 2, "3 - 男爵 (Baron)": 2,
    "3 - 男爵夫人 (Baroness)": 2, "4 - 侍女 (Handmaid)": 2, "4 - 马屁精 (Sycophant)": 2,
    "5 - 王子 (Prince)": 2, "5 - 伯爵 (Count)": 2, "6 - 国王 (King)": 1,
    "6 - 警官 (Constable)": 1, "7 - 女伯爵 (Countess)": 1, "7 - 太后 (Dowager)": 1,
    "8 - 公主 (Princess)": 1, "9 - 大主教 (Bishop)": 1
}

class GameState:
    def __init__(self):
        self.current_mode = 'basic'
        self.current_config = CONFIG_BASIC.copy()
        self.played_cards = {key: 0 for key in self.current_config.keys()}

    def reset(self):
        self.played_cards = {key: 0 for key in self.current_config.keys()}

state = GameState()

def calculate_data():
    stats = []
    total_remaining = 0
    total_cards = 0
    sorted_keys = sorted(state.current_config.keys())

    for card in sorted_keys:
        total = state.current_config[card]
        played = state.played_cards.get(card, 0)
        remaining = max(0, total - played)
        total_remaining += remaining
        total_cards += total
        
        stats.append({
            "name": card,
            "total": total,
            "played": played,
            "remaining": remaining,
            "probability": 0
        })
    
    for item in stats:
        if total_remaining > 0:
            item['probability'] = round((item['remaining'] / total_remaining) * 100, 1)
        else:
            item['probability'] = 0.0
            
    return {
        'stats': stats,
        'total_remaining': total_remaining,
        'total_cards': total_cards,
        'current_mode': state.current_mode,
        'mode_name': '基础版 (16张)' if state.current_mode == 'basic' else '拓展版 (32张)'
    }

async def broadcast_update():
    data = calculate_data()
    # Serialize template to string
    # In FastAPI, we can use templates.TemplateResponse but that returns a Response object.
    # We need the HTML string. Jinja2Templates.get_template(name).render(context)
    template = templates.env.get_template("card_list_fragment.html")
    html_content = template.render(stats=data['stats'])
    
    await sio.emit('update_game', {
        'html': html_content,
        'total': data['total_remaining'],
        'total_cards': data['total_cards'],
        'mode_name': data['mode_name'],
        'current_mode': data['current_mode']
    }, namespace='/loveletters')

# --- Routes ---

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    data = calculate_data()
    return templates.TemplateResponse("index.html", {"request": request, "data": data, "stats": data['stats']})

# --- SocketIO Events ---

@sio.on('connect', namespace='/loveletters')
async def connect(sid, environ):
    # Send update on connect (unicast? or just broadcast to be safe/easy)
    # Ideally unicast, but for this simple app broadcast is fine or just emit to sid
    # Re-using broadcast logic for simplicity, but let's try to just emit to this sid first?
    # But broadcast_update computes data.
    data = calculate_data()
    template = templates.env.get_template("card_list_fragment.html")
    html_content = template.render(stats=data['stats'])
    await sio.emit('update_game', {
        'html': html_content,
        'total': data['total_remaining'],
        'total_cards': data['total_cards'],
        'mode_name': data['mode_name'],
        'current_mode': data['current_mode']
    }, room=sid, namespace='/loveletters')

@sio.on('switch_mode', namespace='/loveletters')
async def switch_mode(sid, mode):
    if mode == 'extension':
        state.current_mode = 'extension'
        state.current_config = CONFIG_EXTENSION.copy()
    else:
        state.current_mode = 'basic'
        state.current_config = CONFIG_BASIC.copy()
    state.reset()
    await broadcast_update()

@sio.on('card_action', namespace='/loveletters')
async def card_action(sid, payload):
    action = payload.get('action')
    card_name = payload.get('card')
    
    if action == 'add':
        if card_name in state.played_cards and state.played_cards[card_name] < state.current_config[card_name]:
            state.played_cards[card_name] += 1
    elif action == 'remove':
        if card_name in state.played_cards and state.played_cards[card_name] > 0:
            state.played_cards[card_name] -= 1
            
    await broadcast_update()

@sio.on('reset_game', namespace='/loveletters')
async def reset_game(sid):
    state.reset()
    await broadcast_update()
