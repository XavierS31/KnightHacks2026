import asyncio
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from backend.app.shared.inference import HuggingFaceInference, InferenceError
from backend.app.shared.settings import Settings


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str


class FakeClient:
    def __init__(self, content='{"answer":"yes"}', failure=None):
        self.content = content
        self.failure = failure
        self.calls = []

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=self.content))], usage=None)


def live_settings(**overrides):
    values = dict(_env_file=None, app_mode="live", hf_token="test-secret-never-log",
                  hf_model_id="test/model", hf_provider="hf-inference", experiment_budget_limit=1)
    values.update(overrides)
    return Settings(**values)


async def generate(adapter):
    return await adapter.generate_structured(role="test", messages=[{"role": "user", "content": "test"}],
                                             output_schema=Answer, prompt_version="test-v1")


@pytest.mark.parametrize("overrides,code", [
    ({"app_mode": "fixture"}, "FIXTURE_INFERENCE_FORBIDDEN"),
    ({"hf_token": ""}, "INFERENCE_NOT_CONFIGURED"),
    ({"hf_model_id": ""}, "INFERENCE_NOT_CONFIGURED"),
    ({"hf_provider": ""}, "INFERENCE_NOT_CONFIGURED"),
    ({"experiment_budget_limit": 0}, "BUDGET_NOT_APPROVED"),
    ({"hf_model_id": "https://untrusted.example/model"}, "INVALID_MODEL_ID"),
])
async def test_preflight_never_invokes_client(overrides, code):
    client = FakeClient()
    with pytest.raises(InferenceError) as failure:
        await generate(HuggingFaceInference(live_settings(**overrides), client=client))
    assert failure.value.code == code
    assert client.calls == []


async def test_schema_and_provenance():
    client = FakeClient()
    result = await generate(HuggingFaceInference(live_settings(), client=client))
    assert result.value.answer == "yes"
    assert client.calls[0]["response_format"]["json_schema"]["strict"] is True
    assert result.provenance["provider"] == "hf-inference"
    assert result.provenance["model_id"] == "test/model"
    assert result.provenance["token_usage_if_reported"] is None
    assert "test-secret-never-log" not in str(result.provenance)


@pytest.mark.parametrize("content", ['{"wrong":"field"}', '{"answer":"ok","extra":true}', "not JSON"])
async def test_invalid_outputs_rejected_without_retry(content):
    client = FakeClient(content)
    with pytest.raises(InferenceError, match="INVALID_MODEL_OUTPUT"):
        await generate(HuggingFaceInference(live_settings(), client=client))
    assert len(client.calls) == 1


async def test_provider_failure_is_sanitized():
    client = FakeClient(failure=RuntimeError("token=test-secret-never-log"))
    with pytest.raises(InferenceError) as failure:
        await generate(HuggingFaceInference(live_settings(), client=client))
    assert str(failure.value) == "INFERENCE_REQUEST_FAILED"
    assert len(client.calls) == 1


@pytest.mark.parametrize("error", [TimeoutError("secret"), httpx.ReadTimeout("secret"),
                                   httpx.ConnectError("secret"), httpx.HTTPStatusError(
                                       "secret", request=httpx.Request("POST", "https://example.com"),
                                       response=httpx.Response(429))])
async def test_transient_failure_has_one_retry(error):
    client = FakeClient(failure=error)
    with pytest.raises(InferenceError) as failure:
        await generate(HuggingFaceInference(live_settings(), client=client))
    assert failure.value.retryable
    assert len(client.calls) == 2


async def test_semaphore_limits_parallel_requests():
    class CountingClient(FakeClient):
        running = 0
        peak = 0

        async def chat_completion(self, **kwargs):
            self.running += 1
            self.peak = max(self.peak, self.running)
            await asyncio.sleep(.01)
            result = await super().chat_completion(**kwargs)
            self.running -= 1
            return result

    client = CountingClient()
    adapter = HuggingFaceInference(live_settings(hf_max_inflight=2), client=client)
    await asyncio.gather(*(generate(adapter) for _ in range(5)))
    assert client.peak == 2
