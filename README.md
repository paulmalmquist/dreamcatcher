# Dreamcatcher

Public source repository: https://github.com/paulmalmquist/dreamcatcher

```sh
git clone https://github.com/paulmalmquist/dreamcatcher.git
cd dreamcatcher
```

A URL-first internal app gallery with an original animated Three.js space design, persistent sharing, governed queries, exact-package policies, portable skills, and a TypeScript SDK.

This is a functional single-node beta foundation, not a claim of production certification. The bundled apps and warehouse contain synthetic demonstration data. No company systems, secrets, or attached personal documents are included.

## Run on your computer

Requires Python 3.12 and Node.js 22.14+ with npm. Run these commands inside the extracted `dreamcatcher` directory.

macOS / Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/setup.py
npm ci --ignore-scripts
npm run build
python scripts/run.py
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\setup.py
npm ci --ignore-scripts
npm run build
.\.venv\Scripts\python.exe scripts\run.py
```

Open **http://localhost:8000**. Use `builder@demo.local` and password `Dreamcatcher-local-1!`. Other local accounts are `reviewer`, `admin`, `viewer`, and `outsider` at `demo.local`, with the same password. These are deliberately local-demo accounts, not production credentials.

`setup.py` creates `.env` with fresh local secrets only if it does not already exist. The first server start creates `data/registry.sqlite` and a separate synthetic `data/warehouse.sqlite`. Keep this directory to retain changes. Do not expose demo mode to a network. Changing `DC_DEMO_PASSWORD` after initial seeding does not reset existing accounts.

Optional Docker path: after `python scripts/setup.py`, run `docker compose up --build`. This recipe is supplied but was not executed in the authoring environment. It binds only localhost and persists a named volume.

## Try the full flow

1. Sign in as builder. Open Build Readiness and run its query with `{"program_id":"terran-r"}`. Run the skill under the Skills tab.
2. Bookmark an app, reload, and confirm it remains saved.
3. Register your own HTTPS app link. It becomes a persistent private draft.
4. Open its Release tab: create an immutable release manifest, attach trusted build evidence, have a different reviewer approve it, then publish as owner. See [release guide](docs/RELEASES.md).
5. Set sharing to a team or Workspace. Sign in as viewer to test access. The outsider can see workspace-shared apps but cannot run their governed data queries.
6. Export the sample skill ZIP. A destination needs the referenced query version and its own local approval. Importing the same id/version twice is rejected; a changed package requires a new version.
7. Download the SDK from the homepage, create a one-hour app-bound token in app details, and follow [SDK instructions](sdk/README.md).
8. Sign in as admin for people/groups and package policy. Sign in as reviewer to approve/revoke assets and inspect audit events. Revocation blocks subsequent executions even for already-published apps.

## What is implemented

| Capability | Implementation |
| --- | --- |
| Design | Responsive React gallery, original thumbnails, Three.js nebula/stars, reduced-motion default and pause |
| Identity | Scrypt local passwords; configurable OIDC Authorization Code + PKCE; explicit membership provisioning |
| App sharing | Private drafts; owner-controlled user/group/workspace run/edit grants; favorites; publish/unpublish |
| Query governance | Immutable versions, SQL parsing, source/grain contracts, typed bound parameters, independent review and revocation |
| Query execution | Read-only local SQLite adapter; optional BigQuery per-caller mapped service-account impersonation |
| Packages | Complete npm lock inventory including nested dependencies; exact name/version/integrity/source policies; install scripts denied |
| Release gate | Manifest and lock digests, HMAC-signed build evidence, independent approval, current-policy rechecks |
| Skills | Validated ZIP import/export, destination reapproval, deterministic query workflow execution; no arbitrary code execution |
| SDK | Built ESM package with TypeScript declarations, identity/query/skill methods, short-lived app-scoped tokens |
| Operations | Audit records, session revocation, tests, lockfiles, local setup, CI workflow, container recipe |

## Repository map

```text
frontend/src/          React UI, space shader, API client and management panels
frontend/components/   Local UI primitives
backend/dreamcatcher/  FastAPI, auth, schema, policies, adapters and demo seed
sdk/                  Portable TypeScript client and tests
tests/                API and security boundary tests
scripts/              Setup, server, operator provisioning, evidence signer, packaging
docs/                 Architecture, release workflow and production checklist
artifacts/            SDK tarball generated by npm run build
```

API schema: `GET /api/openapi.json`. UI and API use the same origin. For frontend development, run the API and `npm run dev`; Vite proxies `/api` and `/auth`. Set `DC_ORIGIN=http://localhost:5173` for browser mutation origin checks in that development mode.

## Verify

```sh
python -m pytest -q
npm run typecheck
npm run build
npm run test:sdk
```

## Push to your GitHub workspace

For the one-way transfer into Paul OS at work, start with [the work-computer handoff](docs/WORK-COMPUTER-HANDOFF.md) and paste [WORK-AGENT-PROMPT.md](WORK-AGENT-PROMPT.md) into your local coding agent. `python scripts/doctor.py` provides a read-only installation preflight; `--json` produces structured results without printing secret values.

Create an **empty** repository under your own account or organization, then:

```sh
git init
git add .
git commit -m "Initial Dreamcatcher beta"
git branch -M main
git remote add origin https://github.com/YOUR_WORKSPACE/dreamcatcher.git
git push -u origin main
```

For a separate private work repository, use your organization's approved creation and transfer process. Review staged files first; `.env`, databases, tokens, dependencies and build output must stay excluded. Never push company modifications or data back to this public prototype.

Before corporate rollout, read [architecture](docs/ARCHITECTURE.md), [security and deployment checklist](docs/SECURITY.md), and [release workflow](docs/RELEASES.md). Appsmith informed the capability inventory, not this UI or a forked Appsmith codebase.
