"""Realtime event streaming: Server-Sent Events (GET) + WebSocket (WS)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import async_session_factory, get_db
from app.core.errors import AuthenticationError
from app.core.security import decode_token
from app.models import User
from app.services.realtime_service import _Subscriber, event_hub, realtime_manager

router = APIRouter(prefix="/realtime", tags=["realtime"])


async def _sse_mux(_: AsyncSession, sub: _Subscriber, since: str | None) -> AsyncIterator[str]:
    """Replay recent history, then stream live events as Server-Sent Events."""
    for event in await event_hub.history(since=since):
        yield f"id: {event['event_id']}\ndata: {json.dumps(event)}\n\n"
    async for line in realtime_manager.stream_sse(sub):
        yield line


@router.get("/events")
async def stream_events(
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    since: str | None = None,
) -> StreamingResponse:
    """Stream platform events as Server-Sent Events.

    ``session`` is injected to satisfy the auth dependency graph; live events
    live in the in-process hub and are not persisted.
    """
    sub = await realtime_manager.connect_sse()
    background_tasks.add_task(_close, sub)
    return StreamingResponse(
        _sse_mux(session, sub, since),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _close(sub: _Subscriber) -> None:
    await realtime_manager.close(sub)


@router.websocket("")
async def websocket_events(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        claims = decode_token(token, "access")
        user_id = uuid.UUID(str(claims.get("sub")))
    except (AuthenticationError, ValueError, TypeError):
        await websocket.close(code=4401)
        return
    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            await websocket.close(code=4401)
            return
        sub = await realtime_manager.connect_ws(websocket)
        try:
            await realtime_manager.pump_ws(websocket, sub)
        except WebSocketDisconnect:
            pass
        finally:
            await realtime_manager.close(sub)


__all__ = ["router"]
