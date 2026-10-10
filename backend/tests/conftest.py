import os
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr

from backend.app.shared.database import NeonDatabase
from backend.app.shared.settings import Settings

# A disposable TLS PostgreSQL URL. Each test uses its own schema and drops it afterwards.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


@pytest.fixture
def isolated():
    if not TEST_DATABASE_URL:
        pytest.skip("Set TEST_DATABASE_URL")
    schema = f"gate_{uuid4().hex}"
    with psycopg.connect(TEST_DATABASE_URL, sslmode="require", autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
        separator = "&" if "?" in TEST_DATABASE_URL else "?"
        url = f"{TEST_DATABASE_URL}{separator}options=-csearch_path%3D{schema}"
        settings = Settings(_env_file=None, app_mode="live", database_url=SecretStr(url))
        database = NeonDatabase(settings)
        try:
            yield settings, database
        finally:
            database.close()
            admin.execute(f"DROP SCHEMA {schema} CASCADE")
