# Severity and confidence rubric

Grade impact and certainty separately. Severity says how much harm the issue
can cause; confidence says how sure the evidence makes you. Rank the report by
severity, then confidence, then breadth (count of instances), then effort.

## Severity

| Severity | Meaning | Typical examples |
| --- | --- | --- |
| Critical | Exploitable now, data loss or corruption, or production outage on a common path | reachable known vulnerability with a fix available, SQL built from user input, secret committed to the repository, migration that drops data |
| High | Incorrect behavior or security weakness on a plausible path, or a broken architectural rule that spreads | swallowed exception on a payment path, domain importing an HTTP framework, missing authorization check, dependency without a lock |
| Medium | Maintainability cost that slows every change in an area, or a latent defect on a rare path | function with complexity well above the gate in a hot spot, duplicated business rule in two packages, missing tests for documented errors |
| Low | Local readability or consistency issue with small cost | unnamed numeric literal, inconsistent naming in one module, missing docstring on an internal helper |
| Info | Observation with no action required now | tool not configured, convention worth documenting |

Raise severity one step when the issue sits on a hot spot or a public boundary;
lower it one step when the code is scheduled for removal with an owner and date.

## Confidence

| Confidence | Evidence required |
| --- | --- |
| High | Reproduced (failing test, executed command) or certain from static facts (import exists, literal is present, version is in the advisory range) |
| Medium | Tool finding confirmed by reading the code, with dynamic use not fully excluded |
| Low | Tool finding or reasoning not yet confirmed; dynamic dispatch, plugins or configuration could change the answer |

Critical and high findings need medium or high confidence. A low-confidence
issue that would be critical is reported as "needs verification" with the
check that would settle it.

## Systemic findings

When one root cause produces many instances (the same rule in 40 files),
report one finding with:

- the pattern and its root cause;
- the count and the command that counted it;
- three representative `path:line` locations;
- a remediation that removes the cause (a gate, a shared helper, a generator),
  not 40 manual edits.

## Owner routing

| Finding area | Owner skill |
| --- | --- |
| Behavior-preserving restructuring, complexity | `kit-refactor` |
| Names, contracts and terms across files | `kit-consistency` |
| Layers, ports, adapters, dependency direction | `kit-hexagonal-architecture` |
| Python types, errors, logging, docstrings, magic numbers | `kit-python-service` |
| Vulnerabilities, pins, licenses, provenance | `kit-supply-chain` |
| Duplicated knowledge | `kit-duplication-review` |
| Over-engineering | `kit-simplify-review` |
| Python, syntax and dependency upgrades | `kit-modernize` |
| Change impact before a large remediation | `kit-graph-analysis` |

## Effort

Estimate effort in coarse buckets (hours, days, weeks) and state what drives
it (callers, tests missing, data migration). Do not convert effort into a
score that hides the severity.
