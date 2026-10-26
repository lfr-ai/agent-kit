# Packaging migration: setup.py to pyproject and a uv lockfile

Move static metadata into `pyproject.toml` (PEP 621), keep a standards-based
build backend (PEP 517), and commit one lockfile. Do it before other
modernization batches when the build cannot express a new Python version or
dependency group cleanly.

## Mapping `setup()` arguments

| `setup.py` / `setup.cfg` | `pyproject.toml` | Note |
| --- | --- | --- |
| `name`, `version` | `[project] name`, `version` | or `dynamic = ["version"]` with the backend's version source |
| `description`, `long_description` | `description`, `readme = "README.md"` | content type is inferred from the extension |
| `python_requires` | `requires-python` | must match the CI matrix and Ruff `target-version` |
| `install_requires` | `dependencies` | keep ranges; exact pins belong in the lockfile |
| `extras_require` | `[project.optional-dependencies]` | only for user-facing extras |
| test or lint requirements files | `[dependency-groups]` (PEP 735) | development-only; not published |
| `entry_points["console_scripts"]` | `[project.scripts]` | other groups go to `[project.entry-points."group"]` |
| `license`, `license_files` | `license = "MIT"` (SPDX expression), `license-files` | PEP 639 metadata |
| `classifiers`, `keywords`, `url` | same keys, `[project.urls]` | |
| `packages=find_packages(...)`, `package_dir` | backend configuration, for example `[tool.setuptools.packages.find]` | prefer a `src/` layout |
| `package_data`, `include_package_data` | backend configuration | verify files appear in the wheel |
| custom `cmdclass`, build-time code | keep a minimal `setup.py` only for it | static metadata still moves |

## Steps

1. Freeze the current artifacts: build the old sdist and wheel and keep their
   file lists and `METADATA`.
2. Write `[build-system]` and `[project]`; remove the migrated keys from
   `setup.py`/`setup.cfg`, deleting the files when nothing dynamic remains.
3. Build again (`uv build` or `python -m build`) and diff the file lists and
   metadata against step 1: same modules, data files, entry points and
   dependency ranges.
4. Install the wheel into a clean environment away from the checkout, import
   the package and run its console scripts.
5. Adopt the lockfile: `uv lock`, commit `uv.lock`, switch CI to
   `uv sync --locked`, and add `uv lock --check` so manifest and lock never
   drift. Remove superseded `requirements*.txt` files or generate them from the
   lock (`uv export`) when a consumer still needs them.
6. Record the before and after artifact comparison in the ledger.

## Failure modes

- **Missing package data.** Templates or JSON files vanish from the wheel.
  Detect with the file-list diff in step 3.
- **Checkout-only imports.** Moving from a flat layout to `src/` reveals
  imports that only worked from the repository root. Detect with the
  clean-environment import.
- **Dynamic version drift.** The version source differs from the tag. Build
  from a tagged commit and compare.
- **Development tools in runtime dependencies.** Move them to dependency
  groups; check with deptry or the published metadata.

## Primary sources

- [Writing pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [PEP 621](https://peps.python.org/pep-0621/), [PEP 517](https://peps.python.org/pep-0517/),
  [PEP 735](https://peps.python.org/pep-0735/), [PEP 639](https://peps.python.org/pep-0639/)
- [setuptools: configuring with pyproject.toml](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)
- [uv: project layout and lockfile](https://docs.astral.sh/uv/concepts/projects/layout/)
- [uv: building distributions](https://docs.astral.sh/uv/concepts/projects/build/)
