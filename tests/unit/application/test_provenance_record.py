"""The composer's provenance record satisfies the verifier's single schema owner."""

import hashlib
from pathlib import Path

from agent_kit.application.provenance import ProvenanceService
from agent_kit.application.provenance.record import (
    PROVENANCE_FIELDS,
    PROVENANCE_SCHEMA_VERSION,
    SOURCE_FIELDS,
    provenance_record,
)
from agent_kit.core.guards import is_json_object
from agent_kit.core.models import (
    Bundle,
    BundleKind,
    Catalog,
    ComposedSnapshot,
    SourceDocument,
)

_FILES = {"apm.yml": b"name: x\n", "apm-policy.yml": b"p\n", "LICENSE": b"MIT\n"}
_CATALOG = Catalog(
    budgets=(),
    bundles=(Bundle(kind=BundleKind.PORTABLE, name="backend", path="packages/b"),),
    profiles=(),
    schema_version=1,
    supported_runtimes=("copilot",),
    version="0.1.0",
)


def _document(relative_path: str, content: bytes) -> SourceDocument:
    return SourceDocument(
        content=content,
        frontmatter=None,
        frontmatter_error=False,
        is_directory=False,
        is_symlink=False,
        parse_error=False,
        relative_path=relative_path,
        text=content.decode("utf-8"),
        yaml_value=None,
    )


def test_record_uses_the_shared_schema_fields_and_version() -> None:
    """Field names and version come from the owner the verifier also uses."""
    record = provenance_record(_CATALOG, "backend", ("backend",), dict(_FILES))

    assert set(record) == PROVENANCE_FIELDS
    assert PROVENANCE_SCHEMA_VERSION == 1
    assert record["schema_version"] == PROVENANCE_SCHEMA_VERSION
    source = record["source"]
    assert is_json_object(source)
    assert set(source) == SOURCE_FIELDS
    assert source == {
        "catalog_version": "0.1.0",
        "profile": "backend",
        "bundles": [{"name": "backend", "path": "packages/b"}],
    }
    assert record["files"] == {
        name: hashlib.sha256(content).hexdigest()
        for name, content in sorted(_FILES.items())
    }


def test_verifier_accepts_the_record_written_by_the_composer() -> None:
    """A freshly written record verifies cleanly against the same files."""
    record = provenance_record(_CATALOG, "backend", ("backend",), dict(_FILES))
    snapshot = ComposedSnapshot(
        files=tuple(_document(name, content) for name, content in _FILES.items()),
        provenance=record,
        provenance_error=False,
        provenance_is_symlink=False,
        root=Path("composed"),
        root_is_symlink=False,
    )

    report = ProvenanceService().verify(snapshot)

    assert report.valid
    assert report.version == "0.1.0"
