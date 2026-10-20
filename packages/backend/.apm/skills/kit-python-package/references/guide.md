# Python packaging guide

## Purpose

Validate a Python package's metadata, artifacts, and installed behavior before
publishing or deploying, and freeze applications into executables when users
cannot install Python.

## Map of this skill

| Topic | Reference or asset |
| --- | --- |
| `pyproject.toml` tables and fields | [project metadata](pyproject-metadata.md) |
| Backends, versions, wheels, sdists, entry points | [build and artifacts](build-and-artifacts.md) |
| Frozen executables | [PyInstaller](pyinstaller.md) |
| Starting metadata | [pyproject template](../assets/pyproject.toml.template) |
| Runtime resource access | [resource helper](../assets/resources.py.template) |
| PyInstaller build definition | [spec template](../assets/app.spec.template) |
| CI build and smoke | [workflow template](../assets/ci-build.yml.template) |
| Structural metadata scan | [checker](../assets/check_pyproject.py) |
| Evidence record | [package review](../assets/package-review.md.template) |

## Acceptance gates

- The declared build backend produces valid metadata, including supported
  dynamic version or license configuration; do not require every value to be a
  literal key.
- Package data that runtime code needs is included in the built artifact.
- Console entry points are declared and usable after installation.
- The installed artifact works away from the source checkout.

## Failure modes

- Missing package data (templates, schemas, `py.typed`) causing runtime failures
  only after installation.
- Incorrect metadata or an unsupported `requires-python` that prevents
  installation on target platforms.
- Implicit imports that rely on repository layout rather than installed package
  layout.
- Development tools shipped as runtime dependencies, inflating every install.
- Local path dependencies that build locally but cannot be published.
- Frozen executables missing dynamically imported modules or distribution
  metadata, failing only on code paths the smoke test did not reach.
- One-file executables writing data into their temporary extraction folder and
  losing it on exit.

## Verification prerequisites

- Locked build tooling and a clean output directory.
- An isolated environment for installation, outside the checkout.
- CI runners for each target platform when producing compiled wheels or frozen
  executables.

## Negative cases

- Broken package discovery or misconfigured namespace packages leading to
  installed import failures.
- Entry point missing from the installed environment's scripts directory.
- Dynamic plugin missing from a frozen bundle.

## Scope and limits

This skill verifies metadata, artifact contents, and installed behavior. It does
not replace full integration tests, license compliance review, or platform
compatibility suites. Signing and publication are operator-approved release
steps.

Use the [artifact evidence record](../assets/package-review.md.template).
Run the actual declared backend (for example the consumer's locked `uv build`
workflow) and inspect/install the resulting artifact away from the checkout.
A custom required-key parser is neither backend validation nor license review.

## Sources

- <https://packaging.python.org/>
- <https://peps.python.org/pep-0621/>
- <https://pyinstaller.org/en/stable/>
