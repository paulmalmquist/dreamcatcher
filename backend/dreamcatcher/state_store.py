"""App state is separate from control metadata. Only the trusted API connects here."""
import os
import sqlite3
import time
from contextlib import contextmanager
from fastapi import HTTPException
from . import db as storage
from .db import canonical, digest, PostgresConnection, postgres

SCHEMA = '''CREATE TABLE IF NOT EXISTS app_records(app_id TEXT NOT NULL,user_id TEXT NOT NULL,collection TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,version INTEGER NOT NULL,updated REAL NOT NULL,PRIMARY KEY(app_id,user_id,collection,key));
CREATE TABLE IF NOT EXISTS state_requests(app_id TEXT NOT NULL,user_id TEXT NOT NULL,idempotency_key TEXT NOT NULL,request_digest TEXT NOT NULL,result TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(app_id,user_id,idempotency_key));'''


@contextmanager
def state_connection(app_id, user_id):
    url = os.getenv('DC_STATE_DATABASE_URL')
    if url:
        if url == os.getenv('DC_DATABASE_URL'):
            raise RuntimeError('State and control-plane connections must be separate')
        with postgres(url) as conn:
            db = PostgresConnection(conn)
            role = db.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
            policies = db.execute("SELECT relrowsecurity,relforcerowsecurity,pg_has_role(current_user,relowner,'USAGE') AS is_owner FROM pg_class WHERE oid IN ('app_records'::regclass,'state_requests'::regclass)").fetchall()
            if role['rolsuper'] or role['rolbypassrls'] or len(policies) != 2 or any(not r['relrowsecurity'] or not r['relforcerowsecurity'] or r['is_owner'] for r in policies):
                raise HTTPException(503, 'State role or row-security configuration is unsafe')
            db.execute("SELECT set_config('dc.app_id', ?, true)", (app_id,))
            db.execute("SELECT set_config('dc.user_id', ?, true)", (user_id,))
            yield db
        return
    if os.getenv('DC_ENV') == 'production':
        raise HTTPException(503, 'Configure a separate PostgreSQL state store')
    storage.DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(storage.DATA / 'app-state.sqlite', timeout=15)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        conn.execute('BEGIN IMMEDIATE')
        with conn:
            yield conn
    finally:
        conn.close()


def get(app_id, user_id, collection, key):
    import json
    with state_connection(app_id, user_id) as db:
        row = db.execute('SELECT value,version FROM app_records WHERE app_id=? AND user_id=? AND collection=? AND key=?', (app_id, user_id, collection, key)).fetchone()
        return {'value': json.loads(row['value']), 'version': row['version']} if row else {'value': None, 'version': 0}


def put(app_id, user_id, collection, key, body):
    import json
    fingerprint = digest({'collection': collection, 'key': key, **body.model_dump()})
    with state_connection(app_id, user_id) as db:
        previous = db.execute('SELECT * FROM state_requests WHERE app_id=? AND user_id=? AND idempotency_key=?', (app_id, user_id, body.idempotency_key)).fetchone()
        if previous:
            if previous['request_digest'] != fingerprint:
                raise HTTPException(409, 'Idempotency key was used for a different request')
            return json.loads(previous['result'])
        params = (app_id, user_id, collection, key)
        if body.expected_version == 0:
            cursor = db.execute('INSERT INTO app_records VALUES(?,?,?,?,?,?,?) ON CONFLICT(app_id,user_id,collection,key) DO NOTHING', (*params, canonical(body.value), 1, time.time()))
        else:
            cursor = db.execute('UPDATE app_records SET value=?,version=version+1,updated=? WHERE app_id=? AND user_id=? AND collection=? AND key=? AND version=?', (canonical(body.value), time.time(), *params, body.expected_version))
        if cursor.rowcount != 1:
            raise HTTPException(409, 'Record version changed; read the current value before retrying')
        result = {'version': body.expected_version + 1}
        db.execute('INSERT INTO state_requests VALUES(?,?,?,?,?,?)', (app_id, user_id, body.idempotency_key, fingerprint, canonical(result), time.time()))
        return result
