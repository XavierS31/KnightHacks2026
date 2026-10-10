"""Exclusive local paid-run journal; hosted/multiworker accounting remains C-owned.

Reservations reach disk before inference. Crash reservations remain charged on
recovery. A leftover lock requires operator reconciliation, never automatic reset.
"""
import json
import os
from decimal import Decimal
from pathlib import Path

from backend.app.features.personas.inference_budget import ExperimentBudget


class LocalGenerationBudget(ExperimentBudget):
    def __init__(self, directory: Path, experiment_id: str, limit: Decimal, *,
                 approval_reference: str):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "budget.json"
        self.lock_path = directory / "paid-run.lock"
        self.lock = self.lock_path.open("x", encoding="utf-8")
        try:
            super().__init__(experiment_id, limit, approval_reference=approval_reference)
            if self.path.exists():
                record = json.loads(self.path.read_text(encoding="utf-8"))
                if (record["experiment_id"] != experiment_id
                        or Decimal(record["limit_dollars"]) != limit
                        or record["approval_reference"] != approval_reference):
                    raise ValueError("LOCAL_BUDGET_CONFIGURATION_MISMATCH")
                self._blocked = record["blocked"]
                for entry in record["entries"]:
                    amount = Decimal(entry["reserved_dollars"])
                    charge = (amount if entry["status"] == "reserved"
                              else Decimal(entry["charged_dollars"]))
                    if not charge.is_finite() or charge < 0 or not amount.is_finite() or amount < 0:
                        raise ValueError("INVALID_LOCAL_BUDGET")
                    self._charged += charge
                    self._entries[entry["reservation_id"]] = {
                        "reserved_dollars": amount, "charged_dollars": charge,
                        "status": ("crash_reservation_retained" if entry["status"] == "reserved"
                                   else entry["status"]), "mandatory": entry["mandatory"],
                        "protected_dollars": Decimal(0), "policy_id": entry["policy_id"]}
                if self._charged > limit:
                    self._blocked = True
        except BaseException:
            self.close()
            raise

    async def _persist(self):
        record = await self.snapshot()
        record["storage"] = "exclusive_local_generation_journal_not_neon"
        temporary = self.path.with_suffix(".pending")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    async def reserve(self, amount, *, mandatory, policy_id):
        key = await super().reserve(amount, mandatory=mandatory, policy_id=policy_id)
        await self._persist()
        return key

    async def settle(self, reservation_id, charge, *, status):
        await super().settle(reservation_id, charge, status=status)
        await self._persist()

    def close(self):
        self.lock.close()
        self.lock_path.unlink(missing_ok=True)
