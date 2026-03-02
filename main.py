import uvicorn
import os
import importlib
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import socketio

import database
from sio_server import sio, gateway
from state_store import get_store, close_store

APPS_CONFIG = {
    "avalon": "Avalon.main",
    "cabo": "cabo.app",
    "lasvegas": "lasvegas.app",
    "loveletters": "LoveLetters.fastapi_app",
    "flip7": "flip7.app",
    "modernart": "ModernArt.app"
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    # 初始化推送网关（订阅 state_store 事件频道）
    gateway.init()
    yield
    # 关闭状态存储连接
    await close_store()

app = FastAPI(title="Board Game Portal", lifespan=lifespan)

# Mount Static Files
app.mount("/static", StaticFiles(directory="static"), name="static")

loaded_apps = []

for mount_path, module_name in APPS_CONFIG.items():
    try:
        mod = importlib.import_module(module_name)
        sub_router = getattr(mod, "router")
        app.include_router(sub_router)
        if mount_path == "avalon":
            app.mount(
                "/avalon/assets",
                StaticFiles(directory=os.path.join("Avalon", "assets")),
                name="avalon-assets",
            )
        loaded_apps.append(mount_path)
    except Exception as e:
        print(f"Error importing {mount_path}: {e}")

# Templates for Landing Page
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    leaderboard = await database.get_global_leaderboard()
    return templates.TemplateResponse("index.html", {"request": request, "leaderboard": leaderboard, "loaded_apps": loaded_apps})

@app.get("/gamelist", response_class=HTMLResponse)
async def gamelist(request: Request):
    return templates.TemplateResponse("gamelist.html", {"request": request})

@app.get("/api/leaderboard")
async def get_leaderboard_api():
    return await database.get_leaderboard()

# Wrap the main FastAPI app with socketio ASGIApp
final_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path='/socket.io')

if __name__ == "__main__":
    uvicorn.run("main:final_app", host="0.0.0.0", port=8000, reload=True)
