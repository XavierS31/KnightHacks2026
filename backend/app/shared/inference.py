"""Bounded HF-only inference. A nonzero budget is opt-in, not spend accounting.

No fixture may call this adapter. Never persist raw provider errors or model prompts.
Consumers must supply strict Pydantic schemas and persist returned provenance.
"""
import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Generic, TypeVar
from uuid import uuid4

import httpx
from huggingface_hub import AsyncInferenceClient
from pydantic import BaseModel, ValidationError

from backend.app.shared.settings import Settings

Output = TypeVar("Output", bound=BaseModel)


class InferenceError(Exception):
    def __init__(self, code: str, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class InferenceResult(Generic[Output]):
    value: Output
    provenance: dict[str, Any]


class HuggingFaceInference:
    """One instance per app/worker; injectable client keeps tests offline.

    This adapter limits requests but cannot measure dollar spend: callers must run
    the pilot forecast and enforce experiment-level accounting before full batches.
    """

    def __init__(self, settings: Settings, client: Any = None):
        self.settings = settings
        self._client = client
        self._semaphore = asyncio.Semaphore(settings.hf_max_inflight)

    def _validate_configuration(self):
        if self.settings.app_mode == "fixture":
            raise InferenceError("FIXTURE_INFERENCE_FORBIDDEN")
        if not (self.settings.hf_token.get_secret_value()
                and self.settings.hf_model_id and self.settings.hf_provider):
            raise InferenceError("INFERENCE_NOT_CONFIGURED")
        if self.settings.experiment_budget_limit <= 0:
            raise InferenceError("BUDGET_NOT_APPROVED")
        # Never allow caller-controlled endpoints or credentials in model IDs.
        for model in (self.settings.hf_model_id, self.settings.hf_coding_model_id):
            if "://" in model or model.startswith(("/", "\\")):
                raise InferenceError("INVALID_MODEL_ID")

    async def generate_structured(
        self, *, role: str, messages: list[dict[str, str]], output_schema: type[Output],
        prompt_version: str, coding: bool = False,
        request_context: dict[str, str] | None = None,
    ) -> InferenceResult[Output]:
        self._validate_configuration()
        model = (self.settings.hf_coding_model_id if coding else "") or self.settings.hf_model_id
        if self._client is None:
            self._client = AsyncInferenceClient(
                token=self.settings.hf_token.get_secret_value(),
                provider=self.settings.hf_provider,
                timeout=self.settings.hf_request_timeout_seconds,
            )
        config = {"model": model, "provider": self.settings.hf_provider,
                  "temperature": 0, "max_tokens": 1024, "prompt_version": prompt_version}
        loop = asyncio.get_running_loop()
        started = loop.time()
        async with self._semaphore:
            for attempt in range(2):
                try:
                    async with asyncio.timeout(self.settings.hf_request_timeout_seconds):
                        response = await self._client.chat_completion(
                            messages=messages, model=model, temperature=0, max_tokens=1024,
                            response_format={"type": "json_schema", "json_schema": {
                                "name": output_schema.__name__, "strict": True,
                                "schema": output_schema.model_json_schema(),
                            }},
                        )
                    content = response.choices[0].message.content
                    if not isinstance(content, str):
                        raise InferenceError("INVALID_MODEL_OUTPUT")
                    try:
                        value = output_schema.model_validate_json(content)
                    except (ValidationError, ValueError):
                        raise InferenceError("INVALID_MODEL_OUTPUT") from None
                    usage = getattr(response, "usage", None)
                    context = request_context or {}
                    provenance = {
                        "request_id": str(uuid4()), "role": role, "model_id": model,
                        "provider": self.settings.hf_provider, "prompt_version": prompt_version,
                        "configuration_hash": hashlib.sha256(json.dumps(
                            config, sort_keys=True).encode()).hexdigest(),
                        "latency_ms": round((loop.time() - started) * 1000),
                        "retry_count": attempt, "status": "completed",
                        "token_usage_if_reported": {
                            name: getattr(usage, name, None)
                            for name in ("prompt_tokens", "completion_tokens", "total_tokens")
                        } if usage else None,
                        "experiment_id": context.get("experiment_id"),
                        "session_id": context.get("session_id"),
                    }
                    return InferenceResult(value=value, provenance=provenance)
                except InferenceError:
                    raise
                except (IndexError, AttributeError, TypeError):
                    raise InferenceError("INVALID_MODEL_OUTPUT") from None
                except Exception as failure:
                    status = getattr(getattr(failure, "response", None), "status_code", None)
                    transient = isinstance(failure, (TimeoutError, ConnectionError,
                                                     httpx.TimeoutException, httpx.NetworkError)) or (
                        status == 429 or (isinstance(status, int) and status >= 500))
                    if transient and attempt == 0:
                        delay = 0.25
                        # Honor numeric Retry-After without allowing unbounded waits.
                        headers = getattr(getattr(failure, "response", None), "headers", {})
                        try:
                            delay = min(2.0, max(delay, float(headers.get("retry-after", delay))))
                        except (TypeError, ValueError):
                            pass
                        await asyncio.sleep(delay)
                        continue
                    raise InferenceError("INFERENCE_REQUEST_FAILED", retryable=transient) from None
        raise InferenceError("INFERENCE_REQUEST_FAILED")

    async def close(self):
        if self._client is not None and hasattr(self._client, "close"):
            await self._client.close()
