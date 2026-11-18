"""Root artifact checks inspect untracked files without deleting user content."""

from pathlib import Path

import pytest
from scripts.checks.docs import _REQUIRED, check

from agent_kit.infrastructure.catalog import ROOT_DOCUMENTS


def test_repository_ownership_file_is_a_root_document() -> None:
    assert "OWNERSHIP.md" in ROOT_DOCUMENTS
    assert "OWNERSHIP.md" in _REQUIRED
    assert "projects.md" not in ROOT_DOCUMENTS
    assert "projects.md" not in _REQUIRED


@pytest.fixture
def documented_root(tmp_path: Path) -> Path:
    for name in _REQUIRED:
        (tmp_path / name).write_text("Project entry.\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "name",
    [
        "download.html",
        "page.HTM",
        "research.rst",
        "out_final.txt",
        "scratch.md",
        "download.mdx",
        "download.json",
        "response.xml",
        "copied_pyproject.toml",
        ".research.html",
    ],
)
def test_unapproved_root_artifact_fails_without_mutation(
    documented_root: Path, name: str
) -> None:
    artifact = documented_root / name
    artifact.write_text("Research output.\n", encoding="utf-8")

    failures = check(documented_root)

    assert any(f"unexpected root artifact: {name}" in failure for failure in failures)
    assert artifact.read_text(encoding="utf-8") == "Research output.\n"


def test_standard_root_documents_and_data_remain_allowed(
    documented_root: Path,
) -> None:
    for name in ("CHANGELOG.md", "GOVERNANCE.md", "SUPPORT.md"):
        (documented_root / name).write_text(
            "Project documentation.\n", encoding="utf-8"
        )
    for name in (
        "catalog.json",
        "cspell.json",
        "license-allowlist.json",
        "package.json",
        ".jscpd.json",
        ".mcp.json",
    ):
        (documented_root / name).write_text("{}\n", encoding="utf-8")
    for name in ("pyproject.toml", "ruff.toml", "ty.toml", ".cz.toml"):
        (documented_root / name).write_text(
            "# Project configuration.\n", encoding="utf-8"
        )

    assert check(documented_root) == []


def test_nested_authored_documents_are_not_root_artifacts(
    documented_root: Path,
) -> None:
    docs = documented_root / "docs"
    docs.mkdir()
    (docs / "design.md").write_text("Approved project design.\n", encoding="utf-8")
    site = documented_root / "site"
    site.mkdir()
    (site / "index.html").write_text("<h1>Authored site</h1>\n", encoding="utf-8")

    assert check(documented_root) == []
