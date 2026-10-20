# Tooling

Pick the lightest tool that answers the question. Confirm installed versions
and flags with each tool's own help before running; options change between
releases.

## Matrix

| Need | Python | JavaScript and TypeScript | Any language |
| --- | --- | --- | --- |
| Module import graph | `import_graph.py`, grimp, pydeps | dependency-cruiser, madge | text search over import lines |
| Enforce architecture rules | import-linter | dependency-cruiser rules | CI check on search results |
| Symbol references | editor references, Pyright or Jedi via the editor | TypeScript language service via the editor | ripgrep with word boundaries |
| Call hierarchy | editor call hierarchy | editor call hierarchy | ripgrep, then read |
| Change coupling over time | git history | git history | git history |

## Stdlib import graph

[import_graph.py](../assets/import_graph.py) works on any Python package
directory without installing anything:

```text
python assets/import_graph.py src/shop                         # cycles, exit 1 if any
python assets/import_graph.py src/shop --module-level-only     # import-time cycles only
python assets/import_graph.py src/shop --reverse shop.orders --depth 2
python assets/import_graph.py src/shop --forward shop.api.views
python assets/import_graph.py src/shop --chain shop.api.views shop.storage.db
python assets/import_graph.py src/shop --json > graph.json
python assets/import_graph.py src/shop --dot > graph.dot
```

Resolution rules: relative imports are resolved against the importing module's
package; `from x import y` becomes an edge to `x.y` when `x.y` is a module,
otherwise to `x`; `import a.b.c` becomes an edge to the deepest existing
module. External packages are ignored unless `--include-external` is given.
Namespace packages without `__init__.py` work when you pass the directory of
the portion.

## grimp

A library that builds the same kind of graph through the real import system
and answers queries in Python code:

```python
import grimp

graph = grimp.build_graph("shop", exclude_type_checking_imports=True)
graph.find_upstream_modules("shop.orders")  # modules shop.orders depends on
graph.find_downstream_modules("shop.orders")  # modules that depend on it
graph.find_shortest_chain(importer="shop.api.views", imported="shop.storage.db")
```

It requires the package to be importable (installed or on the path) and caches
results in a local directory by default; disable caching in review scripts so
nothing is written.

## import-linter

Turns graph conclusions into checked contracts. Configure in `.importlinter`,
`setup.cfg` or `pyproject.toml`, then run `lint-imports`. Contract types
include `layers`, `forbidden`, `independence`, `protected` and acyclic
sibling checks. Start from [the contract template](../assets/importlinter.ini.template)
and add `ignore_imports` entries only with a reason and an owner.

## pydeps

Renders module dependency diagrams with Graphviz, useful for explaining a
blast radius to reviewers. Limit depth and cluster external packages so the
picture stays readable; diagrams are evidence for people, not gates.

## JavaScript and TypeScript

- dependency-cruiser validates and visualizes module dependencies with rules
  such as "no circular", "no orphans" and forbidden paths.
- madge lists circular dependencies and produces graphs for CommonJS and ES
  modules.

Both need the project's module resolution settings (TypeScript paths, bundler
aliases) to avoid false "missing" edges.

## ripgrep patterns

Fast, read-only, and the best cross-check for string references:

```text
rg -n -w "calculate_total" --type py
rg -n "from shop\.orders(\.| import)|import shop\.orders" --type py
rg -n "\"calculateTotal\"|'calculateTotal'" -g "*.{ts,tsx,js,json,yml,yaml}"
rg -n -F "shop.orders.pricing" -g "!**/tests/**"
rg -l -w "OrderCreated" | sort
```

`-w` adds word boundaries, `-F` searches a fixed string, `-g` filters paths,
`--type` filters languages, and `-l` lists files only. Search configuration
and infrastructure files explicitly; they are often outside default types.

## Change coupling from history

Files that change together often depend on each other even without an import:

```text
git log --format=format: --name-only --since=6.months -- src/shop/orders | sort | uniq -c | sort -rn
```

Use it to find hidden consumers (fixtures, templates, configuration) that a
static graph misses.

## Sources

- [grimp usage](https://grimp.readthedocs.io/en/stable/usage.html)
- [import-linter documentation](https://import-linter.readthedocs.io/en/stable/)
- [import-linter layers contract](https://import-linter.readthedocs.io/en/stable/contract_types/layers/)
- [pydeps documentation](https://pydeps.readthedocs.io/en/latest/)
- [dependency-cruiser](https://github.com/sverweij/dependency-cruiser)
- [madge](https://github.com/pahen/madge)
- [ripgrep user guide](https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md)
- [git log documentation](https://git-scm.com/docs/git-log)
