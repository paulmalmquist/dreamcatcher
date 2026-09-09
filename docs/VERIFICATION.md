# Verification record

Authoring environment: Linux, Python 3.12; Node/npm workspace build.

- 68 backend/integration tests pass after building (2026-09-09). The original 26 tests remain; 42 additions cover three synthetic hosted dashboard uploads, source intake, worker authentication/leases/replay, independent and restricted review, data-contract approval, row/audience separation, schema/freshness/RLS/lineage/grain drift, revoked packages, app-scoped state CAS/idempotency, UI-only agent proposals/candidates, developer/runtime token scope and revocation, deployment revision races, BigQuery dry-run byte/output checks with a fake client, request budgets, Python SDK contracts, CLI ZIP interoperability and work-handoff consistency. Distribution smoke tests run against the built frontend/SDK; without a build the legacy distribution test skips.
- 10 SDK/CLI tests pass: legacy contracts plus request-scoped context, state CAS, path safety, telemetry shape, synthetic source packaging and offline JSON schema checks.
- Frontend TypeScript check and Vite production build pass; SDK declarations and distributable tarball build successfully.
- Both portable SKILL.md instruction packages pass the skill validator. Python compilation and Node template syntax checks pass; the SDK tarball contains CLI, schema, declarations and dashboard template assets.
- No live corporate IdP or BigQuery calls, PostgreSQL connections/RLS tests, real model calls, container build/run, Windows execution, automated browser interaction, penetration test or live-host deployment verification was performed. Tests use real FastAPI HTTP routes and temporary SQLite persistence, with explicitly synthetic warehouse and build/deployment/model worker doubles.
- Python test tooling emits two upstream deprecation warnings. They do not fail the tests. The Three.js chunk is relatively large and is lazy-loaded independently of the UI.

Re-run the commands in README on your machine and in CI; this record is not a substitute for production acceptance tests.

Run `python scripts/mock-uploads.py` for the focused, verbose synthetic upload suite.
The test database is temporary and no running registry or GCP project is contacted.
Future work-only live integration results must stay in the work environment.
