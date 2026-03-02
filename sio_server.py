"""
sio_server.py - Socket.IO 推送网关 (Event Gateway)

职责：
  1. 维护全局 Socket.IO 服务端实例
  2. EventGateway 订阅 state_store 的事件频道，自动向前端广播 state_update
  3. 游戏模块不再直接调用 sio.emit()，而是通过 state_store.publish() 发布事件
"""

import socketio
from state_store import get_store

sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')


class EventGateway:
    """
    推送网关：订阅 state_store 中的游戏事件频道，
    自动将事件广播给前端 WebSocket 客户端。
    """

    # 所有游戏的事件频道名称
    GAME_CHANNELS = [
        "game:avalon",
        "game:cabo",
        "game:lasvegas",
        "game:loveletters",
        "game:flip7",
        "game:modernart",
    ]

    def __init__(self) -> None:
        self._initialized = False

    def init(self) -> None:
        """注册所有游戏频道的订阅回调。应在应用启动时调用一次。"""
        if self._initialized:
            return
        store = get_store()
        for channel in self.GAME_CHANNELS:
            store.subscribe(channel, self._on_game_event)
        self._initialized = True

    async def _on_game_event(self, channel: str, event_data: dict) -> None:
        """
        收到游戏引擎发布的事件后，向前端广播 state_update。

        event_data 应包含：
          - game: 游戏标识 (e.g. "lasvegas")
          - event: 事件名称 (e.g. "add_player", "reset")
          - 其他可选字段
        """
        namespace = event_data.get("namespace", "/")
        await sio.emit(
            "state_update",
            event_data,
            namespace=namespace,
        )


# 全局网关实例
gateway = EventGateway()
