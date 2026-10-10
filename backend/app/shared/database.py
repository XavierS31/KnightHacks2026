"""Lazy, server-only Neon boundary. Importing it never creates a connection."""

from contextlib import contextmanager
from threading import Lock
from typing import Any, Callable, Iterator

from psycopg import Error as PostgresError
from psycopg_pool import ConnectionPool, PoolTimeout

from backend.app.shared.settings import Settings, get_settings


class DatabaseUnavailable(RuntimeError):
    """A sanitized availability/configuration error safe for application reporting."""


class NeonDatabase:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        pool_factory: Callable[..., Any] = ConnectionPool,
    ) -> None:
        self._settings = settings if settings is not None else get_settings()
        self._pool_factory = pool_factory
        self._pool: Any = None
        self._lock = Lock()

    def _get_pool(self) -> Any:
        if self._settings.app_mode != "live":
            raise DatabaseUnavailable("Persistent database access is disabled in fixture mode.")
        secret = self._settings.database_url.get_secret_value()
        if not secret:
            raise DatabaseUnavailable("DATABASE_URL is required for persistent database access.")
        with self._lock:
            if self._pool is not None:
                return self._pool
            candidate = None
            try:
                candidate = self._pool_factory(
                    conninfo=secret,
                    name="repofusion-neon",
                    min_size=1,
                    max_size=4,
                    timeout=5,
                    kwargs={"sslmode": "require", "connect_timeout": 5},
                    open=False,
                )
                candidate.open(wait=True, timeout=5)
            except Exception:
                if candidate is not None:
                    try:
                        candidate.close()
                    except Exception:
                        pass
                raise DatabaseUnavailable("Persistent database connection could not be established.") from None
            self._pool = candidate
            return candidate

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """Commit successful scopes, roll back exceptions, and return the connection to the pool."""
        pool = self._get_pool()
        try:
            with pool.connection(timeout=5) as connection:
                yield connection
        except (PostgresError, PoolTimeout):
            raise DatabaseUnavailable("Persistent database operation failed.") from None

    def close(self) -> None:
        with self._lock:
            if self._pool is not None:
                pool, self._pool = self._pool, None
                pool.close()
