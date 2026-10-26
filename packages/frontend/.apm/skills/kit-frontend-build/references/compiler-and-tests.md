# Compiler options and test runner

Reviewed 2026-10-23 against the TypeScript tsconfig reference and Vitest 5
documentation. The single-file strict configuration in `kit-react-feature`
suits small apps; the solution-style templates here separate browser code
from tooling files that run in Node.

## Strict compiler options

| Option | Value | What it catches |
| --- | --- | --- |
| `strict` | `true` | Implicit `any`, unchecked `null`, unsafe `this`, and related families |
| `noUncheckedIndexedAccess` | `true` | `items[0]` and record lookups typed as possibly `undefined` |
| `exactOptionalPropertyTypes` | `true` | Assigning `undefined` to an optional property that should be absent |
| `verbatimModuleSyntax` | `true` | Type-only imports must say `import type`; no elided side effects |
| `moduleResolution` | `"bundler"` with `module: "ESNext"` | Resolution that matches Vite, including `exports` maps |
| `isolatedModules` | `true` | Constructs a per-file transpiler such as Oxc or esbuild cannot compile |
| `noImplicitOverride` | `true` | Accidental overrides in classes |
| `noFallthroughCasesInSwitch` | `true` | Missing `break` |
| `noPropertyAccessFromIndexSignature` | `true` | Dot access hiding dynamic keys |
| `noEmit` | `true` | Type checking only; Vite transpiles |
| `skipLibCheck` | `true` | Faster checks; does not weaken checks on your code |

Do not relax an option to clear errors. Fix the types, or add a narrowly scoped
`@ts-expect-error` with a reason when a third-party type is wrong, and record
the upstream issue.

## Project layout

- `tsconfig.json`: solution file with `files: []` and `references` only.
- `tsconfig.app.json`: browser source (`src`), DOM libs, aliases, Vite types.
- `tsconfig.node.json`: `vite.config.ts`, `vitest.config.ts`, and other
  Node-side tooling with Node types and no DOM.
- Run `tsc -b` (build mode) in CI so every referenced project is checked.

## Path aliases

| Approach | Use when | Notes |
| --- | --- | --- |
| `paths` `@/*` plus Vite `resolve.alias` | Common app setup | Keep both in sync; one alias root |
| `package.json` `imports` (`#app/*`) | Prefer platform-defined resolution | Works across Node, Vite, and TypeScript without duplication |
| Relative imports | Small projects | No configuration; long `../../` chains signal a layout issue |

Pick one approach per repository. Aliases are for source roots, not for
reaching into another feature's internals (see `kit-react-feature`).

## Vitest configuration

| Decision | Choose | Reason |
| --- | --- | --- |
| Config | `vitest.config.ts` merging `vite.config.ts` | Same aliases and plugins as the app |
| Environments | `projects`: `unit` in `node`, `dom` in `jsdom` or `happy-dom` | Pure logic runs faster and cannot touch the DOM by accident |
| DOM implementation | `jsdom` for fidelity; `happy-dom` for speed when its gaps do not matter | Verify focus, layout-free APIs, and `form` behavior you rely on |
| Real browser | Vitest browser mode or Playwright for layout, focus, and CSS | DOM emulators do not render |
| Coverage | `provider: "v8"`, explicit `include`, thresholds | V8 coverage is native and accurate with source maps |
| Globals | `globals: false` | Explicit imports keep types honest |
| Isolation | `restoreMocks`, `unstubGlobals`, `unstubEnvs` | No leakage between tests |
| Retries | None for unit tests | Retries hide nondeterminism |

Test design, providers, MSW, and determinism belong to `kit-frontend-testing`.

## Failure modes

| Symptom | Cause | Repair |
| --- | --- | --- |
| Type errors only in CI | Editor uses a different tsconfig | `tsc -b` with references locally and in CI |
| Alias resolves in tests, not build | Alias declared only in Vitest | Declare once in Vite config; merge into Vitest |
| `document is not defined` | DOM test in the node project | Move file or adjust project globs |
| Coverage silently low | `include` missing; untested files omitted | Set `coverage.include` to source globs |
| Runtime import of a type | Missing `import type` | `verbatimModuleSyntax` reports it |

## Primary sources

- TSConfig reference: <https://www.typescriptlang.org/tsconfig/>
- TypeScript project references: <https://www.typescriptlang.org/docs/handbook/project-references.html>
- TypeScript module resolution (`bundler`): <https://www.typescriptlang.org/docs/handbook/modules/reference.html>
- Node.js subpath imports: <https://nodejs.org/api/packages.html#subpath-imports>
- Vitest configuration: <https://vitest.dev/config/>
- Vitest projects: <https://vitest.dev/guide/projects>
- Vitest coverage: <https://vitest.dev/guide/coverage>
- Vitest test environments: <https://vitest.dev/guide/environment>
