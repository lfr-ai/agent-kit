---
name: kit-frontend-build
description: Use when configuring Vite, Bun, tsconfig, Vitest, client environment variables, bundle budgets or source maps.
license: MIT
---

# Configure a predictable frontend build

## Resources

- [Build guide](references/guide.md): Vite configuration, environment
  variables, targets, code splitting, preview, Bun, failure modes.
- [Compiler and test runner](references/compiler-and-tests.md): strict
  `tsconfig` options, aliases, project references, Vitest environments and
  coverage.
- [Budgets, source maps, and CSP](references/budgets-and-csp.md): size
  budgets, source map policy, Content Security Policy compatibility, and
  dependency hygiene.
- [Bundle budget worksheet](assets/bundle-budget.md.template) to fill per
  release or dependency change.
- Templates: [Vite config](assets/vite.config.ts.template) with its
  [contract test](assets/vite.config.test.ts.template),
  [solution tsconfig](assets/tsconfig.solution.json.template) (copy to
  `tsconfig.json`) with [app](assets/tsconfig.app.json.template) and
  [tooling](assets/tsconfig.node.json.template) projects,
  [Vitest projects](assets/vitest.config.ts.template),
  [environment example](assets/env.example.template) (copy to `.env.example`).
- Checker: [public variable names](assets/check_frontend_env.py)
  (`PATHS`, `--allow`, `--prefix`).
- Related owners: runtime configuration and the built-bundle secret scan in
  `kit-runtime-config`; feature folders in `kit-react-feature`; test design in
  `kit-frontend-testing`; tooling policy bullets in the frontend tooling
  instructions.

## Procedure

1. Read the guide; record the installed Vite, TypeScript, Vitest, and package
   manager versions and the browser support target.
2. Use the package manager the lockfile declares. Choose Bun only with a
   committed `bun.lock`, CI installs with `--frozen-lockfile`, and a documented
   runtime decision; never mix lockfiles.
3. Keep one Vite config for build and dev; set `build.target` from the support
   matrix, keep dev proxies out of production, and verify with `vite preview`.
4. Expose only intentionally public values through the `VITE_` prefix; treat
   every exposed value as published. Run the public variable checker on `.env*`
   files and source, then the bundle scan from `kit-runtime-config`.
5. Turn on strict compiler options (`strict`, `noUncheckedIndexedAccess`,
   `exactOptionalPropertyTypes`, `verbatimModuleSyntax`, `moduleResolution`
   `bundler`); fix code instead of relaxing options.
6. Define path aliases once in `tsconfig` and mirror them in Vite; prefer
   `#`-subpath imports or `@/` consistently, never both.
7. Split Vitest into node and DOM projects; choose jsdom or happy-dom
   deliberately; collect V8 coverage with thresholds.
8. Rely on route-level dynamic imports first; add manual chunk groups only for
   measured cache wins, and recheck the waterfall after each change.
9. Set size budgets per entry and route chunk; fail CI on regression and record
   the measurement in the worksheet.
10. Choose a source map policy (hidden maps uploaded to error tracking, or none
    published) and keep maps off public hosting unless that is intended.
11. Keep the output compatible with a strict Content Security Policy: no inline
    scripts or `eval`, explicit `connect-src` origins.
12. Audit added dependencies for size, maintenance, license, and duplicates;
    report exact commands, results, and checks that did not run.

## Acceptance gates

- [ ] Frozen install, typecheck, lint, tests, and production build pass in CI.
- [ ] No secret-like `VITE_` names; built output passed the bundle scan.
- [ ] Strict compiler options are on with no suppressions added.
- [ ] Budgets are enforced and the worksheet records current sizes.
- [ ] Source maps follow the recorded policy; none are served unintentionally.
- [ ] The production build runs under the intended CSP without violations.
