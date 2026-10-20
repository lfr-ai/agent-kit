# Refactoring catalog: safe mechanical steps

Each entry is a small, behavior-preserving transformation with a fixed order
of steps. Run the focused tests after every numbered step that leaves the code
compiling; if a step fails, undo that step rather than debugging forward.
Automated IDE refactorings (rename, extract, move) are usually safer than hand
edits, but still re-run tests: dynamic access, reflection, string references
and configuration are invisible to them.

Names follow common usage; the steps are written for this kit.

## Rename (variable, function, class, module)

1. Find every reference, including strings: serialization keys, logging
   fields, configuration, templates, reflection (`getattr`), plugin entry
   points, documentation and tests.
2. Decide whether the name is **published** (imported by other packages, used
   in stored data or an API). If published, use the migration form below.
3. Private name: rename with the editor's rename refactoring, then search for
   the old name as text to catch the rest.
4. Published name, migration form:
   - Add the new name and make the old name a thin alias that delegates.
   - Move internal callers to the new name.
   - Mark the alias deprecated (a warning, a changelog entry) for at least one
     release.
   - Remove the alias in a later, separately announced change.

## Extract function

1. Pick a fragment with one purpose. Name it after **what** it does, not how.
2. List the variables the fragment reads (become parameters) and writes
   (become return values). More than one written variable often means two
   functions.
3. Create the function, copy the fragment in, add parameters and return.
4. Replace the fragment with a call. Run tests.
5. Look for other copies of the same fragment and replace them only if they
   represent the same knowledge (see [duplication](duplication.md)).

## Inline function

Use when a function's body is as clear as its name, or before re-extracting a
better boundary.

1. Check it is not polymorphic (overridden) and not part of a public API.
2. Replace each call with the body, substituting arguments.
3. Run tests after each call site, then delete the function.

## Extract variable / inline variable

Give a complex expression a name, or remove a name that adds nothing. Keep
evaluation order and the number of evaluations unchanged; an expression with
side effects (I/O, clock, random) must not move or repeat.

## Change function signature (add, remove, reorder parameters)

1. If callers are few and all in this repository, change them in the same step.
2. Otherwise use parallel change:
   - Create a new function with the new signature that holds the logic.
   - Make the old function delegate to it.
   - Migrate callers one by one, running tests.
   - Delete the old function when no caller remains.
3. Prefer keyword-only parameters for new optional arguments so later
   reordering does not break positional callers.

## Introduce parameter object

When several parameters always travel together (`start`, `end`, `timezone`),
create an immutable value type, pass it alongside the old parameters, migrate
callers, then remove the old parameters. Validation that was repeated at each
call site moves into the value type's constructor.

## Move function / move module

1. Copy the function to its new home and adapt its imports.
2. Make the old location delegate to (or re-export) the new one.
3. Move callers, including tests, to import from the new location.
4. Search for string references: entry points, package data, dotted paths in
   configuration and patch targets in tests (`mock.patch("pkg.old.name")`).
5. Remove the old location. Install the package outside the source tree and
   import the new path to prove packaging still includes it.

## Split phase

When one function both parses input and computes on it, split it into
`parse(raw) -> Intermediate` and `compute(intermediate) -> Result`.

1. Extract the second half into a function that takes the values the first half
   produced.
2. Introduce an intermediate data structure holding those values.
3. Move the first half into its own function returning that structure.
The intermediate structure becomes a natural seam for tests.

## Replace conditional with polymorphism or a table

Use when the same `if/elif` or `match` on a type code appears in several
places.

1. Characterize each branch with a test.
2. Create one class or one table entry per branch, behind a common interface.
3. Move one branch at a time, running tests after each.
4. Replace each conditional with dispatch once all branches moved.
Do not do this for a single conditional in one place; a `match` is clearer.

## Replace magic literal with named constant

Name the meaning, not the value (`MAX_LINE_ITEMS`, not `FIFTY`). Only unify two
equal literals if they mean the same thing.

## Encapsulate variable or collection

Replace direct access to shared mutable state with functions that read and
update it; return copies or immutable views of collections. This creates the
choke point that later refactorings and thread-safety fixes need.

## Slide statements and split loop

Move related statements together, then split a loop that does two things into
two loops. Check that statements you slide past have no side effects or shared
state you would reorder. Performance concerns come after clarity and need a
measurement, not an assumption.

## Remove dead code

1. Prove it is dead: no static references, no string or reflective references,
   no entry point, no external consumer, no feature flag that enables it.
2. Check coverage data from the full test suite and, where available,
   production telemetry or logs.
3. Delete it in its own commit so it is easy to restore.
Commented-out code is dead code; version control remembers it.

## Safety checklist for every step

- One transformation per commit or checkpoint, with a message naming it.
- Tests ran green before the first step and after the last one.
- Behavior at boundaries unchanged: defaults, error types and messages,
  ordering, side-effect count and timing, serialization formats.
- No new dependency, public name, or configuration key unless the refactoring
  goal requires it.
- The [behavior ledger](../assets/behavior.md.template) records anything
  observable that changed intentionally.

## Sources

- [Martin Fowler: Refactoring catalog](https://refactoring.com/catalog/)
- [Martin Fowler: Parallel Change](https://martinfowler.com/bliki/ParallelChange.html)
- [VS Code: refactoring](https://code.visualstudio.com/docs/editing/refactoring)
- [Python warnings: DeprecationWarning](https://docs.python.org/3/library/warnings.html)
- [Python packaging: entry points](https://packaging.python.org/en/latest/specifications/entry-points/)
