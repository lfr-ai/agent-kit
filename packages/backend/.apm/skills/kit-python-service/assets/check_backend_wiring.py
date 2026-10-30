# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Enforce layer import rules in a backend package without importing it.

Each rule names a source layer and the layers it must not import, using the
first segment below the package: with ``--package shop``, the module
``shop.presentation.api`` belongs to layer ``presentation``. Relative imports are
resolved before matching. Without any rule, the default is
``presentation:infrastructure`` (transports receive wired services from the
composition root and never import adapters directly).

Examples:
    check_backend_wiring.py src --package shop
    check_backend_wiring.py src --package shop --forbid presentation:infrastructure
    check_backend_wiring.py src --package shop --forbid core:application,presentation
    check_backend_wiring.py src --package shop --forbid-module core:fastapi,sqlalchemy
"""

import argparse
import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
import sys

_EXCLUDED = frozenset({".venv", "node_modules", "apm_modules", "build", "__pycache__"})
_DEFAULT_RULE = "presentation:infrastructure"
_EXIT_USAGE = 2


@dataclass(frozen=True, kw_only=True, slots=True)
class Rule:
    """One forbidden dependency.

    Attributes:
        source: Layer whose modules are checked.
        targets: Forbidden layers (below the package) or absolute module prefixes.
        absolute: Whether ``targets`` are absolute module prefixes instead of layers.
    """

    source: str
    targets: tuple[str, ...]
    absolute: bool = False


class ImportRuleError(ValueError):
    """An input violates the import rule contract."""

    def __init__(self, *, text: str) -> None:
        """Describe the violated invariant.

        Args:
            text: Diagnostic text for the failing input.
        """
        super().__init__(f"rule must look like 'source:target[,target]', got {text!r}")


def parse_rule(text: str, *, absolute: bool = False) -> Rule:
    """Parse ``SOURCE:TARGET[,TARGET...]`` into a rule.

    Args:
        text: Rule text from the command line.
        absolute: Treat targets as absolute module prefixes.

    Returns:
        The parsed rule.

    Raises:
        ImportRuleError: If the text has no source or no target.
    """
    source, separator, raw_targets = text.partition(":")
    targets = tuple(item.strip() for item in raw_targets.split(",") if item.strip())
    if not separator or not source.strip() or not targets:
        raise ImportRuleError(text=text)
    return Rule(source=source.strip(), targets=targets, absolute=absolute)


def module_name(path: Path, root: Path) -> str:
    """Return the dotted module name of ``path`` relative to the source root."""
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def check_module(
    text: str,
    *,
    path: str,
    module: str,
    is_package: bool,
    packages: frozenset[str],
    rules: Iterable[Rule],
    ignore_type_checking: bool = False,
) -> list[str]:
    """Report forbidden imports in one module.

    Args:
        text: Python source text.
        path: Display path used as the finding prefix.
        module: Dotted name of the module.
        is_package: Whether the module is a package ``__init__``.
        packages: Top-level package names whose layers are checked.
        rules: Forbidden dependencies.
        ignore_type_checking: Skip imports guarded by ``if TYPE_CHECKING:``.

    Returns:
        Findings formatted as ``path:line: message``.
    """
    source_layer = _layer(module, packages)
    if source_layer is None:
        return []
    applicable = [rule for rule in rules if rule.source == source_layer]
    if not applicable:
        return []
    tree = ast.parse(text, filename=path)
    skipped = _type_checking_nodes(tree) if ignore_type_checking else set()
    findings: list[str] = []
    for node, imported in _imports(tree, module=module, is_package=is_package):
        if id(node) in skipped:
            continue
        violated = _first_violation(imported, applicable, packages)
        if violated is not None:
            findings.append(
                f"{path}:{node.lineno}: {source_layer} module '{module}' imports "
                f"'{imported}' from forbidden {violated}"
            )
    return findings


def _first_violation(
    imported: str, rules: Iterable[Rule], packages: frozenset[str]
) -> str | None:
    violations = (_violated_target(imported, rule, packages) for rule in rules)
    return next((violated for violated in violations if violated is not None), None)


def _layer(module: str, packages: frozenset[str]) -> str | None:
    parts = module.split(".")
    if len(parts) == 1 or parts[0] not in packages:
        return None
    return parts[1]


def _type_checking_nodes(tree: ast.Module) -> set[int]:
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for statement in node.body:
                guarded.update(id(child) for child in ast.walk(statement))
    return guarded


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _imports(
    tree: ast.Module, *, module: str, is_package: bool
) -> Iterator[tuple[ast.stmt, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name
        elif isinstance(node, ast.ImportFrom):
            for imported in _from_import_names(
                node, module=module, is_package=is_package
            ):
                yield node, imported


def _from_import_names(
    node: ast.ImportFrom, *, module: str, is_package: bool
) -> list[str]:
    base = _resolve(node, module=module, is_package=is_package)
    if base is None:
        return []
    return [
        base if alias.name == "*" else f"{base}.{alias.name}" for alias in node.names
    ]


def _resolve(node: ast.ImportFrom, *, module: str, is_package: bool) -> str | None:
    if node.level == 0:
        return node.module
    anchor = module.split(".") if is_package else module.split(".")[:-1]
    if node.level - 1 > len(anchor):
        return None
    anchor = anchor[: len(anchor) - (node.level - 1)]
    return ".".join([*anchor, *([node.module] if node.module else [])])


def _violated_target(imported: str, rule: Rule, packages: frozenset[str]) -> str | None:
    if rule.absolute:
        for target in rule.targets:
            if imported == target or imported.startswith(f"{target}."):
                return f"module '{target}'"
        return None
    layer = _layer(imported, packages)
    if layer is not None and layer in rule.targets:
        return f"layer '{layer}'"
    return None


def main(argv: list[str] | None = None) -> int:
    """Check every module under the source roots against the layer rules.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Zero when no forbidden import exists, one on findings, two on usage errors.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("roots", nargs="+", type=Path, help="source roots, e.g. 'src'")
    parser.add_argument(
        "--package", action="append", required=True, help="top-level package name"
    )
    parser.add_argument(
        "--forbid", action="append", default=[], help="SOURCE:LAYER[,LAYER...]"
    )
    parser.add_argument(
        "--forbid-module",
        action="append",
        default=[],
        help="SOURCE:MODULE[,MODULE...] with absolute module prefixes",
    )
    parser.add_argument("--ignore-type-checking", action="store_true")
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        rules = [parse_rule(text) for text in args.forbid] + [
            parse_rule(text, absolute=True) for text in args.forbid_module
        ]
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return _EXIT_USAGE
    if not rules:
        rules = [parse_rule(_DEFAULT_RULE)]
    findings = _check_roots(
        args.roots,
        packages=frozenset(args.package),
        rules=rules,
        excluded=_EXCLUDED | set(args.exclude),
        ignore_type_checking=args.ignore_type_checking,
    )
    for finding in findings:
        sys.stdout.write(f"{finding}\n")
    return 1 if findings else 0


def _check_roots(
    roots: Iterable[Path],
    *,
    packages: frozenset[str],
    rules: list[Rule],
    excluded: frozenset[str],
    ignore_type_checking: bool,
) -> list[str]:
    findings: list[str] = []
    for root in roots:
        if not root.is_dir():
            findings.append(f"{root.as_posix()}:1: source root is not a directory")
            continue
        for path in sorted(root.rglob("*.py")):
            if excluded.intersection(path.relative_to(root).parts):
                continue
            try:
                findings.extend(
                    check_module(
                        path.read_text(encoding="utf-8"),
                        path=path.as_posix(),
                        module=module_name(path, root),
                        is_package=path.name == "__init__.py",
                        packages=packages,
                        rules=rules,
                        ignore_type_checking=ignore_type_checking,
                    )
                )
            except (OSError, UnicodeError, SyntaxError):
                findings.append(f"{path.as_posix()}:1: source cannot be parsed")
    return findings


if __name__ == "__main__":
    raise SystemExit(main())
