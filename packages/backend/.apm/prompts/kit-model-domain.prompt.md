---
description: Model a domain concept as value objects, an aggregate with enforced invariants, events, and a repository port, independent of transport and storage.
argument-hint: The domain concept and its rules, e.g. "an order that cannot ship unpaid"
agent: agent
---

# Model a domain concept

Capture business rules in framework-free domain code where they cannot be
bypassed, with tests that state each invariant.

## Input

- The user-supplied argument names the concept and its rules. If the rules
  are vague, list the invariants you infer and ask for confirmation before
  writing code.

## Procedure

1. Load [kit-domain-model](../skills/kit-domain-model/SKILL.md) and use its
   templates and port-binding checker.
2. Read existing domain modules for naming, identity, error, and event
   conventions. Reuse them; do not introduce a parallel style.
3. Write the invariants as plain sentences, each with a valid and an invalid
   example. These become test names.
4. Identify value objects (immutable, equal by value, validated on creation)
   and entities (identity, lifecycle). Choose the aggregate boundary as the
   smallest set that must change together to keep an invariant.
5. Write failing tests for each invariant: creation, every state transition,
   and every rejected command, asserting that rejection leaves state and
   pending events unchanged.
6. Implement value objects, then the aggregate with intention-revealing
   methods; expose read-only views, never mutable internals.
7. Record domain events for facts other parts of the system react to; publish
   them only after the aggregate is saved.
8. Define a repository port in the domain or application layer, plus an
   in-memory adapter that passes the same contract tests as the production
   adapter.
9. Keep the domain free of framework, ORM, transport schema, and SDK imports.
   Map to persistence and transport in adapters.
10. If the persisted shape changes, plan a migration or read adapter (see
    [kit-database-migrations](../skills/kit-database-migrations/SKILL.md)).
11. Run the domain tests, the port-binding checker, and the completion gate.

## Acceptance gates

- [ ] Every invariant has a passing test and a rejected-command test.
- [ ] Value objects are immutable and compare by value.
- [ ] Every port has at least one adapter implementing all members.
- [ ] Domain modules import no infrastructure.

## Output

The invariant list with test names, the model sketch (value objects,
aggregate, events, port), files changed, and commands run with results.
