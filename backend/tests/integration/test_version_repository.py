import json
from contextlib import contextmanager
from copy import deepcopy
from uuid import uuid4

import pytest

from backend.app.features.integration.product.handoff import MANIFEST, ProductHandoff
from backend.app.features.integration.version_repository import (
    VersionConflict,
    VersionRecordInvalid,
    VersionRepository,
)


def frozen():
    return ProductHandoff.model_validate_json(MANIFEST.read_text())


def row(handoff):
    version = handoff.version
    return {**{field: getattr(version, field) for field in ['id', 'label', 'status', 'commit_sha', 'runtime_url']},
            'manifest': handoff.model_dump(mode='json'), 'fixture': False}


class Database:
    def __init__(self, record=None):
        self.record = record
        self.calls = []
        self.failed = False
    @contextmanager
    def connection(self):
        try:
            yield self
        except Exception:
            self.failed = True
            raise
    @contextmanager
    def cursor(self, **kwargs):
        yield self
    def execute(self, query, params=None):
        self.calls.append((query, params))
        if query.startswith('INSERT') and self.record is None:
            self.record = {**dict(zip(['id', 'label', 'status', 'commit_sha', 'runtime_url'], params[:5], strict=True)),
                           'manifest': params[5].obj, 'fixture': False}
    def fetchone(self):
        return self.record


def test_save_is_parameterized_idempotent_and_roundtrips():
    handoff = frozen()
    database = Database()
    repository = VersionRepository(database)
    assert repository.save(handoff) == handoff.version.id
    assert repository.save(handoff) == handoff.version.id
    assert repository.get(handoff.version.id) == handoff
    query, params = next(call for call in database.calls if call[0].startswith('INSERT'))
    assert 'ON CONFLICT (id) DO NOTHING' in query and '%s' in query
    assert str(handoff.version.id) not in query
    assert params[5].obj == handoff.model_dump(mode='json')
    assert any('lock_timeout' in query for query, _ in database.calls)


def test_conflict_never_updates_and_exits_transaction_with_failure():
    handoff = frozen()
    original = row(handoff)
    changed = handoff.model_copy(deep=True)
    changed.limitations.append('Changed manifest')
    database = Database(deepcopy(original))
    with pytest.raises(VersionConflict):
        VersionRepository(database).save(changed)
    assert database.record == original and database.failed
    assert not any('UPDATE' in query for query, _ in database.calls)


@pytest.mark.parametrize('field,value', [('fixture', True), ('status', 'draft'),
                                        ('id', uuid4()), ('manifest', {'invalid': True})])
def test_inconsistent_stored_record_is_rejected(field, value):
    database = Database({**row(frozen()), field: value})
    with pytest.raises(VersionRecordInvalid):
        VersionRepository(database).get(frozen().version.id)


def test_fixture_or_unvalidated_capability_rejected_before_connection():
    handoff = frozen().model_copy(deep=True)
    handoff.version.capabilities[0].validated = False
    database = Database()
    with pytest.raises(VersionRecordInvalid):
        VersionRepository(database).save(handoff)
    assert database.calls == []


def test_unknown_version_and_poisoned_manifest():
    assert VersionRepository(Database()).get(uuid4()) is None
    record = row(frozen())
    record['manifest'] = json.loads(json.dumps(record['manifest']))
    record['manifest']['version']['label'] = "x'); DROP TABLE product_versions; --"
    with pytest.raises(VersionRecordInvalid):
        VersionRepository(Database(record)).get(frozen().version.id)
