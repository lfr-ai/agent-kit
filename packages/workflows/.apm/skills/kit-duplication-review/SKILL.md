---
name: kit-duplication-review
description: Use when deciding whether repeated code or content should share an abstraction without obscuring ownership.
license: MIT
---

# Review duplication and decide what to unify

Clone detectors find repeated token sequences. Whether a repetition is a
problem depends on one question: when one copy changes for a reason, must the
other copy change for the same reason? If yes, it is duplicated knowledge and
should usually be unified. If no, it is coincidence and should stay apart.

## Procedure

1. **Scope the scan** to the changed files plus the packages they belong to.
   Exclude generated code, vendored code, lockfiles, snapshots and build output
   up front. Whole-repository scans are for periodic audits, not reviews.
2. **Configure jscpd** from the [config template](assets/jscpd.json.template)
   following [jscpd configuration](references/jscpd-configuration.md): set
   `format`, `minLines`, `minTokens`, `mode`, `ignore`, `threshold` and the
   `json` reporter. Confirm flags against the installed version's help.
3. **Run the scan** reproducibly and keep the JSON report:

   ```text
   npx jscpd --config .jscpd.json src
   ```

4. **Summarize** the report with the [summarizer](assets/summarize_jscpd_report.py),
   largest clones first:

   ```text
   python assets/summarize_jscpd_report.py report/jscpd-report.json --min-lines 8 --ignore "tests/fixtures/*"
   python assets/summarize_jscpd_report.py report/jscpd-report.json --markdown > clones.md
   ```

5. **Judge each clone** with [duplication versus coincidence](references/judging-clones.md):
   same reason to change, same owner, same lifecycle, rule of three, and
   whether the copies are mirrors of a contract that a generator should own.
6. **Decide per clone**: `extract` (shared function, module or fixture),
   `generate` (from a schema or contract), `parameterize` (one table-driven
   test or function), `keep` (coincidence; optionally suppress), or
   `defer` (record with an owner). Use
   [extraction patterns](references/extraction-patterns.md) to choose the
   smallest correct unification.
7. **Protect behavior.** Before extracting, make sure each copy's behavior is
   pinned by tests; after extracting, the same tests must pass unchanged.
8. **Re-scan** with identical configuration and confirm the clone is gone and
   no new clone or import cycle appeared.
9. **Record evidence** in the [evidence worksheet](assets/templates/duplication-evidence-template.md):
   command, configuration, before and after counts, per-clone decision with
   reason, tests and owners.

## Summarizer contract

The summarizer reads the jscpd `json` reporter output, never runs jscpd, and
prints `path:line: N-line <format> clone of other:start-end (T tokens)` per
clone pair, largest first. It exits 1 when any clone remains after
`--min-lines` and `--ignore` filters or when the reported total exceeds
`--max-percentage`; it exits 2 on a missing or malformed report. Run
`--self-test` after editing it.

## Acceptance gates

- [ ] Scan scope and exclusions are explicit; generated and vendored code are
      excluded before judging.
- [ ] Every reported clone above the agreed size has a recorded decision with
      a reason grounded in "same reason to change", not in the line count.
- [ ] Extractions keep ownership clear: the shared code has one owner and lives
      at the lowest common dependency of its callers.
- [ ] No extraction introduced an import cycle or a dependency from a lower
      layer to a higher one.
- [ ] Tests pinning each former copy pass unchanged after the extraction.
- [ ] The re-scan uses identical configuration and shows the expected change.
- [ ] Suppressions (`jscpd:ignore-start`/`jscpd:ignore-end`, ignore globs) carry
      a reason.

## Do not

- Merge code from different owners or bounded contexts just because tokens
  match; that couples their release cycles.
- Lower `minTokens` or `minLines` until the scan reports trivia, then "fix"
  the trivia.
- Raise `threshold` to make a gate pass without a recorded decision.
- Extract helpers with boolean flags that select between the original copies.

Gates, failure modes and recovery are in the [review guide](references/guide.md).
