"""No network: readiness cap/restart/accounting/sanitized-failure regression gates."""
import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.features.personas import live_readiness
from backend.app.features.personas.mock_worker import BrowserDecision
from backend.app.shared.inference import InferenceError, InferenceResult


@pytest.fixture
def fake_adapter(monkeypatch):
    class FakeAdapter:
        calls = 0
        closed = 0
        failure = None
        usage = None

        def __init__(self, settings):
            self.settings = settings

        async def generate_structured(self, **kwargs):
            type(self).calls += 1
            if self.failure:
                raise self.failure
            return InferenceResult(value=BrowserDecision(kind="click", target_id="load-sample"),
                                   provenance={"model_id": "Qwen/Qwen3-32B",
                                               "provider": "deepinfra", "retry_count": 0,
                                               "token_usage_if_reported": self.usage})

        async def close(self):
            type(self).closed += 1

    monkeypatch.setattr(live_readiness, "Settings", lambda **kwargs: SimpleNamespace(
        hf_model_id="Qwen/Qwen3-32B", hf_provider="deepinfra", hf_coding_model_id="",
        hf_request_timeout_seconds=20))
    monkeypatch.setattr(live_readiness, "HuggingFaceInference", FakeAdapter)
    return FakeAdapter


@pytest.mark.parametrize("cap", ["0", "-1", "4.0001", "NaN", "Infinity"])
async def test_cap_exceeding_authorization_never_creates_marker_or_calls_provider(
    tmp_path, fake_adapter, cap,
):
    marker = tmp_path / "accounting.json"
    with pytest.raises(ValueError, match="authorized"):
        await live_readiness.run_readiness(budget=Decimal(cap), marker=marker)
    assert fake_adapter.calls == 0 and not marker.exists()


async def test_exclusive_restart_marker_prevents_budget_reset_and_new_calls(tmp_path, fake_adapter):
    marker = tmp_path / "accounting.json"
    original = '{"status":"started_do_not_reset_budget","protected_dollars":"4"}'
    marker.write_text(original)
    with pytest.raises(FileExistsError):
        await live_readiness.run_readiness(budget=Decimal("4"), marker=marker)
    assert marker.read_text() == original and fake_adapter.calls == 0


async def test_success_remains_configuration_only_and_retains_missing_usage(tmp_path, fake_adapter):
    marker = tmp_path / "nested" / "accounting.json"
    result = await live_readiness.run_readiness(budget=Decimal("4"), marker=marker)
    assert result["status"] == "validated"
    assert result["input_mode"] == "fixture" and result["trials_completed"] == 0
    assert fake_adapter.calls == fake_adapter.closed == 1
    entry = result["budget"]["entries"][0]
    assert Decimal(entry["charged_dollars"]) > 0
    assert entry["charged_dollars"] == entry["reserved_dollars"]
    assert entry["status"] == "unreported_usage"
    assert json.loads(marker.read_text()) == result
    with pytest.raises(FileExistsError):
        await live_readiness.run_readiness(budget=Decimal("4"), marker=marker)
    assert fake_adapter.calls == 1


async def test_failed_provider_call_keeps_conservative_accounting_and_only_sanitized_code(
    tmp_path, fake_adapter,
):
    fake_adapter.failure = InferenceError("INFERENCE_REQUEST_FAILED", retryable=True)
    marker = tmp_path / "accounting.json"
    result = await live_readiness.run_readiness(budget=Decimal("4"), marker=marker)
    assert result["status"] == "blocked" and result["retryable"] is True
    assert result["code"] == "INFERENCE_REQUEST_FAILED"
    entry = result["budget"]["entries"][0]
    assert entry["status"] == "unreported_or_failed"
    assert entry["charged_dollars"] == entry["reserved_dollars"]
    assert fake_adapter.closed == 1
    assert "provenance" not in result and "messages" not in result
    saved = marker.read_text()
    assert "hf_token" not in saved and "traceback" not in saved and "prompt" not in saved


async def test_budget_below_reservation_never_sends(tmp_path, fake_adapter):
    result = await live_readiness.run_readiness(budget=Decimal("0.000001"),
                                               marker=tmp_path / "accounting.json")
    assert result["code"] == "EXPERIMENT_BUDGET_EXHAUSTED"
    assert fake_adapter.calls == 0 and result["budget"]["entries"] == []


async def test_reported_final_usage_charges_exact_known_tokens(tmp_path, fake_adapter):
    fake_adapter.usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}
    result = await live_readiness.run_readiness(budget=Decimal("4"),
                                               marker=tmp_path / "accounting.json")
    assert Decimal(result["budget"]["charged_dollars"]) == Decimal("0.0000162")
    assert result["budget"]["entries"][0]["status"] == "reported_final_attempt"
