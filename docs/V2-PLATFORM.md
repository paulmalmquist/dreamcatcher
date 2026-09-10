# Containerized Dreamcatcher: implementation and work handoff

This extends the existing URL-first gallery; it does not copy Appsmith's UI or claim
to reproduce Databricks internals. A hosted app and a legacy external link are
different resource types. External URLs still need independently protected hosting.

## Workflow

1. Register a hosted app (Upload your app → containerized app). Choose internal or
   restricted classification; it cannot be silently downgraded in a later upload.
2. Open its Release tab and upload a ZIP with dreamcatcher.json and Dockerfile at the
   root, source, and complete lockfiles. ZIP paths, links, secrets and size limits are
   checked without extraction/execution. Each app/version is immutable.
3. A separately authenticated build worker leases the job and fetches the exact source.
   BuildReport binds source-index digest, normalized manifest digest and image digest,
   a complete dependency inventory and required scan/test results. The trusted worker
   must calculate these results; uploader evidence is never accepted on this API.
4. A different reviewer approves the built submission only if current package, query,
   skill and data-product policies pass. Restricted apps require explicit review grants.
5. A deploy request queues a private preview or production job. The worker verifies the
   image, private edge/ingress, egress, health and resources. Only a valid readiness
   report activates production. Build/deploy failures and unconnected workers do not
   produce a synthetic success. Preview URLs are recorded but a real preview-specific
   edge/session implementation is still required at work; the runtime gateway here
   only serves the active approved production submission.
6. Runtime requests recheck current release, sharing, packages and query/data policies.
   Suspension/revocation denies subsequent gateway calls. The deployment adapter must
   also tear down/restrict the physical service; platform status alone is not teardown.
   Restore by promoting a previously approved submission that still passes policy.

## What the upload declares

`sdk/contracts/dreamcatcher.schema.json` is generated from the server Manifest model.
`runtime.web=spa` requires a built `dist/index.html` (or another safe index.html path).
The trusted builder verifies that the built file exists. An HTTP-only application
sets `web=http` and `entrypoint=null`; index.html is not universal to all containers.
All containers implement dc-http/v1: PORT, /healthz, /readyz, bounded resources,
non-root operation, no host socket and controlled egress. SPA fallback belongs to
the app server, not a blanket rewrite of failed API routes to index.html.

Declarations request exact query/skill references and user-scoped state collections.
They never grant warehouse access, package approval or new runtime destinations.
Image/npm/Python/OS inventory entries are exact version, source and SHA-256 hashes.
The build adapter must derive them from actual artifacts/SBOMs; the registry cannot
prove inventory completeness from an app-provided list or scanner booleans alone.

## Governed analytical dashboards

Use `examples/bigquery/` for plausible **synthetic** GCP inputs. It contains three
certified-view-shaped contracts: assembly readiness, supplier delivery, test telemetry.
Each source has an owner, exact revision, grain/columns, audience, classification,
freshness threshold, row-security model and cost ceiling. Query definitions bind
the exact source revision and ordered output schema. Use approved views, not raw
tables or embedded SELECT * transformations; current parser intentionally rejects
CTEs and unregistered routines. Add capabilities through reviewed contracts, not
parser exceptions tailored to one uploaded app.

The data worker publishes an expiring Observation with schema, business-data watermark,
lineage, grain tests, native RLS/identity-filtered authorized-view proof, column policy
proof and negative access tests. Its retained evidence has a URI and digest. This is
an attestation trust boundary, not an implementation of the company's catalog scanner.
Do not substitute table metadata modification time for a data-freshness watermark.
Trace underlying dependencies, not just the top-level view name. Schema/policy edits
invalidate the product digest; expiration, stale data or drift blocks release/runtime.
Detection is bounded by the observation TTL (maximum one hour, normally five minutes),
not instantaneous. Warehouse-native controls remain the ultimate row/column boundary.

Before each real BigQuery execution, enforce caller entitlements, bind parameters,
dry-run under the intended principal, compare output schema and estimated bytes, and
set maximum_bytes_billed, no result cache, a timeout and a row cap. A per-user fixed
minute request budget applies across apps (default 20). This complements, not replaces,
company BigQuery project/reservation quotas, concurrency limits and spend alerts.
No shared privileged principal fallback exists. The optional per-user service-account
mapping is a sample execution model, NOT human user impersonation; BigQuery sees the
service account. The work integration must choose and prove the actual identity model.

App permission does not imply data permission. A user may discover an app without
using it, or use it while receiving a data denial. Admin/reviewer roles do not bypass
query group checks. Internal apps cannot declare restricted data, including via skills.
Sensitive columns require restricted classification. Exports and drill-through must
use the same governed gateway; there is no unrestricted raw export endpoint.

## Dedicated database: yes, but not a warehouse per app

- Control-plane metadata uses registry.sqlite locally; PostgreSQL is mandatory in
  production (`DC_DATABASE_URL`). Run `scripts/migrate.py` using a migration-only
  account; keep `DC_AUTO_MIGRATE=false` for the running production API.
- Small user preferences use separate app-state.sqlite locally, or a distinct
  PostgreSQL state database/connection (`DC_STATE_DATABASE_URL`). Run the reviewed
  `deploy/postgres-state.sql` migration and grant only needed DML to a non-owner,
  non-superuser, NOBYPASSRLS gateway role. Runtime checks reject unsafe table/role flags.
  FORCE RLS and transaction-local app/user context provide defense in depth. App code
  receives neither connection string. Separate databases per app are optional for
  sensitivity/retention requirements; not the default.
- State supports per-user collection/key reads and bounded JSON writes, expected-version
  compare-and-swap and idempotency keys. It is not a general transaction/SQL service.
  Concurrent PostgreSQL idempotency and policy behavior need live tests; local SQLite
  serializes writers. State and control audit are separate transactions, so configure
  an appropriate state-outbox mechanism at work for strict atomic audit requirements.
- BigQuery remains the analytical system of record. Do not replicate the warehouse
  into application state. Add transactional app-domain models as reviewed migrations.

## App agents and portable skills

The first upload provisions a stable per-app maintainer identity. Each subsequent
submission adds an immutable source/manifest context; it does not create a privileged
resident process. A UI request queues a job against a specific submission. An approved
model worker may return a source-hash-bound AgentProposal restricted to UI paths/file
types. The registry validates it and the owner can create a NEW candidate submission.
No direct live editing, IAM changes, execution of uploaded instructions or automatic
promotion exists. Source is untrusted context, even when it contains SKILL.md.

`skills/app-maintainer/` and `skills/governed-data-validation/` are portable instruction
packages, separate from the existing deterministic query-skill execution engine. Move
them with their contracts and obtain destination approval. No model service or company
connection is configured in this repo. Implement WorkAdapter.agent at work; never use
the model's natural-language assertions as security evidence.

## Worker operation and known limits

`scripts/worker.py` handles one renewable 15-minute lease with up to three claims. Worker keys
are separate by kind and must never be supplied to an untrusted build or app. Source
fetches are lease-bound. Results are single-use; expired/stale/replayed leases fail.
The helper renews every 30 seconds, bounded to one hour per attempt. The next claim
sweep dead-letters three exhausted attempts. Admin-console cancellation/retry still
requires external-job reconciliation; it does not kill cloud tasks. Deployment
retries need fresh admission. See [the operating guide](ADMIN-CONSOLE.md) for
lifecycle deadlines, image-assurance expiry, analytical review and query budgets.

`integrations/adapters.py` intentionally raises IntegrationRequired. Implement the
company-only work_connections module, trusted catalog attestor, runtime edge and
audit sink after discovering real conventions. No generic local shell executor,
public deployment, model invocation or cloud provisioning is hidden in this prototype.
The production control-plane Dockerfile does not include optional warehouse/PostgreSQL
dependencies by default: extend it with company-resolved hash-locked requirements.

The control database has an audit outbox. An append-only external sink, retention,
delivery worker, resource quotas, container teardown and complete operational backup/
restore are work-integration acceptance items, not features claimed by mock tests.

## API map

| Consumer | Endpoint family | Boundary |
| --- | --- | --- |
| Admin console | /api/v2/admin/*; /api/admin/users; /api/v2/runtime-packages | Admin role plus explicit app visibility/capabilities; no warehouse override |
| Builder/reviewer UI | /api/v2/apps/* | Explicit app capabilities and browser CSRF |
| SDK / app backend | /api/v2/runtime/{app}/*; /api/execute/* | User + app + current release + data policy |
| CLI | app overview/source upload/source export | One-hour app-scoped developer token; no approval/deploy/sharing |
| Trusted workers | /api/v2/workers/* | Kind-specific credential plus single-use lease |
| Catalog worker | /api/v2/workers/data/observations | Separate trusted data credential, current product digest |
| Data steward | /api/v2/data-products; /api/v2/queries/*/validate | Policy administration / permitted inspection |

## Reference documentation used

- Databricks Apps: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/
- BigQuery row security: https://docs.cloud.google.com/bigquery/docs/row-level-security-intro
- BigQuery dry runs: https://docs.cloud.google.com/bigquery/docs/running-queries
- BigQuery cost controls: https://docs.cloud.google.com/bigquery/docs/best-practices-costs

These inform the architecture. They are not evidence that this prototype has connected
to, deployed on, or passed the security controls of those platforms.
