import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr

from backend.app.shared.contracts import Action, Feedback, Session
from backend.app.shared.settings import Settings
from backend.migrations.runner import apply, discover

# A disposable TLS PostgreSQL URL. Each test uses its own schema and drops it afterwards.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


@pytest.fixture
def migrated(isolated):
    """A fully migrated schema with one product version and one running experiment."""
    settings, database = isolated
    apply(database, discover())
    version_id, experiment_id = uuid4(), uuid4()
    with database.connection() as connection:
        connection.execute("INSERT INTO product_versions (id, label, status, manifest) "
                           "VALUES (%s, 'v1', 'validated', '{}')", (version_id,))
        connection.execute("INSERT INTO experiments (id, population_id, product_version_id, "
                           "task_set_id, configuration, status) "
                           "VALUES (%s, %s, %s, %s, '{}', 'running')",
                           (experiment_id, uuid4(), version_id, uuid4()))
    return {"settings": settings, "database": database,
            "version_id": version_id, "experiment_id": experiment_id}

INITIAL_MIGRATION = Path(__file__).parents[2] / "migrations" / "001_initial.sql"
LIVE_HF = dict(hf_token="test-secret-never-log", hf_model_id="test/model",
               hf_provider="hf-inference", experiment_budget_limit=1)


class ScriptedClient:
    """Stands in for the HF provider; answers by requested schema name and records each call."""

    def __init__(self):
        self.responses: dict[str, str] = {}
        self.calls: list[dict] = []

    def answer(self, findings, assessments=(), proposals=()):
        self.responses = {
            "AnalystOutput": json.dumps({"findings": list(findings)}),
            "PrioritizerOutput": json.dumps({"assessments": list(assessments)}),
            "UxOutput": json.dumps({"proposals": list(proposals)}),
        }

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses[kwargs["response_format"]["json_schema"]["name"]]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                               usage=None)


@pytest.fixture
def hf_client():
    return ScriptedClient()


@pytest.fixture
def live_settings():
    return Settings(_env_file=None, app_mode="live", **LIVE_HF)


@pytest.fixture
def live_sessions():
    """Four finished sessions of one experiment; labels F1-F3 and A1-A6 follow this order.

    F1/F2 report the same product barrier (A1-A4), F3 is an infrastructure failure (A5-A6)
    and the fourth session succeeded without feedback.
    """
    experiment_id, version_id = uuid4(), uuid4()
    occurred = datetime(2026, 10, 10, tzinfo=UTC)
    sessions = []
    for outcome, barrier in [("application_failure", "Upload button is hidden"),
                             ("application_failure", "Upload button is hidden"),
                             ("infrastructure_failure", "Browser timed out"),
                             ("success", None)]:
        session_id, persona_id = uuid4(), uuid4()
        actions = [Action(id=uuid4(), session_id=session_id, sequence=sequence, timestamp=occurred,
                          kind="click", target="#upload", result=f"Recorded step {sequence}")
                   for sequence in (1, 2)]
        feedback = None if barrier is None else Feedback(
            id=uuid4(), persona_id=persona_id, session_id=session_id, initial_relevance="high",
            post_trial_relevance="medium", decision="stop", useful_parts=[], barriers=[barrier],
            suggested_changes=["Make upload visible"], evidence_action_ids=[actions[0].id],
            reason="Persona could not continue")
        sessions.append(Session(
            id=session_id, experiment_id=experiment_id, persona_id=persona_id,
            product_version_id=version_id, status="completed", outcome=outcome,
            stop_reason="task ended", actions=actions, feedback=feedback, stream_mode="replay"))
    return sessions


@pytest.fixture
def migrated_settings():
    """Live settings whose database is an isolated schema holding the 001 tables."""
    if not TEST_DATABASE_URL:
        pytest.skip("Set TEST_DATABASE_URL")
    schema = f"evolution_{uuid4().hex}"
    separator = "&" if "?" in TEST_DATABASE_URL else "?"
    url = f"{TEST_DATABASE_URL}{separator}options=-csearch_path%3D{schema}"
    with psycopg.connect(TEST_DATABASE_URL, sslmode="require", autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
        try:
            with psycopg.connect(url, sslmode="require", autocommit=True) as connection:
                connection.execute(INITIAL_MIGRATION.read_text())
            yield Settings(_env_file=None, app_mode="live", database_url=SecretStr(url), **LIVE_HF)
        finally:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture(autouse=True)
def synthetic_prototype(request, monkeypatch):
    # Only lifecycle/router/implementer tests inject a selected prototype. Runtime defaults stay empty.
    if request.node.path.name not in {"test_lifecycle.py", "test_retest.py", "test_implementer.py", "test_improvement_intake.py"}:
        return
    from backend.app.features.evolution import router
    from backend.tests.prototype_fixtures import SOURCES, handoff
    monkeypatch.setattr(router, "load_handoff", handoff)
    monkeypatch.setattr(router, "frozen_v1_sources", lambda: dict(SOURCES))
