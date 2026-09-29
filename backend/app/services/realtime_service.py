"""Real-time event hub backed by an in-process pub/sub.

Implements two transports with one interface:

- **Server-Sent Events** (default, resilient, auto-reconnect) over
  ``GET /api/v1/realtime/events``
- **WebSockets** over ``WS /api/v1/realtime``

Events are broadcast to every subscriber.  Because a single API process is the
prototype topology, an in-memory hub is sufficient; Redis pub/sub can be added
behind the same interface when scaling out workers.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from starlette.websockets import WebSocket

from app.core.enums import RealtimeEventType

logger = structlog.get_logger("realtime")


@dataclass
class _Subscriber:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    client_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    closed: bool = False


class EventHub:
    """Broadcast hub for realtime platform events."""

    def __init__(self) -> None:
        self._subscribers: dict[str, _Subscriber] = {}
        self._lock = asyncio.Lock()
        self._history: list[dict[str, Any]] = []
        self._history_limit = 500

    @staticmethod
    def _ts() -> str:
        return datetime.now(UTC).isoformat()

    async def publish(
        self,
        event_type: RealtimeEventType | str,
        payload: dict[str, Any],
        *,
        persistence_hook: Any | None = None,
    ) -> dict[str, Any]:
        """Emit an event to all subscribers. Returns the serialised event."""
        event: dict[str, Any] = {
            "type": event_type.value if hasattr(event_type, "value") else str(event_type),
            "event_id": str(uuid.uuid4()),
            "timestamp": self._ts(),
            "payload": payload,
        }
        if persistence_hook:
            await persistence_hook(event)
        self._history.append(event)
        self._history = self._history[-self._history_limit :]
        async with self._lock:
            subscribers = list(self._subscribers.values())
        for sub in subscribers:
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                sub.queue = asyncio.Queue(maxsize=1000)
                sub.queue.put_nowait(event)
            except Exception:  # pragma: no cover
                pass
        logger.debug("published", type=event["type"])
        return event

    async def subscribe(self) -> _Subscriber:
        sub = _Subscriber()
        async with self._lock:
            self._subscribers[sub.client_id] = sub
        return sub

    async def unsubscribe(self, sub: _Subscriber) -> None:
        sub.closed = True
        async with self._lock:
            self._subscribers.pop(sub.client_id, None)

    async def history(self, since: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        """Recent events, optionally filtered by an ISO-8601 ``since`` stamp."""
        if not since:
            return self._history[-limit:]
        try:
            cutoff = datetime.fromisoformat(since)
        except ValueError:
            return self._history[-limit:]
        items = [e for e in self._history if demoafter(e, cutoff)][-limit:]
        return items

    def subscriber_count(self) -> int:
        return len(self._subscribers)


def demoafter(event: dict[str, Any], cutoff: Any) -> bool:
    try:
        ts = datetime.fromisoformat(event["timestamp"])
        return ts >= cutoff
    except (KeyError, ValueError):
        return True


event_hub: EventHub = EventHub()


@dataclass
class RealtimeSession:
    """Lifetime holder for one SSE/WS client connection."""

    ws: Any = None
    sub: _Subscriber | None = None


class RealtimeManager:
    """Ties an SSE or WebSocket connection to the shared hub."""

    async def connect_sse(self) -> _Subscriber:
        return await event_hub.subscribe()

    async def connect_ws(self, websocket: WebSocket) -> _Subscriber:
        await websocket.accept()
        return await event_hub.subscribe()

    async def close(self, sub: _Subscriber | None) -> None:
        if sub:
            await event_hub.unsubscribe(sub)

    @classmethod
    async def stream_sse(cls, sub: _Subscriber) -> AsyncIterator[str]:
        """Async generator yielding ``data: <json>\\n\\n`` chunks."""
        while not sub.closed:
            try:
                event = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
            except TimeoutError:
                yield "event: heartbeat\ndata: {}\n\n"
                continue
            except Exception:
                break
            yield f"id: {event['event_id']}\ndata: {json.dumps(event)}\n\n"

    @classmethod
    async def pump_ws(cls, websocket: Any, sub: _Subscriber) -> None:
        """Forward hub events to a WebSocket subscriber."""
        try:
            while not sub.closed:
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                except TimeoutError:
                    continue
                await websocket.send_json(event)
        except Exception:
            pass


realtime_manager: RealtimeManager = RealtimeManager()

__all__ = [
    "EventHub",
    "RealtimeManager",
    "RealtimeSession",
    "event_hub",
    "realtime_manager",
]
