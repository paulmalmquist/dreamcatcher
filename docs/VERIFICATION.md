# Verification record

Authoring environment: Linux, Python 3.12; Node/npm workspace build.

- 26 backend tests pass after building: frontend/SDK distribution smoke test, login and persistence, CSRF, query and skill execution, app/data access separation, SDK scope and app binding, asset revocation, private drafts, immutable versions, typed parameter binding/injection, skill round-trip import with pending approval, unsafe ZIP paths/secrets, malformed evidence, complete nested dependency inventory, full signed release approval/publication/sharing/unpublication, unsafe SQL, account disable/session revocation and evidence tampering. The distribution smoke test skips if the frontend/SDK have not been built.
- 4 SDK tests pass: request contract and token binding, authorization errors, insecure remote origin rejection, URL credential rejection.
- Frontend TypeScript check and Vite production build pass; SDK declarations and distributable tarball build successfully.
- No live corporate IdP or BigQuery calls, container run, Windows execution, automated browser interaction, penetration test or external-host build verification was performed.
- Python test tooling emits two upstream deprecation warnings. They do not fail the tests. The Three.js chunk is relatively large and is lazy-loaded independently of the UI.

Re-run the commands in README on your machine and in CI; this record is not a substitute for production acceptance tests.
