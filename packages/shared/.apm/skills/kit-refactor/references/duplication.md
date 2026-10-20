# DRY versus incidental duplication

"Don't repeat yourself" is about **knowledge**, not text. Every piece of
knowledge (a business rule, a format, a limit, a mapping) should have one
authoritative representation. Two fragments that look alike but encode
different knowledge are incidental duplication, and merging them couples
things that change for different reasons.

## Tell the two apart

Ask these questions about two similar fragments:

| Question | Same knowledge | Incidental |
| --- | --- | --- |
| If the rule changes, must both change together? | yes | no |
| Do they have the same reason to change (same owner, same requirement)? | yes | no |
| Would a bug in one also be a bug in the other? | yes | no |
| Could you name the shared function after a domain concept? | yes ("invoice_due_date") | only after its mechanics ("add_days_and_round") |
| Do callers belong to the same bounded context? | usually | often not |

Examples:

- Two services each validate that an order total is non-negative, because the
  pricing rule says so. **Same knowledge**: extract one rule and call it from
  both, or let one service own the rule.
- An invoice export and a user export both build CSV rows with a header line.
  **Incidental**: the formats evolve independently; a shared helper for "write
  CSV with header" is fine, but a shared "row builder" that knows both schemas
  is not.
- A test fixture repeats the setup of another test. Duplication in tests is
  cheaper than abstraction that hides what a test does; extract only setup that
  is genuinely the same precondition.

## When to extract

- **Rule of three**: tolerate a second copy; extract on the third, when the
  shape of the real abstraction is visible. Extracting from two examples often
  produces the wrong parameters.
- Extract immediately when the duplicated thing is a constant, limit, format
  string, regular expression or schema that must stay identical by definition.
- Extract when a defect has already been fixed in one copy and missed in the
  other. That is evidence the knowledge is shared.

## How to extract safely

1. Characterize both call sites with tests that pin their current behavior
   (see [characterization tests](characterization-tests.md)).
2. Extract from one site using [extract function](catalog.md#extract-function).
3. Point the second site at it. If the second site needs a flag or extra
   parameter to keep its behavior, stop: the fragments differ, and a boolean
   parameter that switches behavior is a sign of incidental duplication.
4. Name the result after the domain concept and place it with the owner of
   that concept, not in a generic `utils` module.

## Undo a wrong abstraction

A shared function that has grown flags, special cases and callers that use
half of it is cheaper to duplicate back than to keep extending:

1. Inline the shared function into each caller.
2. Delete from each copy the branches that caller never takes.
3. Re-extract only what is still genuinely common.

## Duplication across layers and files

- **Configuration and code**: a limit in a configuration file and the same
  literal in code are duplicated knowledge; read the configuration.
- **Schema and validation**: derive validation from the schema (or the reverse)
  instead of maintaining two definitions.
- **Documentation and code**: link to the source of truth (a generated
  reference, the configuration file) instead of restating values.
- **Generated code**: duplication in generated output is not a defect; fix the
  generator input.

## Measuring duplication

Copy-paste detectors (token-based clone detection) find candidates, not
defects. Triage each reported clone with the questions above, and set a
threshold that ignores short or test-only clones. A rising clone count in
production code over time is a more useful signal than any single report.

## Sources

- [The Pragmatic Programmer, DRY principle (publisher page)](https://pragprog.com/titles/tpp20/the-pragmatic-programmer-20th-anniversary-edition/)
- [Martin Fowler: Rule of three in Refactoring](https://refactoring.com/)
- [Sandi Metz: The Wrong Abstraction](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)
- [Martin Fowler: Bounded Context](https://martinfowler.com/bliki/BoundedContext.html)
