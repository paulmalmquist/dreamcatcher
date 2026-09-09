"""Run only in an operator-controlled build environment; never expose its key to builders."""
import argparse,hashlib,hmac,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from dreamcatcher.db import canonical,digest

def make_evidence(manifest,artifact,audit,key):
    if len(key)<32:raise ValueError('DC_BUILD_SIGNING_KEY must contain at least 32 characters')
    counts=audit.get('metadata',{}).get('vulnerabilities')
    if not isinstance(counts,dict) or any(not isinstance(counts.get(k),int) for k in ('high','critical')):
        raise ValueError('A completed npm audit JSON report is required')
    if counts['high'] or counts['critical']:raise ValueError('High/critical findings prevent attestation')
    payload={'manifest_sha256':digest(manifest),'lock_sha256':digest(manifest['lockfile']),
             'artifact_sha256':hashlib.sha256(artifact).hexdigest(),'security_scan':'passed','issued_at':time.time()}
    return {'payload':payload,'signature':hmac.new(key.encode(),canonical(payload).encode(),hashlib.sha256).hexdigest()}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True);p.add_argument('--artifact',required=True);p.add_argument('--audit',required=True);p.add_argument('--output',required=True)
    a=p.parse_args()
    evidence=make_evidence(json.loads(Path(a.manifest).read_text()),Path(a.artifact).read_bytes(),json.loads(Path(a.audit).read_text()),os.environ.get('DC_BUILD_SIGNING_KEY',''))
    Path(a.output).write_text(json.dumps(evidence,indent=2)+'\n')
    print('Signed evidence written. Deploy exactly this artifact; the registry cannot verify external URL content.')
