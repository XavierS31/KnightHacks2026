"""Generic selected-prototype regression boundaries and fail-closed default."""
from uuid import uuid4

import pytest

from backend.app.features.evolution import qa
from backend.app.features.evolution.boundary import BoundaryDrift, frozen_v1_sources
from backend.app.features.evolution.models import BaseVersion, CheckResult, IsolatedPatch, PatchFile
from backend.tests.prototype_fixtures import SOURCES, handoff


def test_no_selected_prototype_cannot_activate_ignored_runtime(tmp_path):
    (tmp_path/'integration-product-runtime.json').write_text('{"image_id":"old"}')
    with pytest.raises(qa.QaUnavailable, match='No selected'):
        qa.frozen_image_id(tmp_path)
    with pytest.raises(BoundaryDrift):
        frozen_v1_sources()


async def test_default_qa_is_unavailable_before_any_execution():
    with pytest.raises(qa.QaUnavailable):
        await qa.run_regression(None, None, 'unused')


async def test_generic_runner_gets_isolated_patch_and_fixed_catalog(monkeypatch):
    catalog = handoff()
    monkeypatch.setattr(qa, 'load_handoff', lambda: catalog)
    monkeypatch.setattr(qa, 'frozen_v1_sources', lambda: dict(SOURCES))
    base = BaseVersion(version_id=catalog.version.id, label=catalog.version.label,
        fixed_check_ids=[c.id for c in catalog.checks], fixed_checks_sha256=qa.fixed_checks_digest([c.model_dump(mode='json') for c in catalog.checks]))
    patch = IsolatedPatch(sha256='a'*64, files=[PatchFile(path='product/ui/app.js', content='let modified=1;')])
    seen=[]
    async def runner(workspace, checks, image):
        assert (workspace/'app.js').read_text() == 'let modified=1;'
        assert checks == catalog.checks
        seen.append(workspace)
        return [CheckResult(check_id='normal-v1', passed=True, evidence='Synthetic runner fixture')]
    assert (await qa.run_regression(base, patch, catalog.image_id, runner=runner))[0].passed
    assert not seen[0].exists() and SOURCES['product/ui/app.js'].startswith("'use strict'")
    base.version_id=uuid4()
    with pytest.raises(qa.QaUnavailable):
        await qa.run_regression(base, patch, catalog.image_id, runner=runner)
