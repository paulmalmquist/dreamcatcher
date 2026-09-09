import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv('DC_DATA_DIR', str(ROOT / 'data')))

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def digest(value):
    return hashlib.sha256((value if isinstance(value, bytes) else canonical(value).encode())).hexdigest()

@contextmanager
def connect():
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
        db.executescript((Path(__file__).parent / 'schema.sql').read_text())

def event(db, user, action, resource, details=None):
    db.execute('INSERT INTO audit(actor,action,resource,details,created) VALUES(?,?,?,?,?)',
               (user, action, resource, canonical(details or {}), time.time()))

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
