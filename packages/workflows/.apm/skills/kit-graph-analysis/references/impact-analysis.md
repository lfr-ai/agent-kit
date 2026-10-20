# Impact analysis

Impact analysis answers "what could break, and who needs to know?" before a
change is made. The output is a bounded list of modules, symbols, tests and
owners, each with the evidence that put it on the list.

## Inputs

- The change target: module, symbol, contract field, route, event or
  configuration key.
- The kind of change: behavior only, signature, rename or move, deletion,
  data shape, performance characteristics.
- The revision being analyzed.

## Procedure

1. **Classify the change surface.**

   | Change kind | Who can be affected |
   | --- | --- |
   | Internal behavior, same signature | Callers that rely on the old behavior; their tests |
   | Signature change | Every direct caller; subclasses and implementations |
   | Rename or move | Every importer and every string reference |
   | Deletion | Everything above plus dynamic lookups |
   | Data or wire shape | Producers, consumers, stored data, other services |

2. **Direct dependents (depth 1).** Run a reverse query for the module and a
   word-bounded text search for the symbol. Read each hit and classify it:
   uses the changed behavior, uses something else in the module, or false
   positive.
3. **Transitive dependents (depth 2+).** Run the reverse query without a depth
   limit. For each depth-2 module, ask whether the changed behavior propagates
   through the depth-1 module's public surface. Usually only a few do; list
   them and summarize the rest by package.
4. **Cycles.** If the target is inside an import cycle, every module in the
   cycle is depth 1 for practical purposes. Note the cycle and consider
   breaking it first.
5. **Blind spots.** Search for string forms of the name and check every
   category in [the guide](guide.md#blind-spots-of-static-graphs) that applies.
6. **Tests in reach.** For each affected module, find test files that import
   it (`--reverse` on the test package when it is a package, or a text search
   for the import). Mark modules with no test in reach as risks.
7. **Owners.** Map affected paths to owners using the code-owners file or
   recent history; list who must review.
8. **Score and decide.** Use the risk table below to choose the review and
   rollout depth.

## Risk scoring

| Factor | Low | Medium | High |
| --- | --- | --- | --- |
| Depth-1 dependents | 0-3 | 4-15 | more than 15 or crosses packages |
| Test coverage in reach | every affected module | most | key paths untested |
| Blind spots present | none | checked, none found | present and unverifiable |
| Contract exposure | private | internal package API | public, wire or stored data |
| Ownership | one team | two teams | external consumers |

Take the highest row result as the overall risk. High risk calls for a design
note, staged rollout or a compatibility window; medium calls for owner review
of each affected package; low proceeds with normal review.

## Output

Fill the [impact report](../assets/impact-report.md.template) with:

- Commands and revision.
- Depth-1 table: module, importing line, classification, test, owner.
- Depth-2+ summary by package.
- Blind spots checked and findings.
- Risk score with the deciding factor.
- Tests to run and owners to notify.

## Worked example

Changing the rounding rule in `shop.orders.pricing.total`:

1. Reverse query depth 1 finds `shop.orders.checkout` and `shop.api.quotes`.
2. Text search for `total(` within those modules confirms both call it; a
   third hit in `shop.reports.monthly` uses a different `total` (false
   positive, different module).
3. Depth 2 adds `shop.api.views` through `shop.api.quotes`; quotes return the
   value unchanged, so views are affected.
4. String search finds `"orders.pricing.total"` in a scheduled job
   configuration: a blind-spot consumer.
5. Tests: checkout and quotes have tests that assert totals; the scheduled job
   has none, so it is the main risk.
6. Risk: medium (contract exposure internal, one untested path). Plan: add a
   test for the job, notify the reporting owner, release behind no flag.

## Sources

- [Python import system](https://docs.python.org/3/reference/import.html)
- [GitHub code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- [ripgrep user guide](https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md)
