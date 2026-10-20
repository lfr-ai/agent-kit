---
description: Apply to typed frontend implementation and UI tests.
applyTo: "**/*.ts,**/*.tsx,**/*.js,**/*.jsx,**/*.css"
---

- Use the declared package manager, lockfile, compiler, formatter, and test runner.
- Organize code by feature; reuse shared primitives from the existing component library and do not import another feature's internals.
- Validate server data at the HTTP boundary; keep provider details outside domain code.
- Keep one API client module that owns base URL, credentials mode, timeouts, and error mapping.
- Separate remote state from transient UI state; avoid redundant effect-driven state.
- Prefer semantic HTML, labels, keyboard support, visible focus, and explicit errors.
- Keep accessible components local to their feature and reuse existing primitives.
- Cover loading, empty, error, success, and cancellation states.
- Never render untrusted HTML without sanitization; avoid `innerHTML` and equivalent escape hatches.
- Prefer secure cookie flows over tokens in web storage; never log credentials or personal data to the console.
- Lazy-load routes and heavy components, and keep server-only code out of the browser bundle.
- Use user-visible test assertions and resilient browser locators.
- Use the `kit-react-feature` skill for feature implementation.
