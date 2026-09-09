"""Certified analytics contracts. A skill explains these checks; only this gateway enforces them.

WORK-CONNECT: catalog-attestor. Observations must come from the trusted metadata
worker, never from an app uploader or an LLM. See integrations/CONNECTIONS.json.
"""
import json
import time
from typing import Literal
import sqlglot
from sqlglot import exp
from fastapi import HTTPException
from pydantic import Field, model_validator
from .contracts import Strict
from .db import digest

SOURCE = r'^[a-z][a-z0-9-]{4,62}\.[A-Za-z_][A-Za-z0-9_]{0,127}\.[A-Za-z_][A-Za-z0-9_]{0,127}$'


class Column(Strict):
    name: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')
    type: Literal['STRING', 'INTEGER', 'FLOAT', 'BOOLEAN', 'DATE', 'TIMESTAMP', 'NUMERIC']
    sensitive: bool = False


class Product(Strict):
    source: str = Field(pattern=SOURCE)
    revision: int = Field(ge=1)
    owner: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=500)
    classification: Literal['internal', 'restricted']
    grain: list[str] = Field(min_length=1, max_length=10)
    columns: list[Column] = Field(min_length=1, max_length=100)
    allowed_groups: list[str] = Field(min_length=1, max_length=30)
    max_staleness_seconds: int = Field(ge=60, le=604800, default=86400)
    max_bytes_billed: int = Field(ge=1000, le=100000000000, default=100000000)
    # No 'none' mode: work adapters must prove either native RLS or an approved
    # identity-filtered authorized view, INCLUDING its underlying dependencies.
    row_security: Literal['native-rls', 'identity-authorized-view']
    enabled: bool = True

    @model_validator(mode='after')
    def unique(self):
        names = [c.name for c in self.columns]
        if len(names) != len(set(names)) or not set(self.grain).issubset(names):
            raise ValueError('Unique columns and a grain made from those columns are required')
        if len(self.allowed_groups) != len(set(self.allowed_groups)):
            raise ValueError('Duplicate data-access group')
        if any(c.sensitive for c in self.columns) and self.classification != 'restricted':
            raise ValueError('Products with sensitive columns must be classified restricted')
        return self


class Observation(Strict):
    product_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    source: str = Field(pattern=SOURCE)
    object_type: Literal['VIEW', 'MATERIALIZED_VIEW']
    columns: list[Column] = Field(min_length=1, max_length=100)
    data_as_of: float = Field(gt=0)
    ttl_seconds: int = Field(ge=30, le=3600, default=300)
    lineage_verified: bool
    row_security_verified: bool
    column_security_verified: bool
    negative_access_tests_passed: bool
    grain_tests_passed: bool
    evidence_uri: str = Field(pattern=r'^gs://[a-z0-9._-]+/.+', max_length=1000)
    # The object is content-addressed; the worker retains warehouse test evidence.
    evidence_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class QueryContract(Strict):
    products: dict[str, int] = Field(min_length=1, max_length=10)
    output_columns: list[str] = Field(min_length=1, max_length=100)
    max_bytes_billed: int = Field(ge=1000, le=100000000000)
    max_rows: int = Field(ge=1, le=500, default=500)


def query_contract(payload):
    try:
        return QueryContract.model_validate(payload.get('data_contract', {}))
    except ValueError:
        raise HTTPException(422, 'BigQuery queries require a typed data_contract') from None


def findings(db, payload):
    if payload['connector'] != 'bigquery':
        return []
    contract = query_contract(payload)
    problems, products = [], {}
    if set(contract.products) != set(payload['sources']):
        problems.append('Every SQL source must bind an exact certified product revision')
    for source, revision in contract.products.items():
        row = db.execute('SELECT * FROM data_products WHERE source=?', (source,)).fetchone()
        if not row or not row['enabled'] or row['revision'] != revision:
            problems.append('Uncertified, disabled, or changed data product: ' + source)
            continue
        product = json.loads(row['payload'])
        products[source] = product
        if not set(payload['allowed_groups']).issubset(product['allowed_groups']):
            problems.append('Query audience exceeds data-product audience: ' + source)
        if contract.max_bytes_billed > product['max_bytes_billed']:
            problems.append('Query cost limit exceeds data-product budget: ' + source)
        obs = db.execute('SELECT * FROM data_observations WHERE source=?', (source,)).fetchone()
        if not obs or obs['expires'] <= time.time() or obs['product_digest'] != row['digest']:
            problems.append('Fresh trusted metadata observation is required: ' + source)
            continue
        evidence = json.loads(obs['payload'])
        if evidence['columns'] != product['columns']:
            problems.append('Source schema or sensitivity drift: ' + source)
        if time.time() - evidence['data_as_of'] > product['max_staleness_seconds']:
            problems.append('Source data is stale: ' + source)
        for check in ('lineage_verified', 'row_security_verified', 'column_security_verified', 'negative_access_tests_passed', 'grain_tests_passed'):
            if evidence[check] is not True:
                problems.append('Unverified ' + check + ': ' + source)
    tree = sqlglot.parse_one(payload['sql'], read='bigquery')
    aliases = {t.alias_or_name: '.'.join(p.name for p in t.parts) for t in tree.find_all(exp.Table)}
    output = [node.alias_or_name for node in tree.expressions]
    if output != contract.output_columns or len(output) != len(set(output)):
        problems.append('SELECT output must match ordered, unique output_columns')
    for c in tree.find_all(exp.Column):
        if c.name in output and not c.table and c.find_ancestor(exp.Order):
            continue  # ORDER BY a selected alias, not an extra input column.
        candidates = [aliases[c.table]] if c.table in aliases else list(aliases.values()) if not c.table else []
        matches = [s for s in candidates if s in products and c.name in {v['name'] for v in products[s]['columns']}]
        if len(matches) != 1:
            problems.append('Unknown or ambiguous governed column: ' + c.sql())
    # Named UDFs/remote routines require a future separately certified capability.
    if any(isinstance(n, exp.Anonymous) for n in tree.walk()):
        problems.append('Unregistered routines are not permitted')
    return sorted(set(problems))


def enforce(db, payload):
    problems = findings(db, payload)
    if problems:
        raise HTTPException(409, problems)


def observe(db, observation):
    row = db.execute('SELECT * FROM data_products WHERE source=?', (observation.source,)).fetchone()
    if not row or row['digest'] != observation.product_digest:
        raise HTTPException(409, 'Observation is for an outdated product policy')
    if observation.data_as_of > time.time() + 30:
        raise HTTPException(422, 'Data freshness timestamp cannot be in the future')
    from .db import canonical
    db.execute('INSERT INTO data_observations VALUES(?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET product_digest=excluded.product_digest,payload=excluded.payload,observed=excluded.observed,expires=excluded.expires',
               (observation.source, row['digest'], canonical(observation.model_dump()), time.time(), time.time() + observation.ttl_seconds))
