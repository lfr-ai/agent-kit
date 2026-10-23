"""Reject floating versions in repository tooling and automation files.

Each check runs only when its file exists under ``--root``:

- ``pyproject.toml``: build requirements, dependency groups and uv constraint
  lists are pinned with ``==``; published dependencies have an upper bound.
- ``tox.ini``: provisioning ``requires`` are pinned with ``==``.
- ``.pre-commit-config.yaml``: remote ``rev`` values are full commit SHAs, image
  entries carry a digest, entries never run package runners, and
  ``additional_dependencies`` are exact.
- ``package.json``: dependency versions are exact and a lockfile is committed.
- Dockerfiles and dev containers: base images and images carry a digest, features
  are locked by digest, and feature ``version`` options are exact.
- GitHub workflows, local actions and ``Taskfile.yml``: commands never use
  package runners, ad-hoc installs, unlocked syncs or ``latest`` versions.
- MCP manifests: package runners use an exact version and containers a digest.

The scan reads files only; it never resolves tags or contacts a registry.
Templates (``*.template``) are skipped because they hold review placeholders.
Exit codes: 0 clean, 1 findings, 2 unreadable input or bad arguments.
"""

import argparse
from collections.abc import Iterator
import configparser
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import tempfile
import tomllib

_FINDINGS = 1
_INVALID = 2
_NAMED_STAGE = 3  # FROM <image> AS <name>
_SHA1_HEX_LENGTH = 40
_SHA256_HEX_LENGTH = 64
_SELF_TEST_MIN_DIRTY_FINDINGS = 9  # every bad fixture line is counted
_SKIPPED_DIRECTORIES = frozenset(
    {".git", ".venv", ".tox", "node_modules", "build", "dist", "apm_modules"}
)
_EXACT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^\]]*\])?\s*===?\s*[^\s,*;<>=!~]+\s*(;.*)?$"
)
_BOUNDED = re.compile(r"(==|<|~=)")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.+-]+)?$")
_NPM_EXACT = re.compile(r"^(@?[^@\s]+)@\d+\.\d+\.\d+([-+][0-9A-Za-z.+-]+)?$")
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}\b")
_SHA = re.compile(r"[0-9a-f]{40}")
_IMAGE = re.compile(r"^[\w.-]+(:\d+)?(/[\w.-]+)+(:[\w.-]+)?(@sha256:[0-9a-f]{64})?$")
_COMMENT = re.compile(r"(^|\s)#.*$")
_RUNNERS = re.compile(r"(^|[\s;&|(\"'])(npx|bunx|uvx|pipx)(\s|$)")
_COMMAND_RULES = (
    (_RUNNERS, "package runner downloads unpinned code; use a locked dependency"),
    (
        re.compile(r"\bpip3?\s+install\b(?!.*--require-hashes)"),
        "pip install without --require-hashes; install from a hashed lock",
    ),
    (
        re.compile(r"\bnpm\s+(install|i)\b"),
        "npm install can rewrite the lock; use npm ci",
    ),
    (
        re.compile(r"\b(pnpm|yarn|bun)\s+(add|dlx)\b"),
        "ad-hoc package install; change the manifest and lockfile instead",
    ),
    (
        re.compile(
            r"\b(bun|pnpm|yarn)\s+install\b(?!.*(--frozen-lockfile|--immutable))"
        ),
        "install without a frozen lockfile",
    ),
    (
        re.compile(r"\buv\s+(sync|run)\b(?!.*(--locked|--frozen|--no-sync))"),
        "uv command without --locked or --frozen may re-resolve dependencies",
    ),
    (
        re.compile(r"\buv\s+(add|pip\s+install|tool\s+(install|run))\b"),
        "ad-hoc uv install; change pyproject.toml and uv.lock instead",
    ),
    (
        re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(sh|bash|zsh|python[0-9.]*)\b"),
        "downloaded script piped to a shell; pin and verify it first",
    ),
    (re.compile(r"\bgo\s+install\s+\S+@latest\b"), "go install @latest is floating"),
    (
        re.compile(
            r"^\s*-?\s*[\w-]*version\s*:\s*[\"']?(latest|stable|lts|\*)[\"']?\s*$",
            re.IGNORECASE,
        ),
        "floating tool version; pin an exact release",
    ),
)


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One reportable unpinned reference.

    Attributes:
        path: File that contains the reference.
        line: One-based line number, or 1 when no line is known.
        message: Human-readable explanation.
    """

    path: Path
    line: int
    message: str

    def render(self, root: Path) -> str:
        """Return the deterministic ``path:line: message`` form."""
        relative = (
            self.path.relative_to(root) if self.path.is_relative_to(root) else self.path
        )
        return f"{relative.as_posix()}:{self.line}: {self.message}"


def _line_of(text: str, needle: str) -> int:
    """Return the first one-based line that contains ``needle``, or 1."""
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    return 1


def _files(root: Path, *patterns: str) -> Iterator[Path]:
    """Yield matching files below ``root`` outside generated directories."""
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and not _SKIPPED_DIRECTORIES & set(
                path.relative_to(root).parts
            ):
                yield path


def _requirements(value: object) -> list[str]:
    """Return requirement strings from a list, including uv's table form."""
    if not isinstance(value, list):
        return []
    found: list[str] = []
    for item in value:
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict) and isinstance(item.get("requirement"), str):
            found.append(item["requirement"])
    return found


def check_pyproject(path: Path) -> list[Finding]:
    """Require exact tool pins and bounded published dependencies.

    Args:
        path: ``pyproject.toml`` file.
    """
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    findings = [
        Finding(
            path=path,
            line=_line_of(text, requirement),
            message=f"tooling requirement '{requirement}' is not pinned with ==",
        )
        for requirement in _tooling_requirements(data)
        if not _EXACT.match(requirement)
    ]
    findings.extend(
        Finding(
            path=path,
            line=_line_of(text, requirement),
            message=f"published dependency '{requirement}' needs an upper bound",
        )
        for requirement in _published_requirements(data)
        if not _BOUNDED.search(requirement.split(";", 1)[0])
    )
    return findings


def _tooling_requirements(data: dict[str, object]) -> list[str]:
    """Return build, dependency-group and uv requirements that need ``==``."""
    exact: list[str] = []
    build = data.get("build-system")
    if isinstance(build, dict):
        exact += _requirements(build.get("requires"))
    exact += _table_requirements(data.get("dependency-groups"))
    tool = data.get("tool")
    uv = tool.get("uv") if isinstance(tool, dict) else None
    if isinstance(uv, dict):
        for key in (
            "dev-dependencies",
            "constraint-dependencies",
            "build-constraint-dependencies",
            "override-dependencies",
        ):
            exact += _requirements(uv.get(key))
    return exact


def _published_requirements(data: dict[str, object]) -> list[str]:
    """Return project and optional dependencies that need an upper bound."""
    project = data.get("project")
    if not isinstance(project, dict):
        return []
    return [
        *_requirements(project.get("dependencies")),
        *_table_requirements(project.get("optional-dependencies")),
    ]


def _table_requirements(table: object) -> list[str]:
    """Return requirements from every list in a table of requirement lists."""
    if not isinstance(table, dict):
        return []
    return [
        requirement
        for members in table.values()
        for requirement in _requirements(members)
    ]


def check_tox(path: Path) -> list[Finding]:
    """Require exact tox provisioning requirements.

    Args:
        path: ``tox.ini`` file.
    """
    text = path.read_text(encoding="utf-8")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(text)
    raw = parser.get("tox", "requires", fallback="")
    return [
        Finding(
            path=path,
            line=_line_of(text, requirement),
            message=f"tox requirement '{requirement}' is not pinned with ==",
        )
        for requirement in (line.strip() for line in raw.splitlines())
        if requirement and not _EXACT.match(requirement)
    ]


def _dependency_items(
    lines: list[str], index: int, inline: str
) -> list[tuple[int, str]]:
    """Return ``additional_dependencies`` items with their line numbers."""
    if inline.startswith("["):
        return [
            (index + 1, item.strip().strip("\"'"))
            for item in inline.strip("[]").split(",")
            if item.strip()
        ]
    indent = len(lines[index]) - len(lines[index].lstrip())
    items: list[tuple[int, str]] = []
    header_number = index + 1
    for offset, line in enumerate(lines[index + 1 :], start=header_number + 1):
        stripped = line.strip()
        if not stripped:
            continue
        if len(line) - len(line.lstrip()) <= indent or not stripped.startswith("- "):
            break
        items.append((offset, stripped.removeprefix("- ").strip().strip("\"'")))
    return items


def check_precommit(path: Path) -> list[Finding]:
    """Require frozen hook revisions, digests and exact hook dependencies.

    Args:
        path: ``.pre-commit-config.yaml`` file.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    findings: list[Finding] = []
    for index, raw in enumerate(lines):
        line = _COMMENT.sub("", raw).strip()
        number = index + 1
        key, _, value = line.removeprefix("- ").partition(":")
        value = value.strip().strip("\"'")
        if key == "rev" and not _SHA.fullmatch(value):
            findings.append(
                Finding(
                    path=path,
                    line=number,
                    message=f"hook rev '{value}' is mutable; freeze it to a commit SHA",
                )
            )
        elif key == "entry":
            first = value.split(" ", 1)[0]
            if _IMAGE.match(first) and ":" in first and not _DIGEST.search(first):
                findings.append(
                    Finding(
                        path=path,
                        line=number,
                        message=f"hook image '{first}' is not pinned by digest",
                    )
                )
            findings.extend(
                Finding(path=path, line=number, message=message)
                for pattern, message in _COMMAND_RULES
                if pattern.search(value)
            )
        elif key == "additional_dependencies":
            findings.extend(
                Finding(
                    path=path,
                    line=item_line,
                    message=f"hook dependency '{item}' is not an exact version",
                )
                for item_line, item in _dependency_items(lines, index, value)
                if not (_EXACT.match(item) or _NPM_EXACT.match(item))
            )
    return findings


def check_package_json(path: Path) -> list[Finding]:
    """Require exact JavaScript dependency versions and a committed lockfile.

    Args:
        path: ``package.json`` file.
    """
    text = path.read_text(encoding="utf-8")
    data: object = json.loads(text)
    findings: list[Finding] = []
    if isinstance(data, dict):
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            entries = data.get(section)
            if not isinstance(entries, dict):
                continue
            findings.extend(
                Finding(
                    path=path,
                    line=_line_of(text, f'"{name}"'),
                    message=f"{section} '{name}' uses range '{version}'; pin exactly",
                )
                for name, version in entries.items()
                if not (isinstance(version, str) and _SEMVER.match(version))
            )
    locks = (
        "bun.lock",
        "bun.lockb",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    )
    if not any((path.parent / name).is_file() for name in locks):
        findings.append(
            Finding(path=path, line=1, message="no committed JavaScript lockfile")
        )
    return findings


def check_dockerfile(path: Path) -> list[Finding]:
    """Require every external base image to carry a digest.

    Args:
        path: Dockerfile or Containerfile.
    """
    findings: list[Finding] = []
    stages: set[str] = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        arguments = _from_arguments(raw)
        if not arguments:
            continue
        image = arguments[0]
        stage = _stage_name(arguments)
        if stage is not None:
            stages.add(stage)
        if _is_unpinned_base(image, stages):
            findings.append(
                Finding(
                    path=path,
                    line=number,
                    message=f"base image '{image}' is not pinned by digest",
                )
            )
    return findings


def _from_arguments(raw: str) -> list[str]:
    """Return the non-flag arguments of a ``FROM`` line, else an empty list."""
    words = raw.split()
    if not words or words[0].upper() != "FROM":
        return []
    return [word for word in words[1:] if not word.startswith("--")]


def _stage_name(arguments: list[str]) -> str | None:
    """Return the case-folded stage name from ``<image> AS <name>``, if any."""
    if len(arguments) < _NAMED_STAGE:
        return None
    _, keyword, stage, *_ = arguments
    return stage.casefold() if keyword.upper() == "AS" else None


def _is_unpinned_base(image: str, stages: set[str]) -> bool:
    """Return whether an external base image lacks a digest."""
    if image.casefold() in stages or image == "scratch" or "$" in image:
        return False
    return not _DIGEST.search(image)


def _json_document(path: Path) -> object:
    """Read strict JSON or JSON with whole-line ``//`` comments."""
    text = path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("//")]
    return json.loads("\n".join(lines))


def check_devcontainer(path: Path) -> list[Finding]:
    """Require digest-pinned images and digest-locked, exact features.

    Args:
        path: ``devcontainer.json`` file.
    """
    data = _json_document(path)
    if not isinstance(data, dict):
        return [Finding(path=path, line=1, message="dev container must be an object")]
    text = path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    image = data.get("image")
    if isinstance(image, str) and not _DIGEST.search(image):
        findings.append(
            Finding(
                path=path,
                line=_line_of(text, image),
                message=f"image '{image}' is not pinned by digest",
            )
        )
    features = data.get("features")
    if isinstance(features, dict) and features:
        findings.extend(_feature_findings(path, text, features))
    return findings


def _feature_findings(
    path: Path, text: str, features: dict[str, object]
) -> list[Finding]:
    """Report dev container features without a digest lock or exact version."""
    lock_path = path.parent / (
        ".devcontainer-lock.json"
        if path.name.startswith(".")
        else "devcontainer-lock.json"
    )
    locked: object = _json_document(lock_path) if lock_path.is_file() else {}
    entries = locked.get("features") if isinstance(locked, dict) else None
    findings: list[Finding] = []
    for reference, options in features.items():
        entry = entries.get(reference) if isinstance(entries, dict) else None
        if not _is_digest_locked(entry):
            findings.append(
                Finding(
                    path=path,
                    line=_line_of(text, reference),
                    message=f"feature '{reference}' is not locked by digest",
                )
            )
        version = options.get("version") if isinstance(options, dict) else None
        if isinstance(version, str) and not _SEMVER.match(version):
            findings.append(
                Finding(
                    path=path,
                    line=_line_of(text, reference),
                    message=f"feature '{reference}' version '{version}' is not exact",
                )
            )
    return findings


def _is_digest_locked(entry: object) -> bool:
    """Return whether a lockfile feature entry carries a digest and integrity."""
    return bool(
        isinstance(entry, dict)
        and _DIGEST.search(str(entry.get("resolved", "")))
        and str(entry.get("integrity", "")).startswith("sha256:")
    )


def check_commands(path: Path) -> list[Finding]:
    """Reject floating installs in workflow and task command files.

    Args:
        path: Workflow, action or Taskfile.
    """
    findings: list[Finding] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = _COMMENT.sub("", raw)
        findings.extend(
            Finding(path=path, line=number, message=message)
            for pattern, message in _COMMAND_RULES
            if pattern.search(line)
        )
    return findings


def check_mcp(path: Path) -> list[Finding]:
    """Require exact versions or digests for command-based MCP servers.

    Args:
        path: ``.mcp.json`` or ``.vscode/mcp.json`` file.
    """
    data = _json_document(path)
    text = path.read_text(encoding="utf-8")
    servers: object = None
    if isinstance(data, dict):
        servers = data.get("servers", data.get("mcpServers"))
    findings: list[Finding] = []
    if not isinstance(servers, dict):
        return findings
    for name, server in servers.items():
        message = _server_problem(server) if isinstance(server, dict) else None
        if message is not None:
            findings.append(
                Finding(
                    path=path,
                    line=_line_of(text, f'"{name}"'),
                    message=f"{name}: {message}",
                )
            )
    return findings


def _server_problem(server: dict[str, object]) -> str | None:
    """Describe why one MCP server entry is not pinned, if it is not."""
    command = server.get("command")
    args = server.get("args")
    tokens = (
        [item for item in args if isinstance(item, str)]
        if isinstance(args, list)
        else []
    )
    url = server.get("url")
    if isinstance(url, str) and not url.startswith("https://"):
        return "remote server does not use HTTPS"
    if command in {"npx", "bunx", "pnpm", "yarn"} and not any(
        _NPM_EXACT.match(token) for token in tokens
    ):
        return "package runner has no exact package@version argument"
    if command in {"uvx", "pipx"} and not any(
        _EXACT.match(token) or _NPM_EXACT.match(token) for token in tokens
    ):
        return "Python runner has no exact package==version argument"
    if command in {"docker", "podman"} and not any(
        _DIGEST.search(token) for token in tokens
    ):
        return "container server image is not pinned by digest"
    return None


def scan(root: Path) -> list[Finding]:
    """Scan every supported file under one repository root.

    Args:
        root: Repository root directory.
    """
    findings: list[Finding] = []
    single = (
        ("pyproject.toml", check_pyproject),
        ("tox.ini", check_tox),
        (".pre-commit-config.yaml", check_precommit),
        ("package.json", check_package_json),
        (".mcp.json", check_mcp),
        (".vscode/mcp.json", check_mcp),
    )
    for relative, checker in single:
        if (root / relative).is_file():
            findings.extend(checker(root / relative))
    for path in _files(root, "**/Dockerfile", "**/*.Dockerfile", "**/Containerfile"):
        findings.extend(check_dockerfile(path))
    for path in _files(
        root, ".devcontainer/**/devcontainer.json", ".devcontainer.json"
    ):
        findings.extend(check_devcontainer(path))
    for path in _files(
        root,
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        ".github/actions/**/action.yml",
        ".github/actions/**/action.yaml",
        "Taskfile.yml",
        "Taskfile.yaml",
    ):
        findings.extend(check_commands(path))
    return findings


def _self_test() -> int:
    """Check one pinned and one floating fixture repository."""
    good = {
        "pyproject.toml": '[project]\ndependencies = ["pyyaml>=6,<7"]\n'
        '[dependency-groups]\ndev = ["ruff==0.17.1"]\n'
        '[build-system]\nrequires = ["hatchling==1.27.0"]\n',
        "tox.ini": "[tox]\nrequires =\n    tox==4.67.1\n",
        ".pre-commit-config.yaml": "repos:\n  - repo: https://example.org/hooks\n"
        f"    rev: {'a' * _SHA1_HEX_LENGTH}  # frozen: v1\n    hooks:\n      - id: x\n"
        "        additional_dependencies: [ruff==0.17.1]\n",
        "package.json": '{"devDependencies": {"jscpd": "5.4.1"}}',
        "bun.lock": "{}",
        "Dockerfile": f"FROM python:3.13@sha256:{'b' * _SHA256_HEX_LENGTH} AS base\nFROM base\n",
        "Taskfile.yml": "tasks:\n  a:\n    cmds:\n      - uv sync --locked\n",
    }
    bad = {
        "pyproject.toml": '[project]\ndependencies = ["pyyaml>=6"]\n'
        '[dependency-groups]\ndev = ["ruff>=0.17"]\n',
        ".pre-commit-config.yaml": "repos:\n  - repo: https://example.org/hooks\n"
        "    rev: v1.0.0\n    hooks:\n      - id: x\n        entry: npx tool\n",
        "package.json": '{"devDependencies": {"jscpd": "^5.4.1"}}',
        "Dockerfile": "FROM python:3.13\n",
        "Taskfile.yml": "tasks:\n  a:\n    cmds:\n      - uv sync\n      - pip install x\n",
        ".mcp.json": '{"mcpServers": {"x": {"command": "npx", "args": ["tool"]}}}',
    }
    with tempfile.TemporaryDirectory() as directory:
        for name, files in (("good", good), ("bad", bad)):
            root = Path(directory) / name
            root.mkdir()
            for relative, content in files.items():
                (root / relative).write_text(content, encoding="utf-8")
        clean = scan(Path(directory) / "good")
        dirty = scan(Path(directory) / "bad")
    if clean or len(dirty) < _SELF_TEST_MIN_DIRTY_FINDINGS:
        print(f"self-test failed: clean={clean} dirty={len(dirty)}", file=sys.stderr)
        return _FINDINGS
    print("check_pins self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the pin scan or its self-test and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path())
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        return _self_test()
    root = arguments.root.resolve()
    if not root.is_dir():
        print(f"Cannot scan pins: {root} is not a directory", file=sys.stderr)
        return _INVALID
    try:
        findings = scan(root)
    except (OSError, UnicodeDecodeError, ValueError, configparser.Error) as error:
        print(f"Cannot scan pins: {error}", file=sys.stderr)
        return _INVALID
    for finding in findings:
        print(finding.render(root))
    print(f"check-pins: {len(findings)} findings")
    return _FINDINGS if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
