# Your Dreamcatcher dashboard

This is a runnable Node 22 HTTP/SPA template, not a live company connection.

1. Install the downloaded package: `npm install --save-exact /path/to/dreamcatcher-sdk.tgz`. Keep the generated package-lock.json. The SDK is not assumed to be published to npm.
2. Register a hosted app in Dreamcatcher. Replace the query reference in dreamcatcher.json with your independently approved query version.
3. For local development only, set DC_APP_ID, DC_GATEWAY_ORIGIN and your own one-hour app-scoped DC_TOKEN in your terminal. Run `npm run dev`.
4. `dc validate .`, then `dc pack . ../dashboard-source.zip`, then upload via the app control panel. The template needs a currently approved active release to retrieve governed data; without one it intentionally shows an authorization error.
5. Production: the trusted builder supplies APPROVED_NODE_IMAGE as an approved digest, installs your lockfile from an approved registry, scans the finished image, and verifies dist/index.html and dc-http/v1. The runtime listens on PORT with /healthz and /readyz and SPA fallback. Configure private ingress and the authenticated per-user edge; never set a shared DC_TOKEN.

WORK-CONNECT: private-edge injects `x-dreamcatcher-runtime-token` after stripping inbound copies. The server revalidates the opaque token at the gateway on every request. Only an authenticated edge may reach the container; the browser must not receive this token. All egress must be restricted to the gateway and explicitly approved destinations, including browser CSP. Raw BigQuery credentials and database URLs are not application settings.

Replace the simple dist/ dashboard with your frontend build. For the UI-edit agent, put editable React components under src/ and have your isolated build compile src/ into dist/. This zero-build starter has no src/ components: the agent must not be granted server or deployment editing just to change its static HTML.
