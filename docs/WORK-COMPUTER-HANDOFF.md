# Work-computer handoff

This transfer is one-way. The work environment becomes authoritative after import. Do not sync company code, data, secrets, internal URLs, or modified skill contents back to a personal repository. This package contains a standalone beta and synthetic data, not a copy of Paul OS or company infrastructure.

## 1. Establish a local baseline

Extract the archive into its own folder outside the existing Paul OS checkout. Follow README, run the build and tests, then `python scripts/doctor.py`. The preflight only checks local installation/configuration; it does not contact company services or certify the system.

Keep the demo in a separate local data directory. Verify the builder/viewer/outsider flows and record any design changes before integration. Start with Dreamcatcher as its own service and a Paul OS navigation link; embed or merge components only after inspecting the actual work repo. Do not assume Paul OS routes, authentication, database schemas, or skill directories match this package.

## 2. Discover actual integration points

| Input to locate at work | Required decision | Completion evidence |
| --- | --- | --- |
| Existing app/service conventions | Standalone service versus module; package manager, runtime and routing | Decision with exact local file paths |
| Identity provider and session boundary | Issuer/subject mapping, membership source, callback and logout behavior | Real login plus disabled-user/incorrect-audience tests |
| App ownership and groups | Accountable owner; run/edit roles; approved audiences | Example owner, permitted caller and denied caller |
| BigQuery and dbt artifacts | Approved source objects, transformation chain, grain and data owner | Model/source IDs, compiled definitions and SME sign-off |
| Warehouse authorization | Caller-to-principal mapping, IAM, row/column restrictions | Allowed and denied query results using real test identities |
| Package policy and CI | Approved registry, version/integrity policy, trusted build signer | Rejected dependency fixture and verified release artifact |
| Existing skills | Local package convention, runtime/tool contracts and connection bindings | Export/import test with destination review and no credentials |
| Deployment and operations | Host, TLS, secret store, backups, logs and rollback owner | Restore drill and deployment verification record |

Record unknowns explicitly. Do not invent project IDs, group names, role grants or certified tiers. Existing tiered mart/report certification should remain authoritative; Dreamcatcher query approval is a separate control until an explicit mapping is approved.

## 3. Pilot one app and one governed data path

Choose one existing test app with a known owner and one approved dbt-produced BigQuery view. Trace the source → staging → intermediate → mart → consumer transformations from actual local artifacts. Record grain, keys, joins, filters, units, freshness expectations and access rules. Reconcile its results to the existing report or semantic model before exposing it to others.

Register a parameterized query with an exact version and source list. The current parser rejects CTEs; point it at an approved view instead of changing the contract to SELECT *. If the existing corporate authorization model differs from the example service-account mapping, implement an adapter and negative access tests before enabling it.

Configure OIDC with a fresh non-demo registry. Provision the owner, reviewer and pilot callers. A shared app must not transfer the owner's warehouse authority. Demonstrate that a user can discover an app but still receive a data-access denial.

## 4. Connect the trusted release pipeline

Use the actual corporate CI/build system. Generate the full dependency inventory and security results inside that trusted job, build once, attest that artifact and deploy those same bytes. Keep signing authority out of app authors' environments. The supplied signer accepts files; it does not independently establish their provenance.

Test unapproved transitive packages, modified lockfiles, stale or tampered evidence, self-approval, revoked query/skill versions and URL-to-deployment mismatch. External app hosting needs its own immutable release binding; a registry link alone cannot prove what code is running.

## 5. Make skills transferable without transferring trust

Preserve instructions and domain references as portable files. Declare exact query versions and tool/input/output contracts. Map logical connections at the destination and require local approval. This beta executes deterministic query steps only. Existing Python/agent skills need a separately approved isolated runtime adapter; do not run uploaded scripts inside FastAPI.

For each imported skill, check id/version conflict, compatibility, required query approvals, entitlements and expected outputs. Export should exclude credentials and environment-specific permissions. Do not equate portability with automatic activation.

## Acceptance and rollback

Accept the pilot only after: owner and independent reviewer complete a release; permitted users see reconciled results; denied users receive no protected rows; revocation blocks old tokens/releases; a skill round-trip requires destination review; the external app artifact matches the approved build; and registry restore is demonstrated.

Rollback by unpublishing the pilot, revoking app grants/tokens, routing users to the existing app/report, and disabling the new connector. Restore the registry only through the approved backup procedure. Preserve the prior app/report and its data pipeline until the pilot passes acceptance.

Deliver an integration report containing changes, exact file paths, tests performed, evidence locations, unresolved decisions and rollback commands. Keep that report inside the work environment.
