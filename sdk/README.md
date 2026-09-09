# Dreamcatcher SDK

Install the downloaded local package: `npm install ./dreamcatcher-sdk-1.0.0.tgz`.

```ts
import { createDreamcatcher } from '@dreamcatcher/sdk';
const dc = createDreamcatcher({
  baseUrl: 'http://localhost:8000',
  appId: 'build-readiness',
  getToken: () => process.env.DREAMCATCHER_TOKEN!,
});
const result = await dc.queries.run('assembly-readiness@1.0.0', {program_id:'terran-r'});
const skill = await dc.skills.run('review-build-readiness@1.0.0', {program_id:'terran-r'});
```

Generate a one-hour app-bound token from the app detail UI. Use it in the app's backend, not embedded in source or a static page. Tokens cannot administer the registry. Query and skill access are rechecked against the current caller groups, app permissions, release, and dependency approvals on every call. Use a same-origin backend-for-frontend or an independently reviewed authentication flow for remote browser apps; the API deliberately does not allow wildcard credentialed CORS. Tokens are never forwarded through redirects. Production URLs must use HTTPS.
