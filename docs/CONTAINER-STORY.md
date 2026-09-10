# One dashboard, end to end

The `Flight Deck container and browser story` GitHub Actions job exercises the
real gallery UI, upload API, Docker build/run, HTTPS reference edge, per-request
SDK gateway authorization, immutable maintainer candidates and independent review.

## Reproduce

Use a disposable Linux machine/runner with Docker, Node 22, Python 3.12 and OpenSSL.
Do NOT run the harness on an operational worker or a machine with company data.

```sh
npm ci --ignore-scripts
python -m pip install -r requirements.txt -r requirements-e2e.txt
python -m playwright install --with-deps chromium
npm run build
DC_CONTAINER_E2E=1 python tests/e2e/story.py
```

The harness creates a temporary local registry and synthetic accounts. It starts
only the repository-owned fixture, with read-only filesystem, dropped Linux
capabilities, non-root user, and memory/CPU/PID limits. The lab uses Docker **host
networking** and loopback ports 18000, 18086, 18087 and 19443; this is NOT tenant
network isolation. It refuses modified runtime/build inputs and permits exactly
the scripted title edit. It is not an upload worker for arbitrary code.

| Stage | What is exercised |
| --- | --- |
| Upload | Browser registers Flight Deck and uploads a complete source ZIP |
| Build | Actual uploaded source is built into a Docker image; real image ID recorded |
| Review | Owner cannot self-approve; another account approves through the UI |
| Launch | One-use POST code becomes an app-origin HttpOnly cookie; bearer token stays server-side |
| Data | Program A renders; Program B has no rows for the viewer; outsider is denied |
| Edit | Immutable source context produces an explicit deterministic UI-only proposal |
| Rebuild | Candidate gets a new source/image identity; cannot promote until independently approved |
| Replace | Approved UI changes from Build readiness to Mission readiness; old session fails |
| Revoke | Open tab cannot refresh data; reload cannot fetch protected HTML |

## Do not confuse the test doubles with live evidence

The BigQuery results and metadata/security observations are synthetic. Package
inventory, scanner flags and deployment admission reports are **test doubles**, not
certifications. A fake registry-shaped digest string names a real *local* image ID;
no container registry push occurs. No model is contacted: the maintainer reply is
a fixed, labeled fixture. No GCP, corporate SSO, PostgreSQL RLS or production
network/egress controls are tested here. Do not reuse these reports in production.

The report distinguishes real actions from these doubles. GitHub retains
`synthetic-container-story` for seven days: step report, before/after/revoked
screenshots and build/service logs. No browser traces, cookie dumps, private keys
or authentication response bodies are saved. Temporary sessions/keys are discarded
when the run ends. The script cleans up only its own containers/processes.

## Private edge handoff contract

`POST /api/v2/apps/{app_id}/launch` requires a current browser login, CSRF and app
use permission, current release policy, an admitted production deployment and a
configured independent edge. It returns a 60-second code and exact form destination.
The gallery POSTs the code; neither bearer credentials nor the code enter a URL.

`POST /api/v2/edge/exchange` requires `DC_WORKER_EDGE_KEY`, separate from app and
model credentials. A code is one-use, bound to browser login, app, release,
permission revision and exact origin. Exchange repeats current authorization.
Logout, expiry, suspension, revocation and replacement invalidate access.

`integrations/private-edge/server.mjs` is a dependency-free reference implementation.
It uses TLS, host-only Secure/HttpOnly cookies, exact-origin CSRF checks, a request
header allowlist, gateway revalidation before every app request, and response
header restrictions. The upstream cannot set cookies or loosen the edge's CSP.

Operator configuration: `DC_CONTROL_ORIGIN`, `DC_GALLERY_ORIGIN`,
`DC_WORKER_EDGE_KEY`, `DC_EDGE_TLS_KEY`, `DC_EDGE_TLS_CERT`, `DC_EDGE_ROUTES`,
`DC_EDGE_PORT`, and `DC_EDGE_BIND`. Routes are an operator-owned JSON object:

```json
{
  "APP_ID.apps.company.example": {
    "appId": "APP_ID",
    "submissionId": "APPROVED_SUBMISSION_ID",
    "origin": "https://APP_ID.apps.company.example",
    "upstream": "http://private-app-container:8080"
  }
}
```

Work integration must provision real per-app origins, trusted certificates,
private upstream ingress, workload identity/mTLS, restricted egress, edge rate
limits and operator-only atomic routing updates. The in-memory session map is
single-process: use an approved encrypted/scoped session store for multiple replicas;
do not share a bearer token across users or persist it in browser storage. Restart
currently requires users to relaunch. Prefer per-app-scoped edge credentials over
the reference's single privileged key. Preview remains separately scoped and is
not launchable via a production ticket.

`DC_APP_RUNTIME_PORT` optionally admits an exact nondefault HTTPS port; absent
means 443. The same origin must be used by deployer, launch issuer and edge.

Follow the [Playwright CI guide](https://playwright.dev/python/docs/ci) for browser
setup. Docker documents the lack of network isolation with
[host networking](https://docs.docker.com/engine/network/drivers/host/).
