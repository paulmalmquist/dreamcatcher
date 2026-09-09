import os
import sys
import tempfile
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ.update(DC_DEMO='true',DC_ENV='local',DC_BUILD_SIGNING_KEY='test-only-signing-key-not-a-real-secret-000',DC_SESSION_SECRET='test-only-session-key-not-a-real-secret-000',DC_DATA_DIR=tempfile.mkdtemp(prefix='dreamcatcher-test-'))
from dreamcatcher.main import app
from dreamcatcher import db as storage
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path,monkeypatch):
    from dreamcatcher import seed, governance
    monkeypatch.setattr(storage,'DATA',tmp_path)
    monkeypatch.setattr(seed,'DATA',tmp_path)
    if hasattr(governance,'DATA'):
        monkeypatch.setattr(governance,'DATA',tmp_path)
    with TestClient(app) as c:
        yield c

def login(c,who='builder'):
    r=c.post('/api/login',json={'email':who+'@demo.local','password':'Dreamcatcher-local-1!'})
    assert r.status_code==200,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf']
    return r.json()
