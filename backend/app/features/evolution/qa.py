"""Generic isolated regression orchestration; selected prototypes supply a deterministic runner."""
import tempfile
from pathlib import Path

from backend.app.features.evolution.boundary import PRODUCT_BOUNDARY, frozen_v1_sources
from backend.app.features.evolution.lifecycle import fixed_checks_digest
from backend.app.features.evolution.models import CheckResult
from backend.app.features.integration.handoff import ExecutionError, load_handoff


class QaUnavailable(RuntimeError):
    pass


def frozen_image_id(artifact_root):
    # No ignored legacy runtime artifact can implicitly select or activate a prototype.
    raise QaUnavailable('No selected prototype runtime verifier is configured.')


def _fixed_checks(base):
    try:
        handoff = load_handoff()
    except ExecutionError:
        raise QaUnavailable('A validated prototype check catalog is required.') from None
    checks = handoff.checks
    if base.version_id != handoff.version.id or base.fixed_check_ids != [c.id for c in checks] or base.fixed_checks_sha256 != fixed_checks_digest([c.model_dump(mode='json') for c in checks]):
        raise QaUnavailable('The frozen catalog differs from the regression base.')
    return checks


def _materialize(patch, root):
    sources = frozen_v1_sources()
    if any(item.path not in PRODUCT_BOUNDARY for item in patch.files):
        raise QaUnavailable('Patch is outside the frozen prototype boundary.')
    for logical, text in {**sources, **{item.path: item.content for item in patch.files}}.items():
        target = root / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return root / 'product/ui'


async def run_regression(base, patch, image_id, *, runner=None):
    if runner is None:
        raise QaUnavailable('The selected prototype must register independent fixed procedures and an evaluator.')
    checks = _fixed_checks(base)
    with tempfile.TemporaryDirectory(prefix='repofusion-regression-') as directory:
        workspace = _materialize(patch, Path(directory))
        results = await runner(workspace, checks, image_id)
        validated = [CheckResult.model_validate(item) for item in results]
        if len(validated) != len(checks) or {r.check_id for r in validated} != {c.id for c in checks}:
            raise QaUnavailable('Runner returned an incomplete or mismatched fixed-check catalog.')
        return validated
