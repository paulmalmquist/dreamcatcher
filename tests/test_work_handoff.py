import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from dreamcatcher import governance
from dreamcatcher.contracts import Manifest

ROOT = Path(__file__).resolve().parents[1]


def test_connection_inventory_points_to_real_files():
    payload = json.loads((ROOT / 'integrations/CONNECTIONS.json').read_text())
    assert payload['company_connections_configured'] is False
    assert len(payload['connections']) == 9
    for item in payload['connections']:
        assert (ROOT / item['entrypoint'].split(':')[0]).is_file()
        assert item['acceptance'] and item['discover_at_work']


def test_schema_and_server_contract_stay_in_sync():
    assert json.loads((ROOT / 'sdk/contracts/dreamcatcher.schema.json').read_text()) == Manifest.model_json_schema()


def test_unconnected_adapter_does_not_claim_success():
    spec = importlib.util.spec_from_file_location('work_adapter_test', ROOT / 'integrations/adapters.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    adapter = mod.create_adapter()
    for method, args in [('build', ({}, b'')), ('deploy', ({},)), ('agent', ({}, b''))]:
        with pytest.raises(mod.IntegrationRequired): getattr(adapter, method)(*args)


@pytest.mark.parametrize('estimate,schema,status', [(100000001, None, 409), (100, ['unexpected'], 409), (100, None, 200)])
def test_actual_bigquery_adapter_dryrun_budget_and_schema(monkeypatch, estimate, schema, status):
    query = json.loads((ROOT / 'examples/bigquery/queries.json').read_text())[0]
    calls = []
    class Client:
        def query(self, sql, *, job_config, location):
            calls.append(job_config)
            if getattr(job_config, 'dry_run', False):
                return SimpleNamespace(total_bytes_processed=estimate, schema=[SimpleNamespace(name=n) for n in (schema or query['data_contract']['output_columns'])])
            return SimpleNamespace(result=lambda **kw: [], job_id='synthetic-job', total_bytes_processed=100)
    api = SimpleNamespace(QueryJobConfig=lambda **kw: SimpleNamespace(**kw), ScalarQueryParameter=lambda *args: args)
    monkeypatch.setattr(governance, 'bigquery_client', lambda user: (Client(), api))
    if status != 200:
        with pytest.raises(HTTPException) as exc: governance.run_bigquery(query, {'program_id': 'program-a'}, {'id': 'builder'})
        assert exc.value.status_code == status and len(calls) == 1
    else:
        assert governance.run_bigquery(query, {'program_id': 'program-a'}, {'id': 'builder'})['rows'] == []
        assert len(calls) == 2 and calls[1].maximum_bytes_billed == 100000000 and calls[1].use_query_cache is False


def test_principal_mapping_does_not_share_or_fallback(monkeypatch):
    monkeypatch.setenv('DC_BQ_PRINCIPALS', '{}')
    with pytest.raises(HTTPException): governance.bigquery_client({'id': 'unknown'})
    principal = 'shared@synthetic-project.iam.gserviceaccount.com'
    monkeypatch.setenv('DC_BQ_PRINCIPALS', json.dumps({'alice': principal, 'bob': principal}))
    with pytest.raises(HTTPException): governance.bigquery_client({'id': 'alice'})


def test_query_budget_is_committed_independently(client, monkeypatch):
    monkeypatch.setenv('DC_BQ_QUERIES_PER_MINUTE', '1')
    governance.reserve_query_budget('builder')
    with pytest.raises(HTTPException) as exc: governance.reserve_query_budget('builder')
    assert exc.value.status_code == 429
    governance.reserve_query_budget('viewer')


def test_python_sdk_safety_and_request_shape():
    spec = importlib.util.spec_from_file_location('python_sdk_test', ROOT / 'sdk-python/src/dreamcatcher_sdk/__init__.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(ValueError): mod.Dreamcatcher(base_url='http://remote.example.invalid', app_id='test-app', token='x')
    client = mod.Dreamcatcher(base_url='https://gateway.example.invalid', app_id='test-app', token='x')
    with pytest.raises(ValueError): client.state_get('preferences', '../another')
    seen = []
    client._request = lambda *args: seen.append(args)
    client.state_put('preferences', 'dashboard', {'x': 1}, expected_version=0, idempotency_key='test-key-one')
    assert seen[0][1] == {'value': {'x': 1}, 'expected_version': 0, 'idempotency_key': 'test-key-one'}


def test_cli_zip_is_accepted_by_real_upload_parser(tmp_path):
    from dreamcatcher.hosting import unpack_source
    path = tmp_path / 'source.zip'
    subprocess.run(['node', str(ROOT / 'sdk/cli/dc.mjs'), 'pack', str(ROOT / 'examples/apps/build-readiness'), str(path)], check=True, capture_output=True)
    manifest, files = unpack_source(path.read_bytes())
    assert manifest.queries == ['bq-build-readiness@1.0.0']
    assert 'src/Dashboard.jsx' in files
    refusal = subprocess.run(['node', str(ROOT / 'sdk/cli/dc.mjs'), 'pack', str(ROOT / 'examples/apps/build-readiness'), str(path)], capture_output=True)
    assert refusal.returncode != 0
