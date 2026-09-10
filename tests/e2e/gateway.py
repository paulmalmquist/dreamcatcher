"""Isolated synthetic E2E process. NEVER import this into application startup."""
import json
import os
import sys
import time
from pathlib import Path

if os.getenv('DC_E2E_SYNTHETIC') != '1' or os.getenv('DC_ENV') != 'local' or os.getenv('DC_DEMO') != 'true':
    raise SystemExit('Synthetic gateway requires an explicit local E2E environment')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from dreamcatcher.main import app
from dreamcatcher import governance

data = json.loads((ROOT / 'examples/bigquery/synthetic-rows.json').read_text())


def synthetic_warehouse(payload, bound, user):
    rows = [r | {'updated_at': '2026-09-01T12:00:00Z'} for r in data['datasets'][payload['sources'][0]]
            if r['program_id'] == bound['program_id'] and r['program_id'] in data['entitlements'].get(user['id'], [])]
    return {'rows': rows, 'truncated': False, 'synthetic': True}


# Only the remote warehouse call is substituted. The real gateway still performs
# identity, group, query approval, data-product, release, parameter and cost checks.
governance.run_bigquery = synthetic_warehouse


@app.middleware('http')
async def test_api_timing(request, call_next):
    started = time.monotonic()
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        print('E2E_API', request.method, request.url.path, response.status_code,
              round(time.monotonic() - started, 3), flush=True)
    return response


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=18000, access_log=False)
