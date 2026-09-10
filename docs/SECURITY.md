# Security and deployment checklist

## V2 additions

Read docs/V2-PLATFORM.md and integrations/CONNECTIONS.json for the current hosted-app
contracts and unconnected work adapters. Hosted apps use separate discover/use/edit/
deploy/share/review capabilities and explicit review permission for restricted apps.
SDK runtime tokens for hosted apps also bind the active release; developer tokens
cannot approve, deploy or change permissions. Byte/row limits, dry-run output checks,
per-user BigQuery request budgets, expiring certified-source observations and app/user
state isolation are implemented. Worker source/report APIs are separately authenticated
and lease-bound. Upload source is never executed inside the registry.

Production requires PostgreSQL control metadata and a separately permissioned state
database for state features. The provided RLS migration and driver adapter require
real integration tests. Build/scanner, catalog, private-edge/hosting, model and audit
sink adapters are intentionally unconnected; mock worker results are test fixtures,
not production attestations. The registry's dependency inventory gate cannot prove a
worker's inventory is complete without a trusted build/scan implementation.

The sections below also describe the retained URL-first beta. Its HMAC signer is NOT
the hosted worker credential or a replacement for an isolated build pipeline.

## Implemented boundaries

Opaque sessions are hashed at rest; browser sessions use HttpOnly/SameSite cookies and CSRF checks. SDK tokens expire after one hour, are bound to an app, and only allow identity and governed execution endpoints. Disabling an account or changing its role/groups revokes its sessions. Production disables password login, requires OIDC, HTTPS origin, demo off, and a persistent session secret.

Assets and releases are immutable by version. A separate reviewer must approve; admins do not bypass data-group checks. Query execution checks current permissions and current policy, not just an old badge. Audit payloads omit query parameters/results and tokens. Audit rows are local and mutable by database operators; they are not a tamper-proof compliance log. Denied requests are not comprehensively audited yet.

The server never downloads or executes registered app URLs. It does not inspect external hosting, install uploaded dependencies, execute arbitrary skill scripts, or provide an untrusted-code sandbox. SHA/integrity policies depend on a trusted complete build inventory, not a claim from the app author.

## Before any company pilot

- Use a **fresh data directory** with `DC_DEMO=false`. Do not promote the seeded demo database. Demo signing evidence is rejected outside demo mode.
- Set `DC_ENV=production`, `DC_AUTH_MODE=oidc`, a real HTTPS `DC_ORIGIN`, exact `DC_ALLOWED_HOSTS`, and restrictive `DC_APP_HOSTS`. Put a TLS reverse proxy in front; do not publicly expose Uvicorn directly. Configure request limits and rate limiting at the edge.
- Store `DC_SESSION_SECRET`, `DC_OIDC_CLIENT_SECRET` and `DC_BUILD_SIGNING_KEY` in approved secret management. Builders must not know the build-signing key. Rotate keys deliberately; key rotation can invalidate releases.
- Register the OIDC callback as `https://YOUR_HOST/auth/callback`. Set issuer/client values in the environment. Provision by issuer + subject, not email matching. Example initial administrator:

```sh
python scripts/provision.py --issuer https://YOUR_ISSUER --subject PROVIDER_SUBJECT --email admin@example.com --name "Platform Admin" --role admin --group "Data & AI"
```

- Complete real IdP login/logout/session tests. OIDC integration is implemented but has not been exercised against your provider. Membership is manually administered; no SCIM or automatic IdP group sync. App logout does not sign out of the upstream IdP.
- For BigQuery, install optional requirements through your dependency approval process, set project/location/budget, configure workload identity/ADC, and set `DC_BQ_PRINCIPALS` JSON mapping registry user ids to least-privilege service accounts. Configure narrowly scoped impersonation rights and warehouse IAM/row/column policies. Do not give the fallback ADC principal general warehouse authority. No live BigQuery integration was tested here.
- Use authorized dbt-produced views, review grain and column exposure, test positive and negative access cases for each audience, and ensure no other direct data path circumvents the governed service.
- Integrate trusted build/test/scan/deploy evidence. Independently verify audit-report provenance, artifact hash, source revision and complete lock contents. The supplied signer is a helper, not an end-to-end supply-chain platform.
- Review and pin CI actions to organization-approved immutable commits. The provided version-tagged workflow is a starter, not a hardened deployment workflow. CI runs tests/build only; it does not deploy or issue production attestations.
- Configure backup/restore, encryption at rest, access logs, retention, monitoring and an external append-only audit sink. Test restore and revocation. SQLite is single-node; migrate before multi-instance/high-availability use.
- Have security engineers review this new code, dependency licenses, request/body limits, auth and tenancy assumptions. No penetration test or production security certification is claimed.

## Known scope limits

Single organizational workspace; no cross-organization tenancy, public anonymous sharing, email invitations, automatic ownership transfer or secret-manager UI. App/user state isolation exists, but PostgreSQL RLS still requires live verification. Complete package enforcement and LLM execution require the unconnected trusted worker adapters. The synthetic Flight Deck story builds/runs real Docker images and drives Chromium in CI; its scanner/catalog/deployment-admission/model evidence is test doubles, not live company acceptance. Windows execution, native dbt/Power BI ingestion and company hosting remain unverified. See VERIFICATION.md and the current commit's CI run.

The admin console adds real permission-checked operations, not a superuser data
bypass. Review deadlines, analytical attestations, query budgets, renewable worker
leases and expiring image assurance are documented in ADMIN-CONSOLE.md. A recorded
evidence URI/hash or persistent-adapter flag is not proof of real verification;
the trusted work services and negative acceptance tests remain essential.
