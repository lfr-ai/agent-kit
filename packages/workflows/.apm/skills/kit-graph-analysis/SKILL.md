---
name: kit-graph-analysis
description: Use when leveraging code-graph tools to inspect dependencies, change impact, and repository ownership without mutating indices.
license: MIT
---

# Analyze code graphs for impact, debugging and refactoring

A code graph answers "what depends on this?" and "how does control or data get
from here to there?" faster and more completely than reading files one by one.
It never proves runtime behavior on its own: dynamic dispatch, reflection,
configuration-driven wiring and generated code hide edges. Treat graph output
as a map to verify, not as the territory.

## Choose the question first

| Question | Use | Reference |
| --- | --- | --- |
| What breaks if I change this symbol or module? | Reverse dependencies and tests in reach | [impact analysis](references/impact-analysis.md) |
| How does this failing path reach the faulty code? | Forward chain from entry point to symptom | [call-chain debugging](references/call-chain-debugging.md) |
| Can I move, split, rename or delete this safely? | Blast radius plus enforced contracts | [refactoring blast radius](references/refactoring-blast-radius.md) |
| Which tool answers it in this stack? | Tool matrix and exact queries | [tooling](references/tooling.md) |

## Procedure

1. **State the target and the question.** Name the module, symbol or endpoint
   exactly and pick one question from the table. Write the expected answer
   before querying; surprises are the valuable part.
2. **Pick read-only tooling.** Prefer what the project already has: an
   import-linter configuration, an editor's references and call hierarchy, a
   graph index the team maintains. Otherwise use the stdlib
   [import graph tool](assets/import_graph.py) for Python packages and plain
   text search for everything else. Never rebuild or mutate a shared index as
   part of a review.
3. **Build the module graph** and check for cycles first; a cycle widens every
   blast radius to the whole cycle:

   ```text
   python assets/import_graph.py src/<package>
   python assets/import_graph.py src/<package> --skip-type-checking --module-level-only
   ```

4. **Query direct, then transitive, dependencies.** Start at depth 1 and widen
   only when depth-1 results are understood:

   ```text
   python assets/import_graph.py src/<package> --reverse <package>.orders.pricing --depth 1
   python assets/import_graph.py src/<package> --reverse <package>.orders.pricing
   python assets/import_graph.py src/<package> --chain <package>.api.views <package>.storage.db
   ```

5. **Descend to symbols.** Module edges say a file imports another; use text
   search or editor references for the specific function, class, field,
   route, event name or configuration key. Search string forms too: names in
   templates, serialized payloads, dependency-injection registrations,
   `getattr` calls, SQL and infrastructure files.
6. **Cross-check blind spots** listed in [the guide](references/guide.md):
   dynamic imports, plugins and entry points, reflection, framework
   auto-discovery, other repositories and deployed consumers.
7. **Attach tests and owners.** For each impacted module, find the tests that
   import it and the owner who reviews it (code-owners file or history).
8. **Record the evidence** in the [impact report](assets/impact-report.md.template):
   exact commands, counts per depth, verified edges, blind spots checked, tests
   to run, owners to notify. Use the
   [stage worksheet](assets/templates/graph-stages-template.md) for longer
   investigations.
9. **Lock in the result.** When the analysis motivates an architectural rule
   (layers, forbidden imports, independence), propose an
   [import-linter contract](assets/importlinter.ini.template) so the graph
   stays that way.

## Tool contract

`import_graph.py` parses files with `ast`, never imports them, and exits 1 when
cycles exist (2 on unusable input). Cycle lines read
`path:line: import cycle: a -> b -> a (N modules in SCC)`; query lines read
`path:line: importer -> imported (depth N)`. `--json` and `--dot` export the
graph; `--include-external` adds third-party top-level packages as nodes. Run
`--self-test` after editing it.

## Acceptance gates

- [ ] The question, target and expected answer were written before querying.
- [ ] Every claim of "no other callers" is backed by a reverse query and a
      text search for string references, with the commands recorded.
- [ ] Blind spots were checked explicitly or listed as unverified.
- [ ] Impacted modules map to tests that will run and owners who will review.
- [ ] No shared index or cache was rebuilt or modified during the review.
- [ ] Architectural conclusions are proposed as enforceable contracts, not
      only prose.

## Do not

- Present graph reachability as runtime reachability.
- Stop at module edges when the change is to one symbol in a large module.
- Treat an empty result from a stale index as proof of no usage.
