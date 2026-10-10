"""Bounded HF detail batches with exclusive, immutable local checkpoints.

Local checkpoints are operator-run recovery evidence, not Neon experiment storage.
Each persona retains the actual batch inference provenance. No failed call is
replaced by fixtures. The caller must enforce the paid budget independently.
"""
import hashlib
import json
from pathlib import Path

from pydantic import Field

from backend.app.features.personas.population import FictionalDetails, PopulationError
from backend.app.shared.contracts import Contract
from backend.app.shared.inference import InferenceResult


class FictionalDetailBatch(Contract):
    details: list[FictionalDetails] = Field(min_length=5, max_length=5)


def batch_messages(messages, batch_index):
    result = [dict(message) for message in messages]
    result[0]["content"] += (
        " Generate exactly five distinct fictional names. Each record has only "
        "one short skill and one short constraint (under 12 words each). "
        "Return a details array. Be concise; no explanation. /no_think")
    result[-1]["content"] += (
        f" Fictional batch ordinal {batch_index}; distinguish names using this ordinal. /no_think")
    return result


class CheckpointedDetailBatches:
    """Sequential adapter: five persona requests sharing exact context per batch.

    Quotas must be multiples of five. Checkpoints bind model configuration,
    output schema and prompts by digest, preventing reuse for changed inputs.
    An exclusive run lock and durable spend ledger are required at orchestration.
    """

    def __init__(self, adapter, directory: Path):
        self.adapter = adapter
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.index = 0
        self.pending = []
        self.pending_digest = None

    async def generate_structured(self, **kwargs):
        if kwargs["output_schema"] is not FictionalDetails:
            raise PopulationError("BATCH_SCHEMA_MISMATCH")
        settings = self.adapter.adapter.settings
        identity = {"messages": kwargs["messages"], "prompt_version": kwargs["prompt_version"],
                    "model_id": settings.hf_model_id, "provider": settings.hf_provider,
                    "batch_index": self.index // 5,
                    "schema": FictionalDetailBatch.model_json_schema()}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        if self.pending and digest != self.pending_digest:
            raise PopulationError("BATCH_QUOTA_NOT_DIVISIBLE_BY_FIVE")
        if not self.pending:
            path = self.directory / f"batch-{self.index // 5:04d}.json"
            if path.exists():
                record = json.loads(path.read_text(encoding="utf-8"))
                if record["context_digest"] != digest:
                    raise PopulationError("CHECKPOINT_CONTEXT_MISMATCH")
                batch = FictionalDetailBatch.model_validate(record["output"])
                provenance = record["provenance"]
            else:
                messages = batch_messages(kwargs["messages"], self.index // 5)
                result = await self.adapter.generate_structured(
                    **{**kwargs, "output_schema": FictionalDetailBatch, "messages": messages})
                batch, provenance = result.value, result.provenance
                record = {"context_digest": digest, "output": batch.model_dump(mode="json"),
                          "provenance": provenance}
                # Exclusive creation: never overwrite an already frozen chunk.
                with path.open("x", encoding="utf-8") as stream:
                    json.dump(record, stream, sort_keys=True)
                    stream.flush()
                    import os
                    os.fsync(stream.fileno())
            self.pending = [(detail, {**provenance, "batch_record_index": i,
                                      "batch_checkpoint": path.name})
                            for i, detail in enumerate(batch.details)]
            self.pending_digest = digest
        detail, provenance = self.pending.pop(0)
        self.index += 1
        return InferenceResult(value=detail, provenance=provenance)

    def assert_complete(self):
        if self.pending:
            raise PopulationError("UNCONSUMED_GENERATION_BATCH")
