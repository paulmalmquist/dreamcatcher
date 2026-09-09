# Architecture and roadmap

Dreamcatcher is a registry and governed execution service, not a replacement app builder. Teams keep familiar app frameworks and publish URLs. Standard HTTP, SQL contracts, npm lockfiles, ZIP skill packages and an ESM SDK preserve transferable development skills.

## Boundaries

- React/Three.js handles discovery and administration. FastAPI owns all authority; hiding a button is never the permission check.
- The registry stores people, grants, immutable asset/release versions, approvals, package policies and audit events in SQLite.
- The execution layer intersects app permissions, current release readiness and data-group entitlements, then runs a registered query. Clients cannot submit raw SQL for execution.
- Local warehouse access is read-only, uses a separate database, authorizer, bounded runtime and row limit. `_user_id` is server-bound. The demo contracts filter on that identity; reviewers must verify every new contract's row/column semantics.
- BigQuery uses an explicit user-id → execution-principal mapping, not a shared privileged fallback. Warehouse IAM, row policies, policy tags and authorized views remain the actual data perimeter. Mapping two users to the same principal shares that principal's warehouse permissions.
- Corporate transformations remain in dbt/governed views. This beta intentionally rejects CTEs and wildcard SELECTs. It does not parse dbt manifests, administer Power BI permissions or synchronize catalogs yet.
- An external app URL is a destination, not evidence of source, dependency compliance or an immutable deployment. Registry execution is controlled; code hosted elsewhere is not controlled by this process.

## Reference capability inventory

Appsmith's repository and documentation were used as reference categories, not copied implementation. Enterprise feature availability varies; no license-equivalence is claimed.

| Desired capability | This beta | Next production increment |
| --- | --- | --- |
| Authentication | Local demo and configurable OIDC | Validate chosen IdP, group lifecycle, MFA and session policy |
| Sharing / RBAC | User/group/workspace grants; run vs edit | SCIM/group sync, delegated ownership, access reviews |
| Environments | Separate deployments/data directories | Explicit dev/test/prod promotion and policy bundles |
| Governed queries | SQL contracts, review, revocation, local execution | dbt/catalog ingestion, BigQuery IAM integration tests and lineage |
| Approved packages | Exact lock/integrity policy and signed release evidence | Trusted CI build/scanning/deploy integration, registry mirror, license checks, SBOM verification |
| Portable skills | ZIP contracts + deterministic query steps | Versioned runtime adapters, compatibility/evaluation gates, isolated script workers |
| Audit / operations | Local audit records and session revocation | Append-only external audit sink, retention, backups, metrics, alerts |
| Scale / tenancy | Single workspace, single-node SQLite | PostgreSQL migration, tenant-scoped keys/policies and HA |

## Sequencing

1. Beta acceptance: validate gallery flows with real test app links; agree ownership and data-group taxonomy; collect user feedback.
2. Governed pilot: IdP provisioning, approved BigQuery views, per-caller IAM mapping, trusted CI evidence, restricted app-host allowlist, security review.
3. Team sharing: lifecycle/group synchronization, promotion between separate environments, dependency/asset revocation drills, restore tests.
4. Scaled platform: PostgreSQL/HA, external audit and observability, richer skill adapters with isolation and executable evaluations.

The local beta is runnable now. Phases 2–4 require organizational decisions and integrations; they are not represented as already complete.

References: https://github.com/appsmithorg/appsmith ; https://docs.appsmith.com/ ; https://fastapi.tiangolo.com/ ; https://sqlglot.com/ ; https://cloud.google.com/bigquery/docs/parameterized-queries ; https://cloud.google.com/iam/docs/service-account-impersonation
