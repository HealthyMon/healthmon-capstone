from contextlib import contextmanager
from pathlib import Path
import uuid
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = [(p.stem.split('_')[0], p) for p in sorted((ROOT / 'Ai/LLM/migrations').glob('*.sql'))]
MIGRATIONS += [(p.stem.split('_')[0], p) for p in sorted((ROOT / 'Server/migrations').glob('*.sql'))]


class Database:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def connect(self):
        with psycopg.connect(self.settings.database_url, row_factory=dict_row, connect_timeout=5) as c:
            c.execute("SET TIME ZONE 'UTC'")
            c.execute("SET statement_timeout='15s'")
            yield c

    def migrate(self):
        with self.connect() as c:
            c.execute('SELECT pg_advisory_xact_lock(74261022)')
            c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version text PRIMARY KEY,applied_at timestamptz NOT NULL DEFAULT now())')
            versions = {r['version'] for r in c.execute('SELECT version FROM schema_migrations')}
            for version, path in MIGRATIONS:
                if version not in versions:
                    c.execute(path.read_text(encoding='utf-8'))
                    c.execute('INSERT INTO schema_migrations(version) VALUES(%s) ON CONFLICT DO NOTHING', (version,))
            c.execute('INSERT INTO common_server_metadata(singleton,instance_id,environment) VALUES(true,%s,%s) ON CONFLICT DO NOTHING',
                      (self.settings.instance_id or str(uuid.uuid4()), self.settings.environment))
            self.ready(c)

    def ready(self, c=None):
        if c is None:
            with self.connect() as connection:
                return self.ready(connection)
        versions = {r['version'] for r in c.execute('SELECT version FROM schema_migrations')}
        if not {v for v, _ in MIGRATIONS}.issubset(versions):
            raise RuntimeError('Database migrations incomplete')
        if not c.execute("SELECT 1 FROM pg_extension WHERE extname='vector'").fetchone():
            raise RuntimeError('pgvector missing')
        info = c.execute('SELECT instance_id,environment FROM common_server_metadata WHERE singleton').fetchone()
        if not info or info['environment'] != self.settings.environment:
            raise RuntimeError('Database environment does not match APP_ENV; refusing cross-environment writes')
        if self.settings.instance_id and info['instance_id'] != self.settings.instance_id:
            raise RuntimeError('SERVER_INSTANCE_ID does not match the restored database identity')
        return dict(info)


if __name__ == '__main__':
    from .config import Settings
    Database(Settings.from_env()).migrate()
    print('Database migrations completed')
