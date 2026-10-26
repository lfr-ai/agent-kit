---
description: Review, clean up, modernize and simplify a codebase while enforcing project conventions, preserving behavior and verifying maintainability.
argument-hint: Repository scope, improvement goals, constraints and acceptance criteria
agent: agent
---

# Improve a codebase without needless complexity

Analyze the requested scope, then implement justified improvements. Optimize
for maintainability, readability, minimal cognitive load and task-relevant
context, not the newest technology or the fewest lines.

## Input

- The user-supplied argument identifies the scope, goals and constraints.
  When omitted, cover the owned repository, excluding generated, vendored,
  build output and private runtime data.
- Read project facts, applicable instructions, ownership and declared commands.
  Resolve ordinary ambiguity from established patterns; respect approval gates.

## Procedure

1. Define acceptance criteria and an ordered, proportionate plan. Inventory all
   owned surfaces: code, boundaries, tests, configuration, dependencies, tooling,
   CI, documentation and agent setup. Record exclusions and baseline failures.
2. Use [kit-codebase-audit](../skills/kit-codebase-audit/SKILL.md) for read-only
   discovery and evidenced findings. Keep that phase read-only; this prompt
   then proceeds to implementation rather than stopping at the audit report.
3. Map applicable naming, typing, docstring, defaults, error, logging, architecture
   and testing conventions to existing checks or explicit manual review.
   Review centralization by semantic ownership, filename/class alignment and
   module versus subfolder cohesion. For Python, choose plain functions,
   `functools.partial` or decorators deliberately; preserve binding, signatures,
   invocation kind and observable behavior. Use selected `kit-consistency` and
   `kit-python-service` guidance or the project's equivalent, without forcing
   global registries, one-class-per-file rules or new layers.
4. Ground version-sensitive or risky choices in current official documentation.
   Reuse project capabilities and standard-library or platform facilities first;
   popularity or novelty alone does not justify a dependency or rewrite.
5. Rank findings by correctness risk and maintenance cost. Prefer deletion,
   reuse and simpler control flow through
   [kit-simplify-review](../skills/kit-simplify-review/SKILL.md). Preserve required
   validation, errors, observability and recovery; do not optimize line counts.
6. Implement safe changes in small, owned batches using the selected
   `kit-refactor` and `kit-consistency` procedures. Add characterization or
   failing regression tests first. Separate behavior changes from refactoring;
   never weaken a test or gate to pass.
7. Use [kit-modernize](../skills/kit-modernize/SKILL.md) only when an upgrade is
   justified. Follow manifest, lock, audit and compatibility policy before
   installation; do not silently adopt prereleases or bypass cooldowns.
8. Load only relevant instructions, references and evidence. Keep one canonical
   source, summarize large results and delegate independent, bounded work with
   disjoint owned paths.
   Do not expand permissions, activate dormant integrations or copy private facts.
9. Run focused checks while iterating. After the last edit, perform one bounded
   consistency/readability review and the owning completion gates. Revisit only
   a concrete failure or changed requirement; do not restart discovery endlessly.
10. Update related documentation and durable decisions. Report production
    readiness against verified requirements; native, hosted and operational
    behavior needs its own evidence, not just generated files or static checks.

## Acceptance gates

- [ ] Requested implementation is complete, or each remaining item names a blocker.
- [ ] Applicable conventions have passing checks or explicit manual evidence.
- [ ] Required behavior, security boundaries and observability remain protected.
- [ ] Simplification claims explain reduced navigation, state, duplication or
      unused options; context/cost claims use measurements, not estimates.
- [ ] Exact commands and outcomes are recorded; failures and unavailable checks
      are not presented as passes. Publication and deployment remain operator work.

## Output

A concise summary of findings fixed, complexity intentionally kept, deferred
items, verification results and runtime limitations. Link the durable plan or
decision record when one was needed. End with a short `tldr;`.
