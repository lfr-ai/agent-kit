---
name: kit-runtime-config
description: Use when adding frontend runtime settings while separating public values from server secrets.
license: MIT
---

# Expose only safe client configuration

## Resources

- [Public configuration guide](references/guide.md): compatibility and rollback
  gates.
- [Runtime configuration patterns](references/config-patterns.md): build-time
  versus runtime, schema rules, boot sequence, serving, testing, anti-patterns.
- [Public value boundaries](references/public-value-boundaries.md): what may be
  public, review checklist, leak response.
- [Configuration contract](assets/public-config-contract.md) to fill per change.
- Templates: [runtime config module](assets/runtime-config.ts.template) with
  [tests](assets/runtime-config.test.ts.template),
  [example config file](assets/config.json.template),
  [typed build variables](assets/vite-env.d.ts.template),
  [boot sequence](assets/main.tsx.template).
- Checker: [public bundle scanner](assets/scan_public_bundle.py)
  (`ROOT`, `--deny`, `--allow`, `--forbid-source-maps`, `--self-test`).

## Procedure

1. Read the guide; fill the configuration contract.
2. Identify build-time versus runtime delivery and the toolchain's public-value
   rules (for Vite, only `VITE_`-prefixed variables reach client code).
3. Classify every value with the boundaries table; treat browser values as public.
4. Keep credentials, signing material, private endpoints, and authorization
   server-side.
5. Define a strict schema: required keys, safe optional defaults, URL constraints.
6. Load and validate before creating clients; fail visibly on missing or invalid
   values instead of calling an accidental host.
7. Keep one artifact for all environments; no baked-in environment URLs.
8. Test absent, malformed, insecure, stale-version, and valid configuration with
   synthetic values.
9. Verify the startup failure screen is accessible and offers recovery.
10. Scan built assets and source maps with the bundle scanner; record scope and
    limits rather than claiming proof of secret absence.
11. Apply compatibility and rollback gates; never deploy or rotate credentials
    implicitly as part of this procedure.

## Acceptance gates

- [ ] Every key is classified; no private value is delivered to the browser.
- [ ] One schema validates the file in the pipeline and at startup.
- [ ] Invalid configuration produces a visible, accessible startup error.
- [ ] Clients read configuration only after it loaded.
- [ ] The bundle scan ran on build output with its scope reported.
