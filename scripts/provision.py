"""Operator-only CLI for initial local/OIDC account provisioning."""
import argparse,getpass,hashlib,sys
from pathlib import Path
from dotenv import load_dotenv
root=Path(__file__).resolve().parents[1]
load_dotenv(root/'.env');sys.path.insert(0,str(root/'backend'))
from dreamcatcher.db import migrate,connect,canonical,event
from dreamcatcher.auth import password_hash
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--id');p.add_argument('--issuer');p.add_argument('--subject');p.add_argument('--email',required=True);p.add_argument('--name',required=True)
p.add_argument('--role',choices=['admin','reviewer','builder','viewer'],default='viewer');p.add_argument('--group',action='append',default=[])
a=p.parse_args()
if a.issuer and a.subject:
    identifier='oidc-'+hashlib.sha256((a.issuer.rstrip('/')+'|'+a.subject).encode()).hexdigest()[:32];password=None
elif a.id:
    identifier=a.id;raw=getpass.getpass('New password (14+ characters): ')
    if len(raw)<14:raise SystemExit('Password too short')
    password=password_hash(raw)
else:raise SystemExit('Provide --issuer and --subject for OIDC, or --id for local login')
migrate()
with connect() as db:
    db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(identifier,a.email.lower(),a.name,password,a.role,canonical(a.group)))
    event(db,'operator','account.provisioned',identifier)
print('Provisioned '+identifier)
