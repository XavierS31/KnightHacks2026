from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.features.personas.router import router
from backend.app.shared.fixtures import SESSIONS


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("VIEWER_TOKEN", "")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app, client=("127.0.0.1", 50000)) as test_client:
        yield test_client


def test_fixture_not_execution(client):
    response = client.get(f"/api/v1/sessions/{SESSIONS[0].id}")
    assert response.status_code == 200
    assert response.json()["status"] == "fixture"
    assert response.json()["outcome"] == "not_run"
    assert response.json()["actions"] == []


def test_missing_session(client):
    assert client.get(f"/api/v1/sessions/{uuid4()}").status_code == 404


def test_authenticated_viewer(client, monkeypatch):
    monkeypatch.setenv("VIEWER_TOKEN", "viewer-secret")
    url = f"/api/v1/sessions/{SESSIONS[0].id}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer viewer-secret"}).status_code == 200


def test_foreign_origin_forbidden(client):
    assert client.get(f"/api/v1/sessions/{SESSIONS[0].id}",
                      headers={"Origin": "https://untrusted.example"}).status_code == 403


def test_remote_fixture_requires_token(monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("VIEWER_TOKEN", "")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app, client=("192.0.2.2", 50000)) as client:
        assert client.get(f"/api/v1/sessions/{SESSIONS[0].id}").status_code == 401


def test_live_never_returns_fixture(client, monkeypatch):
    monkeypatch.setenv("APP_MODE", "live")
    assert client.get("/api/v1/personas/summary").status_code == 409
    assert client.get(f"/api/v1/sessions/{SESSIONS[0].id}").status_code == 409


def test_stream_exact_fixture_state(client):
    with client.websocket_connect(f"/api/v1/sessions/{SESSIONS[1].id}/stream") as socket:
        socket.send_json({"token": ""})
        event = socket.receive_json()
        assert event["session_id"] == str(SESSIONS[1].id)
        assert event["type"] == "state"
        assert event["mode"] == "fixture"
        assert event["payload"]["session"]["actions"] == []
        assert event["payload"]["session"]["outcome"] == "not_run"


def test_stream_token_required(client, monkeypatch):
    monkeypatch.setenv("VIEWER_TOKEN", "secret")
    with client.websocket_connect(f"/api/v1/sessions/{SESSIONS[0].id}/stream") as socket:
        socket.send_json({"token": "wrong"})
        with pytest.raises(WebSocketDisconnect) as failure:
            socket.receive_json()
        assert failure.value.code == 1008


def test_stream_foreign_origin_forbidden(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/sessions/{SESSIONS[0].id}/stream",
                                      headers={"Origin": "https://untrusted.example"}):
            pass
