---
description: Enforce identity verification and resource authorization at trusted boundaries.
applyTo: "**/auth/**/*.py,**/identity/**/*.py,**/auth/**/*.ts,**/auth/**/*.tsx"
---

- Use provider-maintained or reviewed OIDC/OAuth libraries; code flow with PKCE
  S256, session-bound state and nonce, exact redirects and single-use callbacks.
- APIs accept access tokens for their issuer/audience, not ID tokens. Verify
  signature, algorithm, tenant, time and claims before any permission decision.
- Enforce required scopes/roles and resource ownership in the backend; route
  guards and role-aware UI are not authorization.
- Separate 401, 403 and verifier outages; never refresh/retry on 403 or fail open.
- Keep credentials, token bodies and personal claims out of logs and telemetry.
- Choose supported MSAL caches by threat model; do not extract tokens into a
  parallel hand-written cache or claim browser storage survives XSS.
