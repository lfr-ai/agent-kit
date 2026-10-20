"""Repository-local role projection ownership and rollback contracts."""

from pathlib import Path

import pytest
import scripts.render_native as renderer


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


def test_unowned_role_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing consumer role is not claimed merely because its name matches."""
    target = ".github/agents/kit-example.agent.md"
    path = tmp_path / target
    path.parent.mkdir(parents=True)
    path.write_bytes(b"operator owned")
    monkeypatch.setattr(renderer, "expected", lambda _root: {target: b"generated"})

    with pytest.raises(ValueError, match="unowned"):
        renderer.write(tmp_path)
    assert path.read_bytes() == b"operator owned"


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
