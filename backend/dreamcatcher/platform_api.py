"""Hosted-app control API and scoped runtime gateway. Workers have separate credentials."""
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import Field
from . import auth, hosting, governance, state_store, data_products
from .contracts import Strict, Grants, Manifest, Dependency, BuildReport, EditRequest, AgentProposal, StateWrite
from .db import canonical, connect, digest, event, asset

router = APIRouter(prefix='/api/v2')
User = Annotated[dict, Depends(auth.authenticate)]


class NewHostedApp(Strict):
    name: str = Field(min_length=1, max_length=70)
    description: str = Field(min_length=1, max_length=300)
    category: Literal['Manufacturing', 'Supply chain', 'Test & launch', 'Data & AI']
    classification: Literal['internal', 'restricted'] = 'internal'


class Deploy(Strict):
    environment: Literal['preview', 'production'] = 'preview'


class PackageRule(Dependency):
    approved: bool = True


class Candidate(Strict):
    version: str = Field(pattern=r'^\d+\.\d+\.\d+$')


def review_permission(db, user, app_id):
    auth.require_role(user, 'admin', 'reviewer')
    return hosting.app_permission(db, user, app_id, 'review')


def manage_or_review(db, user, app_id):
    try:
        hosting.app_permission(db, user, app_id, 'edit')
    except HTTPException:
        review_permission(db, user, app_id)


@router.get('/contracts/app')
def schema(user: User):
    return Manifest.model_json_schema()


@router.get('/capabilities')
def capabilities(user: User):
    return {'version': '2.0.0', 'contract': 'dreamcatcher/v1', 'hosting': 'worker-based',
            'workers_configured': {k: len(os.getenv('DC_WORKER_' + k.upper() + '_KEY', '')) >= 32 for k in ('build', 'deploy', 'agent', 'data')},
            'control_database': 'postgresql' if os.getenv('DC_DATABASE_URL') else 'local-sqlite',
            'state_database': 'postgresql' if os.getenv('DC_STATE_DATABASE_URL') else 'local-sqlite',
            'note': 'Queued work requires an independently configured worker. No deployment or scan is simulated.'}


@router.post('/apps', status_code=201)
def create_hosted(body: NewHostedApp, user: User):
    auth.require_role(user, 'builder', 'admin')
    identifier = secrets.token_hex(12)
    payload = body.model_dump() | {'url': '', 'owner': user['name'], 'initials': ''.join(s[0] for s in user['name'].split())[:2], 'theme': 'violet', 'kind': 'data'}
    with connect() as db:
        db.execute('INSERT INTO apps(id,owner,payload,created) VALUES(?,?,?,?)', (identifier, user['id'], canonical(payload), time.time()))
        db.execute('INSERT INTO app_platform(app_id,classification) VALUES(?,?)', (identifier, body.classification))
        event(db, user['id'], 'hosted_app.created', identifier)
    return {'id': identifier, 'status': 'private', 'classification': body.classification}


@router.get('/apps/{app_id}/overview')
def overview(app_id: str, user: User):
    with connect() as db:
        manage_or_review(db, user, app_id)
        p = dict(db.execute('SELECT * FROM app_platform WHERE app_id=?', (app_id,)).fetchone())
        rows = []
        for r in db.execute('SELECT * FROM submissions WHERE app_id=? ORDER BY created DESC', (app_id,)):
            rows.append({k: r[k] for k in ('id', 'version', 'status', 'source_digest', 'manifest_digest', 'image', 'submitter', 'reviewer', 'created')} | {'findings': hosting.findings(db, r), 'manifest': json.loads(r['manifest'])})
        return {**p, 'submissions': rows,
                'grants': [dict(r) for r in db.execute('SELECT subject,permission FROM capability_grants WHERE app_id=?', (app_id,))],
                'deployments': [dict(r) for r in db.execute('SELECT * FROM deployments WHERE app_id=? ORDER BY created DESC', (app_id,))],
                'agent': dict(r) if (r := db.execute('SELECT * FROM app_agents WHERE app_id=?', (app_id,)).fetchone()) else None}


@router.put('/apps/{app_id}/grants')
def grants(app_id: str, body: Grants, user: User):
    with connect() as db:
        hosting.app_permission(db, user, app_id, 'share')
        keys = {(g.subject, g.permission) for g in body.grants}
        if len(keys) != len(body.grants):
            raise HTTPException(422, 'Duplicate grant')
        cursor = db.execute('UPDATE app_platform SET revision=revision+1 WHERE app_id=? AND revision=?', (app_id, body.expected_revision))
        if cursor.rowcount != 1:
            raise HTTPException(409, 'Sharing changed; reload before saving')
        db.execute('DELETE FROM capability_grants WHERE app_id=?', (app_id,))
        db.executemany('INSERT INTO capability_grants VALUES(?,?,?)', [(app_id, g.subject, g.permission) for g in body.grants])
        db.execute('DELETE FROM runtime_sessions WHERE app_id=?', (app_id,))
        event(db, user['id'], 'app.capabilities_changed', app_id, body.model_dump())
    return {'revision': body.expected_revision + 1}


@router.post('/apps/{app_id}/suspend')
def suspend(app_id: str, user: User):
    with connect() as db:
        hosting.app_permission(db, user, app_id, 'share')
        db.execute('UPDATE app_platform SET enabled=0,revision=revision+1 WHERE app_id=?', (app_id,))
        db.execute('DELETE FROM runtime_sessions WHERE app_id=?', (app_id,))
        db.execute("UPDATE deployments SET status='revoked' WHERE app_id=? AND status IN ('queued','ready')", (app_id,))
        event(db, user['id'], 'app.suspended', app_id)
    return {'enabled': False}


@router.post('/apps/{app_id}/resume')
def resume(app_id: str, user: User):
    with connect() as db:
        hosting.app_permission(db, user, app_id, 'share')
        db.execute('UPDATE app_platform SET enabled=1,revision=revision+1 WHERE app_id=?', (app_id,))
        event(db, user['id'], 'app.resumed', app_id)
    return {'enabled': True}


@router.post('/apps/{app_id}/submissions', status_code=201)
async def upload(app_id: str, file: UploadFile, user: User):
    blob = await file.read(hosting.MAX_ARCHIVE + 1)
    with connect() as db:
        return hosting.submit(db, app_id, user, blob)


@router.get('/apps/{app_id}/submissions/{submission_id}/source')
def source(app_id: str, submission_id: str, user: User):
    with connect() as db:
        manage_or_review(db, user, app_id)
        row = db.execute('SELECT source_blob FROM submissions WHERE id=? AND app_id=?', (submission_id, app_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Source not found')
        event(db, user['id'], 'source.exported', app_id, {'submission_id': submission_id})
    return StreamingResponse(io.BytesIO(bytes(row['source_blob'])), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="source.zip"'})


@router.post('/apps/{app_id}/submissions/{submission_id}/approve')
def approve(app_id: str, submission_id: str, user: User):
    with connect() as db:
        app = review_permission(db, user, app_id)
        row = db.execute('SELECT * FROM submissions WHERE id=? AND app_id=?', (submission_id, app_id)).fetchone()
        if not row or row['status'] != 'built':
            raise HTTPException(409, 'Only a successfully built submission can be approved')
        if user['id'] in (app['owner'], row['submitter']):
            raise HTTPException(403, 'Independent review is required')
        problems = hosting.findings(db, row)
        if problems:
            raise HTTPException(409, problems)
        db.execute("UPDATE submissions SET status='approved',reviewer=? WHERE id=? AND status='built'", (user['id'], submission_id))
        event(db, user['id'], 'submission.approved', app_id, {'submission_id': submission_id, 'image': row['image']})
    return {'status': 'approved'}


@router.post('/apps/{app_id}/submissions/{submission_id}/revoke')
def revoke(app_id: str, submission_id: str, user: User):
    with connect() as db:
        review_permission(db, user, app_id)
        cursor = db.execute("UPDATE submissions SET status='revoked' WHERE id=? AND app_id=?", (submission_id, app_id))
        if not cursor.rowcount:
            raise HTTPException(404, 'Submission not found')
        db.execute('DELETE FROM runtime_sessions WHERE submission_id=?', (submission_id,))
        event(db, user['id'], 'submission.revoked', app_id, {'submission_id': submission_id})
    return {'status': 'revoked'}


@router.post('/apps/{app_id}/submissions/{submission_id}/deploy', status_code=202)
def deploy(app_id: str, submission_id: str, body: Deploy, user: User):
    with connect() as db:
        hosting.app_permission(db, user, app_id, 'deploy' if body.environment == 'production' else 'edit')
        row = db.execute('SELECT * FROM submissions WHERE id=? AND app_id=?', (submission_id, app_id)).fetchone()
        if not row or row['status'] not in (('approved',) if body.environment == 'production' else ('built', 'approved')) or hosting.findings(db, row):
            raise HTTPException(409, 'Release is not deployable under current policy')
        if not os.getenv('DC_WORKER_DEPLOY_KEY'):
            raise HTTPException(503, 'Configure a trusted deployment worker before deploying')
        identifier = secrets.token_hex(16)
        revision = db.execute('SELECT revision FROM app_platform WHERE app_id=?', (app_id,)).fetchone()['revision']
        db.execute('INSERT INTO deployments(id,app_id,submission_id,environment,status,requested_by,expected_revision,created) VALUES(?,?,?,?,?,?,?,?)', (identifier, app_id, submission_id, body.environment, 'queued', user['id'], revision, time.time()))
        queue_id = hosting.queue(db, 'deploy', identifier)
        event(db, user['id'], 'deployment.requested', app_id, {'deployment_id': identifier})
    return {'id': identifier, 'status': 'queued', 'job_id': queue_id}


@router.get('/runtime-packages')
def packages(user: User):
    auth.require_role(user, 'admin', 'reviewer')
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM runtime_packages ORDER BY ecosystem,name,version')]


@router.put('/runtime-packages')
def package_policy(body: PackageRule, user: User):
    auth.require_role(user, 'admin')
    with connect() as db:
        db.execute('INSERT INTO runtime_packages VALUES(?,?,?,?,?,?) ON CONFLICT(ecosystem,name,version,integrity) DO UPDATE SET source=excluded.source,approved=excluded.approved', (body.ecosystem, body.name, body.version, body.integrity, body.source, int(body.approved)))
        event(db, user['id'], 'runtime_package.policy', body.ecosystem + ':' + body.name, {'version': body.version, 'approved': body.approved})
    return {'ok': True}


@router.get('/data-products')
def products(user: User):
    with connect() as db:
        result = []
        for row in db.execute('SELECT * FROM data_products ORDER BY source'):
            p = json.loads(row['payload'])
            if user['role'] not in ('admin', 'reviewer') and not set(user['groups']).intersection(p['allowed_groups']):
                continue
            obs = db.execute('SELECT expires,observed FROM data_observations WHERE source=?', (row['source'],)).fetchone()
            result.append(p | {'digest': row['digest'], 'observation': dict(obs) if obs else None})
        return result


@router.put('/data-products')
def certify_product(body: data_products.Product, user: User):
    auth.require_role(user, 'admin')
    with connect() as db:
        old = db.execute('SELECT revision FROM data_products WHERE source=?', (body.source,)).fetchone()
        if body.revision != (old['revision'] + 1 if old else 1):
            raise HTTPException(409, 'Reload and use the next product revision')
        cursor = db.execute('INSERT INTO data_products VALUES(?,?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,digest=excluded.digest,enabled=excluded.enabled,updated=excluded.updated WHERE data_products.revision=excluded.revision-1', (body.source, body.revision, canonical(body.model_dump()), digest(body.model_dump()), int(body.enabled), time.time()))
        if cursor.rowcount != 1:
            raise HTTPException(409, 'Data-product policy changed concurrently; reload before saving')
        event(db, user['id'], 'data.product_policy', body.source, {'revision': body.revision, 'enabled': body.enabled})
    return {'digest': digest(body.model_dump()), 'revision': body.revision}


@router.get('/queries/{identifier}/{version}/validate')
def validate_query(identifier: str, version: str, user: User):
    with connect() as db:
        query = asset(db, 'query', identifier + '@' + version)
        if not query:
            raise HTTPException(404, 'Query not found')
        if user['id'] != query['owner'] and user['role'] not in ('admin', 'reviewer'):
            auth.data_permission(user, query['payload'])
        governance.query_validation(query['payload'])
        problems = data_products.findings(db, query['payload'])
        return {'valid': not problems, 'findings': problems, 'digest': query['digest'], 'status': query['status']}


@router.post('/apps/{app_id}/developer-token')
def developer_token(app_id: str, user: User):
    with connect() as db:
        hosting.app_permission(db, user, app_id, 'edit')
        value, _, expiry = auth.issue_session(db, user['id'], 'developer', app_id)
        event(db, user['id'], 'developer.token_created', app_id)
    return {'token': value, 'expires_at': expiry, 'app_id': app_id, 'scope': 'developer'}


@router.get('/apps/{app_id}/agent')
def agent(app_id: str, user: User):
    with connect() as db:
        manage_or_review(db, user, app_id)
        context = hosting.maintainer_context(db, app_id)
        return context | {'changes': [dict(r) | {'proposal': json.loads(r['proposal']) if r['proposal'] else None} for r in db.execute('SELECT * FROM agent_changes WHERE app_id=? ORDER BY created DESC', (app_id,))]}


@router.post('/apps/{app_id}/agent/changes', status_code=202)
def request_edit(app_id: str, body: EditRequest, user: User):
    with connect() as db:
        hosting.app_permission(db, user, app_id, 'edit')
        context = hosting.maintainer_context(db, app_id, body.submission_id)
        identifier = secrets.token_hex(16)
        db.execute('INSERT INTO agent_changes(id,app_id,submission_id,requester,prompt,component,status,created) VALUES(?,?,?,?,?,?,?,?)', (identifier, app_id, body.submission_id, user['id'], body.prompt, body.component, 'queued', time.time()))
        job_id = hosting.queue(db, 'agent', identifier)
        event(db, user['id'], 'agent.edit_requested', app_id, {'change_id': identifier, 'source_digest': context['source_digest']})
    return {'id': identifier, 'status': 'queued', 'job_id': job_id}


@router.post('/apps/{app_id}/agent/changes/{change_id}/candidate', status_code=201)
def accept_candidate(app_id: str, change_id: str, body: Candidate, user: User):
    with connect() as db:
        hosting.app_permission(db, user, app_id, 'edit')
        change = db.execute('SELECT * FROM agent_changes WHERE id=? AND app_id=?', (change_id, app_id)).fetchone()
        if not change or change['status'] != 'proposed':
            raise HTTPException(409, 'No pending proposal')
        current = db.execute('SELECT context_submission FROM app_agents WHERE app_id=?', (app_id,)).fetchone()
        if current['context_submission'] != change['submission_id']:
            raise HTTPException(409, 'A newer upload exists; request a change against the current context')
        if db.execute('UPDATE app_agents SET context_submission=context_submission WHERE app_id=? AND context_submission=?', (app_id, change['submission_id'])).rowcount != 1:
            raise HTTPException(409, 'App context changed during proposal acceptance')
        row = db.execute('SELECT * FROM submissions WHERE id=?', (change['submission_id'],)).fetchone()
        proposal = hosting.validate_proposal(row, json.loads(change['proposal']))
        manifest, files = hosting.unpack_source(bytes(row['source_blob']))
        for item in proposal['changes']:
            files[item['path']] = item['content'].encode()
        files['dreamcatcher.json'] = canonical(manifest.model_copy(update={'version': body.version}).model_dump()).encode()
        result = hosting.submit(db, app_id, user, hosting.pack_source(files))
        db.execute("UPDATE agent_changes SET status='candidate',candidate_submission=? WHERE id=?", (result['id'], change_id))
        event(db, user['id'], 'agent.candidate_created', app_id, {'change_id': change_id, 'submission_id': result['id']})
    return result


class QueryCall(Strict):
    reference: str = Field(max_length=120)
    parameters: dict = Field(default_factory=dict)


@router.get('/runtime/{app_id}/context')
def runtime_context(app_id: str, user: User):
    with connect() as db:
        row, manifest = hosting.runtime_release(db, user, app_id)
        return {'user': {k: user[k] for k in ('id', 'name', 'groups')}, 'app_id': app_id, 'submission_id': row['id'], 'version': row['version'], 'queries': manifest['queries'], 'skills': manifest['skills'], 'collections': manifest['collections']}


@router.post('/runtime/{app_id}/queries')
def query(app_id: str, body: QueryCall, user: User):
    with connect() as db:
        _, manifest = hosting.runtime_release(db, user, app_id)
        if body.reference not in manifest['queries']:
            raise HTTPException(403, 'Query is not declared by this release')
        result = governance.run_query(db, body.reference, body.parameters, user)
        event(db, user['id'], 'runtime.query', app_id, {'reference': body.reference, 'rows': len(result['rows'])})
        return result


def state_contract(db, user, app_id, collection, key):
    _, manifest = hosting.runtime_release(db, user, app_id)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}', key):
        raise HTTPException(422, 'Invalid record key')
    contract = next((c for c in manifest['collections'] if c['name'] == collection), None)
    if not contract:
        raise HTTPException(403, 'Collection is not declared by this release')
    return contract


@router.get('/runtime/{app_id}/state/{collection}/{key}')
def state_get(app_id: str, collection: str, key: str, user: User):
    with connect() as db:
        state_contract(db, user, app_id, collection, key)
        return state_store.get(app_id, user['id'], collection, key)


@router.put('/runtime/{app_id}/state/{collection}/{key}')
def state_put(app_id: str, collection: str, key: str, body: StateWrite, user: User):
    with connect() as db:
        contract = state_contract(db, user, app_id, collection, key)
        if len(canonical(body.value).encode()) > contract['max_bytes']:
            raise HTTPException(413, 'Record exceeds collection size limit')
        result = state_store.put(app_id, user['id'], collection, key, body)
        event(db, user['id'], 'runtime.state_write', app_id, {'collection': collection, 'version': result['version']})
        return result


class Telemetry(Strict):
    event: Literal['app.open', 'app.error']
    code: Literal['NONE', 'QUERY_FAILED', 'UNHANDLED'] = 'NONE'


@router.post('/runtime/{app_id}/events', status_code=202)
def telemetry(app_id: str, body: Telemetry, user: User):
    with connect() as db:
        hosting.runtime_release(db, user, app_id)
        event(db, user['id'], body.event, app_id, {'code': body.code})
    return {'ok': True}
