"""Check that ``uv.lock`` still matches ``pyproject.toml`` and pins every artifact.

The checker reads both files with ``tomllib``. It never runs uv, resolves
versions, or contacts an index, so it is safe before anything is installed and
complements ``uv lock --check`` where uv is unavailable or not yet trusted.

Findings:

- Stale lock: a requirement from ``[project] dependencies``,
  ``[project.optional-dependencies]``, ``[dependency-groups]`` (with
  ``include-group`` expanded) or legacy ``[tool.uv] dev-dependencies`` differs
  from the metadata uv recorded for the root package. Name, extras and version
  specifier are compared; environment markers are not, because uv rewrites them.
- Stale lock: ``[tool.uv]`` ``constraint-dependencies``,
  ``override-dependencies`` or ``build-constraint-dependencies`` differ from the
  lock ``[manifest]`` table.
- Stale lock: ``requires-python`` differs (single-project repositories only).
- Pin drift: a requirement pinned with ``==`` in ``[project] dependencies``,
  any optional-dependency list, any dependency group, or ``[tool.uv]``
  ``constraint-dependencies`` or ``override-dependencies`` whose locked
  versions all differ from the pin. Build constraints are not checked because
  uv does not lock the build closure.
- Missing hash: a registry or URL package without distribution files, or a
  distribution file without a ``sha256``, ``sha384`` or ``sha512`` hash.
- Mutable Git source: a Git package whose source lacks a full commit hash.

Limitations: workspace members other than the root project are not compared;
direct URL requirements are compared by name only; version strings are compared
as written, so a pin in non-canonical form such as ``==1.0-alpha1`` can be
reported.

Usage:
    python check_lock_freshness.py --project pyproject.toml --lock uv.lock
    python check_lock_freshness.py --self-test

Exit codes: 0 clean, 1 findings, 2 unreadable input or bad arguments.
"""

import argparse
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import tomllib
from typing import TypeGuard

_FINDINGS = 1
_INVALID = 2
_SHA1_HEX_LENGTH = 40
_SHA256_HEX_LENGTH = 64
_COMMIT_LENGTHS = frozenset({_SHA1_HEX_LENGTH, _SHA256_HEX_LENGTH})
_HASHED_SOURCES = ("registry", "url")
_SEPARATORS = re.compile(r"[-_.]+")
_WHITESPACE = re.compile(r"\s+")
_REQUIREMENT = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\s*"
    r"(?:\[(?P<extras>[^\]]*)\])?\s*(?P<version>[^;]*?)\s*(?:;.*)?$"
)
_HASH = re.compile(r"^(sha256|sha384|sha512):[0-9a-f]+$")
_COMMIT = re.compile(r"[0-9a-f]+")
_EXACT_PIN = re.compile(r"^==(?P<version>[^,*]+)$")
_MANIFEST_TABLES = (
    ("constraint-dependencies", "constraints"),
    ("override-dependencies", "overrides"),
    ("build-constraint-dependencies", "build-constraints"),
)


class LockInputError(ValueError):
    """A manifest or lock does not have the documented TOML structure."""


@dataclass(frozen=True, kw_only=True, slots=True, order=True)
class Requirement:
    """A requirement reduced to the fields uv records without rewriting.

    Attributes:
        name: Normalized distribution name.
        extras: Sorted, normalized extras.
        specifier: Sorted version clauses without whitespace; empty when the
            requirement has no version or is a direct reference.
    """

    name: str
    extras: tuple[str, ...] = ()
    specifier: str = ""

    def render(self) -> str:
        """Return the requirement in compact PEP 508 form."""
        extras = f"[{','.join(self.extras)}]" if self.extras else ""
        return f"{self.name}{extras}{self.specifier}"


@dataclass(frozen=True, kw_only=True, slots=True, order=True)
class Finding:
    """One lock problem.

    Attributes:
        path: File the problem is reported against, as given on the command line.
        message: Actionable description.
    """

    path: str
    message: str

    def render(self) -> str:
        """Return the finding as ``path: message``."""
        return f"{self.path}: {self.message}"


def normalize_name(name: str) -> str:
    """Return a distribution or group name normalized as in PEP 503.

    Args:
        name: Name as written in a manifest or lock.

    Returns:
        Lower-case name with runs of ``-``, ``_`` and ``.`` replaced by ``-``.
    """
    return _SEPARATORS.sub("-", name).lower()


def _specifier(text: str) -> str:
    """Return sorted, whitespace-free version clauses; empty for a direct URL."""
    compact = _WHITESPACE.sub("", text)
    if compact.startswith("@"):
        return ""
    compact = compact.removeprefix("(").removesuffix(")")
    return ",".join(sorted(part for part in compact.split(",") if part))


def parse_requirement(text: str) -> Requirement:
    """Reduce one PEP 508 requirement string to its comparable fields.

    Args:
        text: Requirement such as ``"PyYAML[cext] >= 6, < 7; python_version < '4'"``.

    Returns:
        The normalized requirement.

    Raises:
        LockInputError: The text is not a recognizable requirement.
    """
    match = _REQUIREMENT.fullmatch(text)
    if match is None:
        message = f"unsupported requirement {text!r}"
        raise LockInputError(message)
    extras = match.group("extras") or ""
    return Requirement(
        name=normalize_name(match.group("name")),
        extras=tuple(
            sorted(
                normalize_name(item.strip())
                for item in extras.split(",")
                if item.strip()
            )
        ),
        specifier=_specifier(match.group("version")),
    )


def _is_table(value: object) -> TypeGuard[dict[str, object]]:
    """Return whether a parsed TOML value is a table."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _table(parent: Mapping[str, object], key: str, *, where: str) -> dict[str, object]:
    """Return a child table, treating a missing key as empty.

    Raises:
        LockInputError: The value is not a table.
    """
    value = parent.get(key, {})
    if not _is_table(value):
        message = f"{where}.{key} must be a table"
        raise LockInputError(message)
    return value


def _array(parent: Mapping[str, object], key: str, *, where: str) -> list[object]:
    """Return a child array, treating a missing key as empty.

    Raises:
        LockInputError: The value is not an array.
    """
    value = parent.get(key, [])
    if not isinstance(value, list):
        message = f"{where}.{key} must be an array"
        raise LockInputError(message)
    return value


def _declared(items: list[object], *, where: str) -> list[Requirement]:
    """Parse an array of requirement strings from the manifest.

    Raises:
        LockInputError: An item is not a requirement string.
    """
    requirements: list[Requirement] = []
    for item in items:
        if not isinstance(item, str):
            message = f"{where} must contain requirement strings"
            raise LockInputError(message)
        requirements.append(parse_requirement(item))
    return requirements


def _recorded(items: list[object], *, where: str) -> list[Requirement]:
    """Convert lock requirement tables to comparable requirements.

    Raises:
        LockInputError: An item is not a well-formed requirement table.
    """
    requirements: list[Requirement] = []
    for item in items:
        if not _is_table(item) or not isinstance(item.get("name"), str):
            message = f"{where} must contain tables with a name"
            raise LockInputError(message)
        extras = item.get("extras", [])
        specifier = item.get("specifier", "")
        if not isinstance(extras, list) or not isinstance(specifier, str):
            message = f"{where} has malformed extras or specifier"
            raise LockInputError(message)
        requirements.append(
            Requirement(
                name=normalize_name(str(item["name"])),
                extras=tuple(sorted(normalize_name(str(extra)) for extra in extras)),
                specifier=_specifier(specifier),
            )
        )
    return requirements


def _expand_group(
    name: str, groups: Mapping[str, list[object]], *, trail: tuple[str, ...] = ()
) -> list[Requirement]:
    """Expand one PEP 735 dependency group, following ``include-group`` entries.

    Raises:
        LockInputError: The group is unknown, cyclic, or has a bad entry.
    """
    if name in trail:
        message = f"dependency-groups: include cycle through {name!r}"
        raise LockInputError(message)
    if name not in groups:
        message = f"dependency-groups: unknown group {name!r}"
        raise LockInputError(message)
    requirements: list[Requirement] = []
    for item in groups[name]:
        if isinstance(item, str):
            requirements.append(parse_requirement(item))
        elif _is_table(item) and isinstance(item.get("include-group"), str):
            included = normalize_name(str(item["include-group"]))
            requirements.extend(_expand_group(included, groups, trail=(*trail, name)))
        else:
            message = f"dependency-groups.{name} has an unsupported entry"
            raise LockInputError(message)
    return requirements


def declared_groups(manifest: Mapping[str, object]) -> dict[str, list[Requirement]]:
    """Return every dependency group with includes expanded.

    Args:
        manifest: Parsed ``pyproject.toml``.

    Returns:
        Requirements per normalized group name; legacy
        ``tool.uv.dev-dependencies`` entries are merged into ``dev``.

    Raises:
        LockInputError: A group is malformed, unknown, or included cyclically.
    """
    raw = _table(manifest, "dependency-groups", where="pyproject")
    groups: dict[str, list[object]] = {}
    for key in raw:
        groups[normalize_name(key)] = _array(raw, key, where="dependency-groups")
    expanded = {name: _expand_group(name, groups) for name in groups}
    uv = _table(_table(manifest, "tool", where="pyproject"), "uv", where="tool")
    legacy = _declared(_array(uv, "dev-dependencies", where="tool.uv"), where="tool.uv")
    if legacy:
        expanded.setdefault("dev", []).extend(legacy)
    return expanded


def _compare(
    label: str,
    *,
    declared: list[Requirement],
    recorded: list[Requirement],
    path: str,
) -> list[Finding]:
    """Report requirements that appear on only one side of the comparison."""
    wanted, locked = Counter(declared), Counter(recorded)
    findings = [
        Finding(
            path=path,
            message=f"stale lock: {label} declares {item.render()} but the lock "
            "does not record it; run uv lock",
        )
        for item in sorted((wanted - locked).elements())
    ]
    findings.extend(
        Finding(
            path=path,
            message=f"stale lock: the lock records {item.render()} for {label} "
            "but the manifest no longer declares it; run uv lock",
        )
        for item in sorted((locked - wanted).elements())
    )
    return findings


def _packages(lock: Mapping[str, object]) -> list[dict[str, object]]:
    """Return the lock package tables, rejecting a malformed inventory.

    Raises:
        LockInputError: The package list is empty or unnamed.
    """
    packages = _array(lock, "package", where="uv.lock")
    if not packages or not all(
        _is_table(item) and isinstance(item.get("name"), str) for item in packages
    ):
        message = "uv.lock needs a nonempty [[package]] list with names"
        raise LockInputError(message)
    return [item for item in packages if _is_table(item)]


def _root_package(
    packages: list[dict[str, object]], project: str
) -> dict[str, object] | None:
    """Return the lock entry of the local root project, if uv recorded one."""
    for package in packages:
        source = _table(package, "source", where="package")
        if normalize_name(str(package["name"])) == project and any(
            key in source for key in ("editable", "virtual", "directory", "path")
        ):
            return package
    return None


def _project_requirements(manifest: Mapping[str, object]) -> list[Requirement]:
    """Return ``[project]`` dependencies plus every optional-dependency list."""
    project = _table(manifest, "project", where="pyproject")
    declared = _declared(
        _array(project, "dependencies", where="project"), where="project"
    )
    optional = _table(project, "optional-dependencies", where="project")
    for extra in optional:
        declared.extend(
            _declared(_array(optional, extra, where="optional"), where="optional")
        )
    return declared


def _requirements_with_pins(manifest: Mapping[str, object]) -> list[Requirement]:
    """Return every requirement whose ``==`` pin must match the locked version.

    Build constraints are excluded because uv does not lock the build closure.
    """
    declared = _project_requirements(manifest)
    for group in declared_groups(manifest).values():
        declared.extend(group)
    uv = _table(_table(manifest, "tool", where="pyproject"), "uv", where="tool")
    for setting in ("constraint-dependencies", "override-dependencies"):
        declared.extend(_declared(_array(uv, setting, where="tool.uv"), where=setting))
    return declared


def _metadata_findings(
    manifest: Mapping[str, object], root: Mapping[str, object], *, path: str
) -> list[Finding]:
    """Compare declared project and group requirements with the root metadata."""
    metadata = _table(root, "metadata", where="package")
    findings = _compare(
        "[project] dependencies",
        declared=_project_requirements(manifest),
        recorded=_recorded(
            _array(metadata, "requires-dist", where="metadata"), where="requires-dist"
        ),
        path=path,
    )
    groups = declared_groups(manifest)
    raw_dev = _table(metadata, "requires-dev", where="metadata")
    recorded_groups = {
        normalize_name(key): _recorded(
            _array(raw_dev, key, where="requires-dev"), where=key
        )
        for key in raw_dev
    }
    for name in sorted(set(groups) | set(recorded_groups)):
        findings.extend(
            _compare(
                f"dependency group {name!r}",
                declared=groups.get(name, []),
                recorded=recorded_groups.get(name, []),
                path=path,
            )
        )
    return findings


def _manifest_findings(
    manifest: Mapping[str, object], lock: Mapping[str, object], *, path: str
) -> list[Finding]:
    """Compare uv constraint lists and ``requires-python`` with the lock."""
    uv = _table(_table(manifest, "tool", where="pyproject"), "uv", where="tool")
    recorded = _table(lock, "manifest", where="uv.lock")
    findings: list[Finding] = []
    for setting, key in _MANIFEST_TABLES:
        findings.extend(
            _compare(
                f"tool.uv.{setting}",
                declared=_declared(_array(uv, setting, where="tool.uv"), where=setting),
                recorded=_recorded(_array(recorded, key, where="manifest"), where=key),
                path=path,
            )
        )
    project = _table(manifest, "project", where="pyproject")
    wanted = project.get("requires-python")
    locked = lock.get("requires-python")
    if (
        "workspace" not in uv
        and isinstance(wanted, str)
        and isinstance(locked, str)
        and _WHITESPACE.sub("", wanted) != _WHITESPACE.sub("", locked)
    ):
        findings.append(
            Finding(
                path=path,
                message=f"stale lock: requires-python is {wanted!r} in the manifest "
                f"but {locked!r} in the lock; run uv lock",
            )
        )
    return findings


def _pin_findings(
    requirements: list[Requirement], packages: list[dict[str, object]], *, path: str
) -> list[Finding]:
    """Report ``==`` pins whose locked versions all differ from the pin."""
    versions: dict[str, set[str]] = {}
    for package in packages:
        version = package.get("version")
        if isinstance(version, str):
            versions.setdefault(normalize_name(str(package["name"])), set()).add(
                version
            )
    findings: list[Finding] = []
    for requirement in sorted(set(requirements)):
        match = _EXACT_PIN.fullmatch(requirement.specifier)
        locked = versions.get(requirement.name, set())
        if match and locked and match.group("version") not in locked:
            findings.append(
                Finding(
                    path=path,
                    message=f"pin drift: {requirement.render()} is declared but the "
                    f"lock holds {', '.join(sorted(locked))}",
                )
            )
    return findings


def _git_problem(url: str) -> str | None:
    """Describe a Git source that does not end in a full commit hash."""
    commit = url.rsplit("#", 1)[-1] if "#" in url else ""
    if _COMMIT.fullmatch(commit) and len(commit) in _COMMIT_LENGTHS:
        return None
    return "Git source is not pinned to a full commit hash"


def _artifact_problem(package: Mapping[str, object]) -> str | None:
    """Describe a missing hash or mutable Git reference for one package."""
    source = _table(package, "source", where="package")
    git = source.get("git")
    if isinstance(git, str):
        return _git_problem(git)
    if not any(key in source for key in _HASHED_SOURCES):
        return None
    return _hash_problem(package)


def _hash_problem(package: Mapping[str, object]) -> str | None:
    """Describe a registry or URL package whose artifacts lack hashes."""
    artifacts: list[object] = list(_array(package, "wheels", where="package"))
    sdist = package.get("sdist")
    if sdist is not None:
        artifacts.append(sdist)
    if not artifacts:
        return "no distribution files are locked, so nothing can be hash-checked"
    for artifact in artifacts:
        digest = artifact.get("hash") if _is_table(artifact) else None
        if not isinstance(digest, str) or _HASH.fullmatch(digest) is None:
            return "a distribution file has no sha256, sha384 or sha512 hash"
    return None


def _artifact_findings(
    packages: list[dict[str, object]], *, path: str
) -> list[Finding]:
    """Report packages whose locked artifacts cannot be verified on install."""
    findings: list[Finding] = []
    for package in packages:
        problem = _artifact_problem(package)
        if problem:
            label = f"{package['name']}=={package.get('version', '?')}"
            findings.append(Finding(path=path, message=f"{label}: {problem}"))
    return findings


def evaluate(
    manifest: Mapping[str, object], lock: Mapping[str, object], *, lock_path: str
) -> list[Finding]:
    """Compare a parsed manifest and lock and return sorted findings.

    Args:
        manifest: Parsed ``pyproject.toml``.
        lock: Parsed ``uv.lock``.
        lock_path: Label used for every finding.

    Returns:
        Findings sorted by path and message; empty when the lock is fresh.

    Raises:
        LockInputError: Either document has an unexpected structure.
    """
    project = _table(manifest, "project", where="pyproject")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        message = "pyproject.toml needs [project] name; virtual roots are unsupported"
        raise LockInputError(message)
    packages = _packages(lock)
    findings = _manifest_findings(manifest, lock, path=lock_path)
    root = _root_package(packages, normalize_name(name))
    if root is None:
        findings.append(
            Finding(
                path=lock_path,
                message=f"stale lock: no local package {name!r}; run uv lock",
            )
        )
    else:
        findings.extend(_metadata_findings(manifest, root, path=lock_path))
    findings.extend(
        _pin_findings(_requirements_with_pins(manifest), packages, path=lock_path)
    )
    findings.extend(_artifact_findings(packages, path=lock_path))
    return sorted(findings)


def _load(path: Path) -> dict[str, object]:
    """Parse one TOML file."""
    with path.open("rb") as handle:
        return tomllib.load(handle)


_SELF_TEST_MANIFEST = """
[project]
name = "demo"
requires-python = ">=3.13"
dependencies = ["PyYAML >= 6, < 7"]
[dependency-groups]
lint = ["ruff==0.17.1"]
dev = [{include-group = "lint"}]
"""
_SELF_TEST_LOCK = """
requires-python = ">=3.13"
[[package]]
name = "demo"
version = "0.1.0"
source = {{ editable = "." }}
[package.metadata]
requires-dist = [{{ name = "pyyaml", specifier = ">=6,<7" }}]
[package.metadata.requires-dev]
dev = [{{ name = "ruff", specifier = "==0.17.1" }}]
lint = [{{ name = "ruff", specifier = "==0.17.1" }}]
[[package]]
name = "pyyaml"
version = "6.0.3"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://example.invalid/pyyaml.whl", hash = "{pyyaml}" }}]
[[package]]
name = "ruff"
version = "{ruff}"
source = {{ registry = "https://pypi.org/simple" }}
wheels = [{{ url = "https://example.invalid/ruff.whl", hash = "sha256:{digest}" }}]
[[package]]
name = "tool"
version = "1.0.0"
source = {{ git = "https://example.invalid/tool.git?rev=main#{commit}" }}
"""


def self_test() -> list[str]:
    """Check a fresh synthetic lock and a stale one without hashes.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    manifest = tomllib.loads(_SELF_TEST_MANIFEST)
    digest = "a" * _SHA256_HEX_LENGTH
    fresh = tomllib.loads(
        _SELF_TEST_LOCK.format(
            pyyaml=f"sha256:{digest}",
            ruff="0.17.1",
            digest=digest,
            commit="b" * _SHA1_HEX_LENGTH,
        )
    )
    stale = tomllib.loads(
        _SELF_TEST_LOCK.replace(">=6,<7", ">=5").format(
            pyyaml="", ruff="0.16.0", digest=digest, commit="main"
        )
    )
    failures: list[str] = []
    clean = evaluate(manifest, fresh, lock_path="uv.lock")
    if clean:
        failures.append(f"fresh lock reported: {[item.render() for item in clean]}")
    rendered = "\n".join(
        item.render() for item in evaluate(manifest, stale, lock_path="uv.lock")
    )
    failures.extend(
        f"expected finding: {needle}"
        for needle in (
            "declares pyyaml<7,>=6",
            "records pyyaml>=5",
            "pin drift: ruff==0.17.1",
            "pyyaml==6.0.3: a distribution file has no",
            "tool==1.0.0: Git source is not pinned",
        )
        if needle not in rendered
    )
    return failures


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    failures = self_test()
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return _FINDINGS
    print("check_lock_freshness self-test passed")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Check one manifest and lock pair and print findings.

    Args:
        argv: Command-line arguments; ``sys.argv[1:]`` when None.

    Returns:
        0 when the lock is fresh and hashed, 1 on findings, 2 on unusable input.
    """
    arguments = _parser().parse_args(argv)
    if arguments.self_test:
        return _run_self_test()
    try:
        findings = evaluate(
            _load(arguments.project),
            _load(arguments.lock),
            lock_path=arguments.lock.as_posix(),
        )
    except (OSError, tomllib.TOMLDecodeError, LockInputError) as error:
        print(f"check-lock-freshness: cannot check: {error}", file=sys.stderr)
        return _INVALID
    for finding in findings:
        print(finding.render())
    print(f"check-lock-freshness: {len(findings)} findings")
    return _FINDINGS if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
