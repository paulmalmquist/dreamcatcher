"""Operator controls. Metadata visibility does not grant app or warehouse access."""
import json
import os
import time
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from . import auth, hosting
from .contracts import Strict
from .db import ROOT, canonical, connect, event

router = APIRouter(prefix='/api/v2')
User = Annotated[dict, Depends(auth.authenticate)]


class Lifecycle(Strict):
    support_contact: str = Field(min_length=3, max_length=200)
    review_due: float = Field(gt=0)
    profile: Literal['standard-dashboard', 'custom-backend'] = 'custom-backend'
    queries_per_minute: int = Field(default=120, ge=1, le=1000)
    min_refresh_seconds: int = Field(default=0, ge=0, le=3600)
    expected_revision: int = Field(ge=0)


class AnalysisReview(Strict):
    evidence_uri: str = Field(pattern=r'^(?:https://|gs://|git:)[^\s]+$', max_length=1000)
    evidence_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class JobAction(Strict):
    action: Literal['cancel', 'retry']
    reason: str = Field(min_length=8, max_length=300)


def lifecycle(db, app_id):
    row = db.execute('SELECT * FROM app_lifecycle WHERE app_id=?', (app_id,)).fetchone()
    return json.loads(row['payload']) | {'revision': row['revision']} if row else None


def can(db, user, app_id, permission):
    try:
        hosting.app_permission(db, user, app_id, permission)
        return True
    except HTTPException:
        return False


def can_inspect(db, user, app_id):
    return any(can(db, user, app_id, p) for p in ('edit', 'share', 'review'))


def release_findings(db, row):
    problems = []
    production = os.getenv('DC_ENV') == 'production'
    policy = lifecycle(db, row['app_id'])
    if not policy and production:
        problems.append('Record support contact, runtime profile and access-review date')
    if policy and policy['review_due'] <= time.time():
        problems.append('Application ownership/access review is overdue')
    scan = db.execute('SELECT * FROM release_assurance WHERE submission_id=?', (row['id'],)).fetchone()
    if scan and (scan['image'] != row['image'] or not scan['passed'] or scan['expires'] <= time.time()):
        problems.append('Image assurance failed or expired; a trusted rescan is required')
    elif not scan and production:
        problems.append('Current trusted image assurance is required')
    manifest = json.loads(row['manifest'])
    if (production or os.getenv('DC_REQUIRE_ANALYTICAL_REVIEW') == 'true') and (manifest['queries'] or manifest['skills']):
        review = db.execute('SELECT * FROM analytical_reviews WHERE submission_id=?', (row['id'],)).fetchone()
        if not review or review['image'] != row['image']:
            problems.append('Independent analytical review with golden-result evidence is required')
    if policy and policy['profile'] == 'standard-dashboard' and row['evidence']:
        evidence = json.loads(row['evidence'])
        if evidence['checks'].get('platform_runtime_verified') is not True:
            problems.append('Standard dashboard needs trusted platform-runtime verification')
    return problems


def budget(app_id, user_id, reference):
    """Committed separately: failed queries consume budget too. No result caching."""
    now = time.time()
    window = int(now // 60) * 60
    rejected = None
    with connect() as db:
        policy = lifecycle(db, app_id) or {}
        limit = policy.get('queries_per_minute', 120)
        interval = policy.get('min_refresh_seconds', 0)
        db.execute('DELETE FROM app_query_windows WHERE window_start<?', (window - 86400,))
        db.execute('DELETE FROM query_cadence WHERE last_started<?', (now - 86400,))
        if interval:
            previous = db.execute('SELECT last_started FROM query_cadence WHERE app_id=? AND user_id=? AND reference=?', (app_id, user_id, reference)).fetchone()
            if previous and now - previous['last_started'] < interval:
                rejected = 'Dashboard refresh interval exceeded'
        if not rejected:
            cursor = db.execute('INSERT INTO app_query_windows VALUES(?,?,1) ON CONFLICT(app_id,window_start) DO UPDATE SET requests=app_query_windows.requests+1 WHERE app_query_windows.requests<?', (app_id, window, limit))
            if cursor.rowcount != 1:
                rejected = 'Application query budget exceeded'
            elif interval:
                cursor = db.execute('INSERT INTO query_cadence VALUES(?,?,?,?) ON CONFLICT(app_id,user_id,reference) DO UPDATE SET last_started=excluded.last_started WHERE query_cadence.last_started<=?', (app_id, user_id, reference, now, now - interval))
                if cursor.rowcount != 1:
                    rejected = 'Dashboard refresh interval exceeded'
        if rejected:
            event(db, user_id, 'runtime.query_throttled', app_id, {'reference': reference})
    if rejected:
        raise HTTPException(429, rejected, headers={'Retry-After': str(max(1, interval) if 'refresh' in rejected else max(1, 60 - int(now % 60)))})


@router.put('/apps/{app_id}/lifecycle')
def save_lifecycle(app_id: str, body: Lifecycle, user: User):
    with connect() as db:
        hosting.app_permission(db, user, app_id, 'share')
        if body.review_due <= time.time() or body.review_due > time.time() + 366 * 86400:
            raise HTTPException(422, 'Choose a future review date within one year')
        if body.expected_revision and not db.execute('SELECT 1 FROM app_lifecycle WHERE app_id=?', (app_id,)).fetchone():
            raise HTTPException(409, 'Lifecycle policy does not exist; reload before saving')
        revision = body.expected_revision + 1
        cursor = db.execute('INSERT INTO app_lifecycle VALUES(?,?,?,?) ON CONFLICT(app_id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,updated=excluded.updated WHERE app_lifecycle.revision=?', (app_id, canonical(body.model_dump(exclude={'expected_revision'})), revision, time.time(), body.expected_revision)) if body.expected_revision else db.execute('INSERT INTO app_lifecycle VALUES(?,?,1,?) ON CONFLICT(app_id) DO NOTHING', (app_id, canonical(body.model_dump(exclude={'expected_revision'})), time.time()))
        if cursor.rowcount != 1:
            raise HTTPException(409, 'Lifecycle policy changed; reload before saving')
        db.execute('UPDATE app_platform SET revision=revision+1 WHERE app_id=?', (app_id,))
        db.execute('DELETE FROM runtime_sessions WHERE app_id=?', (app_id,))
        event(db, user['id'], 'app.lifecycle_changed', app_id, {'revision': revision, 'profile': body.profile})
    return {'revision': revision}


@router.post('/apps/{app_id}/submissions/{submission_id}/analytical-review')
def analytical_review(app_id: str, submission_id: str, body: AnalysisReview, user: User):
    auth.require_role(user, 'admin', 'reviewer')
    with connect() as db:
        app = hosting.app_permission(db, user, app_id, 'review')
        row = db.execute('SELECT * FROM submissions WHERE id=? AND app_id=?', (submission_id, app_id)).fetchone()
        if not row or row['status'] not in ('built', 'approved'):
            raise HTTPException(409, 'Analytical review requires a built image')
        if user['id'] in (app['owner'], row['submitter']):
            raise HTTPException(403, 'Independent analytical review is required')
        db.execute('INSERT INTO analytical_reviews VALUES(?,?,?,?,?,?) ON CONFLICT(submission_id) DO UPDATE SET image=excluded.image,reviewer=excluded.reviewer,evidence_uri=excluded.evidence_uri,evidence_sha256=excluded.evidence_sha256,created=excluded.created', (submission_id, row['image'], user['id'], body.evidence_uri, body.evidence_sha256, time.time()))
        event(db, user['id'], 'submission.analytical_reviewed', app_id, {'submission_id': submission_id, 'evidence_sha256': body.evidence_sha256})
    return {'recorded': True, 'note': 'Human review record; not an automated verification of evidence content'}


def job_app(db, job):
    table = {'build': 'submissions', 'deploy': 'deployments', 'agent': 'agent_changes'}[job['kind']]
    row = db.execute(f'SELECT app_id FROM {table} WHERE id=?', (job['target'],)).fetchone()
    return row['app_id'] if row else None


def terminal_job(db, job, state, detail):
    cursor = db.execute("UPDATE platform_jobs SET status=?,detail=?,lease_hash=NULL,lease_until=NULL WHERE id=? AND status IN ('queued','leased')", (state, detail, job['id']))
    if cursor.rowcount:
        table = {'build': 'submissions', 'deploy': 'deployments', 'agent': 'agent_changes'}[job['kind']]
        db.execute(f"UPDATE {table} SET status='failed' WHERE id=? AND status='queued'", (job['target'],))
    return bool(cursor.rowcount)


@router.post('/admin/jobs/{job_id}/action')
def job_action(job_id: str, body: JobAction, user: User):
    auth.require_role(user, 'admin')
    with connect() as db:
        job = db.execute('SELECT * FROM platform_jobs WHERE id=?', (job_id,)).fetchone()
        if not job or not can_inspect(db, user, job_app(db, job)):
            raise HTTPException(404, 'Job not found or not visible')
        if body.action == 'cancel':
            if not terminal_job(db, job, 'cancelled', 'OPERATOR_CANCELLED'):
                raise HTTPException(409, 'Job is no longer queued or leased')
        else:
            if job['status'] not in ('failed', 'dead_letter', 'cancelled') or job['kind'] == 'deploy':
                raise HTTPException(409, 'Retry only terminal build/agent jobs; deployments require a new admission request')
            table = 'submissions' if job['kind'] == 'build' else 'agent_changes'
            if db.execute(f"UPDATE {table} SET status='queued' WHERE id=? AND status='failed'", (job['target'],)).rowcount != 1:
                raise HTTPException(409, 'Target changed; submit a new job')
            db.execute("UPDATE platform_jobs SET status='queued',attempts=0,lease_hash=NULL,lease_until=NULL,detail=NULL WHERE id=?", (job_id,))
            db.execute('DELETE FROM job_lease_limits WHERE job_id=?', (job_id,))
        event(db, user['id'], 'job.' + body.action, job_app(db, job), {'job_id': job_id, 'reason': body.reason})
    return {'ok': True, 'note': 'Cancellation rejects future reports. The isolated worker must stop/clean up its external job.'}


@router.get('/admin/overview')
def admin_overview(user: User):
    auth.require_role(user, 'admin')
    with connect() as db:
        apps = []
        for row in db.execute('SELECT a.id,a.owner,a.payload,p.enabled,p.classification,p.active_submission,p.revision FROM apps a JOIN app_platform p ON p.app_id=a.id ORDER BY a.created DESC'):
            if not can_inspect(db, user, row['id']):
                continue
            sub = db.execute('SELECT * FROM submissions WHERE id=?', (row['active_submission'],)).fetchone()
            latest = db.execute('SELECT * FROM submissions WHERE app_id=? ORDER BY created DESC LIMIT 1', (row['id'],)).fetchone()
            selected = sub or latest
            admitted = bool(sub and sub['status'] == 'approved' and db.execute("SELECT 1 FROM deployments WHERE app_id=? AND submission_id=? AND environment='production' AND status='ready'", (row['id'], sub['id'])).fetchone())
            policy = lifecycle(db, row['id'])
            window = int(time.time() // 60) * 60
            usage = db.execute('SELECT requests FROM app_query_windows WHERE app_id=? AND window_start=?', (row['id'], window)).fetchone()
            apps.append({'id': row['id'], 'name': json.loads(row['payload'])['name'], 'owner': row['owner'], 'classification': row['classification'], 'enabled': bool(row['enabled']), 'active_version': sub['version'] if sub else None,
                         'latest_status': latest['status'] if latest else 'no upload', 'findings': hosting.findings(db, selected) if selected else ['Upload source to begin'], 'lifecycle': policy,
                         'runtime_admitted': admitted, 'requests_this_minute': usage['requests'] if usage else 0, 'can_share': can(db, user, row['id'], 'share'), 'can_deploy': can(db, user, row['id'], 'deploy')})
        visible = {a['id'] for a in apps}
        jobs = []
        for j in db.execute('SELECT * FROM platform_jobs ORDER BY created DESC LIMIT 500'):
            app_id = job_app(db, j)
            if app_id in visible:
                jobs.append({k: j[k] for k in ('id', 'kind', 'status', 'attempts', 'detail', 'created', 'lease_until')} | {'app_id': app_id})
        # Scoped events only. Never return lease tokens, source, query parameters or model prompts.
        visible_jobs = {j['id'] for j in jobs}
        audit = [dict(r) | {'details': json.loads(r['details'])} for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 500') if r['resource'] in visible or (r['resource'] in visible_jobs and r['action'].startswith('job.')) or r['action'].startswith(('user.', 'runtime_package.'))][:150]
        inventory = json.loads((ROOT / 'integrations/CONNECTIONS.json').read_text())
        connections = [{'id': c['id'], 'state': c['state'], 'acceptance': c['acceptance'], 'configuration_present': {k: bool(os.getenv(k)) for k in c['configuration']}} for c in inventory['connections']]
        external = [{'id': r['id'], 'name': json.loads(r['payload'])['name'], 'owner': r['owner'], 'version': r['published_version']} for r in db.execute('SELECT a.* FROM apps a LEFT JOIN app_platform p ON p.app_id=a.id WHERE p.app_id IS NULL')]
        return {'apps': apps, 'external_apps': external, 'jobs': jobs, 'audit': audit, 'connections': connections, 'demo': auth.DEMO,
                'pending_audit_delivery': db.execute('SELECT COUNT(*) AS n FROM audit_outbox WHERE delivered IS NULL').fetchone()['n'],
                'notes': ['Restricted apps require explicit app permissions and are otherwise omitted.', 'Configuration presence is not evidence of a live connection.', 'Query counts are gateway requests, not measured BigQuery spend.']}
