"""Real Chromium + Docker synthetic story; no live GCP, scanners, or model.

This is deliberately NOT a production worker. Only the repository-owned Flight
Deck fixture is built. All admission reports are labeled test doubles in evidence.
Runs in an ephemeral Linux CI runner; host networking is NOT tenant isolation.
"""
import hashlib
import importlib.util
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from dreamcatcher.hosting import unpack_source
from dreamcatcher.contracts import REQUIRED_CHECKS

ORIGIN = 'http://127.0.0.1:18000'
SUFFIX = 'apps.localhost'
OUT = ROOT / 'test-results/container-story'
OUT.mkdir(parents=True, exist_ok=True)
PASSWORD = 'Dreamcatcher-local-1!'
KEY = secrets.token_urlsafe(40)
BASE = {'ecosystem': 'image', 'name': 'synthetic-test-base', 'version': '1.0.0', 'integrity': 'sha256:' + 'b' * 64, 'source': 'registry.example.invalid/lab/base'}
REPORT = {'status': 'running', 'real': ['source upload', 'Docker build/run', 'Chromium', 'SDK HTTP', 'gateway authorization', 'independent review', 'edge handoff'],
          'test_doubles': ['BigQuery rows and security observations', 'scanner/package inventory reports', 'deployment admission checks', 'deterministic maintainer response'], 'steps': []}


def step(name):
    REPORT['steps'].append(name)
    print('PASS:', name, flush=True)
    (OUT / 'summary.json').write_text(json.dumps(REPORT, indent=2))


def checked(r, expected=200):
    assert r.status_code == expected, f'{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:1000]}'
    return r.json()


@contextmanager
def login_api(who):
    with httpx.Client(base_url=ORIGIN, timeout=40) as c:
        result = checked(c.post('/api/login', json={'email': who + '@demo.local', 'password': PASSWORD}))
        c.headers['X-CSRF-Token'] = result['csrf']
        yield c


def await_http(path):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(path, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.15)
    raise AssertionError('Service did not become ready: ' + path)


def boot_data():
    with login_api('admin') as admin:
        checked(admin.put('/api/v2/runtime-packages', json=BASE | {'approved': True}))
        for p in json.loads((ROOT / 'examples/bigquery/catalog.json').read_text()):
            result = checked(admin.put('/api/v2/data-products', json=p))
            checked(admin.post('/api/v2/workers/data/observations', headers={'Authorization': 'Bearer ' + KEY}, json={
                'source': p['source'], 'product_digest': result['digest'], 'object_type': 'VIEW', 'columns': p['columns'],
                'data_as_of': time.time(), 'ttl_seconds': 3600, 'lineage_verified': True, 'row_security_verified': True,
                'column_security_verified': True, 'negative_access_tests_passed': True, 'grain_tests_passed': True,
                'evidence_uri': 'gs://synthetic-evidence/not-real.json', 'evidence_sha256': 'c' * 64}))
    queries = json.loads((ROOT / 'examples/bigquery/queries.json').read_text())
    with login_api('builder') as builder, login_api('reviewer') as reviewer:
        for q in queries:
            checked(builder.post('/api/queries', json=q), 201)
            checked(reviewer.post('/api/assets/query/' + q['id'] + '/1.0.0/review', json={'action': 'approve'}))


def claim(kind):
    return checked(httpx.post(ORIGIN + '/api/v2/workers/' + kind + '/claim', json={}, headers={'Authorization': 'Bearer ' + KEY}))['job']


def report(kind, job, body):
    return checked(httpx.post(ORIGIN + f"/api/v2/workers/{kind}/jobs/{job['id']}/report", headers={'Authorization': 'Bearer ' + KEY}, json={'lease': job['lease'], 'result': body}, timeout=40))


def source(kind, job):
    r = httpx.get(ORIGIN + f"/api/v2/workers/{kind}/jobs/{job['id']}/source", headers={'Authorization': 'Bearer ' + KEY, 'X-Job-Lease': job['lease']})
    assert r.status_code == 200
    return r.content


def build_upload(work, revision, base_image):
    job = claim('build')
    assert job
    manifest, files = unpack_source(source('build', job))
    assert manifest.version == revision
    # The harness accepts only its own known Dockerfile/runtime. Not a generic
    # source worker and never a path for arbitrary uploads on a work computer.
    assert files['Dockerfile'] == (ROOT / 'examples/flight-deck/Dockerfile').read_bytes()
    spec = importlib.util.spec_from_file_location('pack_flight_deck', ROOT / 'scripts/pack-flight-deck.py')
    pack = importlib.util.module_from_spec(spec); spec.loader.exec_module(pack)
    _, original = unpack_source(pack.source_bundle())
    assert set(files) == set(original)
    for name, content in files.items():
        if name not in ('src/Dashboard.jsx', 'dreamcatcher.json'):
            assert content == original[name], 'Unexpected fixture mutation: ' + name
    expected_jsx = original['src/Dashboard.jsx'] if revision == '1.0.0' else original['src/Dashboard.jsx'].replace(b'Build readiness', b'Mission readiness')
    assert files['src/Dashboard.jsx'] == expected_jsx
    build_dir = work / ('source-' + revision); build_dir.mkdir()
    for name, value in files.items():
        target = build_dir / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(value)
    tag = 'dc-flight-deck-e2e:' + revision
    with (OUT / ('build-' + revision + '.log')).open('w') as log:
        subprocess.run(['docker', 'build', '--build-arg', 'APPROVED_NODE_IMAGE=' + base_image, '-t', tag, str(build_dir)], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=360)
    image_id = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True).strip()
    # Reference below is deliberately fake; actual local image identity is recorded
    # separately. This does NOT certify a registry push or a production inventory.
    image_ref = 'registry.example.invalid/lab/dashboard@' + image_id
    report('build', job, {'source_digest': job['source_digest'], 'manifest_digest': job['manifest_digest'], 'image': image_ref, 'dependencies': [BASE], 'checks': dict.fromkeys(REQUIRED_CHECKS, True)})
    REPORT.setdefault('images', []).append({'version': revision, 'local_image_id': image_id, 'source_digest': job['source_digest']})
    step('Build uploaded source ' + revision + ' into a real container image')
    return job['target'], tag, image_ref


def share(builder, app, grants):
    overview = checked(builder.get(f'/api/v2/apps/{app}/overview'))
    checked(builder.put(f'/api/v2/apps/{app}/grants', json={'expected_revision': overview['revision'], 'grants': grants}))


def login_ui(page, who):
    page.goto(ORIGIN)
    page.get_by_label('Email', exact=True).fill(who + '@demo.local')
    expect(page.get_by_label('Email', exact=True)).to_have_value(who + '@demo.local')
    page.get_by_label('Password', exact=True).fill(PASSWORD)
    with page.expect_response(lambda r: r.url == ORIGIN + '/api/login' and r.request.method == 'POST') as response:
        page.get_by_role('button', name='Enter your workspace').click()
    assert response.value.status == 200, 'Browser login failed: ' + str(response.value.status)
    expect(page.get_by_role('tab', name='Gallery', exact=True)).to_be_visible(timeout=15000)


def open_app(page, release=True):
    page.goto(ORIGIN)
    page.get_by_role('button', name='Explore Flight Deck', exact=True).click()
    if release:
        page.get_by_role('tab', name='Release', exact=True).click()


def release_record(page, version):
    return page.locator('article.release-record').filter(has=page.get_by_text('v' + version, exact=True))


def launch_ui(page, origin):
    with page.expect_request(lambda r: r.url == origin + '/_dc/launch') as request:
        page.get_by_role('button', name='Launch dashboard', exact=True).click()
    assert request.value.method == 'POST'
    assert request.value.headers.get('origin') == ORIGIN, 'Launch must preserve its exact gallery Origin'
    assert request.value.headers.get('content-type', '').startswith('application/x-www-form-urlencoded')


def approve_ui(page, version):
    open_app(page)
    record = release_record(page, version)
    record.get_by_text('Record independent analytical review', exact=True).click()
    record.get_by_label('Retained golden-test evidence URI').fill('git:tests/frontend.test.mjs')
    record.get_by_label('Evidence SHA-256', exact=True).fill(hashlib.sha256((ROOT / 'tests/frontend.test.mjs').read_bytes()).hexdigest())
    record.get_by_role('button', name='Record reviewed evidence', exact=True).click()
    expect(record.get_by_text('Independent analytical evidence recorded for this image.', exact=True)).to_be_visible()
    record.get_by_role('button', name='Approve', exact=True).click()
    expect(record.get_by_text('approved', exact=True)).to_be_visible()


def deploy_ui(page, app, version, tag, image_ref, work, containers):
    open_app(page)
    release_record(page, version).get_by_role('button', name='Promote', exact=True).click()
    # Wait on the actual control-plane mutation before claiming its leased job.
    with login_api('builder') as c:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if any(d['status'] == 'queued' for d in checked(c.get(f'/api/v2/apps/{app}/overview'))['deployments']):
                break
            time.sleep(.1)
    job = claim('deploy'); assert job and job['image'] == image_ref
    port = 18086 if version == '1.0.0' else 18087
    name = 'dc-flight-deck-' + secrets.token_hex(5)
    subprocess.run(['docker', 'run', '-d', '--name', name, '--network', 'host', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--pids-limit', '64', '--memory', '256m', '--cpus', '0.5',
        '-e', 'DC_ENV=local', '-e', 'PORT=' + str(port), '-e', 'DC_APP_ID=' + app, '-e', 'DC_GATEWAY_ORIGIN=' + ORIGIN, tag], check=True, capture_output=True)
    containers.append(name)
    await_http(f'http://127.0.0.1:{port}/healthz')
    assert httpx.get(f'http://127.0.0.1:{port}/').status_code == 401
    user = subprocess.check_output(['docker', 'inspect', name, '--format', '{{.Config.User}}'], text=True).strip()
    assert user == '65532:65532'
    origin = f'https://{app}.{SUFFIX}:19443'
    routes = {app + '.' + SUFFIX + ':19443': {'appId': app, 'submissionId': job['deployment']['submission_id'], 'origin': origin, 'upstream': f'http://127.0.0.1:{port}'}}
    (work / 'routes.json').write_text(json.dumps(routes))
    report('deploy', job, {'image': image_ref, 'url': origin, 'checks': dict.fromkeys(('private_ingress', 'edge_auth', 'egress_policy', 'health', 'digest_verified', 'resources', 'no_workload_data_credentials'), True)})
    step('Run non-root container ' + version + ' and admit release with test-double deployment evidence')
    return origin


def run():
    assert os.getenv('DC_CONTAINER_E2E') == '1', 'Set DC_CONTAINER_E2E=1 explicitly on a disposable Linux test machine'
    assert shutil.which('docker'), 'Docker is required; this test never substitutes a local process for the container'
    # Use a digest resolved at test time, not a floating tag during either build.
    subprocess.run(['docker', 'pull', 'node:22-bookworm-slim'], check=True)
    base_image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', 'node:22-bookworm-slim'], text=True))[0]['RepoDigests'][0]
    REPORT['test_base_image'] = base_image
    processes, logs, containers = [], [], []
    with tempfile.TemporaryDirectory(prefix='dc-container-story-') as directory:
        work = Path(directory)
        env = os.environ.copy()
        # Inherit PATH/tooling, never carry work connection settings into this lab.
        for key in list(env):
            if key.startswith('DC_'):
                env.pop(key)
        env.update(DC_ENV='local', DC_DEMO='true', DC_E2E_SYNTHETIC='1', DC_DATA_DIR=str(work / 'data'), DC_ORIGIN=ORIGIN,
            DC_BUILD_SIGNING_KEY=KEY, DC_SESSION_SECRET=KEY, DC_IMAGE_REGISTRIES='registry.example.invalid/lab',
            DC_APP_RUNTIME_SUFFIX=SUFFIX, DC_APP_RUNTIME_PORT='19443', DC_BQ_QUERIES_PER_MINUTE='100', DC_REQUIRE_ANALYTICAL_REVIEW='true')
        env.update({'DC_WORKER_' + kind + '_KEY': KEY for kind in ('BUILD', 'DEPLOY', 'AGENT', 'DATA', 'EDGE')})
        try:
            log = (OUT / 'gateway.log').open('w'); logs.append(log)
            processes.append(subprocess.Popen([sys.executable, 'tests/e2e/gateway.py'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT))
            await_http(ORIGIN + '/api/health')
            boot_data()
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(work / 'key.pem'), '-out', str(work / 'cert.pem'), '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,DNS:*.apps.localhost'], check=True, capture_output=True)
            (work / 'routes.json').write_text('{}')
            edge_env = env | {'DC_CONTROL_ORIGIN': ORIGIN, 'DC_GALLERY_ORIGIN': ORIGIN, 'DC_EDGE_TLS_KEY': str(work / 'key.pem'),
                'DC_EDGE_TLS_CERT': str(work / 'cert.pem'), 'DC_EDGE_ROUTES': str(work / 'routes.json'), 'DC_EDGE_PORT': '19443'}
            log = (OUT / 'edge.log').open('w'); logs.append(log)
            processes.append(subprocess.Popen(['node', 'integrations/private-edge/server.mjs'], cwd=ROOT, env=edge_env, stdout=log, stderr=subprocess.STDOUT))
            spec = importlib.util.spec_from_file_location('pack_flight_deck', ROOT / 'scripts/pack-flight-deck.py')
            pack = importlib.util.module_from_spec(spec); spec.loader.exec_module(pack)
            zip_path = work / 'flight-deck.zip'; zip_path.write_bytes(pack.source_bundle())
            with sync_playwright() as pw, login_api('builder') as builder:
                browser = pw.chromium.launch(args=['--host-resolver-rules=MAP *.apps.localhost 127.0.0.1', '--enable-unsafe-swiftshader'])
                contexts = {who: browser.new_context(ignore_https_errors=True, reduced_motion='reduce', viewport={'width': 1440, 'height': 1080}) for who in ('builder', 'reviewer', 'viewer', 'outsider', 'admin')}
                pages = {who: context.new_page() for who, context in contexts.items()}
                browser_errors = []
                for context in contexts.values():
                    context.on('weberror', lambda error: browser_errors.append(str(error.error)))
                for who, page in pages.items():
                    login_ui(page, who)
                    if who != 'admin':
                        expect(page.get_by_role('tab', name='Admin console', exact=True)).to_have_count(0)
                page = pages['builder']
                page.get_by_role('button', name='Upload your app').click()
                form = page.locator('.hosted-registration')
                form.get_by_label('Name', exact=True).fill('Flight Deck')
                form.get_by_label('Description', exact=True).fill('Synthetic manufacturing readiness · container integration test')
                form.get_by_role('button', name='Create hosted app').click()
                expect(page.get_by_role('button', name='Explore Flight Deck', exact=True)).to_be_visible()
                app = next(a['id'] for a in checked(builder.get('/api/state'))['apps'] if a['name'] == 'Flight Deck')
                open_app(page)
                page.get_by_label('Upload source ZIP (up to 8 MiB)').set_input_files(zip_path)
                expect(release_record(page, '1.0.0')).to_be_visible()
                page.screenshot(path=str(OUT / '01-uploaded.png'), full_page=True)
                step('Register Flight Deck and upload its source ZIP through the gallery UI')
                sub, tag, image = build_upload(work, '1.0.0', base_image)
                assert builder.post(f'/api/v2/apps/{app}/submissions/{sub}/approve').status_code == 403
                assert builder.post(f'/api/v2/apps/{app}/submissions/{sub}/deploy', json={'environment': 'production'}).status_code == 409
                approve_ui(pages['reviewer'], '1.0.0')
                origin = deploy_ui(page, app, '1.0.0', tag, image, work, containers)
                share(builder, app, [{'subject': 'user:viewer', 'permission': 'use'}])
                open_app(pages['viewer'], release=False)
                launch_ui(pages['viewer'], origin)
                expect(pages['viewer'].get_by_role('heading', name='Build readiness', exact=True)).to_be_visible()
                expect(pages['viewer'].get_by_text('DEMO-A101', exact=True)).to_be_visible()
                pages['viewer'].screenshot(path=str(OUT / '02-dashboard-before.png'), full_page=True)
                cookies = contexts['viewer'].cookies(origin)
                assert len(cookies) == 1 and cookies[0]['name'] == '__Host-dc_app' and cookies[0]['httpOnly'] and cookies[0]['secure']
                assert 'code=' not in pages['viewer'].url
                pages['viewer'].get_by_label('Program', exact=True).select_option('program-b')
                expect(pages['viewer'].get_by_text('No authorized rows for this program.', exact=True)).to_be_visible()
                pages['viewer'].get_by_label('Program', exact=True).select_option('program-a')
                expect(pages['viewer'].get_by_text('DEMO-A101', exact=True)).to_be_visible()
                with login_api('outsider') as outsider:
                    assert outsider.post(f'/api/v2/apps/{app}/launch').status_code == 403
                # Direct browser requests cannot spoof the edge-injected identity.
                pages['outsider'].set_extra_http_headers({'x-dreamcatcher-runtime-token': 'forged'})
                response = pages['outsider'].goto(origin)
                assert response.status == 401
                step('Launch as viewer; render authorized rows; deny Program B, outsider and forged identity')
                open_app(page)
                page.get_by_label('UI change request').fill('Rename the dashboard heading from Build readiness to Mission readiness. Leave governed data permissions unchanged.')
                page.get_by_role('button', name='Request proposed change', exact=True).click()
                expect(page.get_by_text('queued', exact=True)).to_be_visible()
                job = claim('agent'); assert job and job['context']['app_id'] == app
                assert job['context']['query_contracts'][0]['reference'] == 'bq-build-readiness@1.0.0'
                _, files = unpack_source(source('agent', job))
                before = files['src/Dashboard.jsx']
                report('agent', job, {'base_source_digest': job['context']['source_digest'], 'summary': 'TEST FIXTURE: update heading only; no live model was called.',
                    'changes': [{'path': 'src/Dashboard.jsx', 'before_sha256': hashlib.sha256(before).hexdigest(), 'content': before.decode().replace('Build readiness', 'Mission readiness')}]})
                page.get_by_role('button', name='Refresh status', exact=True).click()
                page.get_by_role('button', name='Create candidate for a new build', exact=True).click()
                expect(release_record(page, '1.0.1')).to_be_visible()
                sub2, tag2, image2 = build_upload(work, '1.0.1', base_image)
                assert sub != sub2 and image != image2
                assert builder.post(f'/api/v2/apps/{app}/submissions/{sub2}/deploy', json={'environment': 'production'}).status_code == 409
                expect(pages['viewer'].get_by_role('heading', name='Build readiness', exact=True)).to_be_visible()
                step('Maintainer context produces UI-only candidate; pending version cannot replace active release')
                approve_ui(pages['reviewer'], '1.0.1')
                deploy_ui(page, app, '1.0.1', tag2, image2, work, containers)
                pages['viewer'].get_by_role('button', name='Refresh data', exact=True).click()
                expect(pages['viewer'].get_by_role('alert')).to_be_visible()
                open_app(pages['viewer'], release=False)
                launch_ui(pages['viewer'], origin)
                expect(pages['viewer'].get_by_role('heading', name='Mission readiness', exact=True)).to_be_visible()
                expect(pages['viewer'].get_by_text('DEMO-A101', exact=True)).to_be_visible()
                pages['viewer'].screenshot(path=str(OUT / '03-dashboard-after.png'), full_page=True)
                step('Independently approve and deploy rebuilt UI; old release session is invalidated')
                share(builder, app, [])
                pages['viewer'].get_by_role('button', name='Refresh data', exact=True).click()
                expect(pages['viewer'].get_by_role('alert')).to_be_visible()
                expect(pages['viewer'].get_by_text('DEMO-A101', exact=True)).to_have_count(0)
                pages['viewer'].screenshot(path=str(OUT / '04-access-revoked.png'), full_page=True)
                response = pages['viewer'].reload()
                assert response.status == 401
                step('Revoke sharing; existing tab loses query access and reload cannot fetch HTML')
                admin = pages['admin']
                admin.get_by_role('tab', name='Admin console', exact=True).click()
                expect(admin.get_by_role('heading', name='Mission control', exact=True)).to_be_visible()
                admin.get_by_role('tab', name='Applications', exact=True).click()
                managed = admin.get_by_role('row').filter(has_text='Flight Deck')
                expect(managed.get_by_role('button', name='Suspend', exact=True)).to_be_disabled()
                share(builder, app, [{'subject': 'user:admin', 'permission': 'share'}])
                admin.get_by_role('button', name='Refresh', exact=True).click()
                expect(managed.get_by_role('button', name='Lifecycle', exact=True)).to_be_enabled()
                managed.get_by_role('button', name='Lifecycle', exact=True).click()
                dialog = admin.get_by_role('dialog')
                dialog.get_by_label('Support contact', exact=True).fill('Synthetic Flight Deck team')
                from datetime import datetime, timezone, timedelta
                due = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
                dialog.get_by_label('Access review due (UTC)', exact=True).fill(due)
                dialog.get_by_label('App query requests per minute', exact=True).fill('75')
                dialog.get_by_role('button', name='Save lifecycle policy', exact=True).click()
                expect(dialog).to_have_count(0)
                expect(managed.get_by_text('Limit 75', exact=True)).to_be_visible()
                managed.get_by_role('button', name='Suspend', exact=True).click()
                admin.get_by_role('button', name='Confirm change', exact=True).click()
                expect(managed.get_by_text('Suspended', exact=True)).to_be_visible()
                managed.get_by_role('button', name='Resume', exact=True).click()
                admin.get_by_role('button', name='Confirm change', exact=True).click()
                expect(managed.get_by_role('button', name='Suspend', exact=True)).to_be_enabled()
                assert checked(builder.get(f'/api/v2/apps/{app}/overview'))['enabled']
                step('Admin console respects app grants, saves lifecycle limits and suspends/resumes through confirmed API controls')
                admin.get_by_role('tab', name='People & access', exact=True).click()
                account = admin.get_by_role('row').filter(has_text='outsider@demo.local')
                for status in ('false', 'true'):
                    account.get_by_role('button', name='Edit access', exact=True).click()
                    dialog = admin.get_by_role('dialog')
                    dialog.get_by_label('Account status', exact=True).select_option(status)
                    dialog.get_by_role('button', name='Review change', exact=True).click()
                    admin.get_by_role('button', name='Confirm change', exact=True).click()
                    expect(account.get_by_text('Enabled' if status == 'true' else 'Disabled', exact=True)).to_be_visible()
                    if status == 'false':
                        assert httpx.post(ORIGIN + '/api/login', json={'email': 'outsider@demo.local', 'password': PASSWORD}).status_code == 401
                admin.get_by_role('tab', name='Connections', exact=True).click()
                expect(admin.get_by_role('heading', name='Work connections', exact=True)).to_be_visible()
                expect(admin.get_by_text('Unverified', exact=True)).to_have_count(9)
                admin.get_by_role('tab', name='Worker jobs', exact=True).click()
                expect(admin.get_by_text('completed', exact=True)).to_have_count(5)
                admin.get_by_role('tab', name='Audit history', exact=True).click()
                expect(admin.get_by_role('cell', name='user.updated', exact=True)).to_have_count(2)
                expect(admin.get_by_role('cell', name='app.lifecycle_changed', exact=True)).to_be_visible()
                admin.screenshot(path=str(OUT / '05-admin-audit.png'), full_page=True)
                admin.get_by_role('tab', name='Overview', exact=True).click()
                admin.set_viewport_size({'width': 390, 'height': 844})
                expect(admin.get_by_role('heading', name='Mission control', exact=True)).to_be_visible()
                admin.screenshot(path=str(OUT / '06-admin-mobile.png'), full_page=True)
                step('Admin account disable/re-enable, unverified connections, scoped worker history and audit records work in Chromium')
                assert not browser_errors, browser_errors
                REPORT['uncaught_browser_errors'] = browser_errors
                browser.close()
            REPORT['status'] = 'passed'
        except BaseException as error:
            REPORT['status'] = 'failed'; REPORT['failure'] = type(error).__name__ + ': ' + str(error)[:2000]
            raise
        finally:
            (OUT / 'summary.json').write_text(json.dumps(REPORT, indent=2))
            # Cleanup only resources created and tracked by this one test run.
            for name in containers:
                with (OUT / (name + '.log')).open('w') as log:
                    subprocess.run(['docker', 'logs', name], stdout=log, stderr=subprocess.STDOUT)
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
            for process in reversed(processes):
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            for log in logs: log.close()


if __name__ == '__main__':
    run()
