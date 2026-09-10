"""One-use browser handoff to a separately authenticated app edge.

WORK-CONNECT: private-edge. Never expose a runtime bearer token to browser JS.
The edge is a privileged service, not code shipped inside an uploaded app.
"""
import hashlib
import os
import secrets
import time
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from . import auth, hosting
from .contracts import Strict
from .db import connect, event
from .workers import authorize

router = APIRouter(prefix='/api/v2')
User = Annotated[dict, Depends(auth.authenticate)]


def runtime_origin(app_id):
    suffix = os.getenv('DC_APP_RUNTIME_SUFFIX', '')
    port = os.getenv('DC_APP_RUNTIME_PORT', '')
    if not suffix or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for c in suffix):
        raise HTTPException(503, 'App runtime domain is not configured')
    if port and (not port.isdigit() or not 1 <= int(port) <= 65535):
        raise HTTPException(503, 'App runtime port is invalid')
    return 'https://' + app_id + '.' + suffix + (':' + port if port and port != '443' else '')


def active_deployment(db, user, app_id):
    release, _ = hosting.runtime_release(db, user, app_id)
    deployment = db.execute("SELECT * FROM deployments WHERE app_id=? AND submission_id=? AND environment='production' AND status='ready' ORDER BY created DESC LIMIT 1", (app_id, release['id'])).fetchone()
    if not deployment or deployment['url'].rstrip('/') != runtime_origin(app_id):
        raise HTTPException(409, 'An admitted production deployment is required')
    return release


@router.post('/apps/{app_id}/launch')
def launch(app_id: str, user: User, response: Response):
    if len(os.getenv('DC_WORKER_EDGE_KEY', '')) < 32:
        raise HTTPException(503, 'The authenticated app edge is not connected')
    if user['scope'] != 'browser':
        raise HTTPException(403, 'Launch requires a browser session')
    with connect() as db:
        sub = active_deployment(db, user, app_id)
        revision = db.execute('SELECT revision FROM app_platform WHERE app_id=?', (app_id,)).fetchone()['revision']
        db.execute('DELETE FROM launch_tickets WHERE expires<? OR consumed=1', (time.time(),))
        # Bound outstanding tickets per login to prevent unlimited session storage.
        if db.execute('SELECT COUNT(*) AS n FROM launch_tickets WHERE parent_hash=?', (user['session_hash'],)).fetchone()['n'] >= 10:
            raise HTTPException(429, 'Too many pending launches; wait one minute')
        code = secrets.token_urlsafe(40)
        origin = runtime_origin(app_id)
        db.execute('INSERT INTO launch_tickets VALUES(?,?,?,?,?,?,?,?,0)', (hashlib.sha256(code.encode()).hexdigest(), user['session_hash'], user['id'], app_id, sub['id'], revision, origin, time.time() + 60))
        event(db, user['id'], 'app.launch_requested', app_id, {'submission_id': sub['id']})
    response.headers['Cache-Control'] = 'no-store'
    return {'action': origin + '/_dc/launch', 'code': code, 'expires_in': 60}


class Exchange(Strict):
    code: str = Field(min_length=40, max_length=100)
    app_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    origin: str = Field(max_length=300)


@router.post('/edge/exchange')
def exchange(body: Exchange, request: Request, response: Response):
    authorize(request, 'edge')
    with connect() as db:
        key = hashlib.sha256(body.code.encode()).hexdigest()
        ticket = db.execute('SELECT * FROM launch_tickets WHERE hash=?', (key,)).fetchone()
        if not ticket or ticket['consumed'] or ticket['expires'] < time.time() or ticket['app_id'] != body.app_id or ticket['origin'] != body.origin:
            raise HTTPException(401, 'Invalid or expired launch code')
        parent = db.execute("SELECT s.*,u.enabled,u.groups_json,u.name,u.email,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.hash=? AND s.scope='browser'", (ticket['parent_hash'],)).fetchone()
        if not parent or not parent['enabled'] or parent['expires'] < time.time():
            raise HTTPException(401, 'The originating login is no longer active')
        import json
        user = {'id': parent['user_id'], 'groups': json.loads(parent['groups_json']), 'role': parent['role']}
        release = active_deployment(db, user, body.app_id)
        revision = db.execute('SELECT revision FROM app_platform WHERE app_id=?', (body.app_id,)).fetchone()['revision']
        if release['id'] != ticket['submission_id'] or revision != ticket['revision']:
            raise HTTPException(409, 'App changed; launch again from the gallery')
        if db.execute('UPDATE launch_tickets SET consumed=1 WHERE hash=? AND consumed=0', (key,)).rowcount != 1:
            raise HTTPException(409, 'Launch code already consumed')
        token, _, expiry = auth.issue_session(db, user['id'], 'sdk', body.app_id)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expiry = min(expiry, parent['expires'])
        db.execute('UPDATE sessions SET expires=? WHERE hash=?', (expiry, token_hash))
        db.execute('INSERT INTO runtime_sessions VALUES(?,?,?,?,?)', (token_hash, token_hash, body.app_id, release['id'], expiry))
        db.execute('INSERT INTO edge_sessions VALUES(?,?)', (token_hash, ticket['parent_hash']))
        event(db, user['id'], 'app.launched', body.app_id, {'submission_id': release['id']})
    response.headers['Cache-Control'] = 'no-store'
    return {'token': token, 'expires_at': expiry, 'submission_id': release['id']}
