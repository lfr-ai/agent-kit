---
description: Apply to frontend package scripts, build settings, and test-runner configuration.
applyTo: "package.json,**/vite.config.*,**/vitest.config.*,**/playwright.config.*,**/tsconfig*.json"
---

- Use the repository's declared package manager and committed lockfile; install in frozen or CI mode in automation.
- Keep test, lint, typecheck, and build commands distinct and report which ones ran.
- Pin or constrain tooling according to existing workspace policy; do not add dormant stacks or a second tool for the same job.
- Keep strict TypeScript compiler options on; do not relax them to silence errors.
- Expose only intentionally public variables to the client through the bundler's public prefix; keep secrets out of build-time variables and inspect browser artifacts for unintended values.
- Keep dev-server proxies and mocks out of production builds.
- Configure test runners for deterministic runs: fixed timezone and locale, isolated environments, and no unit-test retries that hide failures.
- Keep browser tests isolated from live accounts and production services; start the application under test from configuration.
- Keep traces, screenshots, and reports as failure artifacts outside source control.
- Check bundle size and code splitting when adding dependencies; prefer platform APIs over polyfills for supported browsers.
- Change only the owning package's scripts and configuration.
- Use the `kit-runtime-config` skill for environment-specific client configuration.
