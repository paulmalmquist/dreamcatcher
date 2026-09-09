"""Explicit, idempotent local demo. Never loaded with DC_DEMO=false."""
import hashlib
import hmac
import io
import json
import os
import sqlite3
import time
import zipfile
from .db import DATA, asset, canonical, connect, digest, put_asset
from .auth import password_hash

def seed():
    if len(os.getenv('DC_BUILD_SIGNING_KEY','')) < 32:
        raise RuntimeError('Demo requires DC_BUILD_SIGNING_KEY; scripts/setup.py generates one')
    with connect() as db:
        if db.execute("SELECT 1 FROM users WHERE id='builder'").fetchone():
            return
        for identifier,name,role,groups in [('builder','Paul Malmquist','builder',['Manufacturing','Supply chain','Test & launch','Data & AI']),('reviewer','Demo Reviewer','reviewer',['Data & AI']),('admin','Demo Administrator','admin',['Manufacturing','Supply chain','Test & launch','Data & AI']),('viewer','Demo Teammate','viewer',['Manufacturing']),('outsider','Restricted Teammate','viewer',['Other'])]:
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(identifier,identifier+'@demo.local',name,password_hash(os.getenv('DC_DEMO_PASSWORD','Dreamcatcher-local-1!')),role,canonical(groups)))
        definitions=[
            ('assembly-readiness','assembly_readiness',['assembly_id','system_name','readiness_pct'],'One row per assembly','Manufacturing'),
            ('supplier-delivery-risk','supplier_delivery_risk',['po_line_id','supplier_name','risk_level'],'One row per PO line','Supply chain'),
            ('test-run-summary','test_run_summary',['test_run_id','campaign_name','result'],'One row per test run','Test & launch'),
            ('catalog-lineage','catalog_lineage',['object_id','object_name','upstream_ids'],'One row per data object','Data & AI')]
        for identifier,table,fields,grain,group in definitions:
            p={'id':identifier,'version':'1.0.0','name':table,'description':'Local synthetic demonstration data','connector':'sqlite','sources':[table],
               'sql':'SELECT '+', '.join(fields)+' FROM '+table+' WHERE program_id = @program_id AND authorized_user = @_user_id',
               'grain':grain,'parameters':{'program_id':'string'},'allowed_groups':[group]}
            put_asset(db,'query',p,'builder','approved')
        sk={'id':'review-build-readiness','version':'1.0.0','name':'Review build readiness','description':'Retrieve the caller’s authorized assembly readiness records.',
            'runtime':'declarative-query-v1','queries':['assembly-readiness@1.0.0'],'packages':[],'tools':['queries.run'],'allowed_groups':['Manufacturing'],
            'inputs':{'program_id':'string'},'logical_connections':['warehouse'],
            'steps':[{'query':'assembly-readiness@1.0.0','parameters':{'program_id':'$input.program_id'}}]}
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json',canonical(sk))
            z.writestr('SKILL.md','---\nname: review-build-readiness\ndescription: Retrieve authorized assembly readiness through the governed query service.\n---\n\nCall the declared query with program_id. Report the returned assembly identifiers and readiness values. Do not infer records that were not returned. Credentials are provided by the destination runtime.\n')
            z.writestr('references/contract.md','Input: program_id (string). Output: assembly_id, system_name, readiness_pct. Query-level permissions are checked at execution.\n')
        put_asset(db,'skill',sk,'builder','approved',blob=out.getvalue())
        cards=[('build-readiness','Build Readiness','One view of every assembly, blocker, and path to flight.','Manufacturing','violet','readiness',0),
               ('supply-radar','Supply Radar','See material risks before they reach the factory floor.','Supply chain','teal','supply',1),
               ('test-pulse','Test Pulse','Follow test campaigns from first ignition to sign-off.','Test & launch','orange','test',2),
               ('data-compass','Data Compass','Find the right data. Understand the story behind it.','Data & AI','blue','data',3),
               ('mission-control','Mission Control','Turn launch preparation into a shared, actionable plan.','Test & launch','pink','mission',2),
               ('knowledge-orbit','Knowledge Orbit','Bring engineering knowledge into the flow of work.','Data & AI','indigo','knowledge',3)]
        for identifier,name,description,category,theme,kind,index in cards:
            p={'name':name,'description':description,'category':category,'owner':'Paul Malmquist','initials':'PM','theme':theme,'kind':kind,'url':''}
            manifest={'version':'1.0.0','queries':[definitions[index][0]+'@1.0.0'],'skills':['review-build-readiness@1.0.0'] if index==0 else [],'lockfile':{'lockfileVersion':3,'packages':{'':{'name':'builtin-demo','version':'1.0.0'}}}}
            proof={'manifest_sha256':digest(manifest),'lock_sha256':digest(manifest['lockfile']),'artifact_sha256':hashlib.sha256(b'dreamcatcher-builtin-demo').hexdigest(),'security_scan':'passed','issued_at':time.time(),'demo':True}
            evidence={'payload':proof,'signature':hmac.new(os.environ['DC_BUILD_SIGNING_KEY'].encode(),canonical(proof).encode(),hashlib.sha256).hexdigest()}
            db.execute('INSERT INTO apps(id,owner,payload,published_version,created) VALUES(?,?,?,?,?)',(identifier,'builder',canonical(p),'1.0.0',time.time()))
            db.execute('INSERT INTO releases VALUES(?,?,?,?,?,?,?,?)',(identifier,'1.0.0',canonical(manifest),digest(manifest),'approved',canonical(evidence),'reviewer',time.time()))
            db.execute('INSERT INTO grants VALUES(?,?,?)',(identifier,'workspace','run'))
    with sqlite3.connect(DATA/'warehouse.sqlite') as warehouse:
        for _,table,fields,_,_ in definitions:
            warehouse.execute('CREATE TABLE IF NOT EXISTS '+table+' ('+', '.join(x+' TEXT' for x in fields)+', program_id TEXT, authorized_user TEXT)')
        for user in ('builder','admin','viewer','reviewer','outsider'):
            for i,(system,value) in enumerate([('Structures','82'),('Propulsion','95'),('Avionics','73'),('Integration','88')]):
                warehouse.execute('INSERT INTO assembly_readiness VALUES(?,?,?,?,?)',(f'A-{i+1:03}',system,value,'terran-r',user))
            for row in [('PO-104','Precision Metals','Low'),('PO-208','Valve Systems','Elevated')]:
                warehouse.execute('INSERT INTO supplier_delivery_risk VALUES(?,?,?,?,?)',(*row,'terran-r',user))
            warehouse.execute('INSERT INTO test_run_summary VALUES(?,?,?,?,?)',('T-042','Engine qualification','Complete','terran-r',user))
            warehouse.execute('INSERT INTO catalog_lineage VALUES(?,?,?,?,?)',('D-012','manufacturing_readiness','stg_assemblies, int_work_orders','terran-r',user))
