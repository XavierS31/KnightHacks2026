"""Bounded local observations. Attention is not demand; fixtures never enter history."""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from backend.app.shared.contracts import Contract


class Observation(Contract):
    full_name: str
    observed_at: datetime
    stars: int = Field(ge=0)
    forks: int | None = Field(default=None, ge=0)
    source_reference: str | None = Field(default=None, max_length=1000)

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value):
        if value.utcoffset() is None:
            raise ValueError("An observation needs a timezone")
        return value


class MomentumSignal(Contract):
    current: Observation
    baseline: Observation | None = None
    status: Literal["measured", "insufficient_history", "history_unavailable", "fixture"]
    stars_delta: int | None = None
    forks_delta: int | None = None
    elapsed_hours: float | None = None
    note: str


def signal(current, history, status="insufficient_history"):
    eligible = [item for item in history if item.full_name.lower() == current.full_name.lower()
                and timedelta(minutes=1) <= current.observed_at - item.observed_at <= timedelta(days=30)]
    if not eligible:
        return MomentumSignal(current=current, status=status,
                              note="No comparable observation at least one minute earlier within 30 days. Growth is unknown.")
    baseline = min(eligible, key=lambda item: item.observed_at)
    return MomentumSignal(current=current, baseline=baseline, status="measured",
                          stars_delta=current.stars - baseline.stars,
                          forks_delta=(current.forks - baseline.forks
                                       if current.forks is not None and baseline.forks is not None else None),
                          elapsed_hours=(current.observed_at - baseline.observed_at).total_seconds() / 3600,
                          note="Net count change over the displayed interval, not new-star events, adoption or demand.")


class MomentumHistory:
    """Atomic, lock-protected A-owned fallback; C's Neon schema is not changed."""

    def __init__(self, root: Path):
        self.path = root / "integration-momentum.json"

    def observe(self, observations: list[Observation]) -> list[MomentumSignal]:
        lock = self.path.with_suffix(".lock")
        descriptor = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            history = []
            if self.path.exists():
                if self.path.stat().st_size > 1_000_000:
                    raise ValueError("Oversized history")
                payload = json.loads(self.path.read_text())
                if not isinstance(payload, list) or len(payload) > 800:
                    raise ValueError("Invalid history")
                history = [Observation.model_validate(item) for item in payload]
            results = [signal(current, history) for current in observations]
            # Exact cached timestamps never become another measurement.
            for current in observations:
                if not any(item.full_name.lower() == current.full_name.lower()
                           and item.observed_at == current.observed_at for item in history):
                    history.append(current)
            history.sort(key=lambda item: item.observed_at, reverse=True)
            retained, counts = [], {}
            for item in history:
                name = item.full_name.lower()
                if name not in counts and len(counts) >= 100:
                    continue
                if counts.get(name, 0) < 8:
                    retained.append(item)
                    counts[name] = counts.get(name, 0) + 1
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps([item.model_dump(mode="json") for item in retained]))
            temporary.chmod(0o600)
            temporary.replace(self.path)
            return results
        except (OSError, ValueError, TypeError):
            return [MomentumSignal(current=item, status="history_unavailable",
                                   note="Local history is busy, unavailable or invalid. No growth claim was made.")
                    for item in observations]
        finally:
            if descriptor is not None:
                os.close(descriptor)
                try:
                    lock.unlink(missing_ok=True)
                except OSError:
                    pass
