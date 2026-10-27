"""Guards that keep the kit-improve loop narrow, portable and approval-gated."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

_ROOT = Path(__file__).parents[3]
_SKILL = _ROOT / "packages/shared/.apm/skills/kit-improve"
_PROMPT = _ROOT / "packages/shared/.apm/prompts/kit-improve.prompt.md"
_LINK = re.compile(r"\]\((?!https?:|#|\.\./)([^)#\s]+)")
_REQUIRED_PROHIBITIONS = (
    "Never push or merge to the default branch",
    "force-push",
    "rewrite pushed history",
    "tag",
    "change repository settings",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_skill_boundaries_keep_every_publication_prohibition() -> None:
    """The portable skill cannot silently regain a destructive git capability."""
    boundaries = _text(_SKILL / "SKILL.md").split("## Boundaries", 1)[1]
    boundaries = boundaries.split("## Acceptance gates", 1)[0]

    for phrase in _REQUIRED_PROHIBITIONS:
        assert phrase in boundaries


def test_skill_requires_approval_before_every_remote_action() -> None:
    """Push, pull request and merge happen only after the user approves."""
    body = _text(_SKILL / "SKILL.md")

    assert "only\n   after approval" in body
    assert "once the user also approves merging" in body
    assert "asked for in this session" in body


def test_skill_verifies_the_checkout_before_editing() -> None:
    """The skill refuses a checkout whose origin or tree state is unverified."""
    body = _text(_SKILL / "SKILL.md")

    assert "remote get-url origin" in body
    assert "status --short" in body
    assert "never search the disk or clone one unprompted" in body


def test_skill_edits_source_never_installed_copies() -> None:
    """Generated and installed locations are named as off limits."""
    body = _text(_SKILL / "SKILL.md")

    for location in ("apm_modules/", ".github/skills/", ".claude/skills/"):
        assert location in body
    assert "Never edit" in body


@pytest.mark.parametrize("path", [*sorted(_SKILL.rglob("*")), _PROMPT])
def test_loop_files_are_portable(path: Path) -> None:
    """Portable text names no owner, account, machine path or private host."""
    if not path.is_file():
        return
    text = _text(path)

    assert "lfr-ai" not in text
    assert "OneDrive" not in text
    assert not re.search(r"[A-Za-z]:\\\\", text)


def test_skill_links_resolve_inside_the_skill() -> None:
    """Every relative link in the skill and its references exists."""
    for path in (_SKILL / "SKILL.md", *sorted((_SKILL / "references").glob("*.md"))):
        for target in _LINK.findall(_text(path)):
            assert (path.parent / target).exists(), f"{path.name}: {target}"


def test_prompt_loads_the_skill_and_keeps_the_approval_gate() -> None:
    """The prompt delegates to the skill and never allows an unapproved push."""
    text = _text(_PROMPT)

    assert "(../skills/kit-improve/SKILL.md)" in text
    assert "wait for approval" in text
    assert "Never push or merge to the default branch" in text


def test_repository_policy_scopes_git_to_this_repository_with_approval() -> None:
    """The kit's own policy narrows, not removes, the version-control rule."""
    policy = _text(_ROOT / "AGENTS.md")

    assert "In this repository only" in policy
    assert "only after the\n  user approves the exact command" in policy
    assert "Never push or merge to the default branch" in policy
    assert "Version control in any other repository" in policy
