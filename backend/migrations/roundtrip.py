"""Neon write/read/rollback gate. Proves durable persistence through NeonDatabase."""
import argparse
from uuid import UUID, uuid4

from psycopg.conninfo import conninfo_to_dict

from backend.app.shared.database import DatabaseUnavailable, NeonDatabase
from backend.app.shared.settings import Settings
from backend.migrations.runner import discover, recorded


class RoundTripFailed(RuntimeError):
    pass


class _AbortProbe(Exception):
    """Raised inside a connection scope so NeonDatabase rolls the probe write back."""


def write(database, identity: UUID, label: str) -> None:
    with database.connection() as connection:
        connection.execute("INSERT INTO persistence_checks (id, label) VALUES (%s, %s)",
                           (identity, label))


def read(database, identity: UUID):
    with database.connection() as connection:
        return connection.execute("SELECT id, label, created_at FROM persistence_checks "
                                  "WHERE id = %s", (identity,)).fetchone()


def write_then_abort(database, identity: UUID, label: str) -> None:
    try:
        with database.connection() as connection:
            connection.execute("INSERT INTO persistence_checks (id, label) VALUES (%s, %s)",
                               (identity, label))
            if connection.execute("SELECT 1 FROM persistence_checks WHERE id = %s",
                                  (identity,)).fetchone() is None:
                raise RoundTripFailed("Uncommitted probe write was not visible to its transaction.")
            raise _AbortProbe
    except _AbortProbe:
        pass


def run(settings: Settings) -> dict:
    """Write with one pool, read with a fresh pool, then prove an aborted write is absent."""
    migrations = [(item.version, item.checksum) for item in discover()]
    durable, rollback = uuid4(), uuid4()
    writer = NeonDatabase(settings)
    try:
        if recorded(writer) != migrations:
            raise RoundTripFailed("Database migrations are not current; run backend.migrations.runner.")
        write(writer, durable, "durable write/read gate")
    finally:
        writer.close()
    reader = NeonDatabase(settings)
    try:
        row = read(reader, durable)
        if row is None or row[0] != durable:
            raise RoundTripFailed("Committed probe row was not read back through a new pool.")
        write_then_abort(reader, rollback, "rollback gate")
        if read(reader, rollback) is not None:
            raise RoundTripFailed("Rolled-back probe row persisted.")
        with reader.connection() as connection:
            server = connection.execute("SELECT current_setting('server_version'), "
                                        "current_database()").fetchone()
    finally:
        reader.close()
    host = conninfo_to_dict(settings.database_url.get_secret_value()).get("host", "")
    return {"durable_id": durable, "created_at": row[2], "rollback_id": rollback,
            "server_version": server[0], "database": server[1],
            "neon_host": host.endswith(".neon.tech"), "migrations": migrations}


def main():
    parser = argparse.ArgumentParser(description="Prove Neon write/read/rollback through NeonDatabase.")
    parser.add_argument("--live", action="store_true",
                        help="Explicitly opt in to write one probe row to DATABASE_URL.")
    arguments = parser.parse_args()
    settings = Settings()
    if not arguments.live or settings.app_mode != "live" or not settings.database_url.get_secret_value():
        raise SystemExit("Requires --live, APP_MODE=live and DATABASE_URL. No database request made.")
    try:
        evidence = run(settings)
    except (DatabaseUnavailable, RoundTripFailed) as error:
        raise SystemExit(f"Round trip did not complete: {error}") from None
    print(f"Neon host: {'yes' if evidence['neon_host'] else 'no'}; "
          f"PostgreSQL {evidence['server_version']}; database {evidence['database']}")
    for version, checksum in evidence["migrations"]:
        print(f"recorded {version} sha256={checksum}")
    print(f"Durable write {evidence['durable_id']} at {evidence['created_at'].isoformat()} "
          "read back through a new pool.")
    print(f"Rollback probe {evidence['rollback_id']} was visible in its transaction and absent after.")


if __name__ == "__main__":
    main()
