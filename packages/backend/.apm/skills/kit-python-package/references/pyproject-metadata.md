# Project metadata in `pyproject.toml`

## Tables and who reads them

| Table | Standard | Read by |
| --- | --- | --- |
| `[build-system]` | PEP 517 / PEP 518 | Build frontends (`pip`, `uv build`, `python -m build`) to install and call the backend |
| `[project]` | PEP 621 (core metadata in TOML) | The backend, which writes wheel/sdist metadata |
| `[dependency-groups]` | PEP 735 | Development tools (`uv`, `pip` 25.1+); never published |
| `[tool.<name>]` | Tool-owned | That tool only (backend configuration, linters, test runners) |

A project without `[build-system]` is built with a legacy setuptools fallback;
always declare it.

## Required and common `[project]` fields

| Field | Notes |
| --- | --- |
| `name` | Required, static. Letters, digits, `.`, `_`, `-`; compared after normalization (`My_Pkg` equals `my-pkg`) |
| `version` | Static PEP 440 string, or listed in `dynamic` and supplied by the backend (for example from a VCS tag) |
| `requires-python` | Specifier such as `">=3.12"`. Installers skip releases that do not support the interpreter. Avoid upper caps unless the code truly fails on newer versions |
| `dependencies` | PEP 508 requirement strings for runtime only. Libraries use lower bounds and avoid exact pins; applications pin through a lockfile, not here |
| `optional-dependencies` | Named extras for optional runtime features (`pip install pkg[postgres]`). Not for test tooling |
| `readme` | Path or table; rendered on package indexes. The file must exist in the sdist |
| `license` | SPDX expression string such as `"MIT"` or `"Apache-2.0 OR MIT"` (PEP 639) |
| `license-files` | Globs for license texts to ship in the distribution |
| `authors`, `maintainers` | Tables with `name` and/or `email` |
| `classifiers` | Trove classifiers; omit `License ::` classifiers when `license` is an expression |
| `urls` | Homepage, source, issues, changelog |
| `scripts`, `gui-scripts`, `entry-points` | See [build and artifacts](build-and-artifacts.md#entry-points) |

### `dynamic`

A field listed in `dynamic` is computed by the backend at build time. A field
must not be both static and dynamic, and `name` can never be dynamic. Keep
`dynamic` to what the backend actually computes (usually `version`).

### License metadata (PEP 639)

- Use `license = "MIT"` (an SPDX expression) and `license-files = ["LICENSE*"]`.
- The older table form (`license = { text = "MIT" }` or `{ file = "LICENSE" }`) is
  deprecated. Backends that implement PEP 639 (recent setuptools, hatchling,
  flit-core, pdm-backend, uv_build) accept the expression; check the pinned
  backend version before switching.
- Do not combine an expression with `License ::` classifiers.

## Dependencies versus dependency groups

```toml
[project]
dependencies = ["httpx>=0.27", "pydantic>=2.7"]

[project.optional-dependencies]
postgres = ["psycopg[binary]>=3.2"]

[dependency-groups]
test = ["pytest>=8", "pytest-cov"]
lint = ["ruff"]
dev = [{ include-group = "test" }, { include-group = "lint" }]
```

- Test, lint, type-check, and build tools go into dependency groups. They never
  reach users of the published package.
- Local paths and `file:` direct references cannot be published to an index; use
  a workspace or path source in tool configuration (for example
  `[tool.uv.sources]`) instead.

## Validation

- Run [check_pyproject.py](../assets/check_pyproject.py) for fast structural
  checks: build-system, required fields, dynamic conflicts, license form,
  readme presence, development tools in runtime dependencies, local references,
  duplicates, and entry-point syntax.
- Then build with the declared backend and inspect the produced metadata. The
  checker is not a substitute for the backend's own validation, and
  `twine check dist/*` validates the rendered long description for upload.

The [pyproject template](../assets/pyproject.toml.template) applies all of the
above.

## Sources

- <https://packaging.python.org/en/latest/specifications/pyproject-toml/>
- <https://packaging.python.org/en/latest/guides/writing-pyproject-toml/>
- <https://peps.python.org/pep-0621/>
- <https://peps.python.org/pep-0639/>
- <https://peps.python.org/pep-0735/>
- <https://packaging.python.org/en/latest/specifications/dependency-specifiers/>
- <https://packaging.python.org/en/latest/specifications/name-normalization/>
