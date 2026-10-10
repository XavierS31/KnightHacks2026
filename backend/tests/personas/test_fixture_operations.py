import asyncio
import base64
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.features.personas import router as routes
from backend.app.features.personas.fixture_operations import FixtureStore, run_fixture
from backend.app.features.personas.session_execution import frame_event
from backend.app.shared.fixtures import EXPERIMENT, PERSONAS, SESSIONS

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("VIEWER_TOKEN", "")
    monkeypatch.setattr(routes, "store", FixtureStore())
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        yield client


def test_busy_and_four_worker_bound():
    store = FixtureStore()
    ids = [uuid4() for _ in range(5)]
    for identifier in ids[:4]:
        store.reserve(identifier)
    for identifier in [ids[0], ids[4]]:
        with pytest.raises(HTTPException) as failure:
            store.reserve(identifier)
        assert failure.value.status_code == 409
    store.release(ids[0])
    store.reserve(ids[4])


def test_store_bound_and_latest_and_immutable_copies():
    store = FixtureStore()
    saved = []
    for _ in range(21):
        session = SESSIONS[0].model_copy(update={"id": uuid4()}, deep=True)
        saved.append(session)
        store.save(session, None)
    assert len(store.records) == 20
    assert store.get(saved[0].id) is None
    assert store.latest()[saved[-1].persona_id].id == saved[-1].id
    saved[-1].stop_reason = "mutation"
    assert store.get(saved[-1].id)[0].stop_reason != "mutation"


def test_mock_route_summary_detail_and_frame(client, monkeypatch):
    captured = datetime.now(UTC)

    async def execute(persona):
        session = SESSIONS[0].model_copy(update={"id": uuid4(), "persona_id": persona.id}, deep=True)
        routes.store.save(session, frame_event(session, PNG, sequence=8,
                                              frame_sequence=4, timestamp=captured))
        return session

    monkeypatch.setattr(routes, "run_fixture", execute)
    url = f"/api/v1/personas/mock-trials/{PERSONAS[0].id}"
    first = client.post(url).json()
    second = client.post(url).json()
    assert first["id"] != second["id"]
    assert first["status"] == "fixture" and first["outcome"] == "not_run"
    summary = client.get("/api/v1/personas/summary").json()
    assert summary["sessions"][0]["id"] == second["id"]
    assert second["experiment_id"] == summary["experiments"][0]["id"]
    assert summary["experiments"][0]["counts"]["completed"] == 0
    assert client.get(f"/api/v1/sessions/{first['id']}").status_code == 200
    with client.websocket_connect(f"/api/v1/sessions/{second['id']}/stream") as socket:
        socket.send_json({"token": ""})
        state, frame = socket.receive_json(), socket.receive_json()
        assert state["sequence"] == 0 and frame["sequence"] == 1
        assert frame["payload"]["session_id"] == second["id"]
        assert frame["payload"]["captured_at"] == captured.isoformat()
        assert datetime.fromisoformat(frame["timestamp"]) >= captured


def test_mock_auth_origin_unknown_and_live(client, monkeypatch):
    url = f"/api/v1/personas/mock-trials/{PERSONAS[0].id}"
    assert client.post(url, headers={"Origin": "https://foreign.example"}).status_code == 403
    assert client.post(f"/api/v1/personas/mock-trials/{uuid4()}").status_code == 404
    monkeypatch.setenv("VIEWER_TOKEN", "viewer-secret")
    assert client.post(url).status_code == 401
    monkeypatch.setenv("APP_MODE", "live")
    assert client.post(url, headers={"Authorization": "Bearer viewer-secret"}).status_code == 409


def test_route_refuses_same_persona_busy(client):
    routes.store.reserve(PERSONAS[0].id)
    response = client.post(f"/api/v1/personas/mock-trials/{PERSONAS[0].id}")
    assert response.status_code == 409


def test_remote_cannot_execute_even_with_token(monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("VIEWER_TOKEN", "viewer-secret")
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    with TestClient(app, client=("192.0.2.1", 50000)) as client:
        response = client.post(f"/api/v1/personas/mock-trials/{PERSONAS[0].id}",
                               headers={"Authorization": "Bearer viewer-secret"})
        assert response.status_code == 403


def test_browser_failure_sanitized_and_reservation_released(client, monkeypatch):
    async def unavailable(persona):
        raise RuntimeError("hf_secret /private/path")

    monkeypatch.setattr(routes, "run_fixture", unavailable)
    response = client.post(f"/api/v1/personas/mock-trials/{PERSONAS[0].id}")
    assert response.status_code == 503
    assert "hf_secret" not in response.text and "/private/path" not in response.text
    assert not routes.store.busy


@pytest.mark.skipif(os.environ.get("B_BROWSER_TESTS") != "1", reason="Opt-in local Chromium check")
def test_actual_fixture_execution(monkeypatch):
    from backend.app.features.personas import fixture_operations

    store = FixtureStore()
    monkeypatch.setattr(fixture_operations, "store", store)
    result = asyncio.run(run_fixture(PERSONAS[0]))
    assert result.status == "fixture" and result.outcome == "not_run"
    assert result.experiment_id == EXPERIMENT.id
    assert result.stop_reason == "success"
    assert [action.kind for action in result.actions] == ["navigate", "click", "click", "check"]
    assert result.feedback.synthetic and result.feedback.evidence_action_ids
    captured = store.get(result.id)[1]
    assert captured.type == "frame" and captured.payload["frame_sequence"] == 4
    assert base64.b64decode(captured.payload["image_base64"]).startswith(b"\x89PNG\r\n\x1a\n")
