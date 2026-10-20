# Extraction patterns

Choose the smallest unification that removes the duplicated knowledge. Each
pattern lists when it fits, the steps, and how to verify it.

## Extract function

Fits: two or more copies of the same computation in one package or layer.

1. Pin each copy with a test at its current call site.
2. Move one copy into a function named after the knowledge ("round_to_cents"),
   not after the callers.
3. Replace the other copies with calls; delete them.
4. Place the function at the lowest module both callers already depend on.
   If none exists, the copies may belong to different contexts; revisit
   [judging clones](judging-clones.md).

Verify: call-site tests pass unchanged; the function has its own focused tests
for edge cases that were scattered across callers.

## Parameterize

Fits: copies differ only in literal values or a small, closed set of options.

1. Identify the varying values; if they are behaviors rather than values, use
   a small mapping from key to function instead of a boolean flag.
2. Make the values explicit parameters with no defaults that hide behavior.
3. In tests, replace parallel test functions with one parameterized test whose
   table lists each former case.

Verify: the test table reads as a specification; each row names the scenario.

## Generate from a single source

Fits: mirrors of a contract across a boundary (API models, client validation,
database models, event payloads).

1. Choose the authoritative source: the API specification, the schema, the
   migration or the event definition.
2. Generate the mirrors in the build, or verify them against the source with
   a contract test if generation is not available.
3. Exclude generated output from duplication scans.

Verify: changing the source and regenerating updates every mirror; a contract
test fails when a hand-edited mirror drifts.

## Shared fixture or builder

Fits: repeated test setup that obscures what each test checks.

1. Extract a builder with sensible defaults and explicit overrides for the
   fields each test cares about.
2. Keep assertions and the meaningful inputs in each test body.

Verify: each test still reads on its own; a reader sees the inputs that matter
without opening the builder.

## Template or module for configuration

Fits: repeated infrastructure or pipeline definitions per environment or
service.

1. Use the tool's own reuse mechanism (modules, templates, reusable workflows)
   instead of external text generation.
2. Pass environment differences as explicit parameters; never hide them in
   conditionals inside the shared definition.

Verify: a plan or preview for each environment shows no unintended change.

## Suppress with a reason

Fits: intentional duplication that a detector will keep reporting (migrations,
mirrored lookup tables compared by a test, standalone documentation pages).

1. Prefer path-level `ignore` entries for whole categories.
2. Use `jscpd:ignore-start` / `jscpd:ignore-end` comments only for a specific
   region, with a reason in the comment.

Verify: the suppression appears in the evidence worksheet with an owner.

## Anti-patterns

- **Flag arguments** that switch between the original copies' behaviors.
- **Utility dumping grounds** (`utils.py`, `common/`) that every package imports,
  creating a hub in the dependency graph.
- **Cross-team shared code** without versioning, turning local changes into
  coordinated releases.
- **Extraction before tests**, which turns a refactor into a behavior change.

## Evidence

Record the pattern used, the before and after clone counts from identical
scans, and the tests that pin behavior, in the
[evidence worksheet](../assets/templates/duplication-evidence-template.md).

## Sources

- [pytest parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [pytest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [Terraform modules](https://developer.hashicorp.com/terraform/language/modules)
- [GitHub Actions reusable workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows)
- [jscpd repository and documentation](https://github.com/kucherenko/jscpd)
