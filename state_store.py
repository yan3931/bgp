"""
state_store.py - 统一的内存状态存储抽象 (Truth State)

支持两种后端：
  - MemoryStore：基于 Python dict + asyncio.Lock，零依赖 fallback（开发环境）
  - RedisStore：基于 redis.asyncio，适用于多进程 / 多容器部署（生产环境）

通过环境变量 REDIS_URL 自动切换后端。
"""

from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine, Dict, List, Optional


# ---------------------------------------------------------------------------
# 事件回调类型
# ---------------------------------------------------------------------------
EventCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------
class BaseStore(ABC):
    """状态存储的统一接口。"""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """获取键对应的 JSON 字符串值。"""
        ...

    @abstractmethod
    async def set(self, key: str, value: Any) -> None:
        """将值序列化为 JSON 并存储。"""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除指定键。"""
        ...

    @abstractmethod
    async def publish(self, channel: str, event_data: dict) -> None:
        """发布事件到指定频道。"""
        ...

    @abstractmethod
    def subscribe(self, channel: str, callback: EventCallback) -> None:
        """订阅指定频道的事件。"""
        ...

    async def get_json(self, key: str) -> Optional[Any]:
        """获取并反序列化 JSON 值。"""
        raw = await self.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_json(self, key: str, value: Any) -> None:
        """将任意 Python 对象序列化为 JSON 存储。"""
        await self.set(key, json.dumps(value, ensure_ascii=False))

    async def close(self) -> None:
        """关闭连接 / 释放资源（子类按需实现）。"""
        pass


# ---------------------------------------------------------------------------
# MemoryStore — 开发环境零依赖实现
# ---------------------------------------------------------------------------
class MemoryStore(BaseStore):
    """基于内存字典的状态存储，适用于单进程开发环境。"""

    def __init__(self) -> None:
        self._data: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._subscribers: Dict[str, List[EventCallback]] = {}

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            return self._data.get(key)

    async def set(self, key: str, value: Any) -> None:
        serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        async with self._lock:
            self._data[key] = serialized

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def publish(self, channel: str, event_data: dict) -> None:
        callbacks = self._subscribers.get(channel, [])
        for cb in callbacks:
            try:
                await cb(channel, event_data)
            except Exception as e:
                print(f"[MemoryStore] Error in subscriber callback for '{channel}': {e}")

    def subscribe(self, channel: str, callback: EventCallback) -> None:
        self._subscribers.setdefault(channel, []).append(callback)


# ---------------------------------------------------------------------------
# RedisStore — 生产环境实现
# ---------------------------------------------------------------------------
class RedisStore(BaseStore):
    """基于 redis.asyncio 的状态存储，支持多进程 / 多容器部署。"""

    def __init__(self, redis_url: str) -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "redis 包未安装。请运行: pip install redis[hiredis]"
            )
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        self._subscribers: Dict[str, List[EventCallback]] = {}
        self._listener_task: Optional[asyncio.Task] = None

    async def get(self, key: str) -> Optional[str]:
        return await self._redis.get(key)

    async def set(self, key: str, value: Any) -> None:
        serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        await self._redis.set(key, serialized)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def publish(self, channel: str, event_data: dict) -> None:
        # 同时触发本地订阅回调和 Redis Pub/Sub
        message = json.dumps(event_data, ensure_ascii=False)
        await self._redis.publish(channel, message)
        # 本地回调（用于同进程内的 EventGateway）
        callbacks = self._subscribers.get(channel, [])
        for cb in callbacks:
            try:
                await cb(channel, event_data)
            except Exception as e:
                print(f"[RedisStore] Error in subscriber callback for '{channel}': {e}")

    def subscribe(self, channel: str, callback: EventCallback) -> None:
        self._subscribers.setdefault(channel, []).append(callback)

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        await self._pubsub.close()
        await self._redis.close()


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_store_instance: Optional[BaseStore] = None


def get_store() -> BaseStore:
    """
    获取全局状态存储实例。

    根据环境变量 REDIS_URL 决定使用哪种后端：
      - 设置了 REDIS_URL → RedisStore
      - 未设置 → MemoryStore（零依赖 fallback）
    """
    global _store_instance
    if _store_instance is None:
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            _store_instance = RedisStore(redis_url)
            print(f"[StateStore] Using RedisStore: {redis_url}")
        else:
            _store_instance = MemoryStore()
            print("[StateStore] Using MemoryStore (in-memory fallback)")
    return _store_instance


async def close_store() -> None:
    """关闭全局状态存储（在应用停机时调用）。"""
    global _store_instance
    if _store_instance is not None:
        await _store_instance.close()
        _store_instance = None
