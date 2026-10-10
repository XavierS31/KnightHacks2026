"""A's immutable version repository, consuming C's existing table/pool contract."""
import argparse
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.features.integration.product.handoff import ProductHandoff, verified_handoff
from backend.app.shared.database import DatabaseUnavailable, NeonDatabase
from backend.app.shared.settings import Settings


class VersionConflict(ValueError):
    pass


class VersionRecordInvalid(ValueError):
    pass


class VersionRepository:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _timeouts(cursor):
        cursor.execute("SET LOCAL statement_timeout = '5s'")
        cursor.execute("SET LOCAL lock_timeout = '2s'")

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

    def save(self, handoff: ProductHandoff):
        version = handoff.version
        if (handoff.mode != 'live' or version.status != 'validated'
                or not version.capabilities or any(not item.validated for item in version.capabilities)):
            raise VersionRecordInvalid('Only a validated live handoff may enter this repository.')
        data = handoff.model_dump(mode='json')
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                self._timeouts(cursor)
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
        return version.id

    def get(self, identity: UUID):
        with self.database.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                self._timeouts(cursor)
                cursor.execute("SELECT id,label,status,commit_sha,runtime_url,manifest,fixture "
                               "FROM product_versions WHERE id=%s", (identity,))
                return self._read(cursor.fetchone())


def main():
    parser = argparse.ArgumentParser(description='Save/read the frozen A handoff through C’s existing schema.')
    parser.add_argument('--live', action='store_true', help='Explicitly opt in to a configured, migrated Neon database.')
    arguments = parser.parse_args()
    settings = Settings()
    if not arguments.live or settings.app_mode != 'live' or not settings.database_url.get_secret_value():
        raise SystemExit('Requires --live, APP_MODE=live and C’s configured/migrated DATABASE_URL. No database request made.')
    handoff = verified_handoff(settings.artifact_root)
    database = NeonDatabase(settings)
    try:
        repository = VersionRepository(database)
        identity = repository.save(handoff)
        observed = repository.get(identity)
        assert observed is not None and observed.model_dump(mode='json') == handoff.model_dump(mode='json')
        print('Validated version manifest persisted and read back with exact equality.')
    except (DatabaseUnavailable, VersionConflict, VersionRecordInvalid):
        raise SystemExit('Version persistence did not complete; check C’s configuration/schema and immutable version state.') from None
    finally:
        database.close()


if __name__ == '__main__':
    main()
