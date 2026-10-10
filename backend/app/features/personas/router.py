import asyncio
import hmac
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from backend.app.shared.contracts import PersonaSummary, Session, StreamEvent
from backend.app.shared.fixtures import EXPERIMENT, PERSONAS, SESSIONS
from backend.app.shared.settings import Settings, get_settings

router = APIRouter(tags=["personas"])
LOCAL_ORIGINS = {f"http://{host}:{port}" for host in ("127.0.0.1", "localhost")
                 for port in (5173, 4173, 8000)}


@router.get("/personas/summary", response_model=PersonaSummary)
def summary(settings: Settings = Depends(get_settings)):
    require_fixture(settings)
    return PersonaSummary(mode="fixture", personas=PERSONAS, experiments=[EXPERIMENT],
                          sessions=SESSIONS, next_gate="Execute one real browser task with saved evidence.")


def require_fixture(settings: Settings):
    if settings.app_mode != "fixture":
        raise HTTPException(status_code=409, detail={"code": "LIVE_SESSIONS_NOT_IMPLEMENTED",
                            "message": "Real session storage and execution are not implemented yet."})


def authorize(settings: Settings, host: str | None, token: str):
    expected = settings.viewer_token.get_secret_value()
    if expected:
        return hmac.compare_digest(expected.encode(), token.encode())
    return settings.app_mode == "fixture" and host in {"127.0.0.1", "::1", "localhost"}


def find_session(session_id: UUID) -> Session:
    session = next((item for item in SESSIONS if item.id == session_id), None)
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND",
                            "message": "Session was not found."})
    return session


@router.get("/sessions/{session_id}", response_model=Session)
def session_detail(session_id: UUID, request: Request, settings: Settings = Depends(get_settings)):
    require_fixture(settings)
    if request.headers.get("origin") and request.headers["origin"] not in LOCAL_ORIGINS:
        raise HTTPException(status_code=403, detail={"code": "VIEWER_ORIGIN_FORBIDDEN",
                            "message": "Viewer origin is not permitted."})
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    if not authorize(settings, request.client.host if request.client else None, token):
        raise HTTPException(status_code=401, detail={"code": "VIEWER_UNAUTHORIZED",
                            "message": "A valid viewer token or local fixture connection is required."})
    return find_session(session_id)


@router.websocket("/sessions/{session_id}/stream")
async def session_stream(websocket: WebSocket, session_id: UUID):
    settings = get_settings()
    if settings.app_mode != "fixture":
        await websocket.close(code=1008, reason="Live sessions are not implemented")
        return
    if websocket.headers.get("origin") and websocket.headers["origin"] not in LOCAL_ORIGINS:
        await websocket.close(code=1008, reason="Viewer origin is not permitted")
        return
    await websocket.accept()
    try:
        # Credentials travel in a first message, never in URLs/logs.
        async with asyncio.timeout(5):
            auth = await websocket.receive_json()
        if not isinstance(auth, dict) or not isinstance(auth.get("token", ""), str):
            await websocket.close(code=1008, reason="Invalid viewer credentials")
            return
        if not authorize(settings, websocket.client.host if websocket.client else None,
                         auth.get("token", "")):
            await websocket.close(code=1008, reason="Viewer unauthorized")
            return
        try:
            session = find_session(session_id)
        except HTTPException:
            await websocket.close(code=1008, reason="Session not found")
            return
        sequence = 0
        event = StreamEvent(session_id=session.id, sequence=sequence, timestamp=datetime.now(UTC),
                            type="state", mode="fixture", payload={
                                "session": session.model_dump(mode="json"),
                                "notice": "Fixture only. No browser actions or frames have been captured.",
                            })
        await websocket.send_json(event.model_dump(mode="json"))
        while True:
            try:
                async with asyncio.timeout(15):
                    await websocket.receive_text()
            except TimeoutError:
                sequence += 1
                heartbeat = StreamEvent(session_id=session.id, sequence=sequence,
                                        timestamp=datetime.now(UTC), type="heartbeat", mode="fixture",
                                        payload={"execution": "not_run"})
                await websocket.send_json(heartbeat.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
    except (TimeoutError, ValueError):
        await websocket.close(code=1008, reason="Viewer disconnected or authentication expired")
