# Synthetic work-connection fixtures

Nothing here represents a real company dataset, supplier, test result or launch decision.
The GCP project `dc-synthetic-demo`, evidence bucket and `.invalid` registry/hosting
names are placeholders. Never treat them as discovered work infrastructure.

`bigquery/catalog.json` defines three view-shaped data products; `queries.json` binds
exact versions, output schemas and budgets. `synthetic-rows.json` holds two programs
and test-only caller entitlements. Warehouse native RLS is NOT simulated merely by
adding a filter in production: the test double filters these rows to test the gateway
flow, while the work connector must prove actual warehouse authorization.

`apps/` contains source-contract fixtures and small React dashboard components, not
complete runnable images. They intentionally have no dist/ build output or installed
dependencies. A real build must compile them with the company's approved toolchain
and reject a missing index.html. The SDK's `templates/dashboard/` is a separate runnable
Node/static dashboard starter. Mock workers can report success in tests to exercise
control-plane transitions; this is not evidence that fixture containers were built.

| Mock upload | Registered source | Tested result |
| --- | --- | --- |
| Build Readiness | analytics_governed.assembly_readiness_v1 | Source accepted, mock build/review/deploy, one synthetic program-a row |
| Supplier Delivery | analytics_governed.supplier_delivery_v1 | Same control flow; Manufacturing-only viewer denied data |
| Test Telemetry | analytics_governed.test_telemetry_v1 | Same control flow; approved Test & launch query contract |

Negative cases include raw dataset references, unknown columns, expanded audiences,
cost limits, missing build checks, expired/replayed leases, restricted app discovery,
schema/freshness/row-policy drift, revoked dependencies, cross-app tokens and forbidden
agent edits. Run `python scripts/mock-uploads.py`; see docs/VERIFICATION.md.

At work, keep these fixtures unchanged as regressions. Add real connections and real
acceptance cases only in the company checkout, using CLAUDE.md and WORK-CONNECT markers.
