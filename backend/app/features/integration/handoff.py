"""Generic immutable prototype catalog. No prototype is selected by default."""
import hashlib
from pathlib import Path

from pydantic import Field

from backend.app.shared.contracts import Contract, ProductVersion

ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / 'product/manifest.json'

class ExecutionError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

class FixedCheck(Contract):
    id: str
    goal: str
    initial_state: str
    expected: dict
    action_budget: int = Field(ge=1, le=12)


class ProductHandoff(Contract):
    mode: str = 'live'
    version: ProductVersion
    source_commits: dict[str, str]
    image_id: str
    implementation_hashes: dict[str, str]
    checks: list[FixedCheck]
    initial_states: dict[str, dict]
    validation: dict
    limitations: list[str]



def load_handoff(path=MANIFEST):
    try:
        raw = path.read_bytes()
        if len(raw) > 1_000_000:
            raise ValueError('Oversized catalog')
        handoff = ProductHandoff.model_validate_json(raw)
        if (handoff.mode != 'live' or handoff.version.status != 'validated'
                or not handoff.checks or not handoff.implementation_hashes
                or not handoff.source_commits or not handoff.image_id
                or not handoff.version.capabilities or any(not c.validated for c in handoff.version.capabilities)
                or any(check.initial_state not in handoff.initial_states for check in handoff.checks)):
            raise ValueError('Incomplete catalog')
        return handoff
    except (OSError, ValueError, TypeError):
        raise ExecutionError('VALIDATED_PROTOTYPE_REQUIRED') from None


def implementation_hashes(handoff=None):
    handoff = handoff or load_handoff()
    result = {}
    for name in handoff.implementation_hashes:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or not name.startswith('product/') or (ROOT / path).is_symlink() or not (ROOT / path).resolve().is_relative_to((ROOT / "product").resolve()):
            raise ExecutionError('INVALID_PROTOTYPE_PATH')
        try:
            result[name] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        except OSError:
            raise ExecutionError('VERSION_NOT_VALIDATED') from None
    return result


def verified_handoff(artifact_root=None, *, path=MANIFEST):
    handoff = load_handoff(path)
    if implementation_hashes(handoff) != handoff.implementation_hashes:
        raise ExecutionError('VERSION_NOT_VALIDATED')
    # Runtime availability/execution must be established by the selected prototype's runner.
    return handoff
