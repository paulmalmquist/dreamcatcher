# Flight Deck — complete synthetic upload

A small purple-accented React dashboard for manufacturing readiness. It has an
editable JSX heading, program selector, summary cards, assembly table, loading,
empty and denied-access states. The server uses Dreamcatcher's SDK; no browser
credentials or direct BigQuery client are included.

From the repository root:

```sh
npm ci --ignore-scripts
npm run build
python scripts/pack-flight-deck.py --output flight-deck-source.zip
```

Upload that ZIP in a hosted app's Release tab. It is assembled with this checkout's
exact lockfile, SDK runtime and SDK server template. `node build.mjs` creates
`dist/index.html`, `app.js`, and `style.css`; a missing index prevents startup.
Unlike `examples/apps/*` (small contract fixtures), this bundle is buildable.

For a complete disposable-container/browser test, see `docs/CONTAINER-STORY.md`.
The ordinary app registry does not run a test worker automatically. Queued means
queued. Do not approve fabricated evidence to use this in a real environment.
