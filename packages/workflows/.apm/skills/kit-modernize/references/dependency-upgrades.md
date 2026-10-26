# Dependency upgrades in risk tiers

Upgrade in the order that keeps each failure easy to attribute. A batch mixes
packages only when they share a tier and a reason; a major upgrade of a runtime
dependency is always its own batch.

## Tiers

| Tier | Contents | Batch size | Typical verification |
| --- | --- | --- | --- |
| 0 | Development tools: linters, formatters, type checkers, test plugins | several together | gates pass; new findings triaged, not suppressed |
| 1 | Runtime patch and minor upgrades within semantic-version promises | several together | full suite, deprecation warnings as errors |
| 2 | Interpreter version | alone | full suite on old and new versions during transition, wheel install |
| 3 | Runtime major upgrades and replacement of abandoned packages | one package per batch | migration guide applied, contract and integration tests, staged rollout |
| 4 | Mechanical syntax rewrites (Ruff `UP`) | one rule family per batch | no behavior change: tests unchanged and passing, diff reviewed |

## Commands with uv

```text
uv tree --outdated --depth 1            # direct dependencies with newer versions
uv lock --upgrade-package <name>        # one package within the declared range
uv add --no-sync "<name>>=<new>,<<next major>"   # raise a declared range
uv lock --check                         # lockfile matches the manifest
uv sync --locked                        # install exactly the lockfile
```

Change the manifest and the lockfile in the same batch; audit the new lock
before syncing as described in `kit-supply-chain`.

## Abandoned or superseded packages

Judge maintenance with the criteria in the tool-selection reference of
`kit-codebase-audit` (release recency, maintainers, adoption, license). Common
replacements:

| Legacy package or API | Replacement | Note |
| --- | --- | --- |
| `six`, `future` | Python 3 syntax and stdlib | remove after the last Python 2 path is gone |
| `mock` backport | `unittest.mock` | change imports only |
| `pytz` | `zoneinfo` (3.9) with `tzdata` where the OS lacks a database | `localize` and `normalize` calls disappear; test DST edges |
| `toml`, `tomli` for reading | `tomllib` (3.11) | `tomllib` reads bytes from a binary file handle |
| `importlib_metadata`, `importlib_resources` backports | `importlib.metadata`, `importlib.resources` | check the API version the code uses |
| `pkg_resources` | `importlib.metadata`, `importlib.resources`, `packaging` | setuptools deprecates `pkg_resources` |
| `distutils` | setuptools, `packaging`, `shutil`, `sysconfig` | removed from the stdlib in 3.12 |
| `appdirs` | `platformdirs` | API is close; check directory names |
| `asynctest` | `unittest.IsolatedAsyncioTestCase` or pytest async plugins | test-only |
| `nose` | pytest | test-only; convert fixtures and generators |
| `setup.py` command invocations | `python -m build`, `uv build`, `pip install .` | see packaging migration |

## Deprecations

1. Run the suite with first-party deprecations as errors, for example the
   pytest setting `filterwarnings = ["error::DeprecationWarning:shop.*"]` or
   `python -W error::DeprecationWarning`.
2. Read the changelog and migration guide of each upgraded package between
   the old and new versions; deprecated APIs are usually removed one major
   version later.
3. Record every remaining warning in the ledger with the package, the call
   site and the version that removes it.

## Failure modes

- **Silent behavior change in a minor release.** Detect with contract and
  integration tests at the boundary that uses the package.
- **Transitive conflict.** A major upgrade forces another package to move.
  Upgrade them in one batch only if they cannot move independently; record
  why.
- **Lock drift.** The manifest changes without a new lock, or the reverse.
  `uv lock --check` in CI catches it.
- **Upgrade as cover for refactoring.** Rewrites mixed into an upgrade batch
  make the rollback lose unrelated work. Split them.

## Primary sources

- [uv: locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [uv: managing dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/)
- [Python warnings filter](https://docs.python.org/3/library/warnings.html#the-warnings-filter)
- [pytest: controlling warnings](https://docs.pytest.org/en/stable/how-to/capture-warnings.html)
- [zoneinfo](https://docs.python.org/3/library/zoneinfo.html)
- [tomllib](https://docs.python.org/3/library/tomllib.html)
- [importlib.metadata](https://docs.python.org/3/library/importlib.metadata.html)
- [setuptools: pkg_resources deprecation](https://setuptools.pypa.io/en/latest/pkg_resources.html)
- [platformdirs](https://github.com/tox-dev/platformdirs)
