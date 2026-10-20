# Build backends, versions, artifacts, and entry points

## Build backends

| Backend | `build-backend` | Notes |
| --- | --- | --- |
| Hatchling | `hatchling.build` | Pure-Python; plugins for VCS versions and build hooks |
| setuptools | `setuptools.build_meta` | Required for C extensions via `setup.py`; supports `pyproject.toml`-only projects |
| Flit core | `flit_core.buildapi` | Minimal, pure-Python packages only |
| PDM backend | `pdm.backend` | Pure-Python; dynamic versions from SCM |
| uv build | `uv_build` | Fast pure-Python builds with a fixed `src/` layout convention |
| scikit-build-core, meson-python, maturin | various | Compiled extensions (CMake, Meson, Rust) |

Choose the simplest backend that supports the project. Pin its version range in
`build-system.requires` so builds are reproducible.

## Layout

- Prefer a `src/` layout (`src/order_tools/...`). Tests then import the installed
  package instead of accidentally importing the source tree, which catches
  missing package data and broken discovery.
- Keep one top-level import package per distribution unless you deliberately use
  namespace packages.
- Ship `py.typed` in typed libraries so type checkers use inline annotations.

## Versioning (PEP 440)

- Release versions: `1.4.0`; pre-releases `1.5.0a1`, `1.5.0b2`, `1.5.0rc1`;
  post-releases `1.4.0.post1`; development builds `1.5.0.dev3`.
- Local version labels (`1.4.0+build.7`) are for local builds only; public
  indexes reject them.
- Choose one source of truth: a static `version` in `pyproject.toml`, or a
  dynamic version from a VCS tag via the backend. Expose it at runtime with
  `importlib.metadata.version("order-tools")` rather than duplicating a
  `__version__` constant.
- Semantic versioning is a convention layered on PEP 440; document what a major
  bump means for your users.

## Wheels and source distributions

| Artifact | Contents | Installed by |
| --- | --- | --- |
| sdist (`.tar.gz`) | Source tree subset, `pyproject.toml`, `PKG-INFO` | Builds a wheel on the installing machine |
| Wheel (`.whl`) | Ready-to-install files, `*.dist-info` metadata | Unpacked directly; no build step |

- Pure-Python wheels are tagged `py3-none-any`. Compiled wheels carry interpreter,
  ABI, and platform tags (`cp313-cp313-manylinux_2_28_x86_64`); build one per
  target in CI.
- Always publish both an sdist and wheels for libraries. Applications deployed
  from a private index may publish wheels only.
- Inspect both artifacts before publishing:

  ```text
  uv build --out-dir dist/
  python -m zipfile -l dist/order_tools-1.4.0-py3-none-any.whl
  tar -tzf dist/order_tools-1.4.0.tar.gz
  ```

  Confirm package data (templates, schemas, `py.typed`), license files, and the
  absence of tests, caches, secrets, and local configuration.
- Install the wheel into a fresh virtual environment outside the checkout and
  run the import and CLI smoke there.

## Package data

- Files inside the import package are included by most backends when they are
  tracked by version control or matched by include rules; verify, do not
  assume. Configure explicit includes for non-Python files when needed.
- Read packaged files with `importlib.resources.files("order_tools") /
  "templates" / "invoice.html"`, never with paths relative to the current
  working directory. The [resource helper](../assets/resources.py.template) also
  covers frozen executables.

## Entry points

```toml
[project.scripts]
order-tools = "order_tools.cli:main"

[project.gui-scripts]
order-tools-gui = "order_tools.gui:run"

[project.entry-points."order_tools.exporters"]
csv = "order_tools.exporters.csv:CsvExporter"
```

- Console scripts are generated wrappers that import `module` and call
  `function()`; its return value becomes the exit code. Keep `main` small: parse
  arguments, build the composition root, return an `int`.
- Plugin groups (`entry-points`) are discovered with
  `importlib.metadata.entry_points(group="order_tools.exporters")`.
- Test the installed command (`order-tools --help`) from the built wheel, not
  `python -m` from the source tree.

## Publication

- Upload from CI with trusted publishing (OpenID Connect) instead of long-lived
  API tokens where the index supports it.
- Generate checksums and keep build logs as release evidence.
- Publishing is an operator-approved step, never part of an authoring session.

## Sources

- <https://packaging.python.org/en/latest/tutorials/packaging-projects/>
- <https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/>
- <https://packaging.python.org/en/latest/specifications/version-specifiers/>
- <https://packaging.python.org/en/latest/specifications/binary-distribution-format/>
- <https://packaging.python.org/en/latest/specifications/source-distribution-format/>
- <https://packaging.python.org/en/latest/specifications/entry-points/>
- <https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/>
- <https://docs.python.org/3/library/importlib.resources.html>
- <https://docs.python.org/3/library/importlib.metadata.html>
- <https://docs.astral.sh/uv/concepts/build-backend/>
- <https://hatch.pypa.io/latest/config/build/>
