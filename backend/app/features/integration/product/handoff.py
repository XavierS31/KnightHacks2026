"""Immutable A handoff; drift invalidates its validated status."""
import hashlib
import json
from pathlib import Path

from pydantic import Field

from backend.app.features.integration.product.models import TableInput, TableOutput
from backend.app.shared.contracts import Contract, ProductVersion

ROOT = Path(__file__).resolve().parents[5]
MANIFEST = Path(__file__).parent / 'v1/manifest.json'


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


class ProductReadiness(Contract):
    status: str
    runtime_url: str = 'http://127.0.0.1:8001'
    version: ProductVersion | None = None
    message: str


def verified_handoff(artifact_root: Path):
    from backend.app.features.integration.product.executor import ExecutionError
    try:
        handoff = ProductHandoff.model_validate_json(MANIFEST.read_text())
        from backend.app.features.integration.product.freeze import implementation_hashes
        if handoff.implementation_hashes != implementation_hashes():
            raise ValueError('Implementation set drift')
        runtime = json.loads((artifact_root / 'integration-product-runtime.json').read_text())
        if runtime['image_id'] != handoff.image_id:
            raise ValueError('Image drift')
        for path, digest in handoff.implementation_hashes.items():
            if '..' in Path(path).parts or not path.startswith(('backend/app/features/integration/',
                                                              'frontend/src/features/integration/')):
                raise ValueError('Unsupported path')
            if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
                raise ValueError('Implementation drift')
        return handoff
    except (OSError, ValueError, KeyError, TypeError):
        raise ExecutionError('VERSION_NOT_VALIDATED') from None


def readiness(artifact_root: Path):
    from backend.app.features.integration.product.executor import ExecutionError
    try:
        handoff = verified_handoff(artifact_root)
        return ProductReadiness(status='validated_on_fixed_checks', version=handoff.version,
                                message='Configured image ID and source fingerprints match the validated manifest. Start the separate product process; this does not probe process availability.')
    except ExecutionError:
        return ProductReadiness(status='not_validated_here',
                                message='Build the pinned image and run the product validation/freeze command. A different checkout/image cannot inherit this machine’s validation.')


INPUT_SCHEMA = TableInput.model_json_schema()
OUTPUT_SCHEMA = TableOutput.model_json_schema()
