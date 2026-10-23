"""Windows sharing retries preserve atomic no-replace publication."""

from pathlib import Path
import time

import pytest

import agent_kit.infrastructure.output_adapter as adapter


class SharingDeniedError(PermissionError):
    winerror = 5

    def __init__(self) -> None:
        super().__init__("Windows sharing access denied")


def test_transient_windows_denial_retries_the_same_atomic_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "owned.txt").write_bytes(b"owned")
    output = tmp_path / "output"
    original = Path.rename
    calls = 0
    waits: list[float] = []

    def rename(path: Path, target: Path) -> Path:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SharingDeniedError
        return original(path, target)

    monkeypatch.setattr(adapter.sys, "platform", "win32")
    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(time, "sleep", waits.append)
    adapter._publish_directory(stage, output)

    assert calls == 2
    assert waits == [0.1]
    assert (output / "owned.txt").read_bytes() == b"owned"


def test_permanent_windows_denial_remains_an_explicit_bounded_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    calls = 0
    waits: list[float] = []

    def rename(path: Path, target: Path) -> Path:
        nonlocal calls
        calls += 1
        raise SharingDeniedError

    monkeypatch.setattr(adapter.sys, "platform", "win32")
    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(time, "sleep", waits.append)
    with pytest.raises(SharingDeniedError, match="sharing access denied"):
        adapter._publish_directory(stage, tmp_path / "output")

    assert calls == 5
    assert waits == [0.1, 0.2, 0.4, 0.8]
    assert stage.is_dir()


def test_competing_destination_is_never_replaced_after_a_sharing_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    output = tmp_path / "output"
    calls = 0

    def rename(path: Path, target: Path) -> Path:
        nonlocal calls
        calls += 1
        target.mkdir()
        (target / "other.txt").write_bytes(b"other writer")
        raise SharingDeniedError

    monkeypatch.setattr(adapter.sys, "platform", "win32")
    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(time, "sleep", lambda _delay: None)
    with pytest.raises(FileExistsError):
        adapter._publish_directory(stage, output)

    assert calls == 1
    assert (output / "other.txt").read_bytes() == b"other writer"
    assert stage.is_dir()


def test_publication_rechecks_path_indirection_before_retrying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    output = tmp_path / "output"
    calls = 0
    original = Path.is_junction

    def rename(path: Path, target: Path) -> Path:
        nonlocal calls
        calls += 1
        raise SharingDeniedError

    def junction(path: Path) -> bool:
        return (calls > 0 and path == output.parent) or original(path)

    monkeypatch.setattr(adapter.sys, "platform", "win32")
    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(Path, "is_junction", junction)
    monkeypatch.setattr(time, "sleep", lambda _delay: None)
    with pytest.raises(ValueError, match="symlink or junction"):
        adapter._publish_directory(stage, output)
    assert calls == 1


def test_nonsharing_permission_error_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PrivilegeDeniedError(PermissionError):
        winerror = 1314

        def __init__(self) -> None:
            super().__init__("privilege required")

    stage = tmp_path / "stage"
    stage.mkdir()
    waits: list[float] = []

    def rename(path: Path, target: Path) -> Path:
        raise PrivilegeDeniedError

    monkeypatch.setattr(adapter.sys, "platform", "win32")
    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(time, "sleep", waits.append)
    with pytest.raises(PrivilegeDeniedError, match="privilege required"):
        adapter._publish_directory(stage, tmp_path / "output")
    assert waits == []
