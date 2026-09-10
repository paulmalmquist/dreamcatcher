"""Leased jobs for separately operated builders, deployers and UI-edit agents.

The registry never executes uploaded code. Worker reports are privileged evidence,
not user-supplied checkboxes. WORK-CONNECT: isolated-build, private-hosting, app-agent.
"""
import hashlib
import hmac
import io
import json
import os
import secrets
import time
from typing import Literal
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field
from . import hosting, data_products
from .contracts import Strict, BuildReport
from .db import connect, canonical, event

router = APIRouter(prefix='/api/v2/workers')
Kind = Literal['build', 'deploy', 'agent']


def authorize(request, kind):
    expected = os.getenv('DC_WORKER_' + kind.upper() + '_KEY', '')
    if len(expected) < 32:
        raise HTTPException(503, 'Trusted ' + kind + ' worker is not configured')
    if not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + expected):
        raise HTTPException(401, 'Invalid worker credential')


def leased(db, kind, job_id, lease):
    row = db.execute('SELECT * FROM platform_jobs WHERE id=? AND kind=?', (job_id, kind)).fetchone()
    if not row or row['status'] != 'leased' or row['lease_until'] < time.time() or not hmac.compare_digest(row['lease_hash'], hashlib.sha256(lease.encode()).hexdigest()):
        raise HTTPException(409, 'Lease is expired, completed, or does not match')
    return row


@router.post('/{kind}/claim')
def claim(kind: Kind, request: Request):
    authorize(request, kind)
    with connect() as db:
        from .operations import terminal_job, job_app
        for exhausted in db.execute("SELECT * FROM platform_jobs WHERE kind=? AND status='leased' AND lease_until<? AND attempts>=3", (kind, time.time())).fetchall():
            if terminal_job(db, exhausted, 'dead_letter', 'LEASES_EXHAUSTED'):
                event(db, 'worker:' + kind, 'job.dead_letter', job_app(db, exhausted), {'job_id': exhausted['id']})
        row = db.execute("SELECT * FROM platform_jobs WHERE kind=? AND attempts<3 AND (status='queued' OR (status='leased' AND lease_until<?)) ORDER BY created LIMIT 1", (kind, time.time())).fetchone()
        if not row:
            return {'job': None}
        token = secrets.token_urlsafe(40)
        until = time.time() + 900
        cursor = db.execute("UPDATE platform_jobs SET status='leased',lease_hash=?,lease_until=?,attempts=attempts+1 WHERE id=? AND attempts=? AND (status='queued' OR (status='leased' AND lease_until<?))", (hashlib.sha256(token.encode()).hexdigest(), until, row['id'], row['attempts'], time.time()))
        if cursor.rowcount != 1:
            return {'job': None}
        db.execute('INSERT INTO job_lease_limits VALUES(?,?) ON CONFLICT(job_id) DO UPDATE SET deadline=excluded.deadline', (row['id'], time.time() + 3600))
        job = {'id': row['id'], 'kind': kind, 'target': row['target'], 'lease': token, 'expires_at': until}
        if kind == 'build':
            sub = db.execute('SELECT * FROM submissions WHERE id=?', (row['target'],)).fetchone()
            job.update({k: sub[k] for k in ('app_id', 'source_digest', 'manifest_digest')})
            job['manifest'] = json.loads(sub['manifest'])
        elif kind == 'deploy':
            deployment = db.execute('SELECT * FROM deployments WHERE id=?', (row['target'],)).fetchone()
            sub = db.execute('SELECT * FROM submissions WHERE id=?', (deployment['submission_id'],)).fetchone()
            job.update({'deployment': dict(deployment), 'image': sub['image'], 'manifest': json.loads(sub['manifest']), 'source_digest': sub['source_digest']})
        else:
            change = db.execute('SELECT * FROM agent_changes WHERE id=?', (row['target'],)).fetchone()
            job.update({'request': change['prompt'], 'component': change['component'], 'context': hosting.maintainer_context(db, change['app_id'], change['submission_id'])})
        return {'job': job}


class LeaseProof(Strict):
    lease: str = Field(min_length=20, max_length=100)


@router.post('/{kind}/jobs/{job_id}/heartbeat')
def heartbeat(kind: Kind, job_id: str, body: LeaseProof, request: Request):
    authorize(request, kind)
    with connect() as db:
        job = leased(db, kind, job_id, body.lease)
        limit = db.execute('SELECT deadline FROM job_lease_limits WHERE job_id=?', (job_id,)).fetchone()
        if not limit or limit['deadline'] <= time.time():
            raise HTTPException(409, 'Lease reached its one-hour hard deadline')
        until = min(time.time() + 900, limit['deadline'])
        if db.execute("UPDATE platform_jobs SET lease_until=? WHERE id=? AND status='leased' AND lease_hash=? AND lease_until>=?", (until, job_id, job['lease_hash'], time.time())).rowcount != 1:
            raise HTTPException(409, 'Lease changed during renewal')
    return {'expires_at': until, 'hard_deadline': limit['deadline']}


@router.get('/{kind}/jobs/{job_id}/source')
def source(kind: Kind, job_id: str, request: Request):
    authorize(request, kind)
    if kind == 'deploy':
        raise HTTPException(403, 'Deployment workers receive image digests, not source')
    with connect() as db:
        job = leased(db, kind, job_id, request.headers.get('x-job-lease', ''))
        target = job['target']
        if kind == 'agent':
            target = db.execute('SELECT submission_id FROM agent_changes WHERE id=?', (target,)).fetchone()['submission_id']
        blob = db.execute('SELECT source_blob FROM submissions WHERE id=?', (target,)).fetchone()['source_blob']
    return StreamingResponse(io.BytesIO(bytes(blob)), media_type='application/zip')


class Report(Strict):
    lease: str = Field(min_length=20, max_length=100)
    result: dict = Field(default_factory=dict)
    failure_code: Literal['BUILD_FAILED', 'POLICY_FAILED', 'HOSTING_FAILED', 'MODEL_FAILED'] | None = None


class Deployed(Strict):
    image: str
    url: str = Field(max_length=1000)
    checks: dict[str, bool]


@router.post('/{kind}/jobs/{job_id}/report')
def report(kind: Kind, job_id: str, body: Report, request: Request):
    authorize(request, kind)
    with connect() as db:
        job = leased(db, kind, job_id, body.lease)
        # CAS first in this transaction: two concurrent reports cannot both commit.
        if db.execute("UPDATE platform_jobs SET status='completed',lease_hash=NULL,lease_until=NULL WHERE id=? AND status='leased' AND lease_hash=?", (job_id, job['lease_hash'])).rowcount != 1:
            raise HTTPException(409, 'Job already completed')
        if body.failure_code:
            db.execute("UPDATE platform_jobs SET status='failed',detail=? WHERE id=?", (body.failure_code, job_id))
            table = {'build': 'submissions', 'agent': 'agent_changes', 'deploy': 'deployments'}[kind]
            db.execute(f"UPDATE {table} SET status='failed' WHERE id=? AND status NOT IN ('approved','revoked')", (job['target'],))
            event(db, 'worker:' + kind, 'job.failed', job_id, {'code': body.failure_code})
            return {'status': 'failed'}
        try:
            if kind == 'build':
                parsed = BuildReport.model_validate(body.result)
                sub = db.execute('SELECT * FROM submissions WHERE id=?', (job['target'],)).fetchone()
                if sub['status'] != 'queued' or parsed.source_digest != sub['source_digest'] or parsed.manifest_digest != sub['manifest_digest']:
                    raise HTTPException(409, 'Build report does not match pending source')
                db.execute("UPDATE submissions SET status='built',image=?,evidence=? WHERE id=?", (parsed.image, canonical(parsed.model_dump()), sub['id']))
                record_assurance(db, sub['id'], parsed.image, all(parsed.checks.get(k) is True for k in hosting.REQUIRED_CHECKS))
            elif kind == 'agent':
                change = db.execute('SELECT * FROM agent_changes WHERE id=?', (job['target'],)).fetchone()
                sub = db.execute('SELECT * FROM submissions WHERE id=?', (change['submission_id'],)).fetchone()
                proposal = hosting.validate_proposal(sub, body.result)
                db.execute("UPDATE agent_changes SET status='proposed',proposal=? WHERE id=?", (canonical(proposal), change['id']))
            else:
                parsed = Deployed.model_validate(body.result)
                deployment = db.execute('SELECT * FROM deployments WHERE id=?', (job['target'],)).fetchone()
                sub = db.execute('SELECT * FROM submissions WHERE id=?', (deployment['submission_id'],)).fetchone()
                platform = db.execute('SELECT * FROM app_platform WHERE app_id=?', (deployment['app_id'],)).fetchone()
                allowed = ('approved',) if deployment['environment'] == 'production' else ('built', 'approved')
                if deployment['status'] != 'queued' or not platform['enabled'] or sub['status'] not in allowed or hosting.findings(db, sub):
                    raise HTTPException(409, 'Deployment admission changed while worker ran')
                url = urlsplit(parsed.url)
                suffix = os.getenv('DC_APP_RUNTIME_SUFFIX', '')
                port = os.getenv('DC_APP_RUNTIME_PORT', '')
                if port and (not port.isdigit() or not 1 <= int(port) <= 65535):
                    raise HTTPException(503, 'Invalid runtime port')
                expected_host = deployment['app_id'] + ('-preview' if deployment['environment'] == 'preview' else '') + '.' + suffix
                checks = ('private_ingress', 'edge_auth', 'egress_policy', 'health', 'digest_verified', 'resources', 'no_workload_data_credentials')
                if parsed.image != sub['image'] or not suffix or url.scheme != 'https' or url.hostname != expected_host or (url.port or 443) != int(port or 443) or url.username or url.password or url.query or url.fragment or url.path not in ('', '/') or not all(parsed.checks.get(k) is True for k in checks):
                    raise HTTPException(422, 'Private routing, image identity, or deployment checks failed')
                db.execute("UPDATE deployments SET status='ready',url=?,detail=? WHERE id=?", (parsed.url, canonical(parsed.checks), deployment['id']))
                if deployment['environment'] == 'production':
                    cursor = db.execute('UPDATE app_platform SET active_submission=?,revision=revision+1 WHERE app_id=? AND revision=?', (sub['id'], sub['app_id'], deployment['expected_revision']))
                    if cursor.rowcount != 1:
                        raise HTTPException(409, 'App changed during deployment; re-admit with current permissions and revision')
                    db.execute('DELETE FROM runtime_sessions WHERE app_id=?', (sub['app_id'],))
            event(db, 'worker:' + kind, 'job.completed', job_id, {'target': job['target']})
        except ValueError:
            raise HTTPException(422, 'Worker report does not satisfy its typed contract') from None
    return {'status': 'completed'}


def record_assurance(db, submission_id, image, passed):
    validity = max(60, min(604800, int(os.getenv('DC_SCAN_VALIDITY_SECONDS', '86400'))))
    db.execute('INSERT INTO release_assurance VALUES(?,?,?,?,?) ON CONFLICT(submission_id) DO UPDATE SET image=excluded.image,observed=excluded.observed,expires=excluded.expires,passed=excluded.passed', (submission_id, image, time.time(), time.time() + validity, int(passed)))


class Rescan(Strict):
    submission_id: str = Field(max_length=80)
    image: str = Field(max_length=600)
    passed: bool
    evidence_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    evidence_uri: str = Field(pattern=r'^(?:gs://|https://)[^\s]+$', max_length=1000)


@router.post('/build/rescan')
def rescan(body: Rescan, request: Request):
    authorize(request, 'build')
    with connect() as db:
        row = db.execute('SELECT * FROM submissions WHERE id=?', (body.submission_id,)).fetchone()
        if not row or row['image'] != body.image or row['status'] not in ('built', 'approved'):
            raise HTTPException(409, 'Rescan must bind an existing built image')
        record_assurance(db, row['id'], body.image, body.passed)
        event(db, 'worker:build', 'image.rescanned', row['app_id'], body.model_dump())
    return {'recorded': True}


@router.post('/data/observations')
def observation(body: data_products.Observation, request: Request):
    authorize(request, 'data')
    with connect() as db:
        data_products.observe(db, body)
        event(db, 'worker:data', 'data.observed', body.source, {'product_digest': body.product_digest, 'evidence_sha256': body.evidence_sha256})
    return {'ok': True}
