---
name: kit-python-package
description: Use when structuring, building, or validating a distributable Python package or command-line entry point.
license: MIT
---

# Keep the installed package self-contained

## Procedure

1. Read the build backend, package layout, supported Python versions, and lockfile workflow. Prefer a `src/` layout so tests exercise the installed package.
2. Declare metadata in `[project]` per PEP 621 with an SPDX `license` expression, `requires-python`, and a single version source; see [project metadata](references/pyproject-metadata.md). Start new projects from the [pyproject template](assets/pyproject.toml.template).
3. Keep runtime dependencies in `dependencies`, optional features in extras, and test/lint/build tools in `[dependency-groups]`. Never publish local or `file:` direct references.
4. Run [check_pyproject.py](assets/check_pyproject.py) for fast structural feedback, then rely on the backend's own validation.
5. Declare package data explicitly and read it with `importlib.resources`; the [resource helper](assets/resources.py.template) also works in frozen bundles.
6. Define console scripts and plugin groups as entry points (`module:function`), not shell wrappers; see [build and artifacts](references/build-and-artifacts.md).
7. Ensure start-up does not read repository files, developer home paths, or undeclared environment state.
8. Build into a fresh output directory with the locked backend, list wheel and sdist contents, and confirm package data, license files, and `py.typed` are present while tests, caches, and secrets are absent.
9. Install the built wheel into an isolated environment outside the checkout and exercise the public import and CLI contract there.
10. For end-user executables, freeze with PyInstaller from a committed spec ([spec template](assets/app.spec.template)); choose one-folder or one-file deliberately, list hidden imports and data files, and build per platform; see [PyInstaller](references/pyinstaller.md).
11. Automate steps 4, 8, 9, and 10 in CI with the [build workflow template](assets/ci-build.yml.template); signing and publication remain operator-approved jobs.
12. Record evidence in the [package review](assets/package-review.md.template): commands, artifact inventory, smoke results, checksums, and the interpreter/platform matrix actually exercised.
13. Preserve the lockfile through the project's manager; never hand-edit generated lock data.
14. Read the [packaging guide](references/guide.md) and the root [checklist](guide.md) for failure modes and scope.

## Acceptance gates

- `[build-system]` and PEP 621 metadata are complete; `check_pyproject.py` reports no findings or each is explained.
- The wheel installs in an isolated environment and its import and CLI smoke pass outside the source checkout.
- Required package data and license files are present in the built artifacts; tests, caches, and secrets are absent.
- Development tools are absent from runtime dependencies.
- Frozen executables (when produced) pass a smoke test that loads data files and dynamically imported modules on every target platform.
- Unexercised interpreters or platforms are reported, not implied.

## Commands

```text
python assets/check_pyproject.py pyproject.toml
python assets/check_pyproject.py --self-test
uv build --out-dir dist/
python -m zipfile -l dist/<name>-<version>-py3-none-any.whl
pyinstaller app.spec --clean --noconfirm
```

A few metadata-key checks are not packaging validation; always build, inspect, and install the real artifact.
