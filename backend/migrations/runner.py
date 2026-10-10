"""Ordered, checksummed migrations applied through C's NeonDatabase boundary."""
import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from psycopg import Error as PostgresError

from backend.app.shared.database import DatabaseUnavailable, NeonDatabase
from backend.app.shared.settings import Settings

DIRECTORY = Path(__file__).parent
FILE_NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
# Serializes concurrent runners for the duration of one migration transaction.
LOCK_KEY = 4_127_001
BOOTSTRAP = """CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)"""


class MigrationError(RuntimeError):
    """A sanitized ordering, checksum or execution failure. No migration was committed."""


@dataclass(frozen=True)
class Migration:
    version: str
    checksum: str
    sql: str


def discover(directory: Path = DIRECTORY) -> list[Migration]:
    """Return contiguous 001, 002, ... migrations with the SHA-256 of their exact bytes."""
    migrations = []
    for position, path in enumerate(sorted(directory.glob("*.sql")), start=1):
        match = FILE_NAME.match(path.name)
        if match is None:
            raise MigrationError(f"Migration file name is not NNN_name.sql: {path.name}")
        if int(match.group(1)) != position:
            raise MigrationError(f"Migration numbers must be contiguous from 001: {path.name}")
        content = path.read_bytes()
        migrations.append(Migration(path.stem, hashlib.sha256(content).hexdigest(),
                                    content.decode("utf-8")))
    return migrations


def recorded(database) -> list[tuple[str, str]]:
    """Return applied (version, checksum) pairs in order; empty before the first migration."""
    with database.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('schema_migrations') IS NOT NULL")
            if not cursor.fetchone()[0]:
                return []
            cursor.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
            return cursor.fetchall()


def apply(database, migrations: list[Migration]) -> list[str]:
    """Apply all pending migrations in one transaction and return their versions.

    Applied history must be an unchanged prefix of the files. Any mismatch or SQL failure
    rolls the whole transaction back, so a database is never left partly migrated.
    """
    with database.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '60s'")
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
            cursor.execute(BOOTSTRAP)
            cursor.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
            history = cursor.fetchall()
            expected = [(item.version, item.checksum) for item in migrations[:len(history)]]
            if history != expected:
                raise MigrationError("Applied migration history differs from the migration files; "
                                     "add a new numbered migration instead of editing an applied one.")
            pending = migrations[len(history):]
            for migration in pending:
                try:
                    cursor.execute(migration.sql)
                except PostgresError as error:
                    raise MigrationError(f"{migration.version} failed with SQLSTATE "
                                         f"{error.sqlstate}; nothing was committed.") from None
                cursor.execute("INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                               (migration.version, migration.checksum))
            return [migration.version for migration in pending]


def main():
    parser = argparse.ArgumentParser(description="List or apply ordered database migrations.")
    parser.add_argument("--live", action="store_true",
                        help="Explicitly opt in to apply pending migrations to DATABASE_URL.")
    arguments = parser.parse_args()
    migrations = discover()
    for migration in migrations:
        print(f"file {migration.version} sha256={migration.checksum}")
    if not arguments.live:
        print("No database request made. Add --live with APP_MODE=live to apply.")
        return
    settings = Settings()
    if settings.app_mode != "live" or not settings.database_url.get_secret_value():
        raise SystemExit("Requires APP_MODE=live and DATABASE_URL. No database request made.")
    database = NeonDatabase(settings)
    try:
        applied = apply(database, migrations)
        print(f"Applied now: {', '.join(applied) or 'none (already current)'}")
        for version, checksum in recorded(database):
            print(f"recorded {version} sha256={checksum}")
    except (DatabaseUnavailable, MigrationError) as error:
        raise SystemExit(f"Migration did not complete: {error}") from None
    finally:
        database.close()


if __name__ == "__main__":
    main()
