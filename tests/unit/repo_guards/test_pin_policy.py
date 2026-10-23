"""Version-pin policy for tooling, automation, containers, and agent integrations."""

from pathlib import Path
import runpy

import pytest
import scripts.verify as verify_module

_ROOT = Path(__file__).resolve().parents[3]
_CHECKER = runpy.run_path(
    str(_ROOT / "packages/shared/.apm/skills/kit-verify-change/assets/check_pins.py")
)
_DIGEST = "sha256:" + "a" * 64


def _scan(root: Path, files: dict[str, str]) -> list[str]:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    findings = _CHECKER["scan"](root)
    return [finding.message for finding in findings]


def test_repository_has_no_floating_versions() -> None:
    assert _CHECKER["scan"](_ROOT) == []
    assert verify_module._CHECKS["pins"][1].endswith("check_pins.py")


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (
            {"pyproject.toml": '[dependency-groups]\ndev = ["ruff>=0.17"]\n'},
            "not pinned with ==",
        ),
        (
            {"pyproject.toml": '[build-system]\nrequires = ["hatchling"]\n'},
            "not pinned with ==",
        ),
        (
            {"pyproject.toml": '[tool.uv]\nbuild-constraint-dependencies = ["x>=1"]\n'},
            "not pinned with ==",
        ),
        (
            {"pyproject.toml": '[project]\ndependencies = ["pyyaml>=6"]\n'},
            "upper bound",
        ),
        ({"tox.ini": "[tox]\nrequires =\n    tox>=4\n"}, "not pinned with =="),
        (
            {".pre-commit-config.yaml": "repos:\n  - repo: x\n    rev: v1.0.0\n"},
            "mutable",
        ),
        (
            {
                ".pre-commit-config.yaml": "repos:\n  - repo: local\n    hooks:\n"
                "      - id: x\n        entry: lycheeverse/lychee:0.24.2\n"
            },
            "digest",
        ),
        (
            {
                ".pre-commit-config.yaml": "repos:\n  - repo: local\n    hooks:\n"
                "      - id: x\n        entry: bunx --bun jscpd@5.4.1\n"
            },
            "package runner",
        ),
        (
            {
                ".pre-commit-config.yaml": "repos:\n  - repo: local\n    hooks:\n"
                "      - id: x\n        additional_dependencies:\n"
                "          - types-pyyaml\n"
            },
            "exact version",
        ),
        (
            {"package.json": '{"devDependencies": {"jscpd": "^5.4.1"}}'},
            "pin exactly",
        ),
        ({"package.json": '{"devDependencies": {"jscpd": "5.4.1"}}'}, "lockfile"),
        ({"Dockerfile": "FROM python:3.13-slim\n"}, "digest"),
        (
            {".devcontainer/devcontainer.json": '{"image": "python:3.13"}'},
            "digest",
        ),
        (
            {
                ".devcontainer/devcontainer.json": '{"features": '
                '{"ghcr.io/devcontainers/features/node:2": {"version": "22"}}}'
            },
            "not locked by digest",
        ),
        (
            {
                ".devcontainer/devcontainer.json": '{"features": '
                '{"ghcr.io/devcontainers/features/node:2": {"version": "lts"}}}'
            },
            "not exact",
        ),
        (
            {
                ".github/workflows/ci.yml": "jobs:\n  a:\n    steps:\n      - run: uv sync\n"
            },
            "--locked",
        ),
        (
            {
                ".github/workflows/ci.yml": "jobs:\n  a:\n    steps:\n      - run: npm install\n"
            },
            "npm ci",
        ),
        (
            {
                ".github/workflows/ci.yml": "jobs:\n  a:\n    steps:\n"
                "      - run: curl -fsSL https://example.org/i.sh | bash\n"
            },
            "piped to a shell",
        ),
        (
            {
                ".github/workflows/ci.yml": "jobs:\n  a:\n    steps:\n"
                "      - with:\n          version: latest\n"
            },
            "floating tool version",
        ),
        ({"Taskfile.yml": "tasks:\n  a:\n    cmds:\n      - uvx ruff\n"}, "runner"),
        (
            {
                ".mcp.json": '{"mcpServers": {"x": {"command": "npx", "args": ["-y", "tool"]}}}'
            },
            "exact package@version",
        ),
        (
            {
                ".vscode/mcp.json": '{"servers": {"x": {"command": "docker", '
                '"args": ["run", "image:1"]}}}'
            },
            "digest",
        ),
        (
            {".mcp.json": '{"mcpServers": {"x": {"type": "http", "url": "http://x"}}}'},
            "HTTPS",
        ),
    ],
)
def test_floating_reference_is_rejected(
    tmp_path: Path, files: dict[str, str], expected: str
) -> None:
    assert any(expected in message for message in _scan(tmp_path, files))


def test_locked_and_digest_pinned_references_are_accepted(tmp_path: Path) -> None:
    files = {
        "pyproject.toml": '[project]\ndependencies = ["pyyaml>=6.0.2,<7"]\n'
        '[dependency-groups]\ndev = ["ruff==0.17.1", {include-group = "x"}]\n',
        "package.json": '{"devDependencies": {"jscpd": "5.4.1"}}',
        "bun.lock": "{}",
        "Dockerfile": f"FROM python:3.13@{_DIGEST} AS base\nFROM base\n",
        ".devcontainer/devcontainer.json": '{"build": {"dockerfile": "Dockerfile"}, '
        '"features": {"ghcr.io/x/node:2": {"version": "22.23.4"}}}',
        ".devcontainer/devcontainer-lock.json": '{"features": {"ghcr.io/x/node:2": '
        f'{{"resolved": "ghcr.io/x/node@{_DIGEST}", "integrity": "{_DIGEST}"}}}}}}',
        ".github/workflows/ci.yml": "jobs:\n  a:\n    uses: $/.github/workflows/b.yml\n"
        "  b:\n    steps:\n      - run: uv sync --locked\n"
        "      - run: bun install --frozen-lockfile\n      - run: npm ci\n",
        ".mcp.json": '{"mcpServers": {"x": {"command": "npx", "args": ["-y", '
        '"tool@1.2.3"]}, "y": {"type": "http", "url": "https://example.org/mcp"}}}',
    }
    assert _scan(tmp_path, files) == []


def test_unreadable_input_exits_two(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("not = [valid", encoding="utf-8")

    assert _CHECKER["main"](["--root", str(tmp_path)]) == 2
