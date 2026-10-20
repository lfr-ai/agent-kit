"""Hypothesis invariants for provenance paths, hashing, and output containment."""

import hashlib
from pathlib import Path, PurePosixPath

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_kit.application.services.provenance_service import (
    ProvenanceService,
    _path_is_relative,
)
from agent_kit.core.models import (
    ComposedSnapshot,
    CompositionPlan,
    PlannedFile,
    SourceDocument,
)
from agent_kit.infrastructure.output_adapter import OutputAdapter

_SEGMENT = st.text(
    alphabet=st.characters(
        codec="utf-8", exclude_characters="/\\\x00", exclude_categories=("Cs",)
    ),
    min_size=1,
    max_size=12,
).filter(lambda part: part not in {".", ".."})
_RELATIVE = st.lists(_SEGMENT, min_size=1, max_size=4).map("/".join)
_REQUIRED = ("apm.yml", "apm-policy.yml", "LICENSE")


@given(_RELATIVE)
def test_canonical_relative_paths_are_accepted(relative: str) -> None:
    """Every slash-joined path of ordinary segments is a valid ledger key."""
    if PurePosixPath(relative).as_posix() == relative and ":" not in relative:
        assert _path_is_relative(relative)


@given(_RELATIVE, st.sampled_from(["../", "/", "./", "a/../", "x//"]))
def test_traversal_and_noncanonical_prefixes_are_rejected(
    relative: str, prefix: str
) -> None:
    """Parent references, absolute, and non-canonical spellings never pass."""
    assert not _path_is_relative(prefix + relative)


@given(_RELATIVE)
def test_backslash_paths_are_rejected(relative: str) -> None:
    """Windows separators are refused regardless of the remaining text."""
    assert not _path_is_relative(relative.replace("/", "\\") + "\\x")


def _document(relative: str, content: bytes) -> SourceDocument:
    return SourceDocument(
        content=content,
        frontmatter=None,
        frontmatter_error=False,
        is_directory=False,
        is_symlink=False,
        parse_error=False,
        relative_path=relative,
        text=None,
        yaml_value=None,
    )


@settings(max_examples=60)
@given(st.binary(max_size=64), st.binary(min_size=1, max_size=64))
def test_any_byte_change_to_a_recorded_file_is_drift(
    original: bytes, suffix: bytes
) -> None:
    """Verification accepts exact bytes and rejects every appended change."""
    hashes = {name: hashlib.sha256(original).hexdigest() for name in _REQUIRED}
    provenance = {
        "schema_version": 1,
        "source": {
            "catalog_version": "1.0.0",
            "profile": "p",
            "bundles": [{"name": "b", "path": "b"}],
        },
        "files": hashes,
    }

    def verify(content: bytes) -> set[str]:
        snapshot = ComposedSnapshot(
            files=tuple(_document(name, content) for name in _REQUIRED),
            provenance=provenance,
            provenance_error=False,
            provenance_is_symlink=False,
            root=Path("composed"),
            root_is_symlink=False,
        )
        return {item.code for item in ProvenanceService().verify(snapshot).findings}

    assert verify(original) == set()
    assert verify(original + suffix) == {"provenance.drift"}


@settings(max_examples=40)
@given(st.lists(_RELATIVE, min_size=2, max_size=6))
def test_case_folded_duplicates_are_always_rejected(paths: list[str]) -> None:
    """Any plan whose paths collide after case folding is refused before writing."""
    folded = [path.casefold() for path in paths]
    files = tuple(PlannedFile(content=b"", relative_path=path) for path in paths)
    plan = CompositionPlan(
        bundles=(),
        files=files,
        profile="p",
        root=Path("source"),
        runtimes=(),
        source_paths=(),
        version="1.0.0",
    )
    try:
        OutputAdapter()._validate_files(plan.files)
    except ValueError as error:
        message = str(error)
        assert len(set(folded)) < len(folded) or "unsafe path" in message
    else:
        assert len(set(folded)) == len(folded)
