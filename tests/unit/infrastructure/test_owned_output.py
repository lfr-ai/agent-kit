"""Containment, ledger, atomic replacement, and rollback of owned generated files."""

import json
from pathlib import Path

import pytest

from agent_kit.infrastructure import owned_output
from agent_kit.infrastructure.owned_output import (
    LEDGER_SCHEMA_VERSION,
    OwnedPathError,
    OwnedPathIssue,
    ledger_bytes,
    ledger_entries,
    owned_path,
    publish_owned,
    replace_file,
)

_LEDGER = "lock.json"


@pytest.mark.parametrize("relative", ["../outside", "/absolute", "a\\b", ""])
def test_unsafe_relative_paths_are_rejected(tmp_path: Path, relative: str) -> None:
    with pytest.raises(OwnedPathError) as raised:
        owned_path(tmp_path, relative)
    assert raised.value.issue is OwnedPathIssue.UNSAFE


def test_linked_component_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = tmp_path / "generated"
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == linked or original(path)
    )

    with pytest.raises(OwnedPathError) as raised:
        owned_path(tmp_path, "generated/file.md")
    assert raised.value.issue is OwnedPathIssue.LINKED


def test_contained_path_is_joined_beneath_the_root(tmp_path: Path) -> None:
    assert owned_path(tmp_path, "a/b.md") == tmp_path / "a" / "b.md"


def test_ledger_bytes_attest_files_in_their_given_order() -> None:
    content = ledger_bytes({"b": b"2", "a": b"1"})

    assert content.endswith(b"}\n")
    document = json.loads(content)
    assert document["schema_version"] == LEDGER_SCHEMA_VERSION
    assert list(document["files"]) == ["b", "a"]
    assert ledger_entries(document) == document["files"]


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"files": {}},
        {"schema_version": 2, "files": {}},
        {"schema_version": 1, "files": []},
        {"schema_version": 1, "files": {}, "extra": True},
    ],
)
def test_ledger_entries_reject_other_shapes(document: object) -> None:
    assert ledger_entries(document) is None


def test_failed_replacement_check_keeps_the_destination(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    target.write_bytes(b"before")
    failure = OSError("refused")

    def refuse() -> None:
        raise failure

    with pytest.raises(OSError, match="refused"):
        replace_file(target, b"after", before_replace=refuse)
    assert target.read_bytes() == b"before"
    assert list(tmp_path.iterdir()) == [target]


def test_publication_writes_changes_and_removes_dropped_files(tmp_path: Path) -> None:
    (tmp_path / "old.md").write_bytes(b"old")

    publish_owned(
        {"new/a.md": b"a"},
        {"old.md": "unused"},
        ledger=_LEDGER,
        resolve=lambda name: owned_path(tmp_path, name),
    )

    assert (tmp_path / "new/a.md").read_bytes() == b"a"
    assert not (tmp_path / "old.md").exists()
    assert (tmp_path / _LEDGER).read_bytes() == ledger_bytes({"new/a.md": b"a"})


def test_failed_publication_restores_prior_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.md").write_bytes(b"first")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    replace = owned_output.replace_file
    failure = OSError("synthetic failure")

    def fail_on_ledger(path: Path, content: bytes) -> None:
        if path.name == _LEDGER:
            raise failure
        replace(path, content)

    monkeypatch.setattr(owned_output, "replace_file", fail_on_ledger)
    with pytest.raises(OSError, match="synthetic failure"):
        publish_owned(
            {"a.md": b"second", "b.md": b"new"},
            {},
            ledger=_LEDGER,
            resolve=lambda name: owned_path(tmp_path, name),
        )

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
