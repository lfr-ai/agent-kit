# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Flag the highest-risk Python calls with a standard-library AST scan.

Rules (select a subset with ``--rule``):

- ``shell-true``: any call passing ``shell=True``.
- ``eval-exec``: calls to the ``eval`` or ``exec`` builtins.
- ``pickle-load``: ``pickle``/``dill``/``marshal`` ``load``/``loads`` and
  ``pickle.Unpickler``, which run code while deserializing.
- ``yaml-unsafe``: ``yaml.load``/``load_all`` without a ``SafeLoader`` or
  ``CSafeLoader``, and ``yaml.unsafe_load``/``full_load`` variants.
- ``mktemp``: ``tempfile.mktemp``, which races between naming and creation.
- ``http-no-timeout``: ``requests`` and ``httpx`` module-level request
  functions called without ``timeout=``.

Import aliases (``import pickle as p``, ``from yaml import load``) are
resolved. Calls on objects (``session.get``) cannot be attributed and are not
reported. A reviewed exception is written on the call's first line as
``# secure: allow[rule-id] reason``.

Output is one ``path:line: [rule-id] message`` per finding, sorted. Exit
status: 0 when clean, 1 when findings exist, 2 for usage or read errors.

Example:
    python check_secure_patterns.py src --rule shell-true --rule eval-exec
    python check_secure_patterns.py --self-test
"""

import argparse
import ast
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import sys

_USAGE_ERROR = 2
_SKIPPED_DIRECTORIES = frozenset(
    {".git", ".hg", ".venv", "venv", ".tox", ".nox", "node_modules", "__pycache__"}
)
_ALLOW = re.compile(r"#\s*secure:\s*allow\[([a-z-]+)\]")
_PICKLE_CALLS = frozenset(
    {
        "pickle.load",
        "pickle.loads",
        "pickle.Unpickler",
        "dill.load",
        "dill.loads",
        "marshal.load",
        "marshal.loads",
    }
)
_YAML_ALWAYS_UNSAFE = frozenset(
    {"yaml.unsafe_load", "yaml.unsafe_load_all", "yaml.full_load", "yaml.full_load_all"}
)
_YAML_LOADER_CALLS = frozenset({"yaml.load", "yaml.load_all"})
_SAFE_LOADERS = ("SafeLoader", "CSafeLoader")
_HTTP_VERBS = ("get", "post", "put", "patch", "delete", "head", "options", "request")
_HTTP_CALLS = frozenset(
    f"{library}.{verb}"
    for library in ("requests", "httpx")
    for verb in (*_HTTP_VERBS, "stream")
)
_LOADER_POSITION = 1


@dataclass(frozen=True, kw_only=True, slots=True, order=True)
class Finding:
    """One reported call.

    Attributes:
        path: POSIX path of the scanned file.
        line: One-based line of the call.
        rule: Rule identifier.
        message: Why the call is risky and what to use instead.
    """

    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        """Return the finding as ``path:line: [rule] message``."""
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


@dataclass(frozen=True, kw_only=True, slots=True)
class Call:
    """A call with its resolved dotted name.

    Attributes:
        node: The call expression.
        name: Fully qualified callee, or None when it cannot be attributed.
        aliases: Local names mapped to the modules or objects they import.
    """

    node: ast.Call
    name: str | None
    aliases: dict[str, str]


def _dotted(node: ast.expr) -> str | None:
    """Return ``a.b.c`` for a name or attribute chain, otherwise None."""
    attributes: list[str] = []
    while isinstance(node, ast.Attribute):
        attributes.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(attributes)])


def resolve(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """Return the qualified name of an expression using import aliases.

    Args:
        node: Callee or argument expression.
        aliases: Local names mapped to their imported targets.

    Returns:
        The dotted name with the first part replaced by its import target.
    """
    dotted = _dotted(node)
    if dotted is None:
        return None
    head, dot, rest = dotted.partition(".")
    return f"{aliases.get(head, head)}{dot}{rest}"


def import_aliases(tree: ast.Module) -> dict[str, str]:
    """Map local names to the absolute modules or objects they import.

    Args:
        tree: Parsed module.

    Returns:
        Local name to dotted target; relative imports are ignored.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.partition(".")[0]
                aliases[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value of a keyword argument, if present."""
    return next((item.value for item in call.keywords if item.arg == name), None)


def _shell_true(call: Call) -> str | None:
    value = _keyword(call.node, "shell")
    if isinstance(value, ast.Constant) and value.value is True:
        return "shell=True lets the shell parse arguments; pass a list with shell=False"
    return None


def _eval_exec(call: Call) -> str | None:
    if call.name in {"eval", "exec", "builtins.eval", "builtins.exec"}:
        return f"{call.name} runs arbitrary code; use ast.literal_eval or a parser"
    return None


def _pickle_load(call: Call) -> str | None:
    if call.name in _PICKLE_CALLS:
        return f"{call.name} executes code from data; use JSON with schema validation"
    return None


def _yaml_unsafe(call: Call) -> str | None:
    if call.name in _YAML_ALWAYS_UNSAFE:
        return f"{call.name} constructs arbitrary objects; use yaml.safe_load"
    if call.name not in _YAML_LOADER_CALLS:
        return None
    loader = _keyword(call.node, "Loader")
    if loader is None and len(call.node.args) > _LOADER_POSITION:
        loader = call.node.args[_LOADER_POSITION]
    loader_name = resolve(loader, call.aliases) if loader is not None else None
    if loader_name and loader_name.endswith(_SAFE_LOADERS):
        return None
    return f"{call.name} without SafeLoader; use yaml.safe_load"


def _mktemp(call: Call) -> str | None:
    if call.name == "tempfile.mktemp":
        return "tempfile.mktemp races; use mkstemp, NamedTemporaryFile or TemporaryDirectory"
    return None


def _http_no_timeout(call: Call) -> str | None:
    keywords = call.node.keywords
    unpacked = any(item.arg is None for item in keywords)
    if (
        call.name in _HTTP_CALLS
        and not unpacked
        and _keyword(call.node, "timeout") is None
    ):
        return f"{call.name} without timeout=; set connect and read timeouts"
    return None


RULES: dict[str, Callable[[Call], str | None]] = {
    "shell-true": _shell_true,
    "eval-exec": _eval_exec,
    "pickle-load": _pickle_load,
    "yaml-unsafe": _yaml_unsafe,
    "mktemp": _mktemp,
    "http-no-timeout": _http_no_timeout,
}


def check_source(
    path: str, text: str, *, rules: Sequence[str] = tuple(RULES)
) -> list[Finding]:
    """Report risky calls in one module.

    Args:
        path: Path used in findings.
        text: Module source.
        rules: Rule identifiers to apply.

    Returns:
        Findings for the module, or one ``syntax`` finding if it cannot parse.
    """
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as error:
        return [
            Finding(
                path=path,
                line=error.lineno or 1,
                rule="syntax",
                message=f"cannot parse: {error.msg}",
            )
        ]
    lines = text.splitlines()
    aliases = import_aliases(tree)
    return [
        finding
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for finding in _call_findings(path, node, aliases=aliases, rules=rules)
        if finding.rule not in _allowed(lines, finding.line)
    ]


def _call_findings(
    path: str, node: ast.Call, *, aliases: dict[str, str], rules: Sequence[str]
) -> Iterator[Finding]:
    """Yield the findings of every selected rule for one call."""
    call = Call(node=node, name=resolve(node.func, aliases), aliases=aliases)
    for rule in rules:
        message = RULES[rule](call)
        if message:
            yield Finding(path=path, line=node.lineno, rule=rule, message=message)


def _allowed(lines: list[str], line: int) -> set[str]:
    """Return rule identifiers allowed by a comment on a one-based line."""
    text = lines[line - 1] if 0 < line <= len(lines) else ""
    return set(_ALLOW.findall(text))


_SELF_TEST_RISKY = """import pickle as p
import subprocess
import yaml
from tempfile import mktemp
import requests
subprocess.run(command, shell=True)
eval(text)
p.loads(blob)
yaml.load(text, Loader=yaml.Loader)
mktemp()
requests.get(url)
subprocess.run(command, shell=True)  # secure: allow[shell-true] fixed command
"""
_SELF_TEST_SAFE = """import ast
import subprocess
import yaml
import requests
subprocess.run(["ls"], shell=False, timeout=5)
ast.literal_eval(text)
yaml.load(text, Loader=yaml.SafeLoader)
yaml.safe_load(text)
requests.get(url, timeout=10)
session.get(url)
"""
_SELF_TEST_EXPECTED = (
    "risky.py:6: [shell-true]",
    "risky.py:7: [eval-exec]",
    "risky.py:8: [pickle-load]",
    "risky.py:9: [yaml-unsafe]",
    "risky.py:10: [mktemp]",
    "risky.py:11: [http-no-timeout]",
)


def self_test() -> list[str]:
    """Run every rule on in-memory risky and safe modules.

    Returns:
        Unmet expectations; empty when the rules behave as documented.
    """
    risky = [item.render() for item in check_source("risky.py", _SELF_TEST_RISKY)]
    safe = [item.render() for item in check_source("safe.py", _SELF_TEST_SAFE)]
    problems = [
        f"missing finding {prefix}"
        for prefix in _SELF_TEST_EXPECTED
        if not any(item.startswith(prefix) for item in risky)
    ]
    if len(risky) != len(_SELF_TEST_EXPECTED):
        problems.append(f"unexpected risky findings: {risky}")
    problems.extend(f"false positive: {item}" for item in safe)
    return problems


def python_files(paths: Sequence[Path]) -> list[Path]:
    """Expand files and directories into Python files, skipping tool caches.

    Explicitly named files are always kept. Inside a directory argument, only
    the parts below that directory are compared with the skipped names, so a
    checkout that itself lives under a folder such as ``venv`` is still scanned.

    Args:
        paths: Files or directories to scan.

    Returns:
        Sorted, unique Python file paths.
    """
    found: set[Path] = set()
    for path in paths:
        if path.is_file():
            found.add(path)
            continue
        found.update(
            candidate
            for candidate in path.rglob("*.py")
            if not _SKIPPED_DIRECTORIES.intersection(candidate.relative_to(path).parts)
        )
    return sorted(found)


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", type=Path, default=[Path()])
    parser.add_argument(
        "--rule",
        action="append",
        choices=list(RULES),
        default=[],
        help="rule to apply; repeatable; default: all rules",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the rules on built-in in-memory modules and exit",
    )
    return parser


def _self_test_status() -> int:
    """Report the self-test result and return 0 on success or 1 on failure."""
    problems = self_test()
    if problems:
        sys.stderr.write(f"{'\n'.join(problems)}\n")
        sys.stdout.write("check_secure_patterns self-test failed.\n")
        return 1
    sys.stdout.write("check_secure_patterns self-test passed.\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Scan paths and print findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when clean, 1 when findings exist, 2 on usage or read errors.
    """
    args = _parser().parse_args(argv)
    if args.self_test:
        return _self_test_status()
    absent = [path for path in args.paths if not path.exists()]
    if absent:
        sys.stderr.write(f"path does not exist: {absent[0].as_posix()}\n")
        return _USAGE_ERROR
    rules = tuple(args.rule) or tuple(RULES)
    findings: list[Finding] = []
    try:
        for path in python_files(args.paths):
            text = path.read_text(encoding="utf-8")
            findings.extend(check_source(path.as_posix(), text, rules=rules))
    except (OSError, UnicodeDecodeError) as error:
        sys.stderr.write(f"cannot read source: {error}\n")
        return _USAGE_ERROR
    for finding in sorted(findings):
        sys.stdout.write(f"{finding.render()}\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
