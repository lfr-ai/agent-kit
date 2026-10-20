# Python packaging pre-publish checklist

Purpose: a short, ordered checklist for validating a package artifact before
publishing or deploying. Detail lives in the [packaging guide](references/guide.md).

## Metadata

- [ ] `[build-system]` declares a pinned backend; `[project]` has `name`, a
      version source, `requires-python`, and an SPDX `license` expression.
- [ ] Runtime dependencies contain no test, lint, or build tools and no local
      direct references; see [project metadata](references/pyproject-metadata.md).
- [ ] `python assets/check_pyproject.py pyproject.toml` reports no findings.

## Artifacts

- [ ] Built into a clean output directory with the locked backend.
- [ ] Wheel and sdist listings include package data (templates, schemas,
      `py.typed`) and license files, and exclude tests, caches, and secrets.
- [ ] Checksums recorded.

## Installed behavior

- [ ] Wheel installed into an isolated environment outside the checkout.
- [ ] Public import and every console entry point run from that environment.
- [ ] Missing configuration and invalid arguments fail with clear messages.

## Frozen executables (when produced)

- [ ] Built from a committed spec on each target platform; see
      [PyInstaller](references/pyinstaller.md).
- [ ] Smoke test loads data files and every dynamically imported module.
- [ ] Signing and publication handed to the operator release job.

## Negative cases

- Broken package discovery or misconfigured namespace packages causing import
  errors only after installation.
- Entry point absent from the installed environment's scripts directory.

## Scope and limits

This checklist verifies metadata and artifact contents; it does not run full
integration tests or platform compatibility suites.

## Sources

- <https://peps.python.org/pep-0621/>
- <https://packaging.python.org/>
