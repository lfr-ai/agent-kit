# Modernization guide

Quality gates, failure modes, rollback and primary sources for modernization
batches. Version facts are in [Python versions](python-versions.md), upgrade
order in [dependency upgrades](dependency-upgrades.md), build changes in
[packaging migration](packaging-migration.md) and rewrites in
[syntax modernization](syntax-modernization.md). Reviewed 2026-10-23.

## Quality gates per batch

| Gate | Pass condition |
| --- | --- |
| Single reason | The batch title names one tier and one reason; the diff contains nothing else |
| Baseline | Tests, types and lint were green (or their failures recorded) before the batch |
| Behavior | Tests pass unchanged; no assertion edited to fit the upgrade |
| Warnings | First-party deprecation warnings are errors, or listed in the ledger with an owner |
| Consistency | `requires-python`, CI matrix, Ruff `target-version`, type-checker version and lockfile agree |
| Artifact | The wheel builds, installs in a clean environment and imports |
| Ratchet | `check_legacy_syntax.py` and Ruff `UP` counts do not rise |
| Rollback | Reverting the batch commit (including the lockfile) restores the previous green state |

## Failure modes

- **Big-bang upgrade.** Interpreter, majors and rewrites land together; a
  failure cannot be attributed. Split by tier.
- **Rewrite changes runtime behavior.** Annotation rewrites break Pydantic or
  dataclass consumers, `StrEnum` changes `str()` output, `TaskGroup` changes
  error types. Detect with boundary tests and serialized-output snapshots.
- **Hidden version floor.** One dependency drops support for the old Python
  in a minor release and the lock resolves differently per interpreter. Lock
  for every supported version and test the matrix.
- **Forgotten surface.** Container images, CI images, documentation, tox or
  nox sessions and pre-commit hooks still name the old version. Search for the
  old version string before closing the batch.
- **Shim removed too early.** A library still supports an older Python than
  the code now assumes. Check `requires-python` before deleting a branch.
- **Policy rule forced on everyone.** `--pathlib` and `--future-annotations`
  are opt-ins; enabling them without an agreed policy creates churn.

## Rollback

1. Revert the batch commit as a whole, including manifest and lockfile.
2. Re-run the baseline gates to prove the previous state is green again.
3. Record the failure, the evidence and the split plan in the ledger.
4. Retry with a smaller batch (fewer packages, one rule family, one
   package directory).

For deployed applications, keep the previous artifact deployable until the
new interpreter or major dependency has run under production load; follow the
project's release rollback, not a source revert alone.

## Checker contract

`check_legacy_syntax.py` parses files with `ast` and never imports them. It
reports `path:line: rule: message` for deprecated `typing` aliases and `%`
string formatting by default, and for `from __future__ import annotations`
(`--future-annotations`) and `os.path` (`--pathlib`) when policy enables them.
It exits 0 when clean, 1 on findings and 2 on missing paths or unparsable
files; `--self-test` runs its built-in regressions. It does not see aliases
built dynamically, string annotations or
`typing` names re-exported through other modules; Ruff `UP` remains the
authoritative rewrite tool.

## Primary sources

- [Status of Python versions](https://devguide.python.org/versions/)
- [Ruff rules](https://docs.astral.sh/ruff/rules/)
- [uv projects](https://docs.astral.sh/uv/concepts/projects/)
- [Python Packaging User Guide](https://packaging.python.org/en/latest/)
- [Python warnings](https://docs.python.org/3/library/warnings.html)
