import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv('DC_DATA_DIR', str(ROOT / 'data')))

class PostgresConnection:
    """Small DB-API adapter; application SQL remains parameterized on both engines."""
    def __init__(self, db): self.db = db
    def execute(self, sql, params=()):
        from psycopg import IntegrityError
        try:
            return self.db.execute(sql.replace('?', '%s'), params)
        except IntegrityError:
            raise sqlite3.IntegrityError('Constraint conflict') from None
    def executemany(self, sql, params):
        with self.db.cursor() as cursor:
            cursor.executemany(sql.replace('?', '%s'), params)
    def executescript(self, sql):
        self.db.execute(sql)

def postgres(url):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise RuntimeError('Install requirements-postgres.txt to use PostgreSQL') from None
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=10)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def digest(value):
    return hashlib.sha256((value if isinstance(value, bytes) else canonical(value).encode())).hexdigest()

@contextmanager
def connect():
    url = os.getenv('DC_DATABASE_URL')
    if url:
        with postgres(url) as db:
            yield PostgresConnection(db)
        return
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / 'registry.sqlite', timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    try:
        with db:
            yield db
    finally:
        db.close()

def migrate():
    with connect() as db:
        if os.getenv('DC_DATABASE_URL'):
            db.execute('SELECT pg_advisory_xact_lock(71829101)')
        for name in ('schema.sql', 'platform-schema.sql'):
            sql = (Path(__file__).parent / name).read_text()
            if os.getenv('DC_DATABASE_URL'):
                sql = sql.replace('BLOB', 'BYTEA').replace('REAL', 'DOUBLE PRECISION')
                sql = sql.replace('audit(id INTEGER PRIMARY KEY', 'audit(id BIGSERIAL PRIMARY KEY')
            db.executescript(sql)

def event(db, user, action, resource, details=None):
    db.execute('INSERT INTO audit(actor,action,resource,details,created) VALUES(?,?,?,?,?)',
               (user, action, resource, canonical(details or {}), time.time()))
    import uuid
    db.execute('INSERT INTO audit_outbox(id,payload,created) VALUES(?,?,?)',
               (uuid.uuid4().hex, canonical({'actor': user, 'action': action, 'resource': resource, 'details': details or {}}), time.time()))

def asset(db, kind, reference):
    identifier, separator, version = reference.rpartition('@')
    if not separator:
        return None
    row = db.execute('SELECT * FROM assets WHERE kind=? AND id=? AND version=?', (kind, identifier, version)).fetchone()
    if row:
        return dict(row) | {'payload': json.loads(row['payload'])}

def put_asset(db, kind, payload, owner, status='pending', blob=None):
    raw = canonical(payload)
    db.execute('INSERT INTO assets(kind,id,version,owner,status,payload,digest,blob,created) VALUES(?,?,?,?,?,?,?,?,?)',
               (kind, payload['id'], payload['version'], owner, status, raw, digest(payload), blob, time.time()))
    return payload['id'] + '@' + payload['version']
