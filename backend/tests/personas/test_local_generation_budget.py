from decimal import Decimal

import pytest

from backend.app.features.personas.local_generation_budget import LocalGenerationBudget
from backend.app.shared.inference import InferenceError


def ledger(path, limit="1"):
    return LocalGenerationBudget(path, "test-only", Decimal(limit), approval_reference="test")


async def test_restart_retains_unknown_send_and_settled_charge(tmp_path):
    first = ledger(tmp_path)
    await first.reserve(Decimal("0.7"), mandatory=True, policy_id="fake")
    first.close()
    second = ledger(tmp_path)
    assert (await second.snapshot())["charged_dollars"] == "0.7"
    with pytest.raises(InferenceError, match="EXHAUSTED"):
        await second.reserve(Decimal("0.4"), mandatory=True, policy_id="fake")
    key = await second.reserve(Decimal("0.2"), mandatory=True, policy_id="fake")
    await second.settle(key, Decimal("0.1"), status="reported")
    second.close()
    third = ledger(tmp_path)
    assert (await third.snapshot())["charged_dollars"] == "0.8"
    third.close()


def test_exclusive_lock_and_configuration_cannot_reset_spending(tmp_path):
    first = ledger(tmp_path)
    with pytest.raises(FileExistsError):
        ledger(tmp_path)
    first.close()


async def test_changed_limit_rejected_after_journal_written(tmp_path):
    first = ledger(tmp_path)
    await first.reserve(Decimal("0.1"), mandatory=True, policy_id="fake")
    first.close()
    with pytest.raises(ValueError, match="CONFIGURATION_MISMATCH"):
        ledger(tmp_path, "2")
    assert not (tmp_path / "paid-run.lock").exists()
