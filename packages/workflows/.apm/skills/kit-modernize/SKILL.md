---
name: kit-modernize
description: Use when upgrading Python versions, dependencies, packaging, or syntax in measured, reversible batches.
license: MIT
---

# Modernize in measured, reversible batches

Modernization changes many files for reasons other than features, so every
batch must be small, mechanical where possible, verified on its own and
revertible on its own. Behavior changes ship separately. Whole-repository
discovery belongs to `kit-codebase-audit`; behavior-preserving restructuring
to `kit-refactor`; pins, advisories and provenance to `kit-supply-chain`.

## Procedure

1. **Baseline.** Record the current and target Python versions with their
   support status from [Python versions](references/python-versions.md), the
   dependency tree (`uv tree --outdated` or the project's tool), deprecation
   warnings from the test suite (`python -W error::DeprecationWarning -m pytest`
   or the pytest `filterwarnings` setting) and the legacy-syntax count from the
   [legacy syntax checker](assets/check_legacy_syntax.py). Open the
   [modernization ledger](assets/modernization-ledger.md.template).
2. **Plan batches by risk tier** with the
   [batch plan](assets/upgrade-batch-plan.md.template) and
   [dependency upgrades](references/dependency-upgrades.md): tooling and
   development dependencies, then patch and minor runtime upgrades, then the
   interpreter, then major upgrades and replacements of abandoned packages,
   then mechanical syntax rewrites. One batch, one reason, one revert.
3. **Fix packaging first when it blocks everything else.** Move `setup.py`
   or `setup.cfg` metadata to a PEP 621 `[project]` table and adopt a committed
   uv lockfile following [packaging migration](references/packaging-migration.md).
   Prove the built wheel installs and imports away from the checkout.
4. **Raise the interpreter** in one batch: `requires-python`, CI matrix, Ruff
   `target-version`, type-checker version, container base images and
   documentation. Replace modules removed in the target (for example the
   PEP 594 modules removed in 3.13) and resolve deprecations surfaced as errors.
5. **Rewrite syntax mechanically** with the Ruff `UP` and `FA` selection in the
   [Ruff modernization snippet](assets/ruff-modernize.toml.template), one rule
   family per batch: builtin generics and `X | Y`, PEP 695 type parameters,
   `StrEnum`, f-strings. Review unsafe fixes by hand; see
   [syntax modernization](references/syntax-modernization.md) for runtime
   annotation consumers (Pydantic, dataclasses, FastAPI) that need care.
6. **Adopt language features only where they simplify.** `match`,
   `ExceptionGroup` with `except*`, `asyncio.TaskGroup` and `asyncio.timeout`
   replace code only when the decision tables say so; never as churn.
7. **Remove compatibility shims** once the minimum version makes them dead:
   `sys.version_info` branches, backport packages, `try`/`except ImportError`
   fallbacks, `typing_extensions` names now in `typing`, `six`.
8. **Verify each batch** before starting the next: focused tests, full suite,
   type checker, Ruff, deprecation warnings as errors, a wheel build and clean
   install, and the checker count must not rise:

   ```text
   python assets/check_legacy_syntax.py src tests
   python assets/check_legacy_syntax.py src --pathlib --future-annotations
   ```

   The checker exits 1 on findings and 2 on missing or unparsable files;
   `--pathlib` and `--future-annotations` are policy opt-ins, `--disable`
   turns off a default rule, and `--self-test` runs its built-in regressions.
9. **Roll back by batch.** A failing batch is reverted as a unit, including its
   lockfile change; record the cause in the ledger and split the batch.
10. **Close the ledger**: each item has before and after evidence, the gate
    that now prevents regression, and any deferred item with an owner.

## Acceptance gates

- Each batch has one reason, its own verification evidence and a tested
  rollback; behavior changes are not mixed into modernization batches.
- The lockfile, `requires-python`, CI matrix and tool target versions agree.
- Tests pass with deprecation warnings treated as errors for first-party code,
  or each remaining warning is in the ledger with an owner.
- The built wheel installs and imports in a clean environment.
- The legacy-syntax count and Ruff `UP` findings do not rise between batches;
  the final count matches the ledger.
- Replaced or abandoned dependencies are gone from manifests and lockfiles.

Quality gates, failure modes and primary sources are in the
[modernization guide](references/guide.md).
