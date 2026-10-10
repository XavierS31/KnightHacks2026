from unittest.mock import MagicMock

import pytest
from psycopg import OperationalError
from pydantic import SecretStr

from backend.app.shared.database import DatabaseUnavailable, NeonDatabase
from backend.app.shared.settings import Settings


def settings(mode="live", url="postgresql://fixture:secret@invalid/test"):
    return Settings(_env_file=None, app_mode=mode, database_url=SecretStr(url))


def test_import_and_construction_are_lazy_and_fixture_mode_never_opens():
    factory = MagicMock()
    database = NeonDatabase(settings("fixture"), pool_factory=factory)
    factory.assert_not_called()
    with pytest.raises(DatabaseUnavailable, match="fixture mode"):
        with database.connection():
            pass
    factory.assert_not_called()


def test_missing_credentials_fail_without_pool():
    factory = MagicMock()
    with pytest.raises(DatabaseUnavailable, match="DATABASE_URL"):
        with NeonDatabase(settings(url=""), pool_factory=factory).connection():
            pass
    factory.assert_not_called()


def test_lazy_pool_is_reused_and_closed():
    pool = MagicMock()
    factory = MagicMock(return_value=pool)
    database = NeonDatabase(settings(), pool_factory=factory)
    with database.connection() as connection:
        assert connection is pool.connection.return_value.__enter__.return_value
    with database.connection():
        pass
    factory.assert_called_once()
    assert factory.call_args.kwargs["open"] is False
    assert factory.call_args.kwargs["kwargs"]["sslmode"] == "require"
    pool.open.assert_called_once_with(wait=True, timeout=5)
    database.close()
    pool.close.assert_called_once()


def test_external_errors_are_sanitized_and_failed_pool_is_closed():
    pool = MagicMock()
    pool.open.side_effect = RuntimeError("postgresql://fixture:secret@invalid/test")
    database = NeonDatabase(settings(), pool_factory=MagicMock(return_value=pool))
    with pytest.raises(DatabaseUnavailable) as error:
        with database.connection():
            pass
    assert "secret" not in str(error.value)
    pool.close.assert_called_once()


def test_transaction_context_receives_failure_for_rollback():
    pool = MagicMock()
    database = NeonDatabase(settings(), pool_factory=MagicMock(return_value=pool))
    with pytest.raises(ValueError, match="business failure"):
        with database.connection():
            raise ValueError("business failure")
    assert pool.connection.return_value.__exit__.call_args.args[0] is ValueError


def test_postgres_operation_error_is_sanitized():
    pool = MagicMock()
    pool.connection.return_value.__enter__.side_effect = OperationalError("secret connection text")
    with pytest.raises(DatabaseUnavailable) as error:
        with NeonDatabase(settings(), pool_factory=MagicMock(return_value=pool)).connection():
            pass
    assert "secret" not in str(error.value)
