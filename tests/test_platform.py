import io,json,zipfile,time,hashlib,hmac
import pytest
from fastapi import HTTPException
from conftest import login
from dreamcatcher import governance as g
from dreamcatcher.db import canonical,digest

EXEC={'app_id':'build-readiness','reference':'assembly-readiness@1.0.0','parameters':{'program_id':'terran-r'}}

def test_packaged_sdk_and_frontend(client):
    from dreamcatcher.db import ROOT
    if not (ROOT/'frontend/dist/index.html').exists() or not (ROOT/'artifacts/dreamcatcher-sdk.tgz').exists():
        pytest.skip('Run npm run build for distribution smoke test')
    assert client.get('/').status_code==200
    assert client.get('/api/sdk/download').status_code==401
    login(client)
    r=client.get('/api/sdk/download')
    assert r.status_code==200
    assert r.content[:2]==b'\x1f\x8b'

def test_login_and_persistent_favorite(client):
    assert client.get('/api/state').status_code==401
    login(client)
    assert len(client.get('/api/state').json()['apps'])==6
    assert client.post('/api/apps/build-readiness/favorite').status_code==200
    assert next(a for a in client.get('/api/state').json()['apps'] if a['id']=='build-readiness')['saved']

def test_csrf(client):
    login(client)
    client.headers.pop('X-CSRF-Token')
    assert client.post('/api/apps/build-readiness/favorite').status_code==403

def test_query_and_skill(client):
    login(client,'viewer')
    r=client.post('/api/execute/query',json=EXEC)
    assert r.status_code==200,r.text
    assert len(r.json()['rows'])==4
    r=client.post('/api/execute/skill',json={**EXEC,'reference':'review-build-readiness@1.0.0'})
    assert r.status_code==200,r.text
    assert len(r.json()['results'][0]['rows'])==4

def test_sharing_is_not_data_permission(client):
    login(client,'outsider')
    assert len(client.get('/api/state').json()['apps'])==6
    assert client.post('/api/execute/query',json=EXEC).status_code==403

def test_sdk_scope_and_binding(client):
    login(client)
    token=client.post('/api/tokens',json={'app_id':'build-readiness'}).json()['token']
    client.cookies.clear()
    client.headers['Authorization']='Bearer '+token
    assert client.post('/api/execute/query',json=EXEC).status_code==200
    assert client.get('/api/state').status_code==403
    assert client.post('/api/execute/query',json={**EXEC,'app_id':'supply-radar'}).status_code==403

def test_revoke_blocks_existing_release(client):
    login(client,'reviewer')
    assert client.post('/api/assets/query/assembly-readiness/1.0.0/review',json={'action':'revoke'}).status_code==200
    login(client,'viewer')
    assert client.post('/api/execute/query',json=EXEC).status_code==409

def test_private_draft_and_immutable_version(client):
    login(client)
    r=client.post('/api/apps',json={'name':'New app','description':'Test','category':'Data & AI','url':'https://example.com/app'})
    assert r.status_code==201,r.text
    appid=r.json()['id']
    manifest={'version':'1.0.0','queries':[],'skills':[],'lockfile':{'lockfileVersion':3,'packages':{'':{}}}}
    assert client.post(f'/api/apps/{appid}/releases',json=manifest).status_code==201
    assert client.post(f'/api/apps/{appid}/releases',json=manifest).status_code==409
    assert client.put(f'/api/apps/{appid}/sharing',json={'grants':[{'subject':'workspace','permission':'run'}]}).status_code==409
    login(client,'reviewer')
    assert client.post(f'/api/apps/{appid}/releases/1.0.0/approve').status_code==409

def test_query_parameters_are_bound(client):
    login(client)
    r=client.post('/api/execute/query',json={**EXEC,'parameters':{'program_id':"terran-r' OR 1=1 --"}})
    assert r.status_code==200,r.text
    assert r.json()['rows']==[]
    assert client.post('/api/execute/query',json={**EXEC,'parameters':{'program_id':3}}).status_code==422

def test_export_import_requires_review(client):
    login(client)
    r=client.get('/api/skills/review-build-readiness/1.0.0/export')
    assert r.status_code==200
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(r.content)) as old,zipfile.ZipFile(out,'w') as new:
        for name in old.namelist():
            value=old.read(name)
            if name=='manifest.json':
                m=json.loads(value);m['version']='1.0.1';value=json.dumps(m).encode()
            new.writestr(name,value)
    r=client.post('/api/skills/import',files={'file':('skill.zip',out.getvalue(),'application/zip')})
    assert r.status_code==201,r.text
    assert r.json()['status']=='pending'

@pytest.mark.parametrize('path',['../bad.txt','/absolute.txt','.env','credentials.json'])
def test_unsafe_skill_rejected(path):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr(path,'data')
    with pytest.raises(HTTPException):g.unpack_skill(b.getvalue())

@pytest.mark.parametrize('evidence',[{}, {'payload':[],'signature':'x'},{'payload':{},'signature':123},{'payload':{'issued_at':'bad','artifact_sha256':3},'signature':'x'}])
def test_malformed_evidence_fails_closed(evidence):
    assert not g.validate_evidence({},evidence)

def test_package_inventory_transitive():
    import base64
    p={'version':'1.0.0','integrity':'sha512-'+base64.b64encode(bytes(64)).decode(),'resolved':'https://registry.npmjs.org/a/-/a-1.0.0.tgz'}
    lock={'lockfileVersion':3,'packages':{'':{'dependencies':{'a':'1.0.0'}},'node_modules/a':p,'node_modules/a/node_modules/b':p}}
    assert [r['name'] for r in g.lock_inventory(lock)]==['a','b']
    lock['packages']['node_modules/a']['hasInstallScript']=True
    with pytest.raises(HTTPException):g.lock_inventory(lock)

def test_complete_release_review_publish_and_unshare(client):
    import os
    login(client)
    appid=client.post('/api/apps',json={'name':'Release test','description':'Test','category':'Manufacturing','url':'https://example.com'}).json()['id']
    manifest={'version':'1.0.0','queries':['assembly-readiness@1.0.0'],'skills':[],'lockfile':{'lockfileVersion':3,'packages':{'':{}}}}
    assert client.post(f'/api/apps/{appid}/releases',json=manifest).status_code==201
    p={'manifest_sha256':digest(manifest),'lock_sha256':digest(manifest['lockfile']),'artifact_sha256':'a'*64,'security_scan':'passed','issued_at':time.time()}
    evidence={'payload':p,'signature':hmac.new(os.environ['DC_BUILD_SIGNING_KEY'].encode(),canonical(p).encode(),hashlib.sha256).hexdigest()}
    assert client.post(f'/api/apps/{appid}/releases/1.0.0/evidence',json=evidence).status_code==200
    login(client,'reviewer')
    assert client.post(f'/api/apps/{appid}/releases/1.0.0/approve').status_code==200
    login(client)
    assert client.post(f'/api/apps/{appid}/publish/1.0.0').status_code==200
    assert client.put(f'/api/apps/{appid}/sharing',json={'grants':[{'subject':'group:Manufacturing','permission':'run'}]}).status_code==200
    login(client,'viewer')
    assert client.post('/api/execute/query',json={**EXEC,'app_id':appid}).status_code==200
    login(client)
    assert client.post(f'/api/apps/{appid}/unpublish').status_code==200
    login(client,'viewer')
    assert client.post('/api/execute/query',json={**EXEC,'app_id':appid}).status_code==403

@pytest.mark.parametrize('sql',['DELETE FROM assembly_readiness','SELECT * FROM assembly_readiness','SELECT assembly_id FROM assembly_readiness; SELECT 1','SELECT readfile(assembly_id) FROM assembly_readiness'])
def test_unsafe_query_rejected(sql):
    with pytest.raises(HTTPException):g.query_validation({'id':'unsafe-query','version':'1.0.0','sql':sql,'connector':'sqlite','sources':['assembly_readiness'],'grain':'assembly','parameters':{},'allowed_groups':['Manufacturing']})

def test_account_disable_revokes_sessions(client):
    login(client,'viewer')
    token=client.post('/api/tokens',json={'app_id':'build-readiness'}).json()['token']
    login(client,'admin')
    r=client.put('/api/admin/users',json={'id':'viewer','email':'viewer@demo.local','name':'Viewer','role':'viewer','groups':['Manufacturing'],'enabled':False})
    assert r.status_code==200,r.text
    client.cookies.clear();client.headers['Authorization']='Bearer '+token
    assert client.post('/api/execute/query',json=EXEC).status_code==401

def test_artifact_tampering_invalidates_evidence():
    import os
    manifest={'lockfile':{}}
    p={'manifest_sha256':digest(manifest),'lock_sha256':digest({}),'artifact_sha256':'a'*64,'security_scan':'passed','issued_at':time.time()}
    e={'payload':p,'signature':hmac.new(os.environ['DC_BUILD_SIGNING_KEY'].encode(),canonical(p).encode(),hashlib.sha256).hexdigest()}
    assert g.validate_evidence(manifest,e)
    p['artifact_sha256']='b'*64
    assert not g.validate_evidence(manifest,e)
