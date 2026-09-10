# Verification record

Authoring environment: Linux, Python 3.12; Node/npm workspace build.

- 76 backend/integration tests pass after building (2026-09-10). The original 26 tests remain; 50 additions cover three synthetic hosted dashboard uploads, source intake, worker authentication/leases/replay, independent and restricted review, data-contract approval, row/audience separation, schema/freshness/RLS/lineage/grain drift, revoked packages, app-scoped state CAS/idempotency, UI-only agent proposals/candidates, developer/runtime token scope and revocation, deployment revision races, BigQuery dry-run byte/output checks with a fake client, request budgets, Python SDK contracts, CLI ZIP interoperability, work-handoff consistency, and eight one-use launch/admission/logout tests. Distribution smoke tests run against the built frontend/SDK; without a build the legacy distribution test skips.
- 10 SDK/CLI tests pass: legacy contracts plus request-scoped context, state CAS, path safety, telemetry shape, synthetic source packaging and offline JSON schema checks.
- 3 reference-edge tests pass: identity header replacement, host/cookie/CSRF boundaries, gateway revalidation, constrained response headers, changed releases, outages and expiry. These use real local HTTP with a fake gateway/upstream, not a live company edge.
- Frontend TypeScript check and Vite production build pass; SDK declarations and distributable tarball build successfully.
- Both portable SKILL.md instruction packages pass the skill validator. Python compilation and Node template syntax checks pass; the SDK tarball contains CLI, schema, declarations and dashboard template assets.
- No live corporate IdP or BigQuery calls, PostgreSQL connections/RLS tests, real model calls, Windows execution, penetration test or company-host deployment verification was performed. API tests use real FastAPI HTTP routes and temporary SQLite persistence, with explicitly synthetic warehouse and build/deployment/model worker doubles.
- The Docker/Chromium story passed on 2026-09-10: [GitHub Actions run 34423443728](https://github.com/paulmalmquist/dreamcatcher/actions/runs/34423443728), implementation commit `d69ccb3f7d7f4c3006af3ebd9fef81bc78da11c7`. Both app versions were built and run as non-root containers. A browser uploaded the source, a separate reviewer approved, the viewer launched via the HTTPS edge, forbidden rows/access were denied, a deterministic maintainer proposal was rebuilt/reapproved, the changed heading rendered, and revocation blocked both refresh and HTML reload. No uncaught browser errors occurred. [Retained structured evidence](evidence/2026-09-10-container-story.json) includes distinct source/image identities and the explicit test-double list; see `docs/CONTAINER-STORY.md` for limitations. This is not production security certification.
- Browser verification caught and fixed late demo-email autofill, unnecessary paused-starfield rendering, a cross-origin launch/referrer-policy conflict, and the dashboard selector's accessible name.
- Python test tooling emits two upstream deprecation warnings. They do not fail the tests. The Three.js chunk is relatively large and is lazy-loaded independently of the UI.

Re-run the commands in README on your machine and in CI; this record is not a substitute for production acceptance tests.

Run `python scripts/mock-uploads.py` for the focused, verbose synthetic upload suite.
The test database is temporary and no running registry or GCP project is contacted.
Future work-only live integration results must stay in the work environment.
