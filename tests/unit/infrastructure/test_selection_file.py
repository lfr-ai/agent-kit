"""Bounded, link-refusing reads of composition selection files."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from agent_kit.core.errors import UnreadableDocumentError
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

if TYPE_CHECKING:
    from pathlib import Path

_LIMIT = 65_536


def test_selection_json_is_decoded(tmp_path: Path) -> None:
    path = tmp_path / "agent-kit.json"
    path.write_text('{"schema_version": 1, "profile": "backend"}', encoding="utf-8")

    assert FileCatalogAdapter().load_selection(path) == {
        "schema_version": 1,
        "profile": "backend",
    }


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        pytest.param(b"{not json", "must be valid JSON", id="malformed"),
        pytest.param(
            b'{"profile": "a", "profile": "b"}', "must be valid JSON", id="duplicate"
        ),
        pytest.param(b"\xff\xfe", "must be UTF-8", id="binary"),
        pytest.param(b" " * (_LIMIT + 1), "is too large", id="oversized"),
    ],
)
def test_unsafe_selection_content_is_refused(
    tmp_path: Path, content: bytes, reason: str
) -> None:
    path = tmp_path / "agent-kit.json"
    path.write_bytes(content)

    with pytest.raises(UnreadableDocumentError, match=reason):
        FileCatalogAdapter().load_selection(path)


def test_missing_selection_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UnreadableDocumentError, match="regular file"):
        FileCatalogAdapter().load_selection(tmp_path / "absent.json")


def test_linked_selection_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"schema_version": 1, "profile": "backend"}', encoding="utf-8")
    link = tmp_path / "agent-kit.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is not permitted on this host")

    with pytest.raises(UnreadableDocumentError, match="regular file"):
        FileCatalogAdapter().load_selection(link)
