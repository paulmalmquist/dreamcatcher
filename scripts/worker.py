"""Run one leased job using a trusted operator-installed adapter, never upload code.

No generic shell runner is provided. Copy integrations/adapters.py to an approved
work_connections.py module in the work checkout and implement the three methods.
"""
import argparse
import importlib
import os
import sys
import threading
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_once(kind, adapter, client):
    response = client.post('/api/v2/workers/' + kind + '/claim', json={})
    response.raise_for_status()
    job = response.json()['job']
    if job is None:
        return 'idle'
    stop, lost = threading.Event(), threading.Event()
    def renew():
        while not stop.wait(30):
            try:
                beat = client.post(f"/api/v2/workers/{kind}/jobs/{job['id']}/heartbeat", json={'lease': job['lease']}, timeout=10)
                beat.raise_for_status()
            except Exception:
                lost.set()
                return
    heartbeat = threading.Thread(target=renew, daemon=True)
    heartbeat.start()
    try:
        if kind in ('build', 'agent'):
            source = client.get(f"/api/v2/workers/{kind}/jobs/{job['id']}/source", headers={'x-job-lease': job['lease']})
            source.raise_for_status()
            result = getattr(adapter, kind)(job, source.content)
        else:
            result = adapter.deploy(job)
        body = {'lease': job['lease'], 'result': result}
    except Exception:
        # Do not print source, tokens, model output, or exception text to job logs.
        body = {'lease': job['lease'], 'failure_code': {'build': 'BUILD_FAILED', 'agent': 'MODEL_FAILED', 'deploy': 'HOSTING_FAILED'}[kind]}
    finally:
        stop.set()
        heartbeat.join(timeout=11)
    if lost.is_set():
        # A revoked/lost lease may not publish results. The adapter must separately
        # reconcile its external job; Python threads do not cancel cloud builds.
        return 'lease_lost_reconcile_external_job'
    response = client.post(f"/api/v2/workers/{kind}/jobs/{job['id']}/report", json=body)
    response.raise_for_status()
    return response.json()['status']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=['build', 'deploy', 'agent'], required=True)
    parser.add_argument('--adapter', choices=['integrations.adapters', 'work_connections'], default='integrations.adapters')
    args = parser.parse_args()
    if args.adapter == 'integrations.adapters':
        parser.error('No work adapter configured. Read integrations/CONNECTIONS.json; no job was claimed.')
    origin = os.environ['DC_GATEWAY_ORIGIN']
    from urllib.parse import urlsplit
    url = urlsplit(origin)
    if url.username or url.password or url.query or url.fragment or url.path not in ('', '/') or url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')):
        parser.error('Use a trusted HTTPS gateway origin (loopback HTTP allowed)')
    key = os.environ['DC_WORKER_' + args.kind.upper() + '_KEY']
    adapter = importlib.import_module(args.adapter).create_adapter()
    with httpx.Client(base_url=origin, headers={'Authorization': 'Bearer ' + key}, timeout=60, follow_redirects=False) as client:
        print(run_once(args.kind, adapter, client))
