"""Redis pub/sub for pushing generation events to WebSocket clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis
from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)

EVENTS_CHANNEL = "contentforge:events"


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        stale: list[WebSocket] = []
        for ws in self._connections:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
                else:
                    stale.append(ws)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


async def redis_subscriber_task(redis_url: str, manager: ConnectionManager) -> None:
    import redis.asyncio as aioredis

    r = aioredis.from_url(redis_url, decode_responses=True)
    pubsub = r.pubsub()
    try:
        await pubsub.subscribe(EVENTS_CHANNEL)
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if isinstance(data, str):
                await manager.broadcast(data)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Redis pub/sub subscriber stopped with error")
    finally:
        try:
            await pubsub.unsubscribe(EVENTS_CHANNEL)
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass
        await r.aclose()


def publish_job_event_sync(
    redis_url: str,
    *,
    job_id: int,
    task_name: str,
    ok: bool,
    content_item_id: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "type": "job_done",
        "job_id": job_id,
        "task_name": task_name,
        "ok": ok,
    }
    if content_item_id is not None:
        payload["content_item_id"] = content_item_id
    try:
        client = redis.from_url(redis_url, decode_responses=True)
        try:
            client.publish(EVENTS_CHANNEL, json.dumps(payload))
        finally:
            client.close()
    except Exception:
        logger.exception("publish_job_event_sync failed for job_id=%s", job_id)
