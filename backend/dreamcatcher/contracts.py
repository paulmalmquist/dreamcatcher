"""Portable, strict application and worker contracts. Declarations never grant access."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Collection(Strict):
    name: str = Field(pattern=r'^[a-z][a-z0-9-]{1,63}$')
    scope: Literal['user'] = 'user'
    max_bytes: int = Field(default=16384, ge=64, le=65536)


class Runtime(Strict):
    contract: Literal['dc-http/v1'] = 'dc-http/v1'
    port: int = Field(default=8080, ge=1024, le=65535)
    web: Literal['spa', 'http'] = 'spa'
    entrypoint: str | None = 'dist/index.html'
    health_path: Literal['/healthz'] = '/healthz'
    readiness_path: Literal['/readyz'] = '/readyz'
    cpu: int = Field(default=1, ge=1, le=4)
    memory_mb: int = Field(default=512, ge=128, le=4096)
    max_instances: int = Field(default=2, ge=1, le=10)

    @model_validator(mode='after')
    def entry(self):
        if self.web == 'spa' and (not self.entrypoint or not self.entrypoint.endswith('/index.html')):
            raise ValueError('SPA runtime needs a built index.html entrypoint')
        if self.entrypoint:
            safe_path(self.entrypoint)
        return self


class Manifest(Strict):
    apiVersion: Literal['dreamcatcher/v1'] = 'dreamcatcher/v1'
    version: str = Field(pattern=r'^\d+\.\d+\.\d+$')
    classification: Literal['internal', 'restricted'] = 'internal'
    runtime: Runtime = Field(default_factory=Runtime)
    queries: list[str] = Field(default_factory=list, max_length=100)
    skills: list[str] = Field(default_factory=list, max_length=100)
    collections: list[Collection] = Field(default_factory=list, max_length=20)
    egress: list[str] = Field(default_factory=list, max_length=20)
    editable_paths: list[str] = Field(default_factory=lambda: ['frontend/src/', 'src/', 'tests/'], max_length=10)

    @model_validator(mode='after')
    def unique(self):
        for refs in (self.queries, self.skills):
            if len(set(refs)) != len(refs) or any(not re.fullmatch(r'[a-z][a-z0-9-]{1,63}@\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?', r) for r in refs):
                raise ValueError('Unique exact-version resource references are required')
        if len({c.name for c in self.collections}) != len(self.collections):
            raise ValueError('Collection names must be unique')
        for p in self.editable_paths:
            safe_path(p.rstrip('/'))
            if not p.endswith('/') or not p.startswith(('frontend/src/', 'src/', 'tests/')):
                raise ValueError('Editing is limited to frontend/src/, src/, and tests/ subdirectories')
        if any(not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,252}', d) for d in self.egress):
            raise ValueError('Egress destinations must be exact DNS names, not URLs or wildcards')
        return self


def safe_path(value):
    if not isinstance(value, str) or not value or len(value) > 240 or value.startswith('/') or '\\' in value or ':' in value or any(p in ('', '.', '..') for p in value.split('/')) or any(ord(c) < 32 for c in value):
        raise ValueError('Unsafe archive or source path')
    return value


class Dependency(Strict):
    ecosystem: Literal['npm', 'pypi', 'os', 'image']
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    integrity: str = Field(pattern=r'^sha256:[a-f0-9]{64}$')
    source: str = Field(min_length=1, max_length=500)


class BuildReport(Strict):
    source_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    manifest_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    image: str = Field(max_length=600, pattern=r'^[a-z0-9][a-z0-9./:_-]+@sha256:[a-f0-9]{64}$')
    dependencies: list[Dependency] = Field(min_length=1, max_length=5000)
    checks: dict[str, bool]
    details: str = Field(default='', max_length=2000)


REQUIRED_CHECKS = frozenset({'source_verified', 'inventory_complete', 'secrets', 'vulnerabilities', 'licenses', 'container_contract', 'permission_tests', 'browser_egress', 'non_root'})


class AppGrant(Strict):
    subject: str = Field(pattern=r'^(user:[a-zA-Z0-9-]{2,80}|group:[^\x00-\x1f:]{1,100})$')
    permission: Literal['discover', 'use', 'edit', 'deploy', 'share', 'review']


class Grants(Strict):
    grants: list[AppGrant] = Field(max_length=100)
    expected_revision: int = Field(ge=1)


class EditRequest(Strict):
    submission_id: str = Field(max_length=80)
    prompt: str = Field(min_length=5, max_length=6000)
    component: str = Field(default='', max_length=240)


class FileChange(Strict):
    path: str = Field(max_length=240)
    before_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    content: str = Field(max_length=100000)


class AgentProposal(Strict):
    base_source_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    summary: str = Field(min_length=1, max_length=2000)
    changes: list[FileChange] = Field(min_length=1, max_length=20)


class StateWrite(Strict):
    value: dict
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(pattern=r'^[a-zA-Z0-9-]{8,100}$')
