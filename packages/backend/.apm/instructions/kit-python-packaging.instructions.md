---
description: Apply to Python packaging metadata, build configuration, and PyInstaller spec files.
applyTo: "**/pyproject.toml,**/*.spec,**/MANIFEST.in,**/setup.cfg"
---

- Declare project metadata in `pyproject.toml` (PEP 621) with a pinned build backend in `[build-system]`; do not add `setup.py` logic for static metadata.
- Keep runtime dependencies as compatible ranges and lock exact versions in the project lockfile; put tooling in dependency groups or extras.
- Set `requires-python` to the supported range and test its lower bound.
- Include package data explicitly and verify the built wheel and sdist contain it; installed code must not rely on files from the source checkout.
- Read packaged resources with `importlib.resources`, never with paths relative to the repository.
- Keep the version in one source of truth and expose commands through `[project.scripts]`.
- Treat PyInstaller spec files as executable build code: deterministic, free of secrets, and under version control.
- Pin the PyInstaller version, build on each target operating system (it does not cross-compile), and use `--clean --noconfirm` in automation.
- List `hiddenimports`, `datas`, and `binaries` explicitly instead of collecting whole packages; exclude test and development modules.
- Resolve bundled files at runtime through one helper that uses `sys._MEIPASS` when `sys.frozen` is set.
- Smoke-test the built artifact on a clean machine or container, not only from the source tree.
- Sign and checksum release artifacts through the approved release workflow.
- Use the `kit-python-package` skill for the packaging and release procedure.
