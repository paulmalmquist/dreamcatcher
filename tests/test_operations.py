"""Admin and runtime hardening tests. All identities, rows and attestations are synthetic."""
import json
import time
import pytest
from conftest import login
from test_hosted_apps import environment, create, build, publish, share, claim, report, KEY, IMAGE, BASE
from dreamcatcher import db as storage, operations


def policy(**changes):
    return {'support_contact': 'Synthetic manufacturing support', 'review_due': time.time() + 86400,
            'profile': 'custom-backend', 'queries_per_minute': 120, 'min_refresh_seconds': 0, 'expected_revision': 0, **changes}


@pytest.mark.parametrize('who', ['builder', 'reviewer', 'viewer', 'outsider'])
def test_admin_console_requires_real_admin_role(client, who):
    login(client, who)
    assert client.get('/api/v2/admin/overview').status_code == 403


def test_admin_console_filters_restricted_apps_jobs_and_events(environment):
    c = environment
    normal, _ = create(c)
    restricted, _ = create(c, classification='restricted')
    login(c, 'admin')
    r = c.get('/api/v2/admin/overview')
    assert r.status_code == 200, r.text
    body = r.json()
    assert normal in [a['id'] for a in body['apps']]
    assert restricted not in r.text
    assert KEY not in r.text and 'lease_hash' not in r.text and 'source_blob' not in r.text
    assert len(body['connections']) == 9 and body['external_apps']
    assert all('configuration_present' in item for item in body['connections'])
    login(c)
    share(c, restricted, 'user:admin', 'review')
    login(c, 'admin')
    assert restricted in c.get('/api/v2/admin/overview').text


def test_lifecycle_is_share_scoped_and_compare_and_swap(environment):
    c = environment
    app, _ = create(c)
    path = f'/api/v2/apps/{app}/lifecycle'
    assert c.put(path, json=policy(expected_revision=5)).status_code == 409
    assert c.put(path, json=policy()).json()['revision'] == 1
    assert c.put(path, json=policy()).status_code == 409
    assert c.put(path, json=policy(expected_revision=1)).json()['revision'] == 2
    assert c.put(path, json=policy(expected_revision=2, review_due=time.time()-1)).status_code == 422
    login(c, 'admin')
    assert c.put(path, json=policy(expected_revision=2)).status_code == 403


def test_overdue_review_blocks_already_live_app(environment):
    c = environment
    app, sub = create(c)
    build(c); publish(c, app, sub)
    c.put(f'/api/v2/apps/{app}/lifecycle', json=policy())
    with storage.connect() as db:
        p = operations.lifecycle(db, app)
        p['review_due'] = time.time()-1
        db.execute('UPDATE app_lifecycle SET payload=? WHERE app_id=?', (json.dumps(p), app))
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 403


def test_standard_dashboard_profile_requires_verified_server(environment):
    c = environment
    app, sub = create(c)
    c.put(f'/api/v2/apps/{app}/lifecycle', json=policy(profile='standard-dashboard'))
    build(c)
    login(c, 'reviewer')
    r = c.post(f"/api/v2/apps/{app}/submissions/{sub['id']}/approve")
    assert r.status_code == 409 and 'platform-runtime' in r.text


def test_gateway_budget_cannot_be_bypassed_using_legacy_endpoint(environment):
    c = environment
    app, sub = create(c)
    build(c); publish(c, app, sub)
    c.put(f'/api/v2/apps/{app}/lifecycle', json=policy(queries_per_minute=1))
    body = {'reference': 'bq-build-readiness@1.0.0', 'parameters': {'program_id': 'program-a'}}
    assert c.post(f'/api/v2/runtime/{app}/queries', json=body).status_code == 200
    r = c.post('/api/execute/query', json=body | {'app_id': app})
    assert r.status_code == 429 and r.headers['retry-after']
    login(c, 'admin')
    app_row = next(a for a in c.get('/api/v2/admin/overview').json()['apps'] if a['id'] == app)
    assert app_row['requests_this_minute'] == 1


def test_refresh_cadence_is_user_scoped_and_does_not_cache_rows(environment):
    c = environment
    app, sub = create(c)
    build(c); publish(c, app, sub)
    c.put(f'/api/v2/apps/{app}/lifecycle', json=policy(min_refresh_seconds=60))
    assert share(c, app).status_code == 200
    body = {'reference': 'bq-build-readiness@1.0.0', 'parameters': {'program_id': 'program-a'}}
    path = f'/api/v2/runtime/{app}/queries'
    assert c.post(path, json=body).status_code == 200
    assert c.post(path, json=body).status_code == 429
    login(c, 'viewer')
    assert c.post(path, json=body).status_code == 200


def test_analytical_review_requires_independence_and_binds_new_candidate(environment, monkeypatch):
    c = environment
    app, sub = create(c)
    build(c)
    monkeypatch.setenv('DC_REQUIRE_ANALYTICAL_REVIEW', 'true')
    path = f"/api/v2/apps/{app}/submissions/{sub['id']}"
    evidence = {'evidence_uri': 'gs://synthetic-golden-evidence/readiness.json', 'evidence_sha256': 'd'*64}
    assert c.post(path+'/analytical-review', json=evidence).status_code == 403
    login(c, 'reviewer')
    assert c.post(path+'/approve').status_code == 409
    assert c.post(path+'/analytical-review', json=evidence).status_code == 200
    assert c.post(path+'/approve').status_code == 200
    with storage.connect() as db:
        review = db.execute('SELECT * FROM analytical_reviews WHERE submission_id=?', (sub['id'],)).fetchone()
        assert review['image'] == IMAGE and review['reviewer'] == 'reviewer'
    login(c)
    from test_hosted_apps import bundle
    next_sub = c.post(f'/api/v2/apps/{app}/submissions', files={'file': ('next.zip', bundle(version='1.0.1'))}).json()
    build(c)
    login(c, 'reviewer')
    assert c.post(f"/api/v2/apps/{app}/submissions/{next_sub['id']}/approve").status_code == 409


def test_expired_and_failed_scan_blocks_runtime_and_rescan_is_worker_only(environment):
    c = environment
    app, sub = create(c)
    build(c); publish(c, app, sub)
    with storage.connect() as db:
        db.execute('UPDATE release_assurance SET expires=? WHERE submission_id=?', (time.time()-1, sub['id']))
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 403
    body = {'submission_id': sub['id'], 'image': IMAGE, 'passed': True, 'evidence_sha256': 'e'*64, 'evidence_uri': 'gs://synthetic-rescans/report.json'}
    assert c.post('/api/v2/workers/build/rescan', json=body).status_code == 401
    headers = {'Authorization': 'Bearer '+KEY}
    assert c.post('/api/v2/workers/build/rescan', json=body, headers=headers).status_code == 200
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 200
    assert c.post('/api/v2/workers/build/rescan', json=body | {'passed': False}, headers=headers).status_code == 200
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 403


def test_heartbeat_renewal_deadline_and_cancellation(environment):
    c = environment
    _, sub = create(c)
    job = claim(c, 'build')
    path = f"/api/v2/workers/build/jobs/{job['id']}/heartbeat"
    headers = {'Authorization': 'Bearer '+KEY}
    assert c.post(path, json={'lease': job['lease']}).status_code == 401
    assert c.post(path, json={'lease': job['lease']}, headers=headers).status_code == 200
    with storage.connect() as db:
        db.execute('UPDATE job_lease_limits SET deadline=? WHERE job_id=?', (time.time()-1, job['id']))
    assert c.post(path, json={'lease': job['lease']}, headers=headers).status_code == 409
    login(c, 'admin')
    r = c.post(f"/api/v2/admin/jobs/{job['id']}/action", json={'action': 'cancel', 'reason': 'Synthetic cancellation test'})
    assert r.status_code == 200, r.text
    assert c.post(path, json={'lease': job['lease']}, headers=headers).status_code == 409
    assert report(c, 'build', job, {}).status_code == 409


def test_dead_letter_and_explicit_retry_cannot_reuse_old_lease(environment):
    c = environment
    create(c)
    for _ in range(3):
        old = claim(c, 'build')
        with storage.connect() as db:
            db.execute('UPDATE platform_jobs SET lease_until=? WHERE id=?', (time.time()-1, old['id']))
    assert claim(c, 'build') is None
    login(c, 'admin')
    assert c.get('/api/v2/admin/overview').json()['jobs'][0]['status'] == 'dead_letter'
    assert c.post(f"/api/v2/admin/jobs/{old['id']}/action", json={'action': 'retry', 'reason': 'External synthetic job reconciled'}).status_code == 200
    assert report(c, 'build', old, {}).status_code == 409
    new = claim(c, 'build')
    assert new['lease'] != old['lease']


def test_production_release_rejects_missing_lifecycle_and_analytics(environment, monkeypatch):
    c = environment
    _, sub = create(c)
    build(c)
    monkeypatch.setenv('DC_ENV', 'production')
    with storage.connect() as db:
        row = db.execute('SELECT * FROM submissions WHERE id=?', (sub['id'],)).fetchone()
        findings = operations.release_findings(db, row)
    assert any('support contact' in p for p in findings)
    assert any('analytical review' in p for p in findings)


def test_adding_existing_package_cannot_revoke_approval(environment):
    c = environment
    login(c, 'admin')
    assert c.post('/api/v2/runtime-packages', json=BASE).status_code == 409
    rule = next(p for p in c.get('/api/v2/runtime-packages').json() if p['name'] == BASE['name'])
    assert rule['approved']
    fresh = BASE | {'name': 'synthetic-new-image'}
    assert c.post('/api/v2/runtime-packages', json=fresh).status_code == 201
    assert not next(p for p in c.get('/api/v2/runtime-packages').json() if p['name'] == fresh['name'])['approved']
    login(c, 'builder')
    assert c.post('/api/v2/runtime-packages', json=fresh).status_code == 403


def test_admin_audit_contains_scoped_jobs_and_account_changes(environment):
    c = environment
    app, _ = create(c)
    build(c)
    login(c, 'admin')
    account = next(a for a in c.get('/api/admin/users').json() if a['id'] == 'outsider')
    account['enabled'] = False
    assert c.put('/api/admin/users', json=account).status_code == 200
    overview = c.get('/api/v2/admin/overview').json()
    assert any(e['action'] == 'job.completed' for e in overview['audit'])
    assert any(e['action'] == 'user.updated' for e in overview['audit'])
    assert not next(a for a in overview['apps'] if a['id'] == app)['can_share']
