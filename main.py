import uvicorn
import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import database

# Import sub-game apps
# Standard pattern: try import, fallback to empty FastAPI if fail
avalon_app = FastAPI()
try:
    from Avalon.main import app as avalon_app
except ImportError as e:
    print(f"Error importing Avalon: {e}")

cabo_app = FastAPI()
try:
    from cabo.app import app as cabo_app
except ImportError as e:
    print(f"Error importing Cabo: {e}")

lasvegas_app = FastAPI()
try:
    from lasvegas.app import app as lasvegas_app
except ImportError as e:
    print(f"Error importing Las Vegas: {e}")

flip7_app = FastAPI()
try:
    from flip7.app import app as flip7_app
except ImportError as e:
    print(f"Error importing flip7: {e}")

modernart_app = FastAPI()
try:
    from ModernArt.app import app as modernart_app
except ImportError as e:
    print(f"Error importing ModernArt: {e}")

# LoveLetters: import SIO server and FastAPI routes separately
loveletters_fastapi_app = FastAPI()
loveletters_sio = None
try:
    from LoveLetters.fastapi_app import app as loveletters_fastapi_app, sio as loveletters_sio
except ImportError as e:
    print(f"Error importing LoveLetters: {e}")


app = FastAPI(title="Board Game Portal")

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount Games
app.mount("/avalon", avalon_app)
app.mount("/cabo", cabo_app)
app.mount("/lasvegas", lasvegas_app)
app.mount("/loveletters", loveletters_fastapi_app)
app.mount("/flip7", flip7_app)
app.mount("/modernart", modernart_app)

# Templates for Landing Page
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    leaderboard = database.get_leaderboard()
    return templates.TemplateResponse("index.html", {"request": request, "leaderboard": leaderboard})

@app.get("/gamelist", response_class=HTMLResponse)
async def gamelist(request: Request):
    return templates.TemplateResponse("gamelist.html", {"request": request})

@app.on_event("startup")
def startup_event():
    database.init_db()

@app.get("/api/leaderboard")
async def get_leaderboard_api():
    return database.get_leaderboard()

# Wrap the main FastAPI app with socketio ASGIApp so 
# Socket.IO gets first crack at /loveletters/socket.io requests
import socketio as _sio_module
if loveletters_sio is not None:
    final_app = _sio_module.ASGIApp(loveletters_sio, other_asgi_app=app, socketio_path='/loveletters/socket.io')
else:
    final_app = app

if __name__ == "__main__":
    uvicorn.run("main:final_app", host="0.0.0.0", port=8000, reload=True)
