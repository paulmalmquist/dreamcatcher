"""Read-only installation preflight. Prints no secret values and makes no network calls."""
import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def inspect(root=ROOT):
    checks=[]
    def record(name,passed,detail):
        checks.append({'check':name,'status':'pass' if passed else 'blocked','detail':detail})
    record('Python',sys.version_info >= (3,12),'Python 3.12 or newer required')
    for name in ('fastapi','uvicorn','authlib','dotenv','sqlglot'):
        record('Dependency: '+name,importlib.util.find_spec(name) is not None,'Install requirements.txt in the active Python environment')
    record('Node and npm',bool(shutil.which('node') and shutil.which('npm')),'Node 22.14+ and npm required for rebuilding; versions are not validated here')
    for relative in ('frontend/dist/index.html','artifacts/dreamcatcher-sdk.tgz'):
        record('Build: '+relative,(root/relative).is_file(),'Run npm ci --ignore-scripts, then npm run build')
    values={}
    if importlib.util.find_spec('dotenv') is not None and (root/'.env').is_file():
        from dotenv import dotenv_values
        values=dotenv_values(root/'.env')
    values.update({k:v for k,v in os.environ.items() if k.startswith('DC_')})
    record('Configuration',bool(values),'Run scripts/setup.py locally, or provide environment variables')
    prod=values.get('DC_ENV')=='production'
    for name in ('DC_SESSION_SECRET','DC_BUILD_SIGNING_KEY'):
        value=values.get(name) or ''
        record(name,len(value)>=32 and value!='GENERATE_WITH_SETUP','Provide a persistent secret of at least 32 characters; value is never displayed')
    if prod:
        record('Production identity',values.get('DC_DEMO','false').lower()=='false' and values.get('DC_AUTH_MODE')=='oidc','Production requires demo off and OIDC')
        record('HTTPS origin',(values.get('DC_ORIGIN') or '').startswith('https://'),'Configure the actual HTTPS origin and callback')
        for name in ('DC_OIDC_ISSUER','DC_OIDC_CLIENT_ID','DC_OIDC_CLIENT_SECRET','DC_ALLOWED_HOSTS','DC_APP_HOSTS'):
            record(name,bool(values.get(name)),'Set an explicit corporate value; validity still requires integration testing')
        for name in ('DC_DATABASE_URL','DC_STATE_DATABASE_URL','DC_BQ_PROJECT','DC_IMAGE_REGISTRIES','DC_APP_RUNTIME_SUFFIX'):
            record(name,bool(values.get(name)),'Replace WORK-CONNECT seam with a real approved company value')
        record('Separate state database',bool(values.get('DC_STATE_DATABASE_URL')) and values.get('DC_STATE_DATABASE_URL')!=values.get('DC_DATABASE_URL'),'Different migration/runtime roles and FORCE RLS must also be verified live')
        record('Migration separation',values.get('DC_AUTO_MIGRATE','false')=='false','Run scripts/migrate.py with a migration-only role, not at runtime')
        for kind in ('BUILD','DEPLOY','AGENT','DATA','EDGE'):
            record('Worker credential: '+kind,len(values.get('DC_WORKER_'+kind+'_KEY',''))>=32,'Separate secret per worker; a configured credential is not a healthy worker')
        record('PostgreSQL driver',importlib.util.find_spec('psycopg') is not None,'Resolve requirements-postgres.txt with the company dependency process')
    return {'mode':'production' if prod else 'local','network_checks_performed':False,'checks':checks,
            'limitations':['Does not validate IdP, warehouse IAM, deployed artifacts, or production readiness.','No database is created or modified.']}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    result=inspect()
    if args.json:
        print(json.dumps(result,indent=2))
    else:
        print('Dreamcatcher installation preflight ('+result['mode']+')')
        for row in result['checks']:
            print(row['status'].upper()+': '+row['check']+' — '+row['detail'])
        for note in result['limitations']:print(note)
    sys.exit(1 if any(r['status']=='blocked' for r in result['checks']) else 0)
