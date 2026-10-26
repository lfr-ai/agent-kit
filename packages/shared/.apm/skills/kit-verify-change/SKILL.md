---
name: kit-verify-change
description: Use when handing off a source change or preparing to claim a quality gate passes.
license: MIT
---

# Verify the outcome

## Procedure

1. Run the smallest relevant test while iterating.
2. Identify the repository's declared gate and its metafiles (lockfile, formatter, linter,
   type checker, test, spelling, Markdown, link and secrets configuration); see
   [toolchain metafiles](references/toolchain-metafiles.md). If no single gate exists,
   choose its rows from the [quality gate catalog](references/quality-gate-catalog.md),
   record them in a [gate plan](assets/gate-plan.md.template), and start from the
   [gate script template](assets/run_gate.py.template).
3. Check types, lint, formatting, architecture, and owning contracts in fast-to-slow order
   ([gate ordering](references/gate-ordering.md)).
4. Keep checks read-only. Formatting and other fixers are an explicit separate action
   (`run_gate.py --fix`); review their diff before committing it.
5. Check spelling and links for changed prose
   ([spell and link checking](references/spell-and-link-checking.md),
   [CSpell configuration template](assets/cspell.json.template)); fix typos instead of
   adding them to the word list.
6. Scan for secrets against an audited baseline; rotate anything that leaked
   ([secrets scanning](references/secrets-scanning.md)).
7. Exercise invalid inputs, error propagation, and changed boundary behavior; record the
   red and green runs of the original symptom.
8. Run the declared completion gate after the last edit; in CI-equivalent mode use
   `--keep-going --report gate-report.json`.
9. Keep pre-commit and CI on the same definition and tool versions
   ([parity guidance](references/precommit-ci-parity.md),
   [pre-commit template](assets/pre-commit-config.yaml.template),
   [CI gate workflow template](assets/ci-gate.yml.template)). Pin every tool,
   hook, action, image and feature exactly and enforce it with the
   [pin checker](assets/check_pins.py) ([version pinning](references/version-pinning.md)).
10. Classify every failure as caused, coupled, or pre-existing (prove pre-existing on the
    base revision) and handle each accordingly.
11. Distinguish executed checks from inspection and unavailable prerequisites.
12. Report exact results without lowering thresholds or hiding failures, using the
    [gate report](assets/gate-report.md.template) or the short
    [handoff record](assets/evidence.md.template)
    ([evidence reporting](references/evidence-reporting.md)).

Test the required outcome, not a proxy that could pass while behavior remains broken.

## Acceptance gates

- The full declared gate ran after the last edit, with exact commands, environment and
  exit status recorded.
- No step reported `failed`, `timeout` or `unavailable`; any `skipped` step names its reason
  and is listed under "not verified".
- No fixer, regeneration or baseline rewrite ran inside a check-only gate.
- Thresholds, assertions, ignore lists and word lists were not weakened to pass; any
  deliberate policy change is called out separately.
- The original symptom and the highest-risk negative case have before/after evidence.
- Live host, cloud, IDE or model behavior is claimed only when that surface was exercised.

Start from the [evidence gates](references/guide.md).
