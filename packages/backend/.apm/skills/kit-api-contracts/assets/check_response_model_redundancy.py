# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Flag FastAPI routes whose ``response_model`` repeats the return annotation.

FastAPI uses the return annotation as the response model. Passing the same type
again in ``response_model=`` is redundant and drifts when only one copy is
changed. ``response_model`` is meaningful only when it differs from the
annotation (for example to filter an internal object) or is ``None`` to disable
the generated model; those cases are not reported.

Annotations are normalized before comparison, so ``List[X]`` equals ``list[X]``,
``Optional[X]`` equals ``X | None``, and ``Union[A, B]`` equals ``A | B``.

With ``--require-type``, routes that declare neither a return annotation nor a
``response_model`` are reported too.
"""

import argparse
import ast
from collections.abc import Iterable
from pathlib import Path
import sys

_EXCLUDED = frozenset({".venv", "node_modules", "apm_modules", "build", "__pycache__"})
_DEFAULT_METHODS = (
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "trace",
    "api_route",
)
_ALIASES = {
    "List": "list",
    "Dict": "dict",
    "Set": "set",
    "FrozenSet": "frozenset",
    "Tuple": "tuple",
}


def check_source(
    text: str,
    path: str,
    *,
    methods: frozenset[str] = frozenset(_DEFAULT_METHODS),
    require_type: bool = False,
) -> list[str]:
    """Return findings for route decorators in one module.

    Args:
        text: Python source text.
        path: Display path used as the finding prefix.
        methods: Decorator attribute names treated as route registrations.
        require_type: Also report routes without any response type.

    Returns:
        Findings formatted as ``path:line: message``, sorted by line.
    """
    tree = ast.parse(text, filename=path)
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            call = _route_call(decorator, methods)
            if call is None:
                continue
            model = next(
                (item.value for item in call.keywords if item.arg == "response_model"),
                None,
            )
            message = _judge(node, model, require_type=require_type)
            if message is not None:
                findings.append((call.lineno, message))
    return [f"{path}:{line}: {message}" for line, message in sorted(findings)]


def _route_call(decorator: ast.expr, methods: frozenset[str]) -> ast.Call | None:
    if (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in methods
    ):
        return decorator
    return None


def _judge(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    model: ast.expr | None,
    *,
    require_type: bool,
) -> str | None:
    if model is None:
        if require_type and function.returns is None:
            return f"route '{function.name}' declares no return annotation or response_model"
        return None
    if isinstance(model, ast.Constant) and model.value is None:
        return None
    if function.returns is not None and _normalized(model) == _normalized(
        function.returns
    ):
        return (
            f"route '{function.name}' passes response_model={ast.unparse(model)}, "
            "identical to its return annotation; remove response_model"
        )
    return None


def _normalized(annotation: ast.expr) -> str:
    return ast.dump(
        _Normalizer().visit(ast.parse(ast.unparse(annotation), mode="eval"))
    )


class _Normalizer(ast.NodeTransformer):
    """Rewrite legacy typing spellings into builtin and union syntax."""

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        """Drop a ``typing.`` prefix so ``typing.List`` matches ``List``."""
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "typing":
            return ast.Name(id=_ALIASES.get(node.attr, node.attr), ctx=ast.Load())
        return node

    def visit_Name(self, node: ast.Name) -> ast.expr:
        """Map capitalized typing aliases to builtins."""
        return ast.Name(id=_ALIASES.get(node.id, node.id), ctx=ast.Load())

    def visit_Subscript(self, node: ast.Subscript) -> ast.expr:
        """Turn ``Optional[X]`` and ``Union[A, B]`` into ``|`` unions."""
        self.generic_visit(node)
        if not isinstance(node.value, ast.Name):
            return node
        if node.value.id == "Optional":
            return _union([node.slice, ast.Constant(value=None)])
        if node.value.id == "Union":
            members = (
                node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            )
            return _union(members)
        return node


def _union(members: Iterable[ast.expr]) -> ast.expr:
    items = list(members)
    result = items[0]
    for item in items[1:]:
        result = ast.BinOp(left=result, op=ast.BitOr(), right=item)
    return result


def main(argv: list[str] | None = None) -> int:
    """Scan files or directories for redundant response models.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Zero without findings, otherwise one.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--method",
        action="append",
        default=[],
        help="route decorator attribute name; replaces the default set (repeatable)",
    )
    parser.add_argument("--require-type", action="store_true")
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args(argv)
    methods = frozenset(args.method or _DEFAULT_METHODS)
    excluded = _EXCLUDED | set(args.exclude)
    findings: list[str] = []
    for path in _python_files(args.paths, excluded, findings):
        try:
            findings.extend(
                check_source(
                    path.read_text(encoding="utf-8"),
                    path.as_posix(),
                    methods=methods,
                    require_type=args.require_type,
                )
            )
        except (OSError, UnicodeError, SyntaxError):
            findings.append(f"{path.as_posix()}:1: source cannot be parsed")
    for finding in findings:
        sys.stdout.write(f"{finding}\n")
    return 1 if findings else 0


def _python_files(
    paths: Iterable[Path], excluded: frozenset[str], problems: list[str]
) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if not path.exists():
            problems.append(f"{path.as_posix()}:1: path does not exist")
            continue
        candidates = [path] if path.is_file() else path.rglob("*.py")
        files.update(
            candidate
            for candidate in candidates
            if candidate.suffix == ".py"
            and not excluded.intersection(candidate.relative_to(path).parts)
        )
    return sorted(files)


if __name__ == "__main__":
    raise SystemExit(main())
