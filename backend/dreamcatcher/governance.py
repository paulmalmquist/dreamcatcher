"""Fail-closed policy checks. This process never executes uploaded code."""
import base64
import hashlib
import hmac
import io
import json
import os
import re
import sqlite3
import time
import zipfile
from datetime import date
from pathlib import PurePosixPath
from urllib.parse import urlsplit
import sqlglot
from sqlglot import exp
from fastapi import HTTPException
from .db import DATA, asset, canonical, digest
from .auth import data_permission

IDENTIFIER = re.compile(r'^[a-z][a-z0-9-]{1,63}$')
VERSION = re.compile(r'^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$')

def check_identity(payload):
    if not isinstance(payload, dict) or not all(isinstance(payload.get(k),str) for k in ('id','version')):
        raise HTTPException(422, 'Identity and version must be strings')
    if not IDENTIFIER.fullmatch(payload.get('id', '')) or not VERSION.fullmatch(payload.get('version', '')):
        raise HTTPException(422, 'Use a lowercase hyphenated id and an exact semantic version')

def check_url(value):
    url = urlsplit(value)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
        raise HTTPException(422, 'Use an HTTPS URL without credentials or fragments')
    allowed = [x.strip() for x in os.getenv('DC_APP_HOSTS', '').split(',') if x.strip()]
    if allowed and url.hostname not in allowed:
        raise HTTPException(422, 'App host is not on DC_APP_HOSTS')
    return value

def query_validation(payload):
    check_identity(payload)
    for key in ('sources','allowed_groups'):
        if not isinstance(payload.get(key),list) or not payload[key] or any(not isinstance(v,str) or not v for v in payload[key]):
            raise HTTPException(422, 'Sources and allowed_groups must be nonempty string lists')
    sql = payload.get('sql', '')
    if not isinstance(sql, str) or not 1 <= len(sql) <= 30000:
        raise HTTPException(422, 'SQL is required and limited to 30 KB')
    if payload.get('connector') not in ('sqlite', 'bigquery'):
        raise HTTPException(422, 'Choose sqlite or bigquery')
    dialect = payload['connector']
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.ParseError:
        raise HTTPException(422, 'SQL could not be parsed')
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise HTTPException(422, 'Exactly one SELECT statement is allowed')
    tree = statements[0]
    if any(isinstance(n, (exp.DDL, exp.DML, exp.Command, exp.Star)) for n in tree.walk()):
        raise HTTPException(422, 'Writes, commands, and SELECT * are not allowed')
    forbidden = ('LOAD_EXTENSION', 'READFILE', 'WRITEFILE', 'EXTERNAL_QUERY', 'ML.', 'REMOTE')
    if any(x in sql.upper() for x in forbidden):
        raise HTTPException(422, 'External and filesystem functions are not allowed')
    if tree.args.get('with_'):
        raise HTTPException(422, 'Move CTE transformations into a governed source view for this release')
    sources = sorted({'.'.join(part.name for part in t.parts) for t in tree.find_all(exp.Table)})
    if not sources or sources != sorted(payload.get('sources', [])):
        raise HTTPException(422, {'message': 'Declared sources must exactly match parsed SQL', 'parsed_sources': sources})
    if not payload.get('grain') or not payload.get('allowed_groups'):
        raise HTTPException(422, 'Grain and data-access groups are required')
    params = payload.get('parameters', {})
    if not isinstance(params, dict) or len(params) > 30 or any(not re.fullmatch(r'[a-z][a-z0-9_]*', k) for k in params):
        raise HTTPException(422, 'Invalid parameter names')
    if any(v not in ('string', 'integer', 'number', 'boolean', 'date') for v in params.values()):
        raise HTTPException(422, 'Unsupported parameter type')
    # Reserved identity parameters are bound by the server, never by clients.
    referenced = set(re.findall(r'(?<!:)[@:](\w+)', sql))
    if referenced - set(params) - {'_user_id'} or set(params) - referenced:
        raise HTTPException(422, 'Parameter contract does not match SQL placeholders')
    return {'sources': sources, 'read_only': True, 'grain': payload['grain']}

def bind_parameters(payload, values, user):
    contract = payload.get('parameters', {})
    if set(values) != set(contract):
        raise HTTPException(422, 'Provide exactly the registered parameter names')
    for name, kind in contract.items():
        value = values[name]
        valid = ((kind == 'string' and isinstance(value, str) and len(value) <= 4000)
                 or (kind == 'integer' and type(value) is int)
                 or (kind == 'number' and type(value) in (int, float))
                 or (kind == 'boolean' and type(value) is bool))
        if kind == 'date':
            try:
                valid = isinstance(value, str) and date.fromisoformat(value).isoformat() == value
            except (ValueError, TypeError):
                valid = False
        if not valid:
            raise HTTPException(422, 'Invalid type for parameter ' + name)
    return dict(values) | {'_user_id': user['id']}

def run_query(db, reference, values, user):
    record = asset(db, 'query', reference)
    if not record or record['status'] != 'approved':
        raise HTTPException(409, 'Query version is missing, pending, or revoked')
    p = record['payload']
    data_permission(user, p)
    query_validation(p)  # Defense against policy changes since approval.
    bound = bind_parameters(p, values, user)
    if p['connector'] == 'bigquery':
        return run_bigquery(p, bound, user)
    path = DATA / 'warehouse.sqlite'
    if not path.exists():
        raise HTTPException(503, 'Local warehouse is not configured')
    conn = sqlite3.connect('file:' + str(path.resolve()) + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(False)
    allowed = set(p['sources'])
    def authorize(action, arg1, arg2, database, trigger):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and database == 'main' and arg1 in allowed:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() in {'count','sum','avg','min','max','round','coalesce','lower','upper','length','abs','date','strftime','nullif','ifnull'}:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    conn.set_authorizer(authorize)
    started = time.monotonic()
    steps = [0]
    def progress():
        steps[0] += 1
        return int(steps[0] > 10000 or time.monotonic() - started > 5)
    conn.set_progress_handler(progress, 1000)
    try:
        rows = [dict(row) for row in conn.execute(p['sql'], bound).fetchmany(501)]
        return {'rows': rows[:500], 'truncated': len(rows) > 500, 'reference': reference}
    except sqlite3.Error:
        raise HTTPException(422, 'Query was rejected, exceeded its budget, or did not match the source schema')
    finally:
        conn.close()

def run_bigquery(p, bound, user):
    # No shared privileged fallback: each caller must have an operator-provided principal mapping.
    mapping = json.loads(os.getenv('DC_BQ_PRINCIPALS', '{}'))
    principal = mapping.get(user['id'])
    if not principal:
        raise HTTPException(503, 'No BigQuery execution principal is bound for this caller')
    try:
        import google.auth
        from google.auth import impersonated_credentials
        from google.cloud import bigquery
    except ImportError:
        raise HTTPException(503, 'Install requirements-bigquery.txt to enable this connector')
    source, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    credentials = impersonated_credentials.Credentials(source_credentials=source, target_principal=principal,
                     target_scopes=['https://www.googleapis.com/auth/bigquery'], lifetime=600)
    client = bigquery.Client(project=os.environ['DC_BQ_PROJECT'], credentials=credentials)
    types = {'string':'STRING','integer':'INT64','number':'FLOAT64','boolean':'BOOL','date':'DATE'}
    params = [bigquery.ScalarQueryParameter(k, types[t], bound[k]) for k, t in p['parameters'].items()]
    if '@_user_id' in p['sql']:
        params.append(bigquery.ScalarQueryParameter('_user_id', 'STRING', user['id']))
    cfg = bigquery.QueryJobConfig(query_parameters=params, maximum_bytes_billed=int(os.getenv('DC_BQ_MAX_BYTES', '100000000')),
                                 use_legacy_sql=False, labels={'application':'dreamcatcher'})
    job = client.query(p['sql'], job_config=cfg, location=os.getenv('DC_BQ_LOCATION', 'US'))
    try:
        rows = [dict(r) for r in job.result(timeout=30, max_results=501)]
    except Exception:
        job.cancel()
        raise HTTPException(502, 'BigQuery execution failed or timed out; check server-side job logs')
    return {'rows':rows[:500], 'truncated':len(rows)>500, 'job_id':job.job_id}

def lock_inventory(lock):
    if not isinstance(lock,dict) or lock.get('lockfileVersion') not in (2, 3) or not isinstance(lock.get('packages'), dict):
        raise HTTPException(422, 'A complete npm package-lock v2 or v3 is required')
    if not isinstance(lock['packages'].get(''),dict):
        raise HTTPException(422, 'Root package metadata is required')
    result = []
    for path, p in lock['packages'].items():
        if not isinstance(p,dict) or any(not isinstance(p.get(k,''),str) for k in ('name','version','integrity','resolved')):
            raise HTTPException(422, 'Invalid package metadata')
        if not path:
            continue
        if not isinstance(p, dict) or p.get('link') or 'node_modules/' not in path:
            raise HTTPException(422, 'Links and workspace dependencies require a separate trusted build adapter')
        name = p.get('name') or path.rsplit('node_modules/', 1)[1]
        version, integrity, source = p.get('version', ''), p.get('integrity', ''), p.get('resolved', '')
        if not re.fullmatch(r'(?:@[a-z0-9._-]+/)?[a-z0-9._-]+', name) or not VERSION.fullmatch(version):
            raise HTTPException(422, 'Every dependency must have a valid exact package name and version')
        if not integrity.startswith('sha512-') or not source.startswith('https://registry.npmjs.org/') or p.get('hasInstallScript'):
            raise HTTPException(422, 'Package integrity, registry, or install-script policy failed: ' + name)
        try:
            if len(base64.b64decode(integrity[7:],validate=True)) != 64:
                raise ValueError()
        except ValueError:
            raise HTTPException(422,'Package integrity must be a complete SHA-512 digest')
        result.append({'name':name, 'version':version, 'integrity':integrity, 'source':source})
    # All declared direct dependencies must resolve into the submitted lock.
    root = lock['packages'].get('', {})
    if any(not isinstance(root.get(k,{}),dict) for k in ('dependencies','devDependencies','optionalDependencies')):
        raise HTTPException(422,'Invalid root dependencies')
    for name in set(root.get('dependencies', {})) | set(root.get('devDependencies', {})) | set(root.get('optionalDependencies', {})):
        if 'node_modules/' + name not in lock['packages']:
            raise HTTPException(422, 'Incomplete lockfile: missing direct dependency ' + name)
    return result

def package_findings(db, lock):
    findings = []
    for p in lock_inventory(lock):
        policy = db.execute('SELECT * FROM packages WHERE name=? AND version=?', (p['name'],p['version'])).fetchone()
        if not policy or not policy['approved'] or policy['integrity'] != p['integrity'] or policy['source'] != p['source']:
            findings.append(p['name'] + '@' + p['version'])
    return findings

def validate_evidence(manifest, evidence, fresh=True):
    secret = os.getenv('DC_BUILD_SIGNING_KEY', '')
    if len(secret) < 32 or not isinstance(evidence, dict):
        return False
    payload = evidence.get('payload', {})
    if not isinstance(payload, dict) or not isinstance(evidence.get('signature'), str):
        return False
    if not isinstance(payload.get('artifact_sha256'), str) or not isinstance(payload.get('issued_at'), (int, float)):
        return False
    if payload.get('demo') and os.getenv('DC_DEMO','false').lower() != 'true':
        return False
    expected = hmac.new(secret.encode(), canonical(payload).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, evidence.get('signature', '')):
        return False
    return (payload.get('manifest_sha256') == digest(manifest)
            and payload.get('lock_sha256') == digest(manifest.get('lockfile', {}))
            and bool(re.fullmatch(r'[a-f0-9]{64}', payload.get('artifact_sha256', '')))
            and payload.get('security_scan') == 'passed'
            and (not fresh or 0 <= time.time() - payload.get('issued_at', 0) <= 86400))

def readiness(db, manifest, evidence=None, fresh=True):
    findings = []
    try:
        missing = package_findings(db, manifest.get('lockfile', {}))
        if missing:
            findings.append({'gate':'packages','message':'Unapproved package versions', 'items':missing})
    except HTTPException as error:
        findings.append({'gate':'packages','message':error.detail})
    for kind, key in [('query','queries'),('skill','skills')]:
        for reference in manifest.get(key, []):
            r = asset(db, kind, reference)
            if not r or r['status'] != 'approved':
                findings.append({'gate':key,'message':'Not approved: ' + reference})
            elif kind == 'skill':
                for q in r['payload'].get('queries', []):
                    dep = asset(db, 'query', q)
                    if not dep or dep['status'] != 'approved':
                        findings.append({'gate':'skills','message':'Skill query is no longer approved: '+q})
    if not validate_evidence(manifest, evidence, fresh=fresh):
        findings.append({'gate':'build','message':'A fresh trusted build attestation is required; an app link is not build evidence'})
    return findings

def unpack_skill(content):
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, 'Skill ZIP exceeds 5 MiB')
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
        files = {}
        if len(z.infolist()) > 100 or sum(f.file_size for f in z.infolist()) > 10 * 1024 * 1024:
            raise ValueError('Too many files or expanded size exceeds 10 MiB')
        for f in z.infolist():
            path = PurePosixPath(f.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in f.filename or ':' in f.filename or (f.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Unsafe archive path or symlink')
            if f.is_dir():
                continue
            if f.filename in files or f.flag_bits & 1 or f.file_size > 1024 * 1024:
                raise ValueError('Duplicate, encrypted, or oversized file')
            if path.name.startswith('.env') or path.suffix.lower() in ('.pem','.key','.p12','.pfx','.sqlite','.db') or path.name in ('credentials.json','token.json'):
                raise ValueError('Secrets and runtime data cannot be transferred')
            raw = z.read(f)
            text = raw.decode('utf-8')
            if re.search(r'-----BEGIN .*PRIVATE KEY|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}', text):
                raise ValueError('Potential credential detected')
            files[f.filename] = raw
        if 'SKILL.md' not in files or 'manifest.json' not in files:
            raise ValueError('SKILL.md and manifest.json must be at the archive root')
        manifest = json.loads(files['manifest.json'])
        check_identity(manifest)
        allowed = {'id','version','name','description','queries','packages','runtime','steps','tools','allowed_groups','inputs','logical_connections'}
        if set(manifest) - allowed:
            raise ValueError('Unknown or environment-specific manifest fields')
        if manifest.get('runtime') != 'declarative-query-v1':
            raise ValueError('This runtime supports declarative-query-v1; script runtimes need a separately isolated adapter')
        if not isinstance(manifest.get('queries'), list) or not isinstance(manifest.get('steps'), list) or not 1 <= len(manifest['steps']) <= 10:
            raise ValueError('Declare query references and 1–10 steps')
        if manifest.get('packages'):
            raise ValueError('This interpreter needs no skill-installed packages; external runtimes require a reviewed adapter')
        if set(manifest.get('tools', [])) != {'queries.run'}:
            raise ValueError('Only the queries.run capability is available')
        if not manifest.get('allowed_groups'):
            raise ValueError('Destination data-access groups must be specified')
        for step in manifest['steps']:
            if set(step) != {'query','parameters'} or step['query'] not in manifest['queries'] or not isinstance(step['parameters'], dict):
                raise ValueError('Step must reference a declared query with parameter bindings')
        # Rebuild only validated files, without preserving source filesystem metadata.
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as clean:
            for name, raw in sorted(files.items()):
                clean.writestr(name, raw)
        return manifest, out.getvalue()
    except (ValueError, KeyError, TypeError, UnicodeError, zipfile.BadZipFile, RuntimeError) as error:
        raise HTTPException(422, 'Invalid skill package: ' + str(error))
