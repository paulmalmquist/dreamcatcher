"""HTTP mock uploads with synthetic BigQuery metadata and isolated worker doubles.

These exercise real registry authorization and persistence, NOT GCP or containers.
"""
import io
import json
import time
import zipfile
from pathlib import Path
import pytest
from fastapi import HTTPException
from conftest import login
from dreamcatcher import db as storage, governance, hosting
from dreamcatcher.contracts import REQUIRED_CHECKS

ROOT = Path(__file__).resolve().parents[1]
KEY = 'test-only-worker-key-never-use-at-work-000000'
IMAGE = 'registry.example.invalid/dreamcatcher/dashboard@sha256:' + 'a' * 64
BASE = {'ecosystem': 'image', 'name': 'approved-dashboard-base', 'version': '1.0.0', 'integrity': 'sha256:' + 'b' * 64, 'source': 'registry.example.invalid/dreamcatcher/base'}


@pytest.fixture
def environment(client, monkeypatch):
    for kind in ('BUILD', 'DEPLOY', 'AGENT', 'DATA'):
        monkeypatch.setenv('DC_WORKER_' + kind + '_KEY', KEY)
    monkeypatch.setenv('DC_IMAGE_REGISTRIES', 'registry.example.invalid/dreamcatcher')
    monkeypatch.setenv('DC_APP_RUNTIME_SUFFIX', 'apps.example.invalid')
    catalog = json.loads((ROOT / 'examples/bigquery/catalog.json').read_text())
    queries = json.loads((ROOT / 'examples/bigquery/queries.json').read_text())
    rows = json.loads((ROOT / 'examples/bigquery/synthetic-rows.json').read_text())
    def warehouse(payload, bound, user):
        source = payload['sources'][0]
        records = [r | {'updated_at': '2026-09-01T12:00:00Z'} for r in rows['datasets'][source]
                   if r['program_id'] == bound['program_id'] and r['program_id'] in rows['entitlements'].get(user['id'], [])]
        return {'rows': records, 'truncated': False, 'synthetic': True}
    monkeypatch.setattr(governance, 'run_bigquery', warehouse)
    login(client, 'admin')
    assert client.put('/api/v2/runtime-packages', json=BASE | {'approved': True}).status_code == 200
    for product in catalog:
        r = client.put('/api/v2/data-products', json=product)
        assert r.status_code == 200, r.text
        observation = {'source': product['source'], 'product_digest': r.json()['digest'], 'object_type': 'VIEW',
                       'columns': product['columns'], 'data_as_of': time.time(), 'ttl_seconds': 3600,
                       'lineage_verified': True, 'row_security_verified': True, 'column_security_verified': True,
                       'negative_access_tests_passed': True, 'grain_tests_passed': True,
                       'evidence_uri': 'gs://synthetic-evidence/never-a-live-attestation.json', 'evidence_sha256': 'c' * 64}
        r = client.post('/api/v2/workers/data/observations', json=observation, headers={'Authorization': 'Bearer ' + KEY})
        assert r.status_code == 200, r.text
    login(client)
    for query in queries:
        r = client.post('/api/queries', json=query)
        assert r.status_code == 201, r.text
    login(client, 'reviewer')
    for query in queries:
        r = client.post(f"/api/assets/query/{query['id']}/1.0.0/review", json={'action': 'approve'})
        assert r.status_code == 200, r.text
    login(client)
    return client


def bundle(slug='build-readiness', version='1.0.0', mutate=None):
    root = ROOT / 'examples/apps' / slug
    files = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    manifest = json.loads(files['dreamcatcher.json'])
    manifest['version'] = version
    if mutate:
        mutate(manifest, files)
    files['dreamcatcher.json'] = json.dumps(manifest).encode()
    return hosting.pack_source(files)


def create(c, slug='build-readiness', classification='internal'):
    r = c.post('/api/v2/apps', json={'name': 'Synthetic ' + slug, 'description': 'Mock upload for contract testing only', 'category': 'Manufacturing', 'classification': classification})
    assert r.status_code == 201, r.text
    app = r.json()['id']
    r = c.post(f'/api/v2/apps/{app}/submissions', files={'file': ('source.zip', bundle(slug, mutate=lambda m, f: m.update(classification=classification)), 'application/zip')})
    assert r.status_code == 201, r.text
    return app, r.json()


def claim(c, kind):
    r = c.post('/api/v2/workers/' + kind + '/claim', json={}, headers={'Authorization': 'Bearer ' + KEY})
    assert r.status_code == 200, r.text
    return r.json()['job']


def report(c, kind, job, result):
    return c.post(f"/api/v2/workers/{kind}/jobs/{job['id']}/report", headers={'Authorization': 'Bearer ' + KEY}, json={'lease': job['lease'], 'result': result})


def build(c, failed_check=None):
    job = claim(c, 'build')
    checks = {k: k != failed_check for k in REQUIRED_CHECKS}
    body = {'source_digest': job['source_digest'], 'manifest_digest': job['manifest_digest'], 'image': IMAGE, 'dependencies': [BASE], 'checks': checks}
    r = report(c, 'build', job, body)
    assert r.status_code == 200, r.text
    return job, body


def publish(c, app, sub):
    login(c, 'reviewer')
    r = c.post(f"/api/v2/apps/{app}/submissions/{sub['id']}/approve")
    assert r.status_code == 200, r.text
    login(c)
    r = c.post(f"/api/v2/apps/{app}/submissions/{sub['id']}/deploy", json={'environment': 'production'})
    assert r.status_code == 202, r.text
    job = claim(c, 'deploy')
    checks = dict.fromkeys(('private_ingress', 'edge_auth', 'egress_policy', 'health', 'digest_verified', 'resources', 'no_workload_data_credentials'), True)
    r = report(c, 'deploy', job, {'image': IMAGE, 'url': f'https://{app}.apps.example.invalid', 'checks': checks})
    assert r.status_code == 200, r.text


def share(c, app, subject='user:viewer', permission='use'):
    row = c.get(f'/api/v2/apps/{app}/overview').json()
    return c.put(f'/api/v2/apps/{app}/grants', json={'expected_revision': row['revision'], 'grants': [{'subject': subject, 'permission': permission}]})


@pytest.mark.parametrize('slug', ['build-readiness', 'supplier-delivery', 'test-telemetry'])
def test_mock_dashboard_upload_through_review_and_runtime(environment, slug):
    c = environment
    app, sub = create(c, slug)
    assert c.get(f'/api/v2/apps/{app}/agent').json()['submission_id'] == sub['id']
    build(c)
    publish(c, app, sub)
    r = c.post(f'/api/v2/runtime/{app}/queries', json={'reference': 'bq-' + slug + '@1.0.0', 'parameters': {'program_id': 'program-a'}})
    assert r.status_code == 200, r.text
    assert r.json()['synthetic'] and len(r.json()['rows']) == 1


def test_user_rows_and_discover_is_not_use(environment):
    c = environment
    app, sub = create(c)
    build(c)
    publish(c, app, sub)
    assert share(c, app, permission='discover').status_code == 200
    login(c, 'viewer')
    assert app in [a['id'] for a in c.get('/api/state').json()['apps']]
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 403
    login(c)
    share(c, app)
    login(c, 'viewer')
    r = c.post(f'/api/v2/runtime/{app}/queries', json={'reference': 'bq-build-readiness@1.0.0', 'parameters': {'program_id': 'program-b'}})
    assert r.status_code == 200 and r.json()['rows'] == []
    login(c, 'outsider')
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 403


def test_app_permission_never_grants_data_entitlement(environment):
    c = environment
    app, sub = create(c, 'supplier-delivery')
    build(c)
    publish(c, app, sub)
    share(c, app)
    login(c, 'viewer')
    r = c.post(f'/api/v2/runtime/{app}/queries', json={'reference': 'bq-supplier-delivery@1.0.0', 'parameters': {'program_id': 'program-a'}})
    assert r.status_code == 403


@pytest.mark.parametrize('gate', ['container_contract', 'inventory_complete', 'secrets', 'permission_tests', 'browser_egress'])
def test_failed_build_gate_cannot_be_approved(environment, gate):
    c = environment
    app, sub = create(c)
    build(c, gate)
    login(c, 'reviewer')
    assert c.post(f"/api/v2/apps/{app}/submissions/{sub['id']}/approve").status_code == 409


def test_worker_evidence_cannot_be_forged_or_replayed(environment):
    c = environment
    create(c)
    assert c.post('/api/v2/workers/build/claim', json={}).status_code == 401
    job, body = build(c)
    assert report(c, 'build', job, body).status_code == 409


def test_restricted_app_requires_explicit_reviewer(environment):
    c = environment
    app, sub = create(c, classification='restricted')
    build(c)
    login(c, 'admin')
    assert app not in [a['id'] for a in c.get('/api/state').json()['apps']]
    assert c.get(f'/api/v2/apps/{app}/overview').status_code == 403
    login(c)
    share(c, app, 'user:reviewer', 'review')
    login(c, 'reviewer')
    assert c.post(f"/api/v2/apps/{app}/submissions/{sub['id']}/approve").status_code == 200


def test_archive_traversal_and_missing_manifest_rejected(environment):
    c = environment
    app, _ = create(c)
    for files in ({'../outside': b'x'}, {'Dockerfile': b'FROM scratch'}, {'dreamcatcher.json': b'{}'}):
        r = c.post(f'/api/v2/apps/{app}/submissions', files={'file': ('source.zip', hosting.pack_source(files))})
        assert r.status_code == 422


def test_dependency_revocation_stops_existing_release(environment):
    c = environment
    app, sub = create(c)
    build(c)
    publish(c, app, sub)
    login(c, 'admin')
    c.put('/api/v2/runtime-packages', json=BASE | {'approved': False})
    login(c)
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 403


@pytest.mark.parametrize('kind', ['stale', 'schema', 'rls', 'lineage', 'grain', 'revoked'])
def test_data_drift_stops_existing_release(environment, kind):
    c = environment
    app, sub = create(c)
    build(c)
    publish(c, app, sub)
    source = 'dc-synthetic-demo.analytics_governed.assembly_readiness_v1'
    with storage.connect() as db:
        if kind == 'revoked':
            db.execute('UPDATE data_products SET enabled=0 WHERE source=?', (source,))
        else:
            row = db.execute('SELECT payload FROM data_observations WHERE source=?', (source,)).fetchone()
            p = json.loads(row['payload'])
            if kind == 'stale': p['data_as_of'] = 1
            if kind == 'schema': p['columns'] = p['columns'][:-1]
            if kind == 'rls': p['row_security_verified'] = False
            if kind == 'lineage': p['lineage_verified'] = False
            if kind == 'grain': p['grain_tests_passed'] = False
            db.execute('UPDATE data_observations SET payload=? WHERE source=?', (json.dumps(p), source))
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 403


@pytest.mark.parametrize('bad', ['raw-source', 'unknown-column', 'wide-audience', 'cost', 'output'])
def test_uncertified_query_not_approvable(environment, bad):
    c = environment
    q = json.loads((ROOT / 'examples/bigquery/queries.json').read_text())[0]
    q['version'] = '1.0.1'
    if bad == 'raw-source':
        previous = q['sources'][0]
        q['sources'] = [previous.replace('analytics_governed', 'raw')]
        q['sql'] = q['sql'].replace(previous, q['sources'][0])
        q['data_contract']['products'] = {q['sources'][0]: 1}
    if bad == 'unknown-column': q['sql'] = q['sql'].replace('system_name', 'secret_cost')
    if bad == 'wide-audience': q['allowed_groups'].append('Other')
    if bad == 'cost': q['data_contract']['max_bytes_billed'] *= 2
    if bad == 'output': q['data_contract']['output_columns'] = ['made_up']
    r = c.post('/api/queries', json=q)
    assert r.status_code == 201, r.text
    login(c, 'reviewer')
    r = c.post('/api/assets/query/bq-build-readiness/1.0.1/review', json={'action': 'approve'})
    assert r.status_code == 409, r.text


def test_user_scoped_state_cas_and_idempotency(environment):
    c = environment
    app, sub = create(c)
    build(c)
    publish(c, app, sub)
    path = f'/api/v2/runtime/{app}/state/preferences/dashboard'
    body = {'value': {'program': 'program-a'}, 'expected_version': 0, 'idempotency_key': 'request-one'}
    assert c.put(path, json=body).json() == {'version': 1}
    assert c.put(path, json=body).json() == {'version': 1}
    assert c.put(path, json=body | {'value': {'program': 'different'}}).status_code == 409
    assert c.put(path, json=body | {'idempotency_key': 'request-two'}).status_code == 409
    share(c, app)
    login(c, 'viewer')
    assert c.get(path).json() == {'value': None, 'version': 0}


def test_agent_ui_edit_creates_new_candidate_not_a_live_edit(environment):
    c = environment
    app, sub = create(c)
    initial_agent = c.get(f'/api/v2/apps/{app}/agent').json()['agent_id']
    r = c.post(f'/api/v2/apps/{app}/agent/changes', json={'submission_id': sub['id'], 'prompt': 'Make the title clearer', 'component': 'Dashboard'})
    assert r.status_code == 202
    change = r.json()['id']
    job = claim(c, 'agent')
    _, files = hosting.unpack_source(bundle())
    body = {'base_source_digest': sub['source_digest'], 'summary': 'A clearer title', 'changes': [{'path': 'src/Dashboard.jsx', 'before_sha256': storage.digest(files['src/Dashboard.jsx']), 'content': files['src/Dashboard.jsx'].decode().replace('Build Readiness', 'Assembly Readiness')}]}
    forbidden = body | {'changes': [{'path': 'Dockerfile', 'before_sha256': storage.digest(files['Dockerfile']), 'content': 'FROM hostile'}]}
    assert report(c, 'agent', job, forbidden).status_code == 403
    assert report(c, 'agent', job, body).status_code == 200
    r = c.post(f'/api/v2/apps/{app}/agent/changes/{change}/candidate', json={'version': '1.0.1'})
    assert r.status_code == 201 and r.json()['status'] == 'queued'
    assert c.get(f'/api/v2/apps/{app}/agent').json()['agent_id'] == initial_agent
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 403


def test_developer_token_is_bound_and_cannot_promote(environment):
    c = environment
    app, sub = create(c)
    other, _ = create(c)
    token = c.post(f'/api/v2/apps/{app}/developer-token').json()['token']
    headers = {'Authorization': 'Bearer ' + token}
    assert c.get(f'/api/v2/apps/{app}/overview', headers=headers).status_code == 200
    assert c.get(f'/api/v2/apps/{other}/overview', headers=headers).status_code == 403
    assert c.post(f"/api/v2/apps/{app}/submissions/{sub['id']}/approve", headers=headers).status_code == 403
    assert c.post('/api/v2/workers/build/claim', json={}, headers=headers).status_code == 401


def test_missing_worker_is_explicit(environment, monkeypatch):
    monkeypatch.delenv('DC_WORKER_BUILD_KEY')
    assert environment.post('/api/v2/workers/build/claim', json={}).status_code == 503


def test_hosted_sdk_token_is_release_bound_and_revoked_on_sharing(environment):
    c = environment
    app, sub = create(c)
    build(c)
    publish(c, app, sub)
    token = c.post('/api/tokens', json={'app_id': app}).json()['token']
    headers = {'Authorization': 'Bearer ' + token}
    assert c.get(f'/api/v2/runtime/{app}/context', headers=headers).status_code == 200
    assert c.get(f'/api/v2/apps/{app}/overview', headers=headers).status_code == 403
    assert c.get('/api/v2/runtime/wrong-app/context', headers=headers).status_code == 403
    share(c, app)
    assert c.get(f'/api/v2/runtime/{app}/context', headers=headers).status_code == 401


def test_expired_worker_lease_cannot_read_source(environment):
    c = environment
    create(c)
    job = claim(c, 'build')
    with storage.connect() as db:
        db.execute('UPDATE platform_jobs SET lease_until=0 WHERE id=?', (job['id'],))
    r = c.get(f"/api/v2/workers/build/jobs/{job['id']}/source", headers={'Authorization': 'Bearer ' + KEY, 'x-job-lease': job['lease']})
    assert r.status_code == 409
    newer = claim(c, 'build')
    assert newer['id'] == job['id'] and newer['lease'] != job['lease']


def test_deployment_does_not_activate_after_sharing_changes(environment):
    c = environment
    app, sub = create(c)
    build(c)
    login(c, 'reviewer')
    assert c.post(f"/api/v2/apps/{app}/submissions/{sub['id']}/approve").status_code == 200
    login(c)
    assert c.post(f"/api/v2/apps/{app}/submissions/{sub['id']}/deploy", json={'environment': 'production'}).status_code == 202
    job = claim(c, 'deploy')
    share(c, app)
    checks = dict.fromkeys(('private_ingress', 'edge_auth', 'egress_policy', 'health', 'digest_verified', 'resources', 'no_workload_data_credentials'), True)
    r = report(c, 'deploy', job, {'image': IMAGE, 'url': f'https://{app}.apps.example.invalid', 'checks': checks})
    assert r.status_code == 409
    assert c.get(f'/api/v2/runtime/{app}/context').status_code == 403
