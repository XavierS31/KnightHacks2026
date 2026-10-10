"""A-only conservative reservations; not provider-reported billing or B's budget."""
import json
import os

from backend.app.shared.inference import InferenceError
from backend.app.shared.settings import Settings

# At verified priority rates ($0.12/$0.42 per million tokens), even two attempts
# with <=20 KB prompt/schema bytes and 1,024 output tokens fit below this reserve.
# Failed/timed-out requests consume their full reservation. Never refund unknown use.
RESERVATION_CENTS = 2
MAX_CALLS = 100
MAX_REQUEST_BYTES = 20_000
PRICE_REFERENCE = "https://deepinfra.com/Qwen/Qwen3-32B"


class IntegrationBudget:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.artifact_root / "integration-hf-budget.json"

    def reserve(self, messages, schema):
        if self.settings.app_mode != "live":
            raise InferenceError("FIXTURE_INFERENCE_FORBIDDEN")
        if self.settings.experiment_budget_limit <= 0:
            raise InferenceError("BUDGET_NOT_APPROVED")
        if (self.settings.hf_model_id, self.settings.hf_provider) != ("Qwen/Qwen3-32B", "deepinfra"):
            raise InferenceError("INTEGRATION_PRICING_UNVERIFIED")
        payload = json.dumps({"messages": messages, "schema": schema}, ensure_ascii=False).encode()
        if len(payload) > MAX_REQUEST_BYTES:
            raise InferenceError("INTEGRATION_PROMPT_TOO_LARGE")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise InferenceError("INTEGRATION_BUDGET_BUSY") from None
        try:
            os.close(descriptor)
            ledger = {"calls": 0, "reserved_cents": 0, "price_reference": PRICE_REFERENCE}
            if self.path.exists():
                ledger = json.loads(self.path.read_text())
            if (not isinstance(ledger, dict)
                    or type(ledger.get("calls")) is not int or type(ledger.get("reserved_cents")) is not int
                    or ledger["calls"] < 0 or ledger["reserved_cents"] < 0
                    or ledger["reserved_cents"] != ledger["calls"] * RESERVATION_CENTS):
                raise InferenceError("INTEGRATION_BUDGET_INVALID")
            limit = min(200, int(self.settings.experiment_budget_limit * 100))
            if ledger["calls"] >= MAX_CALLS or ledger["reserved_cents"] + RESERVATION_CENTS > limit:
                raise InferenceError("INTEGRATION_BUDGET_EXHAUSTED")
            ledger["calls"] += 1
            ledger["reserved_cents"] += RESERVATION_CENTS
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(ledger, indent=2) + "\n")
            temporary.chmod(0o600)
            temporary.replace(self.path)
            return ledger.copy()
        except (ValueError, TypeError, KeyError) as exc:
            raise InferenceError("INTEGRATION_BUDGET_INVALID") from exc
        finally:
            lock.unlink()
