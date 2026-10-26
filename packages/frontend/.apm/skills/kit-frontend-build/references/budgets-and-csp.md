# Bundle budgets, source maps, CSP, and dependencies

Reviewed 2026-10-23. Numbers below are starting points; replace them with
measurements from the project's own users and devices.

## Size budgets

| Budget | Starting limit (compressed) | Measured on |
| --- | --- | --- |
| Entry JavaScript (critical path) | 150 KB gzip | `dist/assets/index-*.js` plus statically imported chunks |
| Largest route chunk | 100 KB gzip | Each lazily loaded route |
| Total CSS | 50 KB gzip | All emitted `.css` |
| Single dependency added | 20 KB gzip | Before-and-after build diff |
| Requests on first navigation | Recorded, no silent growth | Browser network panel or Lighthouse run |

- Measure compressed sizes (gzip or Brotli as served), not raw bytes.
- Enforce budgets in CI with the project's size tool; fail on regressions
  rather than raising `build.chunkSizeWarningLimit`.
- Record each measurement and change in the bundle budget worksheet; raising
  a budget needs a named reason and owner.
- Inspect composition with a bundle visualizer before removing or splitting.

## Source map policy

| Policy | Configuration | Fits when |
| --- | --- | --- |
| Hidden maps uploaded to error tracking | `build.sourcemap: "hidden"`; upload step deletes maps from `dist` | Production stack traces are needed |
| No production maps | `build.sourcemap: false` | No error tracking; smallest exposure |
| Public maps | `build.sourcemap: true` | Open-source app or deliberate decision |

Source maps reveal original source, comments, and file layout. Hidden maps
remove the `sourceMappingURL` comment but the files still exist; delete or
block them before deployment and verify with the bundle scan from
`kit-runtime-config` (`--forbid-source-maps`).

## Content Security Policy compatibility

| Directive | Build requirement |
| --- | --- |
| `script-src 'self'` (no `'unsafe-inline'`, no `'unsafe-eval'`) | No inline scripts in `index.html`; no `eval`, `new Function`, or string timers in dependencies |
| `style-src` | Avoid runtime style injection, or provide a nonce through the framework |
| `connect-src` | Lists exactly the API, telemetry, and identity provider origins from runtime config |
| `img-src`, `font-src` | Self-hosted assets or listed CDNs; `data:` only when needed |
| `frame-ancestors` | Set by the server; protects against clickjacking |
| `require-trusted-types-for 'script'` | Optional hardening; check dependencies first |

- Vite's dev server injects inline scripts; test the CSP against a production
  build served like production, not the dev server.
- The theme-before-paint script from `kit-design-system` needs a nonce or a
  hash when inline scripts are disallowed.
- Report violations to a collection endpoint before enforcing a new policy.

## Dependency hygiene

- Prefer platform APIs and existing dependencies over new packages.
- Before adding a package, record size impact, maintenance signals (recent
  releases, open security advisories, maintainer count), license, and whether
  it ships ESM with types.
- Keep one version of each framework package; check duplicates after install.
- Separate `dependencies` (shipped) from `devDependencies` (tooling).
- Remove unused packages in the same change that removes their last import.
- Update through the lockfile with reviewed pull requests; audit in CI.

## Failure modes

| Symptom | Cause | Repair |
| --- | --- | --- |
| Budget raised every sprint | Warning limit increased instead of fixing | Enforce failing budgets; inspect composition |
| Production stack traces unreadable | Maps disabled without upload alternative | Hidden maps with upload, then delete |
| Source exposed publicly | `sourcemap: true` by default | Record policy; scan for `.map` files |
| Blank page under CSP | Inline bootstrap script or `eval` in a dependency | Move to module script; replace dependency |
| Two copies of a framework | Mismatched peer ranges | Deduplicate; align versions |

## Primary sources

- Vite build options (`sourcemap`, `chunkSizeWarningLimit`): <https://vite.dev/config/build-options>
- MDN Content Security Policy: <https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP>
- CSP Level 3: <https://www.w3.org/TR/CSP3/>
- Trusted Types: <https://w3c.github.io/trusted-types/dist/spec/>
- web.dev performance budgets: <https://web.dev/articles/performance-budgets-101>
- OWASP CSP cheat sheet: <https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html>
