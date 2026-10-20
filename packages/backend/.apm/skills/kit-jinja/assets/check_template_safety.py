"""Flag unsafe Jinja environment setup and risky template constructs.

Python sources are parsed without importing them. Calls to Jinja 'Environment'
classes are reported when 'autoescape' is missing or literally False and when
'undefined' is not set (lenient undefined values render as empty text). Direct
'jinja2.Template(...)' construction, 'Markup' around formatted strings, and
'from_string' on non-literal source are reported too. Template files are
scanned line by line for the 'safe' filter, disabled autoescape blocks, dunder
attribute access, the 'attr' filter, environment access, and include/import/
extends targets taken from variables. A line containing
'template-safety: reviewed' (in a Python or Jinja comment) is waived.
Exit 0 means no findings, 1 means findings or unreadable sources.
Run '--self-test' for built-in regressions.
"""

import argparse
import ast
import re
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

_WAIVER = "template-safety: reviewed"
_DEFAULT_SUFFIXES = (".j2", ".jinja", ".jinja2", ".html", ".htm", ".xml")
_ENVIRONMENTS = frozenset(
    {
        "Environment",
        "SandboxedEnvironment",
        "ImmutableSandboxedEnvironment",
        "NativeEnvironment",
    }
)
_TEMPLATE_RULES = (
    (
        re.compile(r"\|\s*safe\b"),
        "'|safe' disables escaping; sanitize in code and pass Markup deliberately",
    ),
    (
        re.compile(r"\{%-?\s*autoescape\s+false\b", re.IGNORECASE),
        "autoescape disabled for a block",
    ),
    (
        re.compile(r"__\w+__"),
        "dunder attribute access is a sandbox-escape pattern",
    ),
    (
        re.compile(r"\|\s*attr\s*\("),
        "'attr' filter enables dynamic attribute lookup; pass explicit values",
    ),
    (
        re.compile(r"\b(environ|getenv)\b"),
        "environment access from a template; pass explicit context values",
    ),
    (
        re.compile(r"\{%-?\s*(include|import|extends|from)\s+(?![\"'\[])"),
        "template name from a variable; resolve names in code from an allow-list",
    ),
)


def _jinja_bindings(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    """Collect names imported from Jinja and aliases of the Jinja package.

    Args:
        tree: Parsed module.

    Returns:
        Mapping of local name to original name, and local package aliases.
    """
    names: dict[str, str] = {}
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            ("jinja2", "markupsafe")
        ):
            for alias in node.names:
                names[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("jinja2"):
                    modules.add(alias.asname or alias.name.split(".")[0])
    return names, modules


def _callee(call: ast.Call, names: dict[str, str], modules: set[str]) -> str | None:
    """Resolve a call to the original Jinja name it refers to.

    Args:
        call: Call node.
        names: Local-to-original names imported from Jinja.
        modules: Local aliases of Jinja packages.

    Returns:
        The original Jinja name, the attribute name for method calls, or None.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return names.get(func.id)
    if isinstance(func, ast.Attribute):
        root = func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id in modules:
            return func.attr
        if func.attr == "from_string":
            return "from_string"
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Return a keyword argument value.

    Args:
        call: Call node.
        name: Keyword name.

    Returns:
        The value node, or None.
    """
    return next((item.value for item in call.keywords if item.arg == name), None)


def _is_dynamic_text(node: ast.expr) -> bool:
    """Return whether an expression builds text from runtime values.

    Args:
        node: Expression node.

    Returns:
        True for f-strings, '%' or '+' formatting, and '.format()' calls.
    """
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
    )


def _python_issue(call: ast.Call, name: str) -> list[str]:
    """Return issues for one resolved Jinja call.

    Args:
        call: Call node.
        name: Original Jinja name.

    Returns:
        Zero or more messages.
    """
    issues: list[str] = []
    if name in _ENVIRONMENTS:
        autoescape = _keyword(call, "autoescape")
        if autoescape is None:
            issues.append(f"{name} without autoescape (defaults to False)")
        elif isinstance(autoescape, ast.Constant) and autoescape.value is False:
            issues.append(f"{name} with autoescape=False")
        if _keyword(call, "undefined") is None:
            issues.append(
                f"{name} without undefined=StrictUndefined renders missing values "
                "as empty text"
            )
    elif name == "Template":
        issues.append(
            "jinja2.Template uses an implicit environment; load templates through "
            "a configured Environment"
        )
    elif name == "Markup" and call.args and _is_dynamic_text(call.args[0]):
        issues.append("Markup around formatted text marks untrusted input as safe")
    elif (
        name == "from_string"
        and call.args
        and not (
            isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        )
    ):
        issues.append(
            "from_string on non-literal source; never render untrusted template "
            "text outside a sandboxed environment"
        )
    return issues


def check_python(text: str, path: str) -> list[str]:
    """Report unsafe Jinja usage in Python source.

    Args:
        text: Python source.
        path: Display path.

    Returns:
        Findings formatted as 'path:line: message'.

    Raises:
        SyntaxError: The source cannot be parsed.
    """
    tree = ast.parse(text, filename=path)
    names, modules = _jinja_bindings(tree)
    if not names and not modules:
        return []
    lines = text.splitlines()
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _callee(node, names, modules)
        if name is None or _WAIVER in lines[node.lineno - 1]:
            continue
        findings.extend(
            (node.lineno, f"{path}:{node.lineno}: {issue}")
            for issue in _python_issue(node, name)
        )
    return [message for _, message in sorted(findings)]


def check_template(text: str, path: str) -> list[str]:
    """Report risky constructs in Jinja template source.

    Args:
        text: Template source.
        path: Display path.

    Returns:
        Findings formatted as 'path:line: message'.
    """
    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if _WAIVER in line:
            continue
        findings.extend(
            f"{path}:{number}: {message}"
            for pattern, message in _TEMPLATE_RULES
            if pattern.search(line)
        )
    return findings


def _files(targets: Sequence[Path], suffixes: Sequence[str]) -> list[Path]:
    """Expand targets into Python and template files.

    Args:
        targets: Files or directories.
        suffixes: Template file suffixes.

    Returns:
        Sorted candidate files.
    """
    wanted = {".py", *suffixes}
    files: set[Path] = set()
    for target in targets:
        candidates = [target] if target.is_file() else target.rglob("*")
        files.update(
            path
            for path in candidates
            if path.is_file()
            and path.suffix in wanted
            and not path.is_symlink()
            and "__pycache__" not in path.parts
            and ".venv" not in path.parts
            and "node_modules" not in path.parts
        )
    return sorted(files)


def scan(targets: Sequence[Path], *, suffixes: Sequence[str]) -> list[str]:
    """Scan targets and return all findings.

    Args:
        targets: Files or directories.
        suffixes: Template file suffixes.

    Returns:
        Findings, including missing targets and unreadable files.
    """
    findings = [
        f"{target.as_posix()}:1: missing or linked target"
        for target in targets
        if not target.exists() or target.is_symlink()
    ]
    for path in _files([item for item in targets if item.exists()], suffixes):
        display = path.as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".py":
                findings.extend(check_python(text, display))
            else:
                findings.extend(check_template(text, display))
        except (OSError, UnicodeError, SyntaxError):
            findings.append(f"{display}:1: source cannot be read or parsed")
    return findings


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    MISSED_PYTHON_ISSUE = "missed Python issue: {source!r} {found}"
    FALSE_POSITIVE = "false positive: {source!r}"
    MISSED_TEMPLATE_ISSUE = "missed template issue: {source!r} {found}"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self,
        issue: SelfTestIssue,
        *,
        source: str | None = None,
        found: list[str] | None = None,
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            source: Observed source for the failing case.
            found: Observed found for the failing case.
        """
        super().__init__(issue.value.format(source=source, found=found))


def self_test() -> None:
    """Exercise environment, template, waiver, and clean cases.

    Raises:
        AssertionError: A regression was detected.
    """
    risky_python = {
        "from jinja2 import Environment\nenv = Environment()\n": "autoescape",
        "import jinja2\nenv = jinja2.Environment(autoescape=False)\n": (
            "autoescape=False"
        ),
        "from jinja2 import Template\nTemplate('x')\n": "implicit environment",
        "from markupsafe import Markup\nMarkup(f'<b>{name}</b>')\n": "Markup",
        "from jinja2 import Environment\nenv = Environment(autoescape=True)\n": (
            "StrictUndefined"
        ),
        "import jinja2\nenv.from_string(source)\n": "from_string",
    }
    for source, fragment in risky_python.items():
        found = check_python(source, "app/render.py")
        if not any(fragment in item for item in found):
            raise SelfTestError(
                SelfTestIssue.MISSED_PYTHON_ISSUE, source=source, found=found
            )
    clean_python = (
        (
            "from jinja2 import Environment, StrictUndefined, select_autoescape\n"
            "env = Environment(autoescape=select_autoescape(), "
            "undefined=StrictUndefined)\n"
        ),
        "from string import Template\nTemplate('$x')\n",
        (
            "from jinja2 import Environment\n"
            "env = Environment()  # template-safety: reviewed (text only)\n"
        ),
        "from markupsafe import Markup\nMarkup('<br>')\n",
    )
    for source in clean_python:
        if check_python(source, "app/render.py"):
            raise SelfTestError(SelfTestIssue.FALSE_POSITIVE, source=source)
    risky_templates = {
        "{{ body|safe }}": "safe",
        "{% autoescape false %}{{ x }}{% endautoescape %}": "autoescape",
        "{{ ''.__class__.__mro__ }}": "dunder",
        "{{ item|attr('x') }}": "attr",
        "{{ environ['HOME'] }}": "environment",
        "{% include name %}": "variable",
    }
    for source, fragment in risky_templates.items():
        found = check_template(source, "t.html")
        if not any(fragment in item for item in found):
            raise SelfTestError(
                SelfTestIssue.MISSED_TEMPLATE_ISSUE, source=source, found=found
            )
    clean_templates = (
        "{% include 'partials/footer.html' %}",
        "{% include ['a.html', 'b.html'] %}",
        "{{ user.name }} {# template-safety: reviewed #} {{ x|safe }}",
        "<p>{{ order.total|round(2) }}</p>",
    )
    for source in clean_templates:
        if check_template(source, "t.html"):
            raise SelfTestError(SelfTestIssue.FALSE_POSITIVE, source=source)


def main(argv: list[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv: Command-line arguments; defaults to 'sys.argv[1:]'.

    Returns:
        0 when clean, 1 when findings were reported.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="files or directories")
    parser.add_argument(
        "--template-suffix",
        action="append",
        default=None,
        help="template suffix to scan (repeatable; default: "
        f"{' '.join(_DEFAULT_SUFFIXES)})",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("check_template_safety self-test passed.")
        return 0
    if not args.paths:
        parser.error("at least one path is required unless --self-test is used")
    findings = scan(
        args.paths, suffixes=tuple(args.template_suffix or _DEFAULT_SUFFIXES)
    )
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
