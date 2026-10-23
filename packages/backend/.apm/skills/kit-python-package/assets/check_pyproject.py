"""Check ``pyproject.toml`` packaging metadata against PEP 517, 621, 639, and 508.

The checker reads the file with ``tomllib`` and never runs a build backend. It
reports a missing or incomplete ``[build-system]``, invalid or missing
``[project]`` fields, fields both static and listed in ``dynamic``, legacy license
tables or license classifiers combined with an SPDX expression, missing readme
files, development tools or local direct references in runtime dependencies,
duplicate requirements, and malformed entry-point object references.
Exit 0 means no findings, 1 means findings or unreadable input.
Run ``--self-test`` for built-in regressions.
"""

import argparse
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
import re
import tomllib

_DEFAULT_DEV_TOOLS = (
    "black",
    "coverage",
    "flake8",
    "hypothesis",
    "isort",
    "mypy",
    "nox",
    "pre-commit",
    "pylint",
    "pyright",
    "pytest",
    "pytest-cov",
    "ruff",
    "tox",
    "ty",
)
_NAME = re.compile(r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", re.IGNORECASE)
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_VERSION = re.compile(
    r"^v?(\d+!)?\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+[a-z0-9.]+)?$",
    re.IGNORECASE,
)
_OBJECT_REFERENCE = re.compile(
    r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*(:[A-Za-z_]\w*(\.[A-Za-z_]\w*)*)?$"
)
_LOCAL_REFERENCE = re.compile(r"@\s*(file:|\.{1,2}/|/|[A-Za-z]:[\\/])")
_STATIC_FIELDS = (
    "version",
    "description",
    "readme",
    "requires-python",
    "license",
    "license-files",
    "authors",
    "maintainers",
    "keywords",
    "classifiers",
    "urls",
    "scripts",
    "gui-scripts",
    "entry-points",
    "dependencies",
    "optional-dependencies",
)


def normalize(name: str) -> str:
    """Normalize a distribution name as described in PEP 503.

    Args:
        name: Distribution or requirement name.

    Returns:
        Lowercase name with runs of ``-``, ``_`` and ``.`` replaced by ``-``.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


class _Locator:
    """Map TOML tables and keys to approximate one-based line numbers."""

    def __init__(self, text: str) -> None:
        """Index table headers.

        Args:
            text: TOML source.
        """
        self.lines = text.splitlines()
        self.headers: dict[str, int] = {}
        for number, line in enumerate(self.lines, start=1):
            match = re.match(r"^\s*\[\s*([^\]]+?)\s*\]\s*(#.*)?$", line)
            if match:
                self.headers.setdefault(match.group(1).replace(" ", ""), number)

    def line(self, table: str, key: str | None = None) -> int:
        """Return the line of a table header or a key inside that table.

        Args:
            table: Dotted table name such as ``project`` or ``project.scripts``.
            key: Optional key within the table.

        Returns:
            One-based line number, or 1 when not found.
        """
        start = self.headers.get(table)
        if start is None:
            return 1
        if key is None:
            return start
        pattern = re.compile(rf"^\s*\"?{re.escape(key)}\"?\s*=")
        for number in range(start + 1, len(self.lines) + 1):
            text = self.lines[number - 1]
            if re.match(r"^\s*\[", text):
                break
            if pattern.match(text):
                return number
        return start


def _check_build_system(
    data: dict[str, object], locate: _Locator
) -> list[tuple[int, str]]:
    """Validate the PEP 517/518 build-system table.

    Args:
        data: Parsed TOML document.
        locate: Line locator.

    Returns:
        Line-numbered messages.
    """
    build = data.get("build-system")
    if not isinstance(build, dict):
        return [(1, "missing [build-system]; frontends fall back to legacy setuptools")]
    issues: list[tuple[int, str]] = []
    requires = build.get("requires")
    if not isinstance(requires, list) or not requires:
        issues.append(
            (locate.line("build-system"), "build-system.requires must list the backend")
        )
    if not isinstance(build.get("build-backend"), str):
        issues.append(
            (locate.line("build-system"), "build-system.build-backend is missing")
        )
    return issues


def _check_identity(
    project: dict[str, object], locate: _Locator
) -> list[tuple[int, str]]:
    """Validate name, version, dynamic, and requires-python.

    Args:
        project: The ``[project]`` table.
        locate: Line locator.

    Returns:
        Line-numbered messages.
    """
    issues: list[tuple[int, str]] = []
    name = project.get("name")
    if not isinstance(name, str) or not _NAME.match(name):
        issues.append(
            (
                locate.line("project", "name"),
                "project.name is missing or not a valid PEP 508 name",
            )
        )
    dynamic = _dynamic_fields(project)
    if dynamic is None:
        issues.append(
            (
                locate.line("project", "dynamic"),
                "project.dynamic must be a list of field names",
            )
        )
        dynamic = []
    if "name" in dynamic:
        issues.append(
            (locate.line("project", "dynamic"), "project.name cannot be dynamic")
        )
    issues.extend(
        (
            locate.line("project", field),
            f"'{field}' is both static and listed in dynamic",
        )
        for field in _STATIC_FIELDS
        if field in project and field in dynamic
    )
    issues.extend(_check_version(project, locate, dynamic))
    return issues


def _dynamic_fields(project: dict[str, object]) -> list[str] | None:
    """Return the ``dynamic`` field names, or None when the value is malformed.

    Args:
        project: The ``[project]`` table.

    Returns:
        Declared dynamic field names, or None for a non-list or non-string entry.
    """
    dynamic = project.get("dynamic", [])
    if not isinstance(dynamic, list):
        return None
    names = [item for item in dynamic if isinstance(item, str)]
    return names if len(names) == len(dynamic) else None


def _check_version(
    project: dict[str, object], locate: _Locator, dynamic: list[str]
) -> list[tuple[int, str]]:
    """Validate the version and requires-python fields.

    Args:
        project: The ``[project]`` table.
        locate: Line locator.
        dynamic: Field names declared dynamic.

    Returns:
        Line-numbered messages.
    """
    issues: list[tuple[int, str]] = []
    version = project.get("version")
    if version is None and "version" not in dynamic:
        issues.append(
            (locate.line("project"), "project.version is missing and not dynamic")
        )
    elif isinstance(version, str) and not _VERSION.match(version):
        issues.append(
            (locate.line("project", "version"), f"version '{version}' is not PEP 440")
        )
    if "requires-python" not in project and "requires-python" not in dynamic:
        issues.append(
            (
                locate.line("project"),
                "requires-python is missing; installers cannot exclude unsupported interpreters",
            )
        )
    return issues


def _check_license(
    project: dict[str, object], locate: _Locator, *, allow_legacy: bool
) -> list[tuple[int, str]]:
    """Validate PEP 639 license metadata.

    Args:
        project: The ``[project]`` table.
        locate: Line locator.
        allow_legacy: Accept the deprecated table form.

    Returns:
        Line-numbered messages.
    """
    issues: list[tuple[int, str]] = []
    license_value = project.get("license")
    line = locate.line("project", "license")
    if isinstance(license_value, dict) and not allow_legacy:
        issues.append(
            (line, "legacy license table; use an SPDX expression string (PEP 639)")
        )
    elif isinstance(license_value, str):
        if not license_value.strip():
            issues.append((line, "license expression is empty"))
        classifiers = project.get("classifiers", [])
        if isinstance(classifiers, list) and any(
            isinstance(item, str) and item.startswith("License ::")
            for item in classifiers
        ):
            issues.append(
                (
                    locate.line("project", "classifiers"),
                    "License classifiers conflict with an SPDX license expression",
                )
            )
    files = project.get("license-files")
    if files is not None and (
        not isinstance(files, list) or not all(isinstance(item, str) for item in files)
    ):
        issues.append(
            (
                locate.line("project", "license-files"),
                "license-files must be a list of glob strings",
            )
        )
    return issues


def _check_readme(
    project: dict[str, object], locate: _Locator, root: Path
) -> list[tuple[int, str]]:
    """Check that a declared readme file exists.

    Args:
        project: The ``[project]`` table.
        locate: Line locator.
        root: Directory containing ``pyproject.toml``.

    Returns:
        Line-numbered messages.
    """
    readme = project.get("readme")
    target = readme.get("file") if isinstance(readme, dict) else readme
    if isinstance(target, str) and not (root / target).is_file():
        return [
            (locate.line("project", "readme"), f"readme file '{target}' does not exist")
        ]
    return []


def _requirement_issues(
    requirements: Iterable[object], label: str, line: int, dev_tools: frozenset[str]
) -> list[tuple[int, str]]:
    """Validate one list of PEP 508 requirement strings.

    Args:
        requirements: Requirement strings.
        label: Field label used in messages.
        line: Line to report.
        dev_tools: Normalized names that do not belong in runtime dependencies.

    Returns:
        Line-numbered messages.
    """
    issues: list[tuple[int, str]] = []
    seen: set[str] = set()
    for requirement in requirements:
        if not isinstance(requirement, str):
            issues.append((line, f"{label} entries must be strings"))
            continue
        match = _REQUIREMENT_NAME.match(requirement)
        if match is None:
            issues.append((line, f"{label}: cannot parse requirement '{requirement}'"))
            continue
        name = normalize(match.group(1))
        if name in seen:
            issues.append((line, f"{label}: duplicate requirement '{name}'"))
        seen.add(name)
        issues.extend(
            (line, message)
            for message in _requirement_risks(requirement, name, label, dev_tools)
        )
    return issues


def _requirement_risks(
    requirement: str, name: str, label: str, dev_tools: frozenset[str]
) -> list[str]:
    """Return publication risks for one parsed requirement.

    Args:
        requirement: Requirement string.
        name: Normalized requirement name.
        label: Field label used in messages.
        dev_tools: Normalized names that do not belong in runtime dependencies.

    Returns:
        Messages for development tools and local direct references.
    """
    risks: list[str] = []
    if name in dev_tools:
        risks.append(
            f"{label}: development tool '{name}' belongs in a dependency group"
        )
    if _LOCAL_REFERENCE.search(requirement):
        risks.append(
            f"{label}: local direct reference '{requirement}' cannot be published"
        )
    return risks


def _check_dependencies(
    project: dict[str, object], locate: _Locator, dev_tools: frozenset[str]
) -> list[tuple[int, str]]:
    """Validate runtime and optional dependencies.

    Args:
        project: The ``[project]`` table.
        locate: Line locator.
        dev_tools: Normalized development tool names.

    Returns:
        Line-numbered messages.
    """
    issues: list[tuple[int, str]] = []
    dependencies = project.get("dependencies", [])
    if isinstance(dependencies, list):
        issues.extend(
            _requirement_issues(
                dependencies,
                "dependencies",
                locate.line("project", "dependencies"),
                dev_tools,
            )
        )
    else:
        issues.append(
            (locate.line("project", "dependencies"), "dependencies must be a list")
        )
    extras = project.get("optional-dependencies", {})
    if isinstance(extras, dict):
        for extra, values in extras.items():
            line = locate.line("project.optional-dependencies", extra)
            if not _NAME.match(extra):
                issues.append((line, f"extra name '{extra}' is invalid"))
            if isinstance(values, list):
                issues.extend(
                    _requirement_issues(values, f"extra '{extra}'", line, frozenset())
                )
    return issues


def _check_entry_points(
    project: dict[str, object], locate: _Locator
) -> list[tuple[int, str]]:
    """Validate console, GUI, and plugin entry-point object references.

    Args:
        project: The ``[project]`` table.
        locate: Line locator.

    Returns:
        Line-numbered messages.
    """
    issues: list[tuple[int, str]] = []
    for group, entries in _entry_point_groups(project).items():
        if not isinstance(entries, dict):
            continue
        table = f"project.{group}"
        for name, reference in entries.items():
            message = _entry_point_issue(group, name, reference)
            if message is not None:
                issues.append((locate.line(table, name), message))
    return issues


def _entry_point_groups(project: dict[str, object]) -> dict[str, object]:
    """Collect script and plugin entry-point tables by group label.

    Args:
        project: The ``[project]`` table.

    Returns:
        Group labels mapped to their raw tables.
    """
    groups: dict[str, object] = {
        "scripts": project.get("scripts", {}),
        "gui-scripts": project.get("gui-scripts", {}),
    }
    plugins = project.get("entry-points", {})
    if isinstance(plugins, dict):
        groups.update(
            {f"entry-points.{name}": value for name, value in plugins.items()}
        )
    return groups


def _entry_point_issue(group: str, name: object, reference: object) -> str | None:
    """Return the problem with one entry-point object reference, if any.

    Args:
        group: Group label such as ``scripts``.
        name: Entry-point name.
        reference: Declared object reference.

    Returns:
        Message, or None for a valid reference.
    """
    if not isinstance(reference, str) or not _OBJECT_REFERENCE.match(reference.strip()):
        return f"{group}.{name}: '{reference}' is not 'module:object'"
    if ":" not in reference and group in {"scripts", "gui-scripts"}:
        return f"{group}.{name}: console scripts need 'module:function'"
    return None


def check_pyproject(
    text: str,
    path: str,
    *,
    root: Path,
    dev_tools: Iterable[str] = _DEFAULT_DEV_TOOLS,
    allow_legacy_license: bool = False,
) -> list[str]:
    """Check one ``pyproject.toml`` document.

    Args:
        text: TOML source.
        path: Display path.
        root: Directory used to resolve relative files such as the readme.
        dev_tools: Distribution names that must not be runtime dependencies.
        allow_legacy_license: Accept the deprecated license table form.

    Returns:
        Findings formatted as ``path:line: message``.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        match = re.search(r"line (\d+)", str(error))
        return [f"{path}:{match.group(1) if match else 1}: invalid TOML: {error}"]
    locate = _Locator(text)
    issues = _check_build_system(data, locate)
    project = data.get("project")
    if not isinstance(project, dict):
        issues.append((1, "missing [project] table (PEP 621)"))
    else:
        tools = frozenset(normalize(item) for item in dev_tools)
        issues.extend(_check_identity(project, locate))
        issues.extend(
            _check_license(project, locate, allow_legacy=allow_legacy_license)
        )
        issues.extend(_check_readme(project, locate, root))
        issues.extend(_check_dependencies(project, locate, tools))
        issues.extend(_check_entry_points(project, locate))
    return [f"{path}:{line}: {message}" for line, message in sorted(issues)]


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    VALID_METADATA_REJECTED = "valid metadata must pass"
    DYNAMIC_VERSION_REJECTED = "dynamic version must pass"
    MISSED_METADATA_ISSUE = "missed '{fragment}': {found}"
    LEGACY_LICENSE_REJECTED = "legacy license must pass when explicitly allowed"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self,
        issue: SelfTestIssue,
        *,
        fragment: str | None = None,
        found: list[str] | None = None,
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            fragment: Observed fragment for the failing case.
            found: Observed found for the failing case.
        """
        super().__init__(issue.value.format(fragment=fragment, found=found))


def self_test() -> None:
    """Exercise valid, legacy, dynamic, dependency, and entry-point cases.

    Raises:
        AssertionError: A regression was detected.
    """
    root = Path(__file__).parent
    valid = (
        '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n\n'
        '[project]\nname = "order-tools"\nversion = "1.2.0"\nrequires-python = ">=3.12"\n'
        'license = "MIT"\ndependencies = ["httpx>=0.27"]\n\n'
        '[project.scripts]\norder-tools = "order_tools.cli:main"\n\n'
        '[dependency-groups]\ndev = ["pytest", "ruff"]\n'
    )
    if check_pyproject(valid, "pyproject.toml", root=root):
        raise SelfTestError(SelfTestIssue.VALID_METADATA_REJECTED)
    dynamic = valid.replace('version = "1.2.0"', 'dynamic = ["version"]')
    if check_pyproject(dynamic, "pyproject.toml", root=root):
        raise SelfTestError(SelfTestIssue.DYNAMIC_VERSION_REJECTED)
    broken = {
        valid.replace("[build-system]", "[tool.other]"): "build-system",
        valid.replace('"1.2.0"', '"one"'): "PEP 440",
        valid.replace('license = "MIT"', 'license = {text = "MIT"}'): "legacy license",
        valid.replace('"httpx>=0.27"', '"httpx", "pytest"'): "development tool",
        valid.replace(
            '"httpx>=0.27"', '"lib @ file:///tmp/lib"'
        ): "local direct reference",
        valid.replace('"httpx>=0.27"', '"httpx", "HTTPX"'): "duplicate",
        valid.replace("order_tools.cli:main", "order tools"): "module:object",
        valid.replace('requires-python = ">=3.12"\n', ""): "requires-python",
        valid.replace(
            'version = "1.2.0"', 'version = "1.2.0"\ndynamic = ["version"]'
        ): "both static",
        valid.replace(
            'license = "MIT"',
            'license = "MIT"\nclassifiers = ["License :: OSI Approved :: MIT License"]',
        ): "classifiers",
        valid.replace(
            'license = "MIT"', 'license = "MIT"\nreadme = "MISSING.md"'
        ): "readme",
        valid + "[broken\n": "invalid TOML",
    }
    for text, fragment in broken.items():
        found = check_pyproject(text, "pyproject.toml", root=root)
        if not any(fragment in item for item in found):
            raise SelfTestError(
                SelfTestIssue.MISSED_METADATA_ISSUE, fragment=fragment, found=found
            )
    legacy = valid.replace('license = "MIT"', 'license = {text = "MIT"}')
    if check_pyproject(legacy, "pyproject.toml", root=root, allow_legacy_license=True):
        raise SelfTestError(SelfTestIssue.LEGACY_LICENSE_REJECTED)


def main(argv: list[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        0 when clean, 1 when findings were reported.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="pyproject.toml files")
    parser.add_argument(
        "--dev-tool",
        action="append",
        default=None,
        help="distribution name forbidden in runtime dependencies (repeatable; "
        "replaces the default list)",
    )
    parser.add_argument("--allow-legacy-license", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("check_pyproject self-test passed.")
        return 0
    if not args.paths:
        parser.error("at least one path is required unless --self-test is used")
    findings: list[str] = []
    for path in args.paths:
        target = path / "pyproject.toml" if path.is_dir() else path
        try:
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            findings.append(f"{target.as_posix()}:1: cannot read: {error}")
            continue
        findings.extend(
            check_pyproject(
                text,
                target.as_posix(),
                root=target.parent,
                dev_tools=tuple(args.dev_tool or _DEFAULT_DEV_TOOLS),
                allow_legacy_license=args.allow_legacy_license,
            )
        )
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
