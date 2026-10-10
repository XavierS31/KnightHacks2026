"""Synthetic contracts for generic handoff/lifecycle tests; never activated by the app."""
import hashlib
from uuid import uuid5

from backend.app.features.evolution.models import BoundedEdit
from backend.app.features.integration.handoff import FixedCheck, ProductHandoff
from backend.app.shared.contracts import Contract
from backend.app.shared.fixtures import VERSION

SOURCES = {'product/ui/app.js': "'use strict';\nlet status='idle';\nlet count=0;\nlet label='Run';\n", 'product/ui/index.html': '<p>Synthetic test</p>', 'product/ui/style.css': 'p{color:black}'}


def handoff():
    capability = VERSION.capabilities[0].model_copy(update={'validated': True})
    return ProductHandoff(version=VERSION.model_copy(update={'label': 'Synthetic prototype v1', 'status': 'validated', 'capabilities': [capability], 'commit_sha': 'a'*40, 'runtime_url': 'http://127.0.0.1:8999'}),
        source_commits={'fixture/engine': 'a'*40}, image_id='sha256:'+'a'*64,
        implementation_hashes={path: hashlib.sha256(text.encode()).hexdigest() for path, text in SOURCES.items()},
        checks=[FixedCheck(id='normal-v1', goal='Run synthetic input', initial_state='synthetic-input', expected={'value': 'ok'}, action_budget=5)],
        initial_states={'synthetic-input': {'value':'test'}}, validation={'synthetic_test': True}, limitations=['Synthetic test contract; not live runtime proof.'])


class TestImprovement(Contract):
    __test__ = False
    key: str
    title: str
    problem: str
    change: str
    acceptance_check: str
    allowed_paths: list[str]
    edits: list[BoundedEdit]


def improvement(key, find, replace):
    return TestImprovement(key=key, title='Synthetic '+key, problem='Synthetic UI condition', change='Change one test literal', acceptance_check='Known test literal changes', allowed_paths=['product/ui/app.js'], edits=[BoundedEdit(path='product/ui/app.js', find=find, replace=replace)])


STALE_STATUS = improvement('status', "status='idle'", "status='changed'")
FIRST_ERROR = improvement('count', 'count=0', 'count=1')
BUSY_BUTTON = improvement('label', "label='Run'", "label='Working'")
BOUNDED_IMPROVEMENTS = [STALE_STATUS, FIRST_ERROR, BUSY_BUTTON]


def quota():
    from backend.app.features.personas.population import CoverageQuota
    task_id = uuid5(handoff().version.id, 'mandatory-task:normal-v1')
    return CoverageQuota(cohort='staff', count=500, active_role='Synthetic tester', location_id='office', device='laptop', task_template_id=task_id, assumption='Synthetic test coverage only')
