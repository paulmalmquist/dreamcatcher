# Admin console — Mission control

The console is a working interface to the beta control plane. It does not provision
GCP, certify scanner output, or claim that the work connections are live.

Start the repo using README, sign in as `admin@demo.local` with the local demo
password, and select **Admin console**. Do not expose demo accounts on a network.
The ordinary gallery, SDK download, uploads and reviewer/builder flows remain.

## What you can operate

| Panel | Working controls | Important boundary |
| --- | --- | --- |
| Overview | Record-derived app, queue and account counts; release blockers | Counts include only inspectable hosted apps; configuration is not health |
| Applications | Current releases, owner, classification, query counts, lifecycle form, release-management dialog, confirmed suspend/resume | Owner or explicit `share` grant required for lifecycle/suspension; restricted inspection requires an app grant |
| People & access | Edit existing roles/groups; confirm account enable/disable | Server revokes affected sessions; corporate IdP provisioning is still separate |
| Package policy | Create exact unapproved rule; explicitly approve/revoke version/hash/source | Duplicate creation returns 409 without changing an existing approval; not a scanner |
| Worker jobs | Inspect scoped queue; cancel with reason; explicitly retry failed build/agent jobs | Stale reports are rejected; external build/container cleanup is the adapter's job |
| Connections | Named replacement seams, configuration-presence flags and required acceptance tests | Always labeled unverified; no secret values or credential input fields |
| Audit history | Recent scoped app/job and global account/package events; pending sink-delivery count | Local records are not tamper-proof; external append-only sink unconnected |

This is one organizational workspace, not a multi-organization tenant console.
New-account provisioning remains in the existing registry/operator workflow.
There is no automatic ownership transfer, email-invitation service, live GCP cost
meter, automatic cloud teardown, or "grant all" administrator bypass.

## App permissions and review

Being a platform admin is not app ownership. Owners explicitly grant capabilities
such as `share`, `use`, `edit`, `deploy` or `review`. Internal apps allow independent
admin/reviewer review by role; restricted apps additionally require an explicit
review grant. Neither role nor app sharing grants warehouse rows or columns.
Direct API requests enforce the same rules as the UI, including session and CSRF
checks. Restricted apps/jobs/audit are omitted without inspection permission.

Suspension invalidates runtime sessions and revokes queued/ready deployment
admission. Resume enables management again; **promote a still-approved release
again** to obtain fresh deployment admission. It does not resurrect revoked routes.
An infrastructure worker must separately reconcile/stop old cloud resources.

## Lifecycle and analytical correctness

Owners can set lifecycle policy inside the app's Release panel; share-authorized
admins can also use Applications → Lifecycle. Supply an accountable support
contact, a future review deadline within one year, a runtime profile, and limits.
Updates use revision checks and revoke current app sessions. Overdue reviews block
new runtime calls. Production (`DC_ENV=production`) requires this policy.

The default is `custom-backend`. Choosing `standard-dashboard` also requires the
trusted builder to attest `checks.platform_runtime_verified=true` for a reviewed
platform-owned runtime. Merely changing the dropdown is not proof. At work verify
the actual server/base image/egress/dependencies; do not trust uploader declarations.

Apps with queries or skills require image-bound independent analytical review in
production. Enable `DC_REQUIRE_ANALYTICAL_REVIEW=true` to exercise the gate locally.
A reviewer opens a built release and records a retained golden-test evidence URI
and SHA-256 before approval. The app owner/submitter cannot self-review; a new
submission/image needs a fresh record. This is a human attestation record, **not**
an automated fetch, execution or certification of the evidence.

Review grain, joins, aggregation, metric units, filters, rounding, empty versus
zero, partial/truncated results and permission-dependent denominators. JSX can
change those meanings without editing SQL. `examples/flight-deck/src/metrics.mjs`
and `tests/frontend.test.mjs` provide synthetic positive/negative golden cases.
Replace expectations with SME-approved company metrics at work; keep the fixtures.
Never give an app-edit agent real protected rows merely to help it edit a UI.

## Request budgets and image assurance

Lifecycle limits default to 120 gateway queries/app/minute and no minimum refresh
interval. These shared database-backed counters apply across legacy and v2 routes;
optional refresh cadence is per app/user/query, independent of selected parameters.
Failed admitted queries consume budget. Rejection returns 429 and `Retry-After`;
there is no result cache or automatic SDK retry. A minute-window quota can allow
boundary bursts, and is not a measured BigQuery spend cap or concurrency controller.

Trusted build reports establish image assurance. It expires after
`DC_SCAN_VALIDITY_SECONDS` (default 86400; bounded to 60..604800). Failed, mismatched
or expired assurance blocks admission/runtime even for a previously approved app.
Production also rejects missing assurance on older releases. Only the build worker
can `POST /api/v2/workers/build/rescan` with the exact submission/image, pass result,
retained evidence URI and SHA-256. Schedule real rescans at work; the endpoint itself
does not run a scanner. Package and catalog policies are still rechecked independently.
Evidence references must be credential-free durable references, not signed URLs.

## Worker recovery

Workers claim 15-minute leases. `scripts/worker.py` renews every 30 seconds, with a
one-hour hard deadline per attempt. Renewal needs both the kind-specific worker
credential and current lease. Expired, completed, cancelled and stale leases cannot
be revived. If renewal is lost, the helper does not submit its result; the operator
must reconcile the external task before retrying.

After three expired attempts, the next claim sweep moves the job to `dead_letter`
and marks its queued target failed. This is not a standalone background scheduler.
Admin recovery requires an explanation and inspection permission for the app.
Retry applies only to terminal build/agent jobs with unchanged failed targets;
deployment failures require a **new admission request**, not blind retry. A cancel
rejects future reports; it cannot kill an independently running cloud job. Implement
idempotent external job IDs, cleanup and orphan reconciliation in the work adapter.

## Shared edge session seam

`integrations/private-edge/session-store.mjs` defines the async `get(id)`,
`put(id, session)` and `delete(id)` contract. `put` must atomically insert only new
IDs, enforce TTL/capacity, and return a boolean. Store app/origin/release binding,
expiry and the server-only runtime token. Never return that token to the browser.

Local mode uses a bounded memory store and requires relaunch after restart.
Production startup instead imports a work-only root `work-edge-sessions.mjs`
exporting `createSessionStore()` and requires `persistent: true`. The flag is an
adapter declaration, not proof of durability. That file is ignored by git and the
transfer packager. WORK-CONNECT: private-edge — implement approved encrypted shared
storage and prove two-replica/restart, TTL, outage, cross-user/app and revocation
tests before enabling production. Store failure must deny access. Local tests use
two handlers with one memory adapter; they do **not** prove real shared persistence.

## Transfer checklist for work Claude

1. Read CLAUDE.md and CONNECTIONS.json; confirm the company-only remote.
2. Retain synthetic regression tests and run all README verification commands.
3. Connect identity/catalog/warehouse first; prove two identities see different
   authorized rows and that denied identities cannot bypass the gateway.
4. Implement isolated build + real image inventory/scan freshness, metric evidence,
   private routing, edge persistence and orphan-job cleanup. No uploaded code on the
   registry host or access to worker/metadata credentials.
5. Use managed control/state databases, least-privilege runtime roles, reviewed
   migrations and tested restore. Validate quotas/CAS/leases under concurrency.
6. Connect append-only audit export and alerts for overdue reviews, stale scans,
   job failures and budget exhaustion. Add policy-change impact previews, ownership
   transfer and scheduled access recertification through company approval processes.

The updated CI container story covers real upload/build/browser/admin actions with
synthetic warehouse/scanner/model evidence. Check the **current commit's** Actions
run; an older screenshot or retained report is not proof for newer source.
