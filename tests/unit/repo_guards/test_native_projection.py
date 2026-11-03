"""Repository-local role projection ownership and rollback contracts."""

import hashlib
import json
from pathlib import Path

import pytest
import scripts.render_native as renderer

_ROOT = Path(__file__).resolve().parents[3]
_SELF_PICKER_ROLES = frozenset({"kit-orchestrator", "kit-debug"})


def test_repository_self_selection_picker_roster_is_minimal() -> None:
    """The repository's own picker offers only the orchestrator and debugger."""
    picker = {
        path.removeprefix(".github/agents/").removesuffix(".agent.md")
        for path, content in renderer.expected(_ROOT).items()
        if path.startswith(".github/agents/") and b"\nuser-invocable: true\n" in content
    }

    assert picker == _SELF_PICKER_ROLES


def _attest_roles(root: Path, files: dict[str, bytes]) -> None:
    """Seed a historical ledger and role bytes in a disposable test workspace."""
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    ledger = root / renderer._LOCK_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in files.items()
                },
            }
        ),
        encoding="utf-8",
    )


def test_projection_updates_only_attested_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changing canonical role source is an explicit update, not an independent edit."""
    target = ".github/agents/kit-example.agent.md"
    first = {target: b"first"}
    monkeypatch.setattr(renderer, "expected", lambda _root: first)
    renderer.write(tmp_path)
    assert renderer.check(tmp_path) == []

    second = {target: b"second"}
    monkeypatch.setattr(renderer, "expected", lambda _root: second)
    assert renderer.check(tmp_path)
    renderer.write(tmp_path)
    assert renderer.check(tmp_path) == []
    (tmp_path / target).write_bytes(b"independent change")

    with pytest.raises(ValueError, match="edited independently"):
        renderer.write(tmp_path)
    assert (tmp_path / target).read_bytes() == b"independent change"


@pytest.mark.parametrize(
    ("directory", "suffix"),
    [(".github/agents", ".agent.md"), (".claude/agents", ".md")],
)
@pytest.mark.parametrize("conflict", [None, "edited-worker", "unowned-destination"])
def test_flattening_workers_preserves_projection_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory: str,
    suffix: str,
    conflict: str | None,
) -> None:
    """Migrate attested nested workers, never independent edits or collisions."""
    old = f"{directory}/subagents/kit-example{suffix}"
    new = f"{directory}/kit-example{suffix}"
    _attest_roles(tmp_path, {old: b"original"})
    if conflict == "edited-worker":
        (tmp_path / old).write_bytes(b"independent change")
    elif conflict == "unowned-destination":
        (tmp_path / new).write_bytes(b"operator owned")
    before = _snapshot(tmp_path)
    monkeypatch.setattr(renderer, "expected", lambda _root: {new: b"updated"})

    if conflict is not None:
        with pytest.raises(ValueError, match=r"edited independently|unowned"):
            renderer.write(tmp_path)
        assert _snapshot(tmp_path) == before
    else:
        renderer.write(tmp_path)
        assert not (tmp_path / old).exists()
        assert (tmp_path / new).read_bytes() == b"updated"
        assert renderer.check(tmp_path) == []


@pytest.mark.parametrize(
    "target",
    [
        ".github/agents/subagents/kit-example.agent.md",
        ".claude/agents/subagents/kit-example.md",
    ],
)
def test_legacy_attestation_does_not_authorize_new_nested_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """A previous nested file can be removed, never rewritten as a new projection."""
    _attest_roles(tmp_path, {target: b"original"})
    before = _snapshot(tmp_path)
    monkeypatch.setattr(renderer, "expected", lambda _root: {target: b"updated"})

    with pytest.raises(ValueError, match="canonical"):
        renderer.write(tmp_path)
    assert _snapshot(tmp_path) == before


def test_flattening_failure_restores_legacy_files_and_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure after a legacy removal restores old bytes and removes flat outputs."""
    old = {
        ".github/agents/subagents/kit-example.agent.md": b"copilot",
        ".claude/agents/subagents/kit-example.md": b"claude",
    }
    _attest_roles(tmp_path, old)
    before = _snapshot(tmp_path)
    output = {name.replace("/subagents/", "/"): data for name, data in old.items()}
    monkeypatch.setattr(renderer, "expected", lambda _root: output)
    unlink = Path.unlink
    calls = 0
    failure = OSError("controlled legacy removal failure")

    def fail_second_removal(path: Path, *, missing_ok: bool = False) -> None:
        nonlocal calls
        if path.relative_to(tmp_path).as_posix() in old:
            calls += 1
            if calls == 2:
                raise failure
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_second_removal)

    with pytest.raises(OSError, match="controlled legacy removal") as raised:
        renderer.write(tmp_path)
    assert raised.value is failure
    assert calls == 2
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    ("directory", "suffix"),
    [(".github/agents", ".agent.md"), (".claude/agents", ".md")],
)
def test_flattening_rejects_linked_legacy_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory: str,
    suffix: str,
) -> None:
    """A legacy attestation cannot authorize reading or deleting through a link."""
    root = tmp_path / "source"
    external = tmp_path / "external"
    external.mkdir()
    filename = f"kit-example{suffix}"
    old = f"{directory}/subagents/{filename}"
    new = f"{directory}/{filename}"
    _attest_roles(root, {old: b"original"})
    (root / old).unlink()
    parent = root / directory / "subagents"
    parent.rmdir()
    (external / filename).write_bytes(b"original")
    try:
        parent.symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    monkeypatch.setattr(renderer, "expected", lambda _root: {new: b"updated"})
    before = _snapshot(root)
    external_before = _snapshot(external)

    with pytest.raises(ValueError, match=r"link|contain"):
        renderer.write(root)
    assert _snapshot(root) == before
    assert _snapshot(external) == external_before


@pytest.mark.parametrize("content", [b"operator owned", b"generated"])
@pytest.mark.parametrize(
    "target",
    [".github/agents/kit-example.agent.md", ".claude/agents/kit-example.md"],
)
def test_unowned_role_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str, content: bytes
) -> None:
    """Neither a matching name nor identical bytes authorize adopting a role."""
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    monkeypatch.setattr(renderer, "expected", lambda _root: {target: b"generated"})

    with pytest.raises(ValueError, match="unowned"):
        renderer.write(tmp_path)
    assert path.read_bytes() == content
    assert not (tmp_path / renderer._LOCK_PATH).exists()


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    ("directory", "suffix"),
    [
        (".github/agents", ".agent.md"),
        (".github/agents/subagents", ".agent.md"),
        (".claude/agents", ".md"),
        (".claude/agents/subagents", ".md"),
    ],
)
@pytest.mark.parametrize(
    "alias_kind",
    [
        "trailing-slash",
        "repeated-slash",
        "dot",
        "trailing-repeated-slash",
        "trailing-dot",
    ],
)
@pytest.mark.parametrize("retain_canonical", [False, True])
def test_ledger_alias_is_rejected_before_any_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    directory: str,
    suffix: str,
    alias_kind: str,
    retain_canonical: bool,
) -> None:
    """An alias cannot authorize writing then deleting the same retained file."""
    filename = f"kit-example{suffix}"
    target = f"{directory}/{filename}"
    _attest_roles(tmp_path, {target: b"original"})
    lock = tmp_path / renderer._LOCK_PATH
    ledger = json.loads(lock.read_bytes())
    digest = ledger["files"][target]
    aliases = {
        "trailing-slash": f"{target}/",
        "repeated-slash": f"{directory}//{filename}",
        "dot": f"{directory}/./{filename}",
        "trailing-repeated-slash": f"{target}//",
        "trailing-dot": f"{target}/.",
    }
    ledger["files"] = {aliases[alias_kind]: digest}
    if retain_canonical:
        ledger["files"][target] = digest
    lock.write_text(json.dumps(ledger), encoding="utf-8")
    before = _snapshot(tmp_path)
    next_content = b"updated" if retain_canonical else b"original"
    planned = target.replace("/subagents/", "/")
    monkeypatch.setattr(renderer, "expected", lambda _root: {planned: next_content})

    with pytest.raises(ValueError, match=r"canonical|unowned"):
        renderer.write(tmp_path)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "invalid",
    [
        ".github/agents/kit-example.md",
        ".claude/agents/kit-example.agent.md",
        ".github/agents/kit-example.agent.md/child",
        ".claude/agents/kit-example.md/child",
        ".github/agents/kit-example.agent.md.",
        ".claude/agents/kit-example.md ",
        ".claude/agents/kit-Example.md",
        ".github/agents/kit-.agent.md",
        ".claude/agents/kit--example.md",
        ".github/agents/other/kit-example.agent.md",
        ".github/agents/subagents/kit-example.md",
        ".claude/agents/subagents/kit-example.agent.md",
        ".github/agents/subagents/subagents/kit-example.agent.md",
        ".claude/agents/subagents/../kit-example.md",
    ],
)
def test_ledger_requires_runtime_specific_role_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    """A prefix is not sufficient authority to mutate arbitrary files."""
    target = ".claude/agents/kit-example.md"
    monkeypatch.setattr(renderer, "expected", lambda _root: {target: b"original"})
    renderer.write(tmp_path)
    lock = tmp_path / renderer._LOCK_PATH
    ledger = json.loads(lock.read_bytes())
    ledger["files"][invalid] = ledger["files"][target]
    lock.write_text(json.dumps(ledger), encoding="utf-8")
    before = _snapshot(tmp_path)
    monkeypatch.setattr(renderer, "expected", lambda _root: {target: b"updated"})

    with pytest.raises(ValueError, match=r"canonical|unowned"):
        renderer.write(tmp_path)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "extra",
    [
        ".github/agents/kit-unknown.agent.md",
        ".github/agents/operator.agent.md",
        ".github/agents/subagents/kit-unknown.agent.md",
        ".github/agents/nested/deeper/operator.agent.md",
        ".claude/agents/kit-unknown.md",
        ".claude/agents/operator.md",
        ".claude/agents/subagents/kit-unknown.md",
        ".claude/agents/nested/deeper/operator.md",
        ".github/agents/kit-operator.agent.md",
        ".claude/agents/kit-operator.md",
    ],
)
def test_inventory_reports_unknown_native_roles_without_deleting_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: str
) -> None:
    """Discovery includes non-kit names and arbitrary nesting, not only expected roles."""
    target = ".github/agents/kit-example.agent.md"
    monkeypatch.setattr(renderer, "expected", lambda _root: {target: b"original"})
    renderer.write(tmp_path)
    path = tmp_path / extra
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"operator owned")
    before = _snapshot(tmp_path)

    assert any(extra in finding for finding in renderer.check(tmp_path))
    assert _snapshot(tmp_path) == before
    renderer.write(tmp_path)
    assert _snapshot(tmp_path) == before


def test_inventory_is_checked_even_when_ledger_has_drifted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = ".claude/agents/kit-example.md"
    monkeypatch.setattr(renderer, "expected", lambda _root: {target: b"original"})
    renderer.write(tmp_path)
    extra = ".claude/agents/operator.md"
    (tmp_path / extra).write_bytes(b"operator owned")
    monkeypatch.setattr(renderer, "expected", lambda _root: {target: b"updated"})

    findings = renderer.check(tmp_path)
    assert any("ledger" in finding for finding in findings)
    assert any(extra in finding for finding in findings)


def test_inventory_ignores_unrelated_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check is repository-local and only considers each runtime's role suffix."""
    monkeypatch.setattr(renderer, "expected", lambda _root: {})
    renderer.write(tmp_path)
    for relative in (
        ".github/agents/notes.txt",
        ".claude/agents/notes.txt",
        ".github/workflows/not-a-role.agent.md",
        "packages/example/.claude/agents/operator.md",
        "user/.github/agents/operator.agent.md",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not a selected projection")
    before = _snapshot(tmp_path)

    assert renderer.check(tmp_path) == []
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "target",
    [
        ".github/agents/kit-example.agent.md",
        ".claude/agents/kit-example.md",
        ".github/agents/subagents/kit-example.agent.md",
        ".claude/agents/subagents/kit-example.md",
    ],
)
def test_removed_attested_role_is_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """Strict ownership must retain the existing legitimate removal operation."""
    _attest_roles(tmp_path, {target: b"original"})
    monkeypatch.setattr(renderer, "expected", lambda _root: {})

    renderer.write(tmp_path)
    assert not (tmp_path / target).exists()
    assert renderer.check(tmp_path) == []


@pytest.mark.parametrize(
    "target",
    [
        ".github/agents/kit-example.md",
        ".claude/agents/kit-example.agent.md",
        ".claude/agents/kit-example.md/.",
        ".github/agents/subagents/kit-example.agent.md",
        ".claude/agents/subagents/kit-example.md",
    ],
)
def test_invalid_planned_paths_are_rejected_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """Source planning cannot broaden the writer's authority."""
    retained = ".github/agents/kit-example.agent.md"
    monkeypatch.setattr(renderer, "expected", lambda _root: {retained: b"original"})
    renderer.write(tmp_path)
    before = _snapshot(tmp_path)
    monkeypatch.setattr(renderer, "expected", lambda _root: {target: b"updated"})

    with pytest.raises(ValueError, match="canonical"):
        renderer.write(tmp_path)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "target",
    [
        ".github/agents/operator.agent.md",
        ".claude/agents/operator.md",
        ".github/agents/subagents/operator.agent.md",
        ".claude/agents/nested/kit-example.md",
    ],
)
def test_ledger_cannot_claim_operator_owned_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """Non-canonical role files are not generated ownership, even with attested bytes."""
    monkeypatch.setattr(renderer, "expected", lambda _root: {})
    renderer.write(tmp_path)
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_bytes(b"operator role")
    lock = tmp_path / renderer._LOCK_PATH
    ledger = json.loads(lock.read_bytes())
    ledger["files"][target] = hashlib.sha256(path.read_bytes()).hexdigest()
    lock.write_text(json.dumps(ledger), encoding="utf-8")
    before = _snapshot(tmp_path)

    with pytest.raises(ValueError, match="unowned"):
        renderer.write(tmp_path)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "directory",
    [
        ".github/agents",
        ".claude/agents",
        ".github/agents/nested",
        ".claude/agents/nested",
    ],
)
def test_inventory_does_not_follow_external_directory_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory: str
) -> None:
    """Recursive inventory must not inspect user/global or any other linked discovery."""
    root = tmp_path / "source"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (external / "operator.agent.md").write_bytes(b"external")
    (external / "operator.md").write_bytes(b"external")
    monkeypatch.setattr(renderer, "expected", lambda _root: {})
    renderer.write(root)
    path = root / directory
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    before = _snapshot(external)

    with pytest.raises(ValueError, match=r"link|contain"):
        renderer.check(root)
    assert _snapshot(external) == before


def test_projection_failure_restores_previous_bytes_and_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed multi-file refresh cannot leave the previous attested setup corrupted."""
    a = ".github/agents/kit-a.agent.md"
    b = ".claude/agents/kit-a.md"
    monkeypatch.setattr(renderer, "expected", lambda _root: {a: b"first", b: b"first"})
    renderer.write(tmp_path)
    original = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        renderer, "expected", lambda _root: {a: b"second", b: b"second"}
    )
    replace = renderer._replace
    calls = 0
    failure = OSError("controlled file replacement failure")

    def fail_once(path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise failure
        replace(path, data)

    monkeypatch.setattr(renderer, "_replace", fail_once)
    with pytest.raises(OSError, match="controlled") as raised:
        renderer.write(tmp_path)
    assert raised.value is failure
    assert {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == original


def test_linked_parent_cannot_redirect_a_role_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An attested filename does not authorize following an external parent link."""
    root = tmp_path / "source"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (root / ".github").mkdir()
    try:
        (root / ".github/agents").symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    monkeypatch.setattr(
        renderer,
        "expected",
        lambda _root: {".github/agents/kit-test.agent.md": b"role"},
    )

    with pytest.raises(ValueError, match=r"link|contain"):
        renderer.write(root)
    assert list(external.iterdir()) == []
