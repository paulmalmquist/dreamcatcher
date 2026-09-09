import hashlib
import hmac
import json
import os
import secrets
import time
from fastapi import HTTPException, Request
from .db import connect, event

DEMO = os.getenv('DC_DEMO', 'false').lower() == 'true'
PRODUCTION = os.getenv('DC_ENV', 'local') == 'production'
ORIGIN = os.getenv('DC_ORIGIN', 'http://localhost:8000').rstrip('/')
AUTH_MODE = os.getenv('DC_AUTH_MODE', 'local')

def password_hash(password):
    salt = secrets.token_bytes(16)
    return salt.hex() + ':' + hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()

def password_matches(password, encoded):
    try:
        salt, expected = encoded.split(':')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(expected, actual)
    except (ValueError, AttributeError):
        return False

def public_user(row):
    return {key: row[key] for key in ('id', 'email', 'name', 'role')} | {'groups': json.loads(row['groups_json'])}

def issue_session(db, user_id, scope='browser', app_id=None):
    token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(24)
    expiry = time.time() + (3600 if scope in ('sdk', 'developer') else 8 * 3600)
    db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',
               (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, expiry, scope, app_id))
    return token, csrf, expiry

def authenticate(request: Request):
    bearer = request.headers.get('authorization', '').startswith('Bearer ')
    token = request.headers['authorization'][7:] if bearer else request.cookies.get('dc_session')
    if not token:
        raise HTTPException(401, 'Sign in to Dreamcatcher')
    with connect() as db:
        row = db.execute('SELECT s.*,u.email,u.name,u.role,u.groups_json,u.enabled FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.hash=?',
                         (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        runtime = None
        if row and row['scope'] == 'sdk' and db.execute('SELECT 1 FROM app_platform WHERE app_id=?', (row['app_id'],)).fetchone():
            runtime = db.execute('SELECT * FROM runtime_sessions WHERE hash=?', (row['hash'],)).fetchone()
            if not runtime or runtime['expires'] < time.time():
                raise HTTPException(401, 'Hosted runtime token expired or was revoked')
    if not row or not row['enabled'] or row['expires'] < time.time():
        raise HTTPException(401, 'Session expired or revoked')
    if bearer != (row['scope'] in ('sdk', 'developer')):
        raise HTTPException(401, 'Wrong token type')
    runtime_path = request.url.path.startswith('/api/v2/runtime/' + str(row['app_id']) + '/')
    if bearer and row['scope'] == 'sdk' and not runtime_path and request.url.path not in ('/api/me', '/api/execute/query', '/api/execute/skill'):
        raise HTTPException(403, 'SDK token cannot administer the platform')
    if bearer and row['scope'] == 'developer':
        base = '/api/v2/apps/' + str(row['app_id'])
        path = request.url.path
        allowed = (path in ('/api/me', '/api/v2/contracts/app') and request.method == 'GET'
                   or path == base + '/overview' and request.method == 'GET'
                   or path == base + '/submissions' and request.method == 'POST'
                   or path.startswith(base + '/submissions/') and path.endswith('/source') and request.method == 'GET'
                   or path == base + '/agent' and request.method == 'GET'
                   or path == base + '/agent/changes' and request.method == 'POST')
        if not allowed:
            raise HTTPException(403, 'Developer token cannot grant access, approve, or deploy')
    if not bearer and request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), row['csrf']):
            raise HTTPException(403, 'Missing or invalid CSRF token')
        origin = request.headers.get('origin')
        if origin and origin != ORIGIN:
            raise HTTPException(403, 'Origin is not allowed')
    return {'id': row['user_id'], 'email': row['email'], 'name': row['name'], 'role': row['role'],
            'groups': json.loads(row['groups_json']), 'csrf': row['csrf'], 'session_hash': row['hash'],
            'token_app': row['app_id'] if bearer else None, 'scope': row['scope'],
            'submission_id': runtime['submission_id'] if runtime else None}

def require_role(user, *roles):
    if user['role'] not in roles:
        raise HTTPException(403, 'This action requires ' + ' or '.join(roles))

def app_permission(db, user, app_id, permission='run'):
    if db.execute('SELECT 1 FROM app_platform WHERE app_id=?', (app_id,)).fetchone():
        from .hosting import app_permission as hosted_permission
        return hosted_permission(db, user, app_id, 'use' if permission == 'run' else permission)
    row = db.execute('SELECT * FROM apps WHERE id=?', (app_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'App not found')
    if user['role'] == 'admin' or row['owner'] == user['id']:
        return dict(row)
    for grant in db.execute('SELECT subject,permission FROM grants WHERE app_id=?', (app_id,)):
        if grant['subject'] in ['workspace', 'user:' + user['id']] + ['group:' + x for x in user['groups']]:
            if permission == 'run' or grant['permission'] == 'edit':
                if row['published_version']:
                    return dict(row)
    raise HTTPException(403, 'App access denied')

def data_permission(user, payload):
    # Administrators do not automatically bypass data entitlements.
    if not set(user['groups']).intersection(payload.get('allowed_groups', [])):
        raise HTTPException(403, 'Your groups do not have access to this data capability')
