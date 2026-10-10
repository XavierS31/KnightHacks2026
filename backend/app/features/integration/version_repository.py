"""A's immutable version repository, consuming C's existing table/pool contract.

A saved version also writes its catalog: initial states, fixed checks and pins (source commits,
implementation fingerprints and runtime image). Migration 004 freezes non-draft versions and
their catalog rows, so a frozen identity cannot be rewritten even outside this repository.
"""
import argparse
from uuid import UUID

from psycopg.errors import RestrictViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.features.integration.product.handoff import ProductHandoff, verified_handoff
from backend.app.shared.database import DatabaseUnavailable, NeonDatabase, bound_transaction
from backend.app.shared.settings import Settings


class VersionConflict(ValueError):
    pass


class VersionRecordInvalid(ValueError):
    pass


class _RewriteAccepted(Exception):
    """Raised inside a savepoint so an unexpected rewrite rolls back."""


def catalog(handoff: ProductHandoff) -> dict:
    """The rows that the manifest implies, keyed by their primary keys."""
    pins = {('source_commit', name): commit for name, commit in handoff.source_commits.items()}
    pins |= {('implementation_sha256', path): digest
             for path, digest in handoff.implementation_hashes.items()}
    pins[('image_id', 'runtime')] = handoff.image_id
    return {
        'initial_states': dict(handoff.initial_states),
        'checks': {check.id: (check.initial_state, check.model_dump(mode='json'))
                   for check in handoff.checks},
        'pins': pins,
    }


class VersionRepository:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _read(row):
        if row is None:
            return None
        try:
            handoff = ProductHandoff.model_validate(row['manifest'])
            version = handoff.version
            if (row['fixture'] is not False or handoff.mode != 'live'
                    or version.status != 'validated' or not version.capabilities
                    or any(not capability.validated for capability in version.capabilities)
                    or str(row['id']) != str(version.id)
                    or any(row[field] != getattr(version, field)
                           for field in ['label', 'status', 'commit_sha', 'runtime_url'])):
                raise ValueError('Record disagreement')
            return handoff
        except (ValueError, TypeError, KeyError):
            raise VersionRecordInvalid('Stored version does not match its validated manifest.') from None

    @staticmethod
    def _stored_catalog(cursor, identity):
        cursor.execute("SELECT state_id, state FROM product_version_initial_states "
                       "WHERE product_version_id=%s", (identity,))
        initial_states = {row['state_id']: row['state'] for row in cursor.fetchall()}
        cursor.execute("SELECT check_id, initial_state_id, definition FROM product_version_checks "
                       "WHERE product_version_id=%s", (identity,))
        checks = {row['check_id']: (row['initial_state_id'], row['definition'])
                  for row in cursor.fetchall()}
        cursor.execute("SELECT kind, name, digest FROM product_version_pins "
                       "WHERE product_version_id=%s", (identity,))
        pins = {(row['kind'], row['name']): row['digest'] for row in cursor.fetchall()}
        return {'initial_states': initial_states, 'checks': checks, 'pins': pins}

    def save(self, handoff: ProductHandoff):
        version = handoff.version
        if (handoff.mode != 'live' or version.status != 'validated'
                or not version.capabilities or any(not item.validated for item in version.capabilities)):
            raise VersionRecordInvalid('Only a validated live handoff may enter this repository.')
        data = handoff.model_dump(mode='json')
        expected = catalog(handoff)
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "INSERT INTO product_versions (id,label,status,commit_sha,runtime_url,manifest,fixture) "
                    "VALUES (%s,%s,%s,%s,%s,%s,false) ON CONFLICT (id) DO NOTHING",
                    (version.id, version.label, version.status, version.commit_sha,
                     version.runtime_url, Jsonb(data)),
                )
                cursor.execute("SELECT id,label,status,commit_sha,runtime_url,manifest,fixture "
                               "FROM product_versions WHERE id=%s FOR SHARE", (version.id,))
                existing = self._read(cursor.fetchone())
                if existing is None or existing.model_dump(mode='json') != data:
                    raise VersionConflict('Version identity already holds a different manifest; no rewrite occurred.')
                # Inserts are idempotent, so a retry also completes a catalog that is missing rows.
                cursor.executemany(
                    "INSERT INTO product_version_initial_states (product_version_id,state_id,state) "
                    "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(version.id, state_id, Jsonb(state))
                     for state_id, state in expected['initial_states'].items()])
                cursor.executemany(
                    "INSERT INTO product_version_checks (product_version_id,check_id,initial_state_id,definition) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(version.id, check_id, state_id, Jsonb(definition))
                     for check_id, (state_id, definition) in expected['checks'].items()])
                cursor.executemany(
                    "INSERT INTO product_version_pins (product_version_id,kind,name,digest) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    [(version.id, kind, name, digest) for (kind, name), digest in expected['pins'].items()])
                if self._stored_catalog(cursor, version.id) != expected:
                    raise VersionConflict('Version catalog already holds different rows; no rewrite occurred.')
        return version.id

    def get(self, identity: UUID):
        with self.database.connection() as connection:
            bound_transaction(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT id,label,status,commit_sha,runtime_url,manifest,fixture "
                               "FROM product_versions WHERE id=%s", (identity,))
                handoff = self._read(cursor.fetchone())
                if handoff is None:
                    return None
                if self._stored_catalog(cursor, identity) != catalog(handoff):
                    raise VersionRecordInvalid('Stored version catalog does not match its manifest.')
                return handoff


def rewrite_rejected(database, identity: UUID) -> bool:
    """Try to rewrite a stored version and one catalog row. True when the database refuses both.

    Each attempt runs in a savepoint that always rolls back, so this check never changes data.
    """
    attempts = ["UPDATE product_versions SET label = label || ' (rewrite)' WHERE id = %s",
                "UPDATE product_version_checks SET definition = '{}' WHERE product_version_id = %s"]
    with database.connection() as connection:
        bound_transaction(connection)
        for statement in attempts:
            try:
                with connection.transaction():
                    if connection.execute(statement, (identity,)).rowcount == 0:
                        return False
                    raise _RewriteAccepted
            except RestrictViolation:
                continue
            except _RewriteAccepted:
                return False
    return True


def main():
    parser = argparse.ArgumentParser(description='Save/read the frozen A handoff through C’s existing schema.')
    parser.add_argument('--live', action='store_true', help='Explicitly opt in to a configured, migrated Neon database.')
    arguments = parser.parse_args()
    settings = Settings()
    if not arguments.live or settings.app_mode != 'live' or not settings.database_url.get_secret_value():
        raise SystemExit('Requires --live, APP_MODE=live and C’s configured/migrated DATABASE_URL. No database request made.')
    from backend.app.features.integration.product.executor import ExecutionError
    try:
        handoff = verified_handoff(settings.artifact_root)
    except ExecutionError:
        raise SystemExit('The local image ID or implementation fingerprints differ from the frozen v1 manifest. '
                         'No database request made.') from None
    database = NeonDatabase(settings)
    try:
        repository = VersionRepository(database)
        identity = repository.save(handoff)
        observed = repository.get(identity)
        if observed is None or observed.model_dump(mode='json') != handoff.model_dump(mode='json'):
            raise SystemExit('Stored version did not read back with exact equality.')
        if not rewrite_rejected(database, identity):
            raise SystemExit('The database accepted a rewrite of the frozen version; apply migration 004.')
        stored = catalog(observed)
        print('Validated version manifest persisted and read back with exact equality.')
        print(f"Catalog: {len(stored['initial_states'])} initial state(s), {len(stored['checks'])} "
              f"check(s), {len(stored['pins'])} pin(s).")
        print('The database refused a rewrite of the frozen version and its catalog.')
    except (DatabaseUnavailable, VersionConflict, VersionRecordInvalid):
        raise SystemExit('Version persistence did not complete; check C’s configuration/schema and immutable version state.') from None
    finally:
        database.close()


if __name__ == '__main__':
    main()
