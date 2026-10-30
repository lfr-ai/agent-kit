# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Build a static import graph for one Python package and query it.

The tool parses source files with ``ast`` and never imports or executes them.
Default mode reports import cycles as ``path:line: import cycle: a -> b -> a``
and exits 1 when any exist. Query modes list reverse dependencies (who
imports a module, transitively), forward dependencies, or the shortest import
chain between two modules, and can export the graph as JSON or Graphviz DOT.
"""

import argparse
import ast
from collections import deque
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

_EXCLUDED = frozenset({"__pycache__", ".venv", "venv", "node_modules", "build"})
_EXIT_USAGE = 2
_JSON_INDENT = 2
_CHAIN_ENDPOINTS = ("FROM", "TO")


@dataclass(frozen=True, kw_only=True, slots=True)
class Graph:
    """Directed import graph between modules of one package.

    Args:
        root: Top-level package name.
        files: Module name to source file for internal modules.
        edges: Importer to imported module to first importing line.
    """

    root: str
    files: dict[str, Path]
    edges: dict[str, dict[str, int]]

    def location(self, source: str, target: str) -> str:
        """Return ``path:line`` of the first import from source to target."""
        line = self.edges.get(source, {}).get(target, 1)
        path = self.files.get(source)
        return f"{path.as_posix() if path else source}:{line}"

    def reverse(self) -> dict[str, set[str]]:
        """Return imported module to the set of its direct importers."""
        result: dict[str, set[str]] = {name: set() for name in self.files}
        for source, targets in self.edges.items():
            for target in targets:
                result.setdefault(target, set()).add(source)
        return result


@dataclass(kw_only=True, slots=True)
class _Collector:
    """Accumulate resolved imports for one module."""

    module: str
    is_package: bool
    known: frozenset[str]
    root: str
    include_external: bool
    found: dict[str, int] = field(default_factory=dict)

    def add(self, name: str, line: int) -> None:
        """Record the longest known prefix of ``name``, or its external root."""
        parts = name.split(".")
        for size in range(len(parts), 0, -1):
            candidate = ".".join(parts[:size])
            if candidate in self.known:
                if candidate != self.module:
                    self.found.setdefault(candidate, line)
                return
        if self.include_external and parts[0] != self.root:
            self.found.setdefault(parts[0], line)

    def base(self, level: int) -> str:
        """Resolve the package that a relative import of ``level`` refers to."""
        parts = self.module.split(".")
        if not self.is_package:
            parts = parts[:-1]
        if level > 1:
            parts = parts[: len(parts) - (level - 1)]
        return ".".join(parts)

    def visit(self, node: ast.Import | ast.ImportFrom) -> None:
        """Resolve one import statement into graph edges."""
        if isinstance(node, ast.Import):
            for alias in node.names:
                self.add(alias.name, node.lineno)
            return
        if node.level:
            base = self.base(node.level)
            prefix = ".".join(part for part in (base, node.module or "") if part)
        else:
            prefix = node.module or ""
        for alias in node.names:
            if alias.name != "*" and f"{prefix}.{alias.name}" in self.known:
                self.add(f"{prefix}.{alias.name}", node.lineno)
            else:
                self.add(prefix, node.lineno)


def _is_type_checking(test: ast.expr) -> bool:
    """Return whether an ``if`` test is ``TYPE_CHECKING`` or ``x.TYPE_CHECKING``."""
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _imports(
    body: list[ast.stmt], *, skip_type_checking: bool, module_level_only: bool
) -> list[ast.Import | ast.ImportFrom]:
    """Collect import statements, honoring the type-checking and scope filters."""
    found: list[ast.Import | ast.ImportFrom] = []
    pending: list[ast.AST] = list(reversed(body))
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.append(node)
            continue
        if module_level_only and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ):
            continue
        if (
            isinstance(node, ast.If)
            and skip_type_checking
            and _is_type_checking(node.test)
        ):
            pending.extend(reversed(node.orelse))
            continue
        pending.extend(reversed(list(ast.iter_child_nodes(node))))
    return found


def _module_name(package_dir: Path, path: Path) -> tuple[str, bool]:
    """Map a source file to its dotted module name and package flag."""
    relative = path.relative_to(package_dir.parent).with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


class GraphInputError(ValueError):
    """An input violates the graph input contract."""

    def __init__(self, *, package_dir: Path) -> None:
        """Describe the violated invariant.

        Args:
            package_dir: Diagnostic package dir for the failing input.
        """
        super().__init__(f"no Python modules under {package_dir}")


def build_graph(
    package_dir: Path,
    *,
    skip_type_checking: bool = False,
    module_level_only: bool = False,
    include_external: bool = False,
) -> Graph:
    """Parse every module under ``package_dir`` and resolve its imports.

    Args:
        package_dir: Directory of the top-level package to analyze.
        skip_type_checking: Ignore imports under ``if TYPE_CHECKING:``.
        module_level_only: Ignore imports inside functions and lambdas.
        include_external: Add top-level external packages as nodes.

    Returns:
        The import graph.

    Raises:
        GraphInputError: The directory holds no Python modules.
        SyntaxError: A module cannot be parsed.
        OSError: A module cannot be read.
    """
    sources = sorted(
        path
        for path in package_dir.rglob("*.py")
        if not _EXCLUDED.intersection(path.relative_to(package_dir).parts)
    )
    if not sources:
        raise GraphInputError(package_dir=package_dir)
    names = {path: _module_name(package_dir, path) for path in sources}
    files = {name: path for path, (name, _) in names.items()}
    known = frozenset(files)
    edges: dict[str, dict[str, int]] = {}
    for path, (name, is_package) in names.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        collector = _Collector(
            module=name,
            is_package=is_package,
            known=known,
            root=package_dir.name,
            include_external=include_external,
        )
        for node in _imports(
            tree.body,
            skip_type_checking=skip_type_checking,
            module_level_only=module_level_only,
        ):
            collector.visit(node)
        edges[name] = dict(sorted(collector.found.items()))
    return Graph(root=package_dir.name, files=files, edges=edges)


class _Tarjan:
    """Iterative Tarjan strongly connected component search state."""

    def __init__(self, edges: dict[str, dict[str, int]]) -> None:
        """Prepare empty traversal state.

        Args:
            edges: Forward import edges keyed by module.
        """
        self._edges = edges
        self.index: dict[str, int] = {}
        self._low: dict[str, int] = {}
        self._stack: list[str] = []
        self._on_stack: set[str] = set()
        self.components: list[list[str]] = []

    def _enter(self, node: str) -> list[str]:
        """Number ``node``, push it, and return its sorted children."""
        self.index[node] = self._low[node] = len(self.index)
        self._stack.append(node)
        self._on_stack.add(node)
        return sorted(self._edges.get(node, {}))

    def _step(self, node: str, child: str, work: list[tuple[str, list[str]]]) -> None:
        """Descend into an unvisited child or record a back edge."""
        if child not in self.index:
            work.append((child, self._enter(child)))
        elif child in self._on_stack:
            self._low[node] = min(self._low[node], self.index[child])

    def _close(self, node: str) -> None:
        """Pop the component rooted at ``node`` when it is a root."""
        if self._low[node] != self.index[node]:
            return
        component: list[str] = []
        while True:
            member = self._stack.pop()
            self._on_stack.discard(member)
            component.append(member)
            if member == node:
                break
        if len(component) > 1:
            self.components.append(sorted(component))

    def run(self, start: str) -> None:
        """Visit every module reachable from ``start``."""
        work: list[tuple[str, list[str]]] = [(start, self._enter(start))]
        while work:
            node, children = work[-1]
            if children:
                self._step(node, children.pop(0), work)
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                self._low[parent] = min(self._low[parent], self._low[node])
            self._close(node)


def strongly_connected(graph: Graph) -> list[list[str]]:
    """Return strongly connected components with more than one module.

    Args:
        graph: Import graph.

    Returns:
        Sorted components, each sorted by module name.
    """
    search = _Tarjan(graph.edges)
    for start in sorted(graph.edges):
        if start not in search.index:
            search.run(start)
    return sorted(search.components)


def shortest_path(
    graph: Graph, source: str, target: str, allowed: set[str] | None = None
) -> list[str] | None:
    """Return the shortest import chain from source to target, if any.

    Args:
        graph: Import graph.
        source: Starting module.
        target: Destination module; may equal ``source`` to find a cycle.
        allowed: Optional set of modules the chain may pass through.

    Returns:
        Module names from source to target inclusive, or None.
    """
    queue: deque[list[str]] = deque([[source]])
    seen: set[str] = set()
    while queue:
        path = queue.popleft()
        for child in sorted(graph.edges.get(path[-1], {})):
            if allowed is not None and child not in allowed:
                continue
            if child == target:
                return [*path, child]
            if child not in seen:
                seen.add(child)
                queue.append([*path, child])
    return None


def cycle_findings(graph: Graph) -> list[str]:
    """Describe one shortest cycle per strongly connected component.

    Args:
        graph: Import graph.

    Returns:
        Deterministic ``path:line: import cycle: ...`` findings.
    """
    findings: list[str] = []
    for component in strongly_connected(graph):
        start = component[0]
        cycle = shortest_path(graph, start, start, set(component)) or [start]
        chain = " -> ".join(cycle)
        location = graph.location(cycle[0], cycle[1]) if len(cycle) > 1 else start
        size = len(component)
        findings.append(f"{location}: import cycle: {chain} ({size} modules in SCC)")
    return findings


def reachable(
    adjacency: dict[str, set[str]] | dict[str, dict[str, int]],
    start: str,
    depth: int | None,
) -> list[tuple[int, str, str]]:
    """Breadth-first walk returning (depth, module, predecessor) tuples.

    Args:
        adjacency: Forward edges or reverse edges.
        start: Module to start from.
        depth: Maximum depth, or None for unlimited.

    Returns:
        Reached modules ordered by depth then name.
    """
    seen = {start}
    frontier = [start]
    result: list[tuple[int, str, str]] = []
    level = 0
    while frontier and (depth is None or level < depth):
        level += 1
        following: list[str] = []
        for node in frontier:
            for child in sorted(adjacency.get(node, ())):
                if child not in seen:
                    seen.add(child)
                    following.append(child)
                    result.append((level, child, node))
        frontier = sorted(following)
    return sorted(result)


def to_dot(graph: Graph) -> str:
    """Render the graph in Graphviz DOT syntax."""
    lines = [f'digraph "{graph.root}" {{', "  rankdir=LR;"]
    lines.extend(f'  "{name}";' for name in sorted(graph.files))
    lines.extend(
        f'  "{source}" -> "{target}";'
        for source in sorted(graph.edges)
        for target in sorted(graph.edges[source])
    )
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_json(graph: Graph) -> str:
    """Render modules and edges as stable JSON."""
    payload = {
        "root": graph.root,
        "modules": {name: graph.files[name].as_posix() for name in sorted(graph.files)},
        "edges": [
            {"from": source, "to": target, "line": line}
            for source in sorted(graph.edges)
            for target, line in sorted(graph.edges[source].items())
        ],
    }
    return json.dumps(payload, indent=_JSON_INDENT, sort_keys=True) + "\n"


def _write_package(root: Path, files: dict[str, str]) -> Path:
    """Create a synthetic package for the self-test."""
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root / "shop"


class ChainQueryRegressionError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(self) -> None:
        """Describe the violated invariant."""
        super().__init__("chain query failed")


def self_test() -> None:
    """Exercise resolution, cycles, filters and queries on a synthetic package.

    Raises:
        AssertionError: Behavior differs from the documented contract.
    """
    with TemporaryDirectory(prefix="import-graph-") as raw:
        package = _write_package(
            Path(raw),
            {
                "shop/__init__.py": "",
                "shop/orders.py": "from . import billing\nimport json\n",
                "shop/billing.py": "from shop.orders import Order\n",
                "shop/api/__init__.py": "from ..orders import create\n",
                "shop/api/views.py": (
                    "from typing import TYPE_CHECKING\n"
                    "if TYPE_CHECKING:\n    from shop import billing\n"
                    "def run():\n    from . import helpers\n"
                ),
                "shop/api/helpers.py": "",
            },
        )
        _check_graph(package)


def _check_graph(package: Path) -> None:
    """Verify edges, cycles, filters and queries for the synthetic package."""
    graph = build_graph(package)
    _check_edges(graph)
    _check_queries(package, graph)


def _check_edges(graph: Graph) -> None:
    """Verify resolved edges and the reported cycle.

    Raises:
        AssertionError: An edge or the cycle is wrong.
    """
    if graph.edges["shop.api"] != {"shop.orders": 1}:
        raise AssertionError(graph.edges["shop.api"])
    if set(graph.edges["shop.api.views"]) != {"shop.billing", "shop.api.helpers"}:
        raise AssertionError(graph.edges["shop.api.views"])
    findings = cycle_findings(graph)
    if (
        len(findings) != 1
        or "shop.billing -> shop.orders -> shop.billing" not in (findings[0])
    ):
        raise AssertionError(findings)


def _check_queries(package: Path, graph: Graph) -> None:
    """Verify import filters, reverse reachability and chain queries.

    Raises:
        AssertionError: A filter or reverse query is wrong.
        ChainQueryRegressionError: A chain query is wrong.
    """
    filtered = build_graph(package, skip_type_checking=True, module_level_only=True)
    if filtered.edges["shop.api.views"]:
        raise AssertionError(filtered.edges["shop.api.views"])
    importers = [name for _, name, _ in reachable(graph.reverse(), "shop.orders", None)]
    if importers != ["shop.api", "shop.billing", "shop.api.views"]:
        raise AssertionError(importers)
    if shortest_path(graph, "shop.api.views", "shop.orders") != [
        "shop.api.views",
        "shop.billing",
        "shop.orders",
    ]:
        raise ChainQueryRegressionError


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("package", nargs="?", type=Path, help="package directory")
    query = parser.add_mutually_exclusive_group()
    query.add_argument("--reverse", metavar="MODULE", help="who imports MODULE")
    query.add_argument("--forward", metavar="MODULE", help="what MODULE imports")
    query.add_argument("--chain", nargs=len(_CHAIN_ENDPOINTS), metavar=_CHAIN_ENDPOINTS)
    query.add_argument("--dot", action="store_true", help="print Graphviz DOT")
    query.add_argument("--json", action="store_true", help="print JSON graph")
    parser.add_argument("--depth", type=int, default=None)
    parser.add_argument("--skip-type-checking", action="store_true")
    parser.add_argument("--module-level-only", action="store_true")
    parser.add_argument("--include-external", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def _query(graph: Graph, args: argparse.Namespace) -> int:
    """Run a reverse, forward or chain query and print the result."""
    modules = [args.reverse or args.forward] if not args.chain else list(args.chain)
    unknown = [name for name in modules if name not in graph.files]
    if unknown:
        sys.stderr.write(f"unknown module: {unknown[0]}\n")
        return _EXIT_USAGE
    if args.chain:
        chain = shortest_path(graph, args.chain[0], args.chain[1])
        sys.stdout.write(f"{' -> '.join(chain) if chain else 'no import chain'}\n")
        return 0
    if args.reverse:
        for level, name, via in reachable(graph.reverse(), args.reverse, args.depth):
            sys.stdout.write(
                f"{graph.location(name, via)}: {name} -> {via} (depth {level})\n"
            )
        return 0
    for level, name, via in reachable(graph.edges, args.forward, args.depth):
        sys.stdout.write(
            f"{graph.location(via, name)}: {via} -> {name} (depth {level})\n"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Build the graph and run the selected mode.

    Args:
        argv: Command-line arguments; ``sys.argv`` when omitted.

    Returns:
        0 on success, 1 when cycles are found, 2 on unusable input.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        sys.stdout.write("import_graph self-test passed.\n")
        return 0
    if args.package is None or not args.package.is_dir():
        sys.stderr.write("a package directory is required\n")
        return _EXIT_USAGE
    try:
        graph = build_graph(
            args.package,
            skip_type_checking=args.skip_type_checking,
            module_level_only=args.module_level_only,
            include_external=args.include_external,
        )
    except (OSError, UnicodeError, SyntaxError, ValueError) as error:
        sys.stderr.write(f"cannot build graph: {error}\n")
        return _EXIT_USAGE
    return _report(graph, args)


def _report(graph: Graph, args: argparse.Namespace) -> int:
    """Print the selected rendering, query result, or cycle findings."""
    if args.dot or args.json:
        sys.stdout.write(to_dot(graph) if args.dot else to_json(graph))
        return 0
    if args.reverse or args.forward or args.chain:
        return _query(graph, args)
    findings = cycle_findings(graph)
    for finding in findings:
        sys.stdout.write(f"{finding}\n")
    count = sum(len(targets) for targets in graph.edges.values())
    sys.stdout.write(
        f"{len(graph.files)} modules, {count} imports, {len(findings)} cycle(s).\n"
    )
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
