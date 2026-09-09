# Our Dreamcatcher SDK 2

This is our SDK, not the Databricks SDK. Install the downloaded package:

```sh
npm install ./dreamcatcher-sdk.tgz
npx dc init my-dashboard
```

It includes ESM/TypeScript, the dc CLI, a versioned JSON schema and a runnable Node
container/dashboard template. It is not assumed to exist in a public npm registry.
Install the tarball into the generated dashboard too, producing package-lock.json.

## Request-scoped server client

```ts
import { forRequest } from '@dreamcatcher/sdk';
const dc = forRequest({
  baseUrl: process.env.DC_GATEWAY_ORIGIN!,
  appId: process.env.DC_APP_ID!,
  token: verifiedAppScopedToken, // From the authenticated private edge, not an email header.
});
const context = await dc.context();
const result = await dc.queries.run('bq-build-readiness@1.0.0', {program_id: 'program-a'});
const current = await dc.state.get('preferences', 'dashboard');
await dc.state.put('preferences', 'dashboard', {program: 'program-a'}, {
  expectedVersion: current.version, idempotencyKey: crypto.randomUUID(),
});
await dc.events.emit('app.open');
```

Create a client per authenticated request, never a shared user singleton.
createDreamcatcher({baseUrl,appId,getToken}) also accepts a request-scoped token callback.
Legacy identity(), queries.run(), skills.run() remain compatible with URL-first apps.
context(), state and events require an active hosted release. No raw SQL, principal
selection, bucket-name or database-connection API is exposed.

The gateway rechecks caller groups, app permissions, release, packages and data policy
on every call. Hosted runtime tokens bind an app AND release. Tokens cannot administer
the registry. Keep them only on the server, never HTML, source, URLs or localStorage.
The private edge/session bridge still needs real work integration; a manual one-hour
SDK token is a local development tool, not production SSO.

HTTPS is required outside loopback; redirects are rejected and timeout defaults to
35 seconds. Use same-origin browser-to-app requests. DreamcatcherError exposes status
and detail: 401/403 access, 409 policy or state conflict, 429 request budget, 503 missing
connection. Do not blindly retry writes with new idempotency keys. No result cache
is supplied; a future cache must include user/entitlements, app release, query version,
parameters and policy revision.

## CLI

```sh
npx dc schema
npx dc validate ./my-dashboard
npx dc pack ./my-dashboard ./dashboard-source.zip
# Set DC_GATEWAY_ORIGIN, DC_APP_ID and DC_DEVELOPER_TOKEN in your terminal.
npx dc submit ./my-dashboard
npx dc status APP_ID
```

Create a developer token in the app Release panel. It lasts one hour and can only
inspect/upload that app and request proposed edits. It cannot approve, deploy, change
sharing, read data or administer workers. The SDK-token revoke control revokes both
token types. init refuses existing directories; pack refuses overwrites. validate
is static validation, NOT a trusted scan, build, governance approval or deployment.

## Python

Install the full repo's sdk-python directory: `python -m pip install ./sdk-python`.

```python
from dreamcatcher_sdk import Dreamcatcher
dc = Dreamcatcher(base_url=gateway_origin, app_id=app_id, token=verified_app_token)
rows = dc.query('bq-build-readiness@1.0.0', {'program_id': 'program-a'})['rows']
current = dc.state_get('preferences', 'dashboard')
dc.state_put('preferences', 'dashboard', {'program': 'program-a'},
             expected_version=current['version'], idempotency_key=request_id)
```

Python uses the standard library, rejects redirects and follows the same request-scope
rules. The registry does not execute uploaded Python code.

## Work integration

Read CLAUDE.md, integrations/CONNECTIONS.json and docs/V2-PLATFORM.md in the full repo.
Retain synthetic BigQuery fixtures while connecting company identity, catalog,
warehouse, isolated build, private hosting, model and PostgreSQL at work only.
