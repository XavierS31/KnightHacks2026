"""Offline batching and checkpoint rejection; fake HF is never live evidence."""
from types import SimpleNamespace

import pytest

from backend.app.features.personas.generation_batches import CheckpointedDetailBatches
from backend.app.features.personas.population import FictionalDetails, PopulationError
from backend.app.shared.inference import InferenceResult


class FakeBudgeted:
    def __init__(self):
        self.adapter = SimpleNamespace(settings=SimpleNamespace(
            hf_model_id="fake", hf_provider="fake"))
        self.calls = 0

    async def generate_structured(self, **kwargs):
        self.calls += 1
        value = kwargs["output_schema"].model_validate({"details": [
            {"synthetic_name": f"Invented {i}", "skills": ["Reading"],
             "constraints": ["Time"]} for i in range(5)]})
        return InferenceResult(value, {"provider": "fake", "request_id": "test-only"})


def arguments(context="same"):
    return {"output_schema": FictionalDetails, "role": "persona_generator",
            "prompt_version": "test", "messages": [
                {"role": "system", "content": "Fictional"},
                {"role": "user", "content": context}]}


async def test_resume_reuses_exact_chunks_without_paid_call(tmp_path):
    fake = FakeBudgeted()
    adapter = CheckpointedDetailBatches(fake, tmp_path)
    first = [await adapter.generate_structured(**arguments()) for _ in range(5)]
    adapter.assert_complete()
    assert fake.calls == 1
    recovered = CheckpointedDetailBatches(fake, tmp_path)
    second = [await recovered.generate_structured(**arguments()) for _ in range(5)]
    assert first == second and fake.calls == 1
    assert [r.provenance["batch_record_index"] for r in first] == list(range(5))


async def test_changed_context_and_partial_batch_fail_closed(tmp_path):
    adapter = CheckpointedDetailBatches(FakeBudgeted(), tmp_path)
    await adapter.generate_structured(**arguments())
    with pytest.raises(PopulationError, match="NOT_DIVISIBLE"):
        await adapter.generate_structured(**arguments("different"))
    with pytest.raises(PopulationError, match="UNCONSUMED"):
        adapter.assert_complete()
    recovered = CheckpointedDetailBatches(FakeBudgeted(), tmp_path)
    with pytest.raises(PopulationError, match="CONTEXT_MISMATCH"):
        await recovered.generate_structured(**arguments("different"))


async def test_provider_change_cannot_reuse_checkpoint(tmp_path):
    fake = FakeBudgeted()
    await CheckpointedDetailBatches(fake, tmp_path).generate_structured(**arguments())
    fake.adapter.settings.hf_provider = "changed"
    with pytest.raises(PopulationError, match="CONTEXT_MISMATCH"):
        await CheckpointedDetailBatches(fake, tmp_path).generate_structured(**arguments())
