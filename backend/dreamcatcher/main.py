import hashlib
import io
import json
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import auth, governance as policy
from .db import ROOT, asset, canonical, connect, digest, event, migrate, put_asset

User = Annotated[dict, Depends(auth.authenticate)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Login(StrictModel):
    email: str = Field(max_length=200)
    password: str = Field(min_length=1, max_length=200)

class NewApp(StrictModel):
    name: str = Field(min_length=1, max_length=70)
    description: str = Field(min_length=1, max_length=300)
    category: Literal['Manufacturing','Supply chain','Test & launch','Data & AI']
    url: str = Field(max_length=2048)

class Grant(StrictModel):
    subject: str = Field(max_length=150)
    permission: Literal['run','edit'] = 'run'

class Sharing(StrictModel):
    grants: list[Grant] = Field(max_length=50)

class Execution(StrictModel):
    app_id: str = Field(max_length=80)
    reference: str = Field(max_length=120)
    parameters: dict = Field(default_factory=dict)

class Approval(StrictModel):
    action: Literal['approve','revoke']

class PackagePolicy(StrictModel):
    name: str = Field(max_length=150)
    version: str = Field(max_length=60)
    integrity: str = Field(max_length=200)
    source: str = Field(max_length=1000)
    approved: bool = True

class Account(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9-]{2,80}$')
    email: str = Field(max_length=200)
    name: str = Field(min_length=1,max_length=100)
    role: Literal['admin','reviewer','builder','viewer']
    groups: list[str] = Field(max_length=30)
    enabled: bool = True
    password: str | None = Field(default=None,min_length=14,max_length=200)

def set_cookie(response, token):
    response.set_cookie('dc_session', token, httponly=True, secure=auth.PRODUCTION, samesite='lax', max_age=28800, path='/')

@asynccontextmanager
async def lifespan(app):
    if auth.PRODUCTION and (auth.DEMO or auth.AUTH_MODE != 'oidc' or not auth.ORIGIN.startswith('https://')):
        raise RuntimeError('Production requires OIDC, HTTPS, and DC_DEMO=false')
    if auth.PRODUCTION and len(os.getenv('DC_SESSION_SECRET','')) < 32:
        raise RuntimeError('Set a strong persistent DC_SESSION_SECRET')
    if auth.PRODUCTION and not os.getenv('DC_DATABASE_URL'):
        raise RuntimeError('Production requires a managed PostgreSQL control database')
    if os.getenv('DC_AUTO_MIGRATE', 'false' if auth.PRODUCTION else 'true') == 'true':
        migrate()
    if auth.DEMO:
        from .seed import seed
        seed()
    yield

app = FastAPI(title='Dreamcatcher API',version='2.0.0',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url='/api/openapi.json')
from .platform_api import router as platform_router
from .workers import router as worker_router
from .launch import router as launch_router
from .operations import router as operations_router
app.include_router(platform_router)
app.include_router(worker_router)
app.include_router(launch_router)
app.include_router(operations_router)
app.add_middleware(SessionMiddleware,secret_key=os.getenv('DC_SESSION_SECRET') or secrets.token_hex(32),
                   session_cookie='dc_oidc_state',https_only=auth.PRODUCTION,same_site='lax',max_age=600)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=[x.strip() for x in os.getenv('DC_ALLOWED_HOSTS','localhost,127.0.0.1,testserver').split(',')])

@app.middleware('http')
async def boundaries(request, call_next):
    if request.method in ('POST','PUT','PATCH'):
        length = request.headers.get('content-length')
        limit = 6 * 1024 * 1024 if request.url.path == '/api/skills/import' else 2 * 1024 * 1024
        if request.url.path.startswith('/api/v2/apps/') and request.url.path.endswith('/submissions'):
            limit = 9 * 1024 * 1024
        if length is None:
            return Response('Content-Length is required',status_code=411)
        try:
            if int(length) < 0 or int(length) > limit:
                return Response('Request exceeds size limit',status_code=413)
        except ValueError:
            return Response('Invalid Content-Length',status_code=400)
        if request.headers.get('transfer-encoding'):
            return Response('Chunked writes are not supported',status_code=400)
        chunks, measured = [], 0
        async for chunk in request.stream():
            measured += len(chunk)
            if measured > limit:
                return Response('Request exceeds size limit', status_code=413)
            chunks.append(chunk)
        if measured != int(length):
            return Response('Content-Length does not match body', status_code=400)
        request._body = b''.join(chunks)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Cross-origin launch forms must preserve Origin for the edge's CSRF check.
    # strict-origin discloses no path/query; same-origin would serialize Origin:null.
    response.headers['Referrer-Policy'] = 'strict-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    if request.url.path.startswith(('/api','/auth')):
        response.headers['Cache-Control'] = 'no-store'
    if auth.PRODUCTION:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

@app.exception_handler(sqlite3.IntegrityError)
async def conflict(request, error):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':'This identity or version already exists; create a new immutable version'},status_code=409)

@app.get('/api/health')
def health():
    with connect() as db:
        db.execute('SELECT 1')
    return {'status':'ok','auth_mode':auth.AUTH_MODE,'demo':auth.DEMO}

@app.post('/api/login')
def login(body: Login, request: Request, response: Response):
    if auth.AUTH_MODE != 'local' or auth.PRODUCTION:
        raise HTTPException(403,'Password login is disabled')
    if request.headers.get('origin') and request.headers['origin'] != auth.ORIGIN:
        raise HTTPException(403,'Origin is not allowed')
    address = request.client.host if request.client else 'unknown'
    success = False
    with connect() as db:
        attempt = db.execute('SELECT * FROM login_attempts WHERE address=?',(address,)).fetchone()
        if attempt and attempt['reset_at'] > time.time() and attempt['attempts'] >= 8:
            raise HTTPException(429,'Too many sign-in attempts; wait 5 minutes')
        row = db.execute('SELECT * FROM users WHERE email=?',(body.email.lower(),)).fetchone()
        if row and row['enabled'] and auth.password_matches(body.password,row['password']):
            token,csrf,expiry=auth.issue_session(db,row['id'])
            db.execute('DELETE FROM login_attempts WHERE address=?',(address,))
            event(db,row['id'],'auth.login',row['id'])
            user = auth.public_user(row) | {'csrf':csrf,'expires':expiry,'demo':auth.DEMO}
            success = True
        else:
            attempts = attempt['attempts']+1 if attempt and attempt['reset_at']>time.time() else 1
            db.execute('INSERT INTO login_attempts VALUES(?,?,?) ON CONFLICT(address) DO UPDATE SET attempts=excluded.attempts,reset_at=excluded.reset_at',(address,attempts,time.time()+300))
    if not success:
        raise HTTPException(401,'Invalid credentials')
    set_cookie(response,token)
    return user

@app.get('/api/me')
def me(user: User):
    return {k:user[k] for k in ('id','email','name','role','groups','csrf')} | {'demo':auth.DEMO}

@app.post('/api/logout')
def logout(user: User,response: Response):
    with connect() as db:
        db.execute('DELETE FROM runtime_sessions WHERE hash IN (SELECT runtime_hash FROM edge_sessions WHERE parent_hash=?)', (user['session_hash'],))
        db.execute('DELETE FROM sessions WHERE hash IN (SELECT runtime_hash FROM edge_sessions WHERE parent_hash=?)', (user['session_hash'],))
        db.execute('DELETE FROM sessions WHERE hash=?',(user['session_hash'],))
        event(db,user['id'],'auth.logout',user['id'])
    response.delete_cookie('dc_session',path='/')
    return {'ok':True}

@app.get('/auth/login')
async def oidc_login(request: Request):
    if auth.AUTH_MODE != 'oidc':
        raise HTTPException(404,'OIDC is not configured')
    return await oauth_client().authorize_redirect(request,auth.ORIGIN+'/auth/callback',code_challenge_method='S256')

def oauth_client():
    from authlib.integrations.starlette_client import OAuth
    issuer = os.environ['DC_OIDC_ISSUER'].rstrip('/')
    if not issuer.startswith('https://'):
        raise HTTPException(503,'OIDC issuer must use HTTPS')
    oauth=OAuth()
    return oauth.register('company',client_id=os.environ['DC_OIDC_CLIENT_ID'],client_secret=os.environ['DC_OIDC_CLIENT_SECRET'],
                          server_metadata_url=issuer+'/.well-known/openid-configuration',client_kwargs={'scope':'openid email profile','code_challenge_method':'S256'})

@app.get('/auth/callback')
async def oidc_callback(request: Request):
    if auth.AUTH_MODE != 'oidc':
        raise HTTPException(404,'OIDC is not configured')
    try:
        token = await oauth_client().authorize_access_token(request)
        identity = token['userinfo']
    except Exception:
        raise HTTPException(401,'OIDC verification failed')
    # Membership is explicitly provisioned; never grant roles from arbitrary claims or matching email.
    identifier = 'oidc-' + hashlib.sha256((os.environ['DC_OIDC_ISSUER'].rstrip('/')+'|'+identity['sub']).encode()).hexdigest()[:32]
    with connect() as db:
        row = db.execute('SELECT * FROM users WHERE id=? AND enabled=1',(identifier,)).fetchone()
        if not row:
            raise HTTPException(403,'Your identity is not provisioned. Ask an administrator to bind your issuer and subject.')
        session,_,_=auth.issue_session(db,identifier)
        event(db,identifier,'auth.oidc_login',identifier)
    request.session.clear()
    response=RedirectResponse('/',status_code=303)
    set_cookie(response,session)
    return response

def app_view(db,row,user):
    p=json.loads(row['payload'])
    hosted = db.execute('SELECT * FROM app_platform WHERE app_id=?', (row['id'],)).fetchone()
    if hosted:
        sub = db.execute('SELECT * FROM submissions WHERE id=?', (hosted['active_submission'],)).fetchone()
        manifest = json.loads(sub['manifest']) if sub else {'queries': [], 'skills': []}
        return p | {'id': row['id'], 'ownerId': row['owner'], 'mine': row['owner'] == user['id'], 'hosted': True,
            'revision': hosted['revision'], 'saved': bool(db.execute('SELECT 1 FROM favorites WHERE user_id=? AND app_id=?', (user['id'],row['id'])).fetchone()),
            'status': 'Suspended' if not hosted['enabled'] else 'Published' if sub and sub['status'] == 'approved' else 'Private draft',
            'version': sub['version'] if sub else '0.1.0', 'grants': [], 'audience': 'Explicit capabilities',
            'queryRefs': manifest['queries'], 'skillRefs': manifest['skills'], 'queries': len(manifest['queries']), 'skills': len(manifest['skills'])}
    grants=[dict(r) for r in db.execute('SELECT subject,permission FROM grants WHERE app_id=?',(row['id'],))]
    published = row['published_version']
    release=db.execute('SELECT * FROM releases WHERE app_id=? AND version=?',(row['id'],published)).fetchone() if published else None
    manifest=json.loads(release['manifest']) if release else {'queries':[],'skills':[]}
    return p | {'id':row['id'],'ownerId':row['owner'],'mine':row['owner']==user['id'],'revision':row['revision'],
        'saved':bool(db.execute('SELECT 1 FROM favorites WHERE user_id=? AND app_id=?',(user['id'],row['id'])).fetchone()),
        'status':'Published' if published else 'Private draft','version':published or '0.1.0','grants':grants,
        'audience':', '.join(g['subject'].removeprefix('group:') for g in grants) or 'Private',
        'queryRefs':manifest.get('queries',[]),'skillRefs':manifest.get('skills',[]),
        'queries':len(manifest.get('queries',[])),'skills':len(manifest.get('skills',[]))}

@app.get('/api/state')
def state(user: User):
    with connect() as db:
        apps=[]
        for row in db.execute('SELECT * FROM apps ORDER BY created DESC').fetchall():
            try:
                if db.execute('SELECT 1 FROM app_platform WHERE app_id=?', (row['id'],)).fetchone():
                    from .hosting import app_permission
                    try:
                        app_permission(db, user, row['id'], 'discover')
                    except HTTPException:
                        app_permission(db, user, row['id'], 'review')
                elif user['role'] not in ('admin','reviewer'):
                    auth.app_permission(db,user,row['id'])
                apps.append(app_view(db,row,user))
            except HTTPException:
                continue
        assets={'queries':[],'skills':[]}
        for row in db.execute('SELECT * FROM assets ORDER BY id,version'):
            p=json.loads(row['payload'])
            if row['owner']!=user['id'] and user['role'] not in ('admin','reviewer') and not set(user['groups']).intersection(p.get('allowed_groups',[])):
                continue
            target='queries' if row['kind']=='query' else 'skills'
            assets[target].append(p|{'status':row['status'],'ownerId':row['owner'],'digest':row['digest'],'owner':row['owner'],
                'source':', '.join(p.get('sources',[])), 'query':(p.get('queries') or [''])[0], 'color':'violet','category':p.get('category','Data & AI'),
                'apps':sum((p['id']+'@'+p['version']) in a.get('queryRefs' if target=='queries' else 'skillRefs',[]) for a in apps)})
        return {'apps':apps,**assets,'packages':[dict(r)|{'purpose':'Exact-version policy','count':0} for r in db.execute('SELECT * FROM packages ORDER BY name,version')]}

@app.post('/api/apps',status_code=201)
def create_app(body: NewApp,user: User):
    auth.require_role(user,'builder','admin')
    policy.check_url(body.url)
    identifier=secrets.token_hex(12)
    payload=body.model_dump()|{'owner':user['name'],'initials':''.join(x[0] for x in user['name'].split())[:2], 'theme':'violet','kind':'data'}
    with connect() as db:
        db.execute('INSERT INTO apps(id,owner,payload,created) VALUES(?,?,?,?)',(identifier,user['id'],canonical(payload),time.time()))
        event(db,user['id'],'app.created',identifier)
        return app_view(db,db.execute('SELECT * FROM apps WHERE id=?',(identifier,)).fetchone(),user)

@app.post('/api/apps/{app_id}/favorite')
def favorite(app_id: str,user: User):
    with connect() as db:
        auth.app_permission(db,user,app_id)
        exists=db.execute('SELECT 1 FROM favorites WHERE user_id=? AND app_id=?',(user['id'],app_id)).fetchone()
        if exists:
            db.execute('DELETE FROM favorites WHERE user_id=? AND app_id=?',(user['id'],app_id))
        else:
            db.execute('INSERT INTO favorites VALUES(?,?)',(user['id'],app_id))
        return {'saved':not bool(exists)}

@app.put('/api/apps/{app_id}/sharing')
def share(app_id: str,body: Sharing,user: User):
    with connect() as db:
        row=auth.app_permission(db,user,app_id,'edit')
        if row['owner']!=user['id'] and user['role']!='admin':
            raise HTTPException(403,'Only the owner or an administrator can change sharing')
        if body.grants and not row['published_version']:
            raise HTTPException(409,'Approve and publish a release before granting team access')
        subjects=[]
        for grant in body.grants:
            if grant.subject!='workspace' and not grant.subject.startswith(('group:','user:')):
                raise HTTPException(422,'Subject must be workspace, group:name, or user:id')
            if grant.subject in subjects:
                raise HTTPException(422,'Duplicate sharing subject')
            subjects.append(grant.subject)
        db.execute('DELETE FROM grants WHERE app_id=?',(app_id,))
        db.executemany('INSERT INTO grants VALUES(?,?,?)',[(app_id,g.subject,g.permission) for g in body.grants])
        event(db,user['id'],'app.sharing_changed',app_id,body.model_dump())
    return {'ok':True}

@app.post('/api/apps/{app_id}/releases',status_code=201)
def create_release(app_id: str,body: dict,user: User):
    if set(body)-{'version','queries','skills','lockfile'} or not isinstance(body.get('version'),str) or not policy.VERSION.fullmatch(body.get('version','')):
        raise HTTPException(422,'Release requires exact version, query references, skill references, and lockfile')
    for key in ('queries','skills'):
        if not isinstance(body.get(key),list) or len(body[key])>100 or any(not isinstance(x,str) or len(x)>120 for x in body[key]):
            raise HTTPException(422,'Invalid references')
    policy.lock_inventory(body.get('lockfile',{}))
    with connect() as db:
        auth.app_permission(db,user,app_id,'edit')
        db.execute('INSERT INTO releases(app_id,version,manifest,digest,created) VALUES(?,?,?,?,?)',(app_id,body['version'],canonical(body),digest(body),time.time()))
        event(db,user['id'],'release.created',app_id+'@'+body['version'])
    return {'digest':digest(body),'version':body['version']}

@app.get('/api/apps/{app_id}/releases')
def releases(app_id: str,user: User):
    with connect() as db:
        if user['role'] not in ('admin','reviewer'):
            auth.app_permission(db,user,app_id,'edit')
        return [dict(r)|{'manifest':json.loads(r['manifest']),'findings':policy.readiness(db,json.loads(r['manifest']),json.loads(r['evidence']) if r['evidence'] else None,fresh=r['status']!='approved')} for r in db.execute('SELECT * FROM releases WHERE app_id=? ORDER BY created DESC',(app_id,))]

@app.post('/api/apps/{app_id}/releases/{version}/evidence')
def evidence(app_id: str,version: str,body: dict,user: User):
    with connect() as db:
        auth.app_permission(db,user,app_id,'edit')
        row=db.execute('SELECT * FROM releases WHERE app_id=? AND version=?',(app_id,version)).fetchone()
        if not row or row['status']!='pending':
            raise HTTPException(409,'Evidence can only attach to a pending release')
        if not policy.validate_evidence(json.loads(row['manifest']),body):
            raise HTTPException(422,'Build evidence signature, digest, scan status, or freshness is invalid')
        db.execute('UPDATE releases SET evidence=? WHERE app_id=? AND version=?',(canonical(body),app_id,version))
        event(db,user['id'],'release.evidence_attached',app_id+'@'+version)
    return {'ok':True}

@app.post('/api/apps/{app_id}/releases/{version}/approve')
def approve_release(app_id: str,version: str,user: User):
    auth.require_role(user,'reviewer','admin')
    with connect() as db:
        owner=db.execute('SELECT owner FROM apps WHERE id=?',(app_id,)).fetchone()
        row=db.execute('SELECT * FROM releases WHERE app_id=? AND version=?',(app_id,version)).fetchone()
        if not row or not owner:
            raise HTTPException(404,'Release not found')
        if owner['owner']==user['id']:
            raise HTTPException(403,'A different reviewer must approve this release')
        findings=policy.readiness(db,json.loads(row['manifest']),json.loads(row['evidence']) if row['evidence'] else None)
        if findings:
            raise HTTPException(409,findings)
        db.execute('UPDATE releases SET status=?,reviewer=? WHERE app_id=? AND version=?',('approved',user['id'],app_id,version))
        event(db,user['id'],'release.approved',app_id+'@'+version)
    return {'ok':True}

@app.post('/api/apps/{app_id}/publish/{version}')
def publish(app_id: str,version: str,user: User):
    with connect() as db:
        auth.app_permission(db,user,app_id,'edit')
        row=db.execute('SELECT * FROM releases WHERE app_id=? AND version=?',(app_id,version)).fetchone()
        if not row or row['status']!='approved':
            raise HTTPException(409,'Release must be approved first')
        findings=policy.readiness(db,json.loads(row['manifest']),json.loads(row['evidence']) if row['evidence'] else None, fresh=False)
        if findings:
            raise HTTPException(409,findings)
        db.execute('UPDATE apps SET published_version=?,revision=revision+1 WHERE id=?',(version,app_id))
        event(db,user['id'],'app.published',app_id,{'version':version})
    return {'ok':True}

@app.post('/api/apps/{app_id}/unpublish')
def unpublish(app_id: str,user: User):
    with connect() as db:
        auth.app_permission(db,user,app_id,'edit')
        db.execute('UPDATE apps SET published_version=NULL,revision=revision+1 WHERE id=?',(app_id,))
        db.execute('DELETE FROM grants WHERE app_id=?',(app_id,))
        event(db,user['id'],'app.unpublished',app_id)
    return {'ok':True}

@app.post('/api/queries',status_code=201)
def create_query(body: dict,user: User):
    auth.require_role(user,'builder','admin')
    allowed={'id','version','name','description','sql','connector','sources','grain','parameters','allowed_groups','data_contract'}
    if set(body)-allowed:
        raise HTTPException(422,'Unsupported query fields')
    result=policy.query_validation(body)
    with connect() as db:
        ref=put_asset(db,'query',body,user['id'])
        event(db,user['id'],'query.registered',ref)
    return {'reference':ref,'validation':result}

@app.post('/api/assets/{kind}/{identifier}/{version}/review')
def review_asset(kind: Literal['query','skill'],identifier: str,version: str,body: Approval,user: User):
    auth.require_role(user,'reviewer','admin')
    with connect() as db:
        ref=identifier+'@'+version
        row=asset(db,kind,ref)
        if not row:
            raise HTTPException(404,'Asset not found')
        if body.action=='approve':
            if row['owner']==user['id']:
                raise HTTPException(403,'A different reviewer must approve this asset')
            if kind=='query':
                policy.query_validation(row['payload'])
                from .data_products import enforce
                enforce(db, row['payload'])
            else:
                for q in row['payload']['queries']:
                    dep=asset(db,'query',q)
                    if not dep or dep['status']!='approved':
                        raise HTTPException(409,'Approve all referenced query versions first')
        status='approved' if body.action=='approve' else 'revoked'
        db.execute('UPDATE assets SET status=? WHERE kind=? AND id=? AND version=?',(status,kind,identifier,version))
        event(db,user['id'],kind+'.'+status,ref)
    return {'status':status}

@app.put('/api/packages')
def package_policy(body: PackagePolicy,user: User):
    auth.require_role(user,'admin')
    p=body.model_dump()
    policy.lock_inventory({'lockfileVersion':3,'packages':{'':{},'node_modules/'+body.name:p|{'resolved':p['source']}}})
    with connect() as db:
        db.execute('INSERT INTO packages VALUES(?,?,?,?,?) ON CONFLICT(name,version) DO UPDATE SET integrity=excluded.integrity,source=excluded.source,approved=excluded.approved',(body.name,body.version,body.integrity,body.source,int(body.approved)))
        event(db,user['id'],'package.policy_changed',body.name+'@'+body.version,{'approved':body.approved})
    return {'ok':True}

@app.post('/api/skills/import',status_code=201)
async def import_skill(file: UploadFile,user: User):
    auth.require_role(user,'builder','admin')
    manifest,blob=policy.unpack_skill(await file.read(5*1024*1024+1))
    with connect() as db:
        ref=put_asset(db,'skill',manifest,user['id'],blob=blob)
        event(db,user['id'],'skill.imported',ref,{'bundle_sha256':digest(blob),'approval':'pending'})
    return {'reference':ref,'status':'pending','bundle_sha256':digest(blob)}

@app.get('/api/skills/{identifier}/{version}/export')
def export_skill(identifier: str,version: str,user: User):
    with connect() as db:
        row=asset(db,'skill',identifier+'@'+version)
        if not row:
            raise HTTPException(404,'Skill not found')
        if row['owner']!=user['id'] and user['role'] not in ('admin','reviewer'):
            auth.data_permission(user,row['payload'])
        event(db,user['id'],'skill.exported',identifier+'@'+version)
    return StreamingResponse(io.BytesIO(row['blob']),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="{identifier}-{version}.zip"'})

def execution_manifest(db,body,user):
    if user.get('token_app') and user['token_app']!=body.app_id:
        raise HTTPException(403,'SDK token is bound to another app')
    app_row=auth.app_permission(db,user,body.app_id)
    if db.execute('SELECT 1 FROM app_platform WHERE app_id=?', (body.app_id,)).fetchone():
        from .hosting import runtime_release
        return runtime_release(db, user, body.app_id)[1]
    release=db.execute('SELECT * FROM releases WHERE app_id=? AND version=?',(body.app_id,app_row['published_version'])).fetchone()
    if not release or release['status']!='approved':
        raise HTTPException(409,'No approved published release')
    manifest=json.loads(release['manifest'])
    findings=policy.readiness(db,manifest,json.loads(release['evidence']) if release['evidence'] else None,fresh=False)
    if findings:
        raise HTTPException(409,findings)
    return manifest

@app.post('/api/execute/query')
def execute_query(body: Execution,user: User):
    with connect() as db:
        manifest=execution_manifest(db,body,user)
        if body.reference not in manifest['queries']:
            raise HTTPException(403,'Query is not in the approved app release')
        from .operations import budget
        budget(body.app_id, user['id'], body.reference)
        result=policy.run_query(db,body.reference,body.parameters,user)
        event(db,user['id'],'query.executed',body.reference,{'app_id':body.app_id,'rows':len(result['rows'])})
    return result

@app.post('/api/execute/skill')
def execute_skill(body: Execution,user: User):
    with connect() as db:
        manifest=execution_manifest(db,body,user)
        if body.reference not in manifest['skills']:
            raise HTTPException(403,'Skill is not in the approved app release')
        row=asset(db,'skill',body.reference)
        if not row or row['status']!='approved':
            raise HTTPException(409,'Skill is not approved')
        p=row['payload']
        auth.data_permission(user,p)
        results=[]
        for step in p['steps']:
            params={}
            for k,v in step['parameters'].items():
                if isinstance(v,str) and v.startswith('$input.'):
                    key=v[7:]
                    if key not in body.parameters:
                        raise HTTPException(422,'Missing skill input: '+key)
                    params[k]=body.parameters[key]
                else:
                    params[k]=v
            from .operations import budget
            budget(body.app_id, user['id'], step['query'])
            results.append(policy.run_query(db,step['query'],params,user))
        event(db,user['id'],'skill.executed',body.reference,{'app_id':body.app_id,'steps':len(results)})
    return {'results':results}

@app.post('/api/tokens')
def token(body: dict,user: User):
    with connect() as db:
        app_id=body.get('app_id','')
        auth.app_permission(db,user,app_id)
        hosted = db.execute('SELECT 1 FROM app_platform WHERE app_id=?', (app_id,)).fetchone()
        if hosted:
            from .hosting import runtime_release
            release, _ = runtime_release(db, user, app_id)
        token,_,expiry=auth.issue_session(db,user['id'],'sdk',app_id)
        if hosted:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            db.execute('INSERT INTO runtime_sessions VALUES(?,?,?,?,?)', (token_hash, token_hash, app_id, release['id'], expiry))
        event(db,user['id'],'sdk.token_created',app_id)
    return {'token':token,'expires_at':expiry,'scope':'execute','app_id':app_id}

@app.post('/api/tokens/revoke-all')
def revoke_tokens(user: User):
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE user_id=? AND scope IN ('sdk','developer')",(user['id'],))
        event(db,user['id'],'sdk.tokens_revoked',user['id'])
    return {'ok':True}

@app.get('/api/admin/users')
def users(user: User):
    auth.require_role(user,'admin')
    with connect() as db:
        return [auth.public_user(r)|{'enabled':bool(r['enabled'])} for r in db.execute('SELECT * FROM users')]

@app.put('/api/admin/users')
def put_user(body: Account,user: User):
    auth.require_role(user,'admin')
    if body.id==user['id'] and (not body.enabled or body.role!='admin'):
        raise HTTPException(409,'Do not remove your own administrator access')
    with connect() as db:
        current=db.execute('SELECT password FROM users WHERE id=?',(body.id,)).fetchone()
        password=auth.password_hash(body.password) if body.password else (current['password'] if current else None)
        db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET email=excluded.email,name=excluded.name,password=excluded.password,role=excluded.role,groups_json=excluded.groups_json,enabled=excluded.enabled',
                   (body.id,body.email.lower(),body.name,password,body.role,canonical(body.groups),int(body.enabled)))
        db.execute('DELETE FROM sessions WHERE user_id=?',(body.id,))
        event(db,user['id'],'user.updated',body.id,{'role':body.role,'groups':body.groups,'enabled':body.enabled})
    return {'ok':True}

@app.get('/api/audit')
def audit(user: User):
    auth.require_role(user,'admin','reviewer')
    with connect() as db:
        return [dict(r)|{'details':json.loads(r['details'])} for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 200')]

@app.get('/api/sdk/download')
def sdk_download(user: User):
    path=ROOT/'artifacts'/'dreamcatcher-sdk.tgz'
    if not path.exists():
        raise HTTPException(503,'Build the SDK with npm run build before downloading')
    return FileResponse(path,media_type='application/gzip',filename='dreamcatcher-sdk-1.0.0.tgz')

FRONTEND=ROOT/'frontend'/'dist'
if FRONTEND.exists():
    app.mount('/',StaticFiles(directory=FRONTEND,html=True),name='frontend')
