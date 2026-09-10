"""Admission tests use worker/warehouse doubles, not a live edge or BigQuery."""
import hashlib
import time
import pytest
from conftest import login
from test_hosted_apps import environment, create, build, publish, share, KEY
from dreamcatcher.db import connect


def setup(c, monkeypatch):
    monkeypatch.setenv('DC_WORKER_EDGE_KEY', KEY)
    app, sub = create(c)
    build(c)
    publish(c, app, sub)
    return app, sub


def exchange(c, app, code, **overrides):
    return c.post('/api/v2/edge/exchange', headers={'Authorization': 'Bearer ' + KEY}, json={'app_id': app, 'code': code, 'origin': 'https://' + app + '.apps.example.invalid', **overrides})


def test_launch_is_one_use_app_bound_and_revocable(environment, monkeypatch):
    c = environment
    app, sub = setup(c, monkeypatch)
    r = c.post(f'/api/v2/apps/{app}/launch')
    assert r.status_code == 200, r.text
    assert r.headers['cache-control'] == 'no-store'
    ticket = r.json()
    assert '?' not in ticket['action']
    assert exchange(c, app, ticket['code'], origin='https://other.example.invalid').status_code == 401
    assert exchange(c, '0' * 24, ticket['code']).status_code == 401
    r = exchange(c, app, ticket['code'])
    assert r.status_code == 200, r.text
    token = r.json()['token']
    assert exchange(c, app, ticket['code']).status_code == 401
    assert c.get(f'/api/v2/runtime/{app}/context', headers={'Authorization': 'Bearer ' + token}).status_code == 200
    assert c.get('/api/state', headers={'Authorization': 'Bearer ' + token}).status_code == 403
    assert c.post('/api/logout').status_code == 200
    assert c.get(f'/api/v2/runtime/{app}/context', headers={'Authorization': 'Bearer ' + token}).status_code == 401


@pytest.mark.parametrize('change', ['expiry', 'sharing', 'suspend', 'revoke', 'logout'])
def test_pending_launch_rechecks_all_admission(change, environment, monkeypatch):
    c = environment
    app, sub = setup(c, monkeypatch)
    ticket = c.post(f'/api/v2/apps/{app}/launch').json()
    if change == 'expiry':
        with connect() as db:
            db.execute('UPDATE launch_tickets SET expires=?', (time.time() - 1,))
    elif change == 'sharing':
        share(c, app)
    elif change == 'suspend':
        assert c.post(f'/api/v2/apps/{app}/suspend').status_code == 200
    elif change == 'revoke':
        login(c, 'reviewer')
        assert c.post(f"/api/v2/apps/{app}/submissions/{sub['id']}/revoke").status_code == 200
    else:
        c.post('/api/logout')
    assert exchange(c, app, ticket['code']).status_code in (401, 403, 409)


def test_discovery_not_launch_and_missing_edge_fails_closed(environment, monkeypatch):
    c = environment
    app, sub = setup(c, monkeypatch)
    share(c, app, permission='discover')
    login(c, 'viewer')
    assert c.post(f'/api/v2/apps/{app}/launch').status_code == 403
    login(c)
    monkeypatch.delenv('DC_WORKER_EDGE_KEY')
    assert c.post(f'/api/v2/apps/{app}/launch').status_code == 503


def test_edge_key_and_csrf_required(environment, monkeypatch):
    c = environment
    app, _ = setup(c, monkeypatch)
    assert c.post(f'/api/v2/apps/{app}/launch', headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    ticket = c.post(f'/api/v2/apps/{app}/launch').json()
    assert c.post('/api/v2/edge/exchange', json={'code': ticket['code'], 'app_id': app, 'origin': ticket['action']}).status_code == 401
    with connect() as db:
        assert db.execute('SELECT hash FROM launch_tickets').fetchone()['hash'] == hashlib.sha256(ticket['code'].encode()).hexdigest()
