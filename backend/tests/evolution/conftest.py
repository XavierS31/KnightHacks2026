from uuid import uuid4

import pytest

from backend.migrations.runner import apply, discover


@pytest.fixture
def migrated(isolated):
    """A fully migrated schema with one product version and one running experiment."""
    settings, database = isolated
    apply(database, discover())
    version_id, experiment_id = uuid4(), uuid4()
    with database.connection() as connection:
        connection.execute("INSERT INTO product_versions (id, label, status, manifest) "
                           "VALUES (%s, 'v1', 'validated', '{}')", (version_id,))
        connection.execute("INSERT INTO experiments (id, population_id, product_version_id, "
                           "task_set_id, configuration, status) "
                           "VALUES (%s, %s, %s, %s, '{}', 'running')",
                           (experiment_id, uuid4(), version_id, uuid4()))
    return {"settings": settings, "database": database,
            "version_id": version_id, "experiment_id": experiment_id}
