# Dreamcatcher — work integration entrypoint

You are receiving a synthetic prototype, NOT an already-connected corporate platform.
The owner wants this transferred to the work computer and connected to real systems.
Read this file, `integrations/CONNECTIONS.json`, `docs/V2-PLATFORM.md`, and
`docs/WORK-COMPUTER-HANDOFF.md` before changing integration behavior.

## First actions

1. Inspect the destination repository and its applicable instructions. Confirm the
   work checkout and approved company Git remote with the human; do not push to a
   personal remote. Preserve local changes. Do not copy company documents here.
2. Run `python scripts/doctor.py --json`, `python -m pytest -q`, `npm run typecheck`,
   `npm run build`, and `npm run test:sdk`. Report missing dependencies, not fake passes.
3. Search `WORK-CONNECT:` and the connection IDs in `integrations/CONNECTIONS.json`.
   These are intentional replacement seams, not TODOs to bypass with mock successes.
4. With permission, inspect actual local company auth, BigQuery/dbt/catalog, CI,
   skill and deployment conventions. Record exact file paths and unresolved choices
   in a WORK-ONLY integration report. The resume/research attachments are NOT config.
5. Pick one real dashboard with an owner and a certified source. Keep the synthetic
   fixtures as regression tests. Connect one seam at a time and run its acceptance test.

## Non-negotiable trust boundaries

- App discover/use/edit/deploy/share/review and warehouse entitlements are separate.
  Administrators do not automatically receive restricted app or row access.
- BigQuery evaluates the execution principal. The sample per-user service-account
  mapping is NOT end-user delegation. Replace it if the company model differs;
  prove negative row/column tests before enabling it. Never add a shared fallback.
- A catalog name, SQL parser, SKILL.md, uploader claim or model answer is not proof
  of governed data. Use trusted, expiring metadata observations and actual warehouse
  policies, with lineage/schema/grain/freshness/negative-test evidence.
- No uploaded code or install scripts run in FastAPI. Workers run separately with
  separate credentials. Build in an isolated sandbox without the worker credential,
  prove the full dependency inventory, and deploy exactly the scanned image digest.
- The app maintainer has a stable identity and immutable upload context, not a
  continuously running privileged agent. Its output is an untrusted proposed UI
  patch. No IAM/SQL/secret/runtime edits or production writes through that capability.
- The private edge is intentionally unconnected. Do not expose the container or
  forward an identity header without validated authentication and gateway authorization.
  Preview routing/session isolation also needs real integration; queued is not deployed.
- Small per-user app preferences belong in a separate state database, with FORCE RLS.
  BigQuery remains the analytics system of record. Do not copy warehouse tables into
  every app database. No database credentials in app containers.
- Never change disabled adapters to return success. Do not set `DC_DEMO=true` in
  production, fabricate a scan result, suppress a failing permission test, or broaden
  IAM merely to make a dashboard work. Ask for approval when new authority is needed.

## Concrete next patch

Create a company-only `work_connections.py` implementing `WorkAdapter`. Start with
catalog observation and a single delegated query, then isolated build/private
hosting, then the approved model endpoint. Run `python scripts/worker.py --kind build
--adapter work_connections` only after its sandbox boundary is reviewed. The command
handles one lease; schedule repeated work with the approved job system.

Implement a work-only real-integration test suite alongside the synthetic tests:
allowed user, denied user, disabled user, cross-app token, restricted reviewer,
schema drift, stale data, sensitive column, cost ceiling, direct-host bypass,
revocation during deployment, supply-chain rejection, agent privilege escalation,
PostgreSQL cross-tenant access, audit export and backup restore.

Finish with evidence locations and remaining blockers. Do not describe mocks as GCP
tests, model proposals as applied changes, or deployment requests as healthy services.
