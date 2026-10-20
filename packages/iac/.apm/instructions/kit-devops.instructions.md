---
description: Apply to deployment scripts, environment definitions, and reverse-proxy configuration.
applyTo: "**/Caddyfile,**/*.caddy,**/nginx*.conf,**/nginx/**,**/*.azcli,**/deploy/**,**/deployment/**,**/environments/**"
---

- Deploy the same immutable, versioned artifact to every environment; vary behavior only through configuration.
- Parameterize deploy scripts per environment and refuse to run when the target environment or a required parameter is missing.
- Make deploys idempotent; inspect current state before changing it and support a preview or dry run.
- Keep secrets in a secret store or the platform's secret mechanism, never in scripts, parameter files, or command lines.
- Run deploy automation with managed or workload identities and least privilege, never personal credentials.
- Pin the CLI, image, and tool versions that deploy scripts use.
- Define health checks and a rollback path (previous artifact or traffic switch) before rollout; prefer staged or blue-green rollouts.
- Terminate TLS with current protocol versions, redirect HTTP to HTTPS, and set security headers such as HSTS at the proxy.
- Set proxy timeouts, request-body limits, and rate limits explicitly; disable response buffering only for streaming routes.
- Trust forwarded client-address headers only from known proxies, and never expose admin or metrics endpoints publicly.
- Keep environment configuration in version control and document every environment-specific value.
- Do not run deploy, rollout, or production commands from an authoring session.
- Use the `kit-infra-review` skill for deployment review.
