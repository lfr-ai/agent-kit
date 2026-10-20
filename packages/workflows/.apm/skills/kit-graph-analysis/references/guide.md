# Graph analysis guide

Quality gates, blind spots, failure modes and recovery for read-only code graph
work. Use with [tooling](tooling.md) for exact queries.

## Quality gates

| Gate | Pass condition |
| --- | --- |
| Reproducible | Every result has the exact command, revision and tool version |
| Read-only | No index, cache or configuration was rebuilt or edited for the review |
| Verified | Key edges confirmed by reading the importing line |
| Complete | Blind spots below checked or explicitly listed as unverified |
| Actionable | Impacted modules map to tests to run and owners to notify |

## Blind spots of static graphs

Static import and call graphs miss edges created at runtime. Check each that
applies to the stack:

- **Dynamic imports**: `importlib.import_module`, `__import__`, `import()` in
  JavaScript, string-based module paths in configuration.
- **Plugins and entry points**: package metadata entry points, framework
  plugin registries, command discovery.
- **Reflection and attribute access**: `getattr` with computed names,
  decorators that register handlers, metaclass hooks.
- **Framework conventions**: URL routing tables, dependency-injection
  containers, ORM model discovery, template lookups by name, test discovery.
- **Serialized contracts**: JSON field names, message topics, event types,
  database columns, environment variable names. A rename that compiles can
  still break a consumer that only shares a string.
- **Other repositories and deployments**: published packages, API clients,
  scheduled jobs, infrastructure templates and dashboards that reference
  names.
- **Conditional imports**: `if TYPE_CHECKING:` blocks (types only) and
  platform or optional-dependency guards. Decide whether they count for your
  question; `--skip-type-checking` removes the first kind.
- **Function-local imports**: executed only when the function runs. They
  matter for impact, but not for import-time cycles; compare runs with and
  without `--module-level-only`.

## Failure modes

- **Stale index.** A maintained graph index lags behind the working tree.
  Detect by comparing its revision with the checkout; fall back to building
  a fresh local graph or text search.
- **Partial scope.** The graph covers one package but consumers live in
  another. Detect by searching the whole repository (and dependents) for the
  top-level package name.
- **Name collisions.** Text search hits unrelated symbols with the same name.
  Narrow by import path, word boundaries and file type; confirm by reading.
- **Over-trusting depth.** Transitive results at depth five or more are mostly
  noise for change review. Report depth 1 and 2 in detail; summarize beyond.
- **Cycles hiding direction.** Inside a strongly connected component every
  module reaches every other; reason about the cycle as one unit and consider
  breaking it before the change.

## Negative cases

- An empty reverse query on a module that is loaded by a plugin registry: the
  graph is right about imports and wrong about usage.
- A refactor approved because no Python module imports a function that an
  HTTP route table references by dotted string.
- A cycle reported only under type checking: real for type checkers, harmless
  at runtime; record it rather than restructuring code for it.

## Recovery

1. If a missed edge caused a break, add the blind-spot category to the
   project's review checklist and a test that exercises the dynamic path.
2. If an index is stale, record its revision in the report and redo the
   critical queries with a fresh local build.
3. If results are too large to review, restrict to depth 1, group by package,
   and list the owners for each group.

## Prerequisites

- Read access to the repository at a known revision.
- Python 3.11 or newer for the stdlib tool; optional third-party tools per
  [tooling](tooling.md).

## Assets

- [Import graph tool](../assets/import_graph.py)
- [Impact report template](../assets/impact-report.md.template)
- [Import-linter contract template](../assets/importlinter.ini.template)
- [Stage worksheet](../assets/templates/graph-stages-template.md)

## Sources

- [Python ast module](https://docs.python.org/3/library/ast.html)
- [Python import system](https://docs.python.org/3/reference/import.html)
- [Python importlib](https://docs.python.org/3/library/importlib.html)
- [typing.TYPE_CHECKING](https://docs.python.org/3/library/typing.html#typing.TYPE_CHECKING)
