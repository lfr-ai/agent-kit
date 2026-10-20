"""Fail-closed provenance schema, source identity, and APM ledger validation."""

import hashlib
from pathlib import Path

import pytest

from agent_kit.application.services.provenance_service import ProvenanceService
from agent_kit.core.models import CheckReport, ComposedSnapshot, SourceDocument

_REQUIRED = ("apm.yml", "apm-policy.yml", "LICENSE")
_SOURCE = {
    "catalog_version": "0.1.0",
    "profile": "backend",
    "bundles": [{"name": "backend", "path": "packages/backend"}],
}


def _document(
    relative_path: str,
    content: bytes = b"content\n",
    *,
    is_symlink: bool = False,
    is_directory: bool = False,
    yaml_value: object | None = None,
) -> SourceDocument:
    return SourceDocument(
        content=content,
        frontmatter=None,
        frontmatter_error=False,
        is_directory=is_directory,
        is_symlink=is_symlink,
        parse_error=False,
        relative_path=relative_path,
        text=content.decode("utf-8", errors="replace"),
        yaml_value=yaml_value,
    )


def _digest(content: bytes = b"content\n") -> str:
    return hashlib.sha256(content).hexdigest()


def _provenance(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "source": _SOURCE,
        "files": {name: _digest() for name in _REQUIRED},
    }
    value.update(overrides)
    return value


def _verify(
    provenance: object | None = None,
    *,
    extra: tuple[SourceDocument, ...] = (),
    provenance_error: bool = False,
    root_is_symlink: bool = False,
    provenance_is_symlink: bool = False,
) -> CheckReport:
    snapshot = ComposedSnapshot(
        files=(*(_document(name) for name in _REQUIRED), *extra),
        provenance=_provenance() if provenance is None else provenance,
        provenance_error=provenance_error,
        provenance_is_symlink=provenance_is_symlink,
        root=Path("composed"),
        root_is_symlink=root_is_symlink,
    )
    return ProvenanceService().verify(snapshot)


def _codes(report: CheckReport) -> set[str]:
    return {item.code for item in report.findings}


def test_minimal_valid_snapshot_reports_source_version() -> None:
    """A complete ledger over exactly the captured files verifies."""
    report = _verify()

    assert report.valid
    assert report.version == "0.1.0"


def test_symlinked_root_and_provenance_are_reported() -> None:
    """Links cannot redirect the verified workspace or its ledger."""
    report = _verify(root_is_symlink=True, provenance_is_symlink=True)

    messages = {item.message for item in report.findings}
    assert "composed root is a symlink" in messages
    assert "provenance file is a symlink" in messages


def test_unreadable_provenance_stops_before_hash_comparison() -> None:
    """A read error is reported once, without inventing other findings."""
    report = _verify(provenance_error=True)

    assert _codes(report) == {"provenance.read"}
    assert report.version is None


@pytest.mark.parametrize(
    "provenance",
    [[], {"schema_version": 1}, {**_provenance(), "unexpected": True}],
)
def test_wrong_top_level_shape_is_a_schema_failure(provenance: object) -> None:
    """Only the three declared top-level fields are accepted."""
    assert _codes(_verify(provenance)) == {"provenance.schema"}


@pytest.mark.parametrize("schema_version", [2, "1", True, None])
def test_schema_version_must_be_integer_one(schema_version: object) -> None:
    """Booleans and strings that compare loosely to 1 are rejected."""
    report = _verify(_provenance(schema_version=schema_version))

    assert "provenance.schema" in _codes(report)


def test_files_must_be_an_object() -> None:
    """A non-mapping file ledger cannot be compared and fails closed."""
    report = _verify(_provenance(files=["apm.yml"]))

    assert any(
        item.message == "provenance files must be an object" for item in report.findings
    )


@pytest.mark.parametrize(
    ("relative", "digest"),
    [
        ("../escape.md", _digest()),
        ("/absolute.md", _digest()),
        ("C:/drive.md", _digest()),
        ("nested\\windows.md", _digest()),
        ("./dot.md", _digest()),
        ("double//slash.md", _digest()),
        ("trailing/", _digest()),
        ("provenance.json", _digest()),
        ("short-hash.md", "abc"),
        ("upper-hash.md", _digest().upper()),
        ("not-a-string.md", 7),
    ],
)
def test_invalid_ledger_entries_are_rejected(relative: str, digest: object) -> None:
    """Every ledger path stays relative and every digest is lowercase SHA-256."""
    files = {**{name: _digest() for name in _REQUIRED}, relative: digest}

    assert "provenance.path" in _codes(_verify(_provenance(files=files)))


@pytest.mark.parametrize("missing", _REQUIRED)
def test_each_required_file_must_be_hashed(missing: str) -> None:
    """Manifest, policy, and license hashes are mandatory."""
    files = {name: _digest() for name in _REQUIRED if name != missing}

    report = _verify(_provenance(files=files))

    assert any(
        item.code == "provenance.required" and missing in item.message
        for item in report.findings
    )


def test_symlinked_output_file_is_reported_and_not_hashed() -> None:
    """A link inside the workspace is a finding, not trusted content."""
    report = _verify(extra=(_document("linked.md", is_symlink=True),))

    assert any(
        item.code == "provenance.symlink" and item.path == "linked.md"
        for item in report.findings
    )


def test_directories_are_ignored_by_hash_comparison() -> None:
    """Directory entries are structure, not unrecorded files."""
    assert _verify(extra=(_document(".apm", is_directory=True),)).valid


@pytest.mark.parametrize(
    "source",
    [
        None,
        {"catalog_version": "0.1.0", "profile": "backend"},
        {**_SOURCE, "catalog_version": "one"},
        {**_SOURCE, "profile": ""},
        {**_SOURCE, "bundles": []},
        {**_SOURCE, "bundles": ["backend"]},
        {**_SOURCE, "bundles": [{"name": "backend", "path": "../outside"}]},
        {**_SOURCE, "bundles": [{"name": 1, "path": "packages/backend"}]},
        {
            **_SOURCE,
            "bundles": [
                {"name": "backend", "path": "packages/backend"},
                {"name": "backend", "path": "packages/other"},
            ],
        },
    ],
)
def test_invalid_source_identity_is_reported_without_a_version(
    source: object,
) -> None:
    """Untrusted source metadata never yields a reported catalog version."""
    report = _verify(_provenance(source=source))

    assert "provenance.source" in _codes(report)
    assert report.version is None


def test_findings_are_sorted_by_path_code_and_message() -> None:
    """Diagnostics are deterministic regardless of discovery order."""
    files = {name: _digest() for name in _REQUIRED}
    files["zz-missing.md"] = _digest()
    files["aa-missing.md"] = _digest()

    report = _verify(_provenance(files=files), extra=(_document("mm-extra.md"),))

    keys = [(item.path, item.code, item.message) for item in report.findings]
    assert keys == sorted(keys)


def _lock(*deployments: object, version: object = "1") -> SourceDocument:
    value = {"lockfile_version": version, "deployments": list(deployments)}
    return _document("apm.lock.yaml", yaml_value=value)


_ENTRY = {
    "kind": "project-relative",
    "value": ".agents/skills/kit-backend/SKILL.md",
    "scope": "project",
    "owners": ["."],
    "active_owner": ".",
    "content_hash": f"sha256:{_digest()}",
}


def test_ledger_entry_without_hash_is_ignored() -> None:
    """Directory deployments carry no content hash and need no comparison."""
    entry = {**_ENTRY, "content_hash": None}

    assert _verify(extra=(_lock(entry),)).valid


@pytest.mark.parametrize(
    "lock",
    [
        _lock(version="2"),
        _document("apm.lock.yaml", yaml_value=["not", "a", "mapping"]),
        _document("apm.lock.yaml", yaml_value={"lockfile_version": "1"}),
        _lock("not-a-mapping"),
        _lock({**_ENTRY, "kind": "user"}),
        _lock({**_ENTRY, "scope": "global"}),
        _lock({**_ENTRY, "owners": ["other"]}),
        _lock({**_ENTRY, "active_owner": "other"}),
        _lock({**_ENTRY, "value": "../outside.md"}),
        _lock({**_ENTRY, "value": "src/not-a-runtime-root.py"}),
        _lock({**_ENTRY, "content_hash": _digest()}),
        _lock({**_ENTRY, "content_hash": "sha256:short"}),
    ],
)
def test_unapproved_apm_ledgers_are_reported(lock: SourceDocument) -> None:
    """Only exact first-party project deliveries under runtime roots are trusted."""
    assert "provenance.delivery" in _codes(_verify(extra=(lock,)))


def test_post_installation_metadata_is_permitted() -> None:
    """APM's own metadata files are not unrecorded authored source."""
    extras = (
        _lock(),
        _document(".gitignore"),
        _document("AGENTS.md"),
        _document("CLAUDE.md"),
    )

    assert _verify(extra=extras).valid


@pytest.mark.parametrize(
    "native",
    [".github/prompts/kit-example.prompt.md", ".claude/commands/kit-example.md"],
)
def test_native_prompt_delivery_requires_an_authored_facade(native: str) -> None:
    authored = ".apm/prompts/kit-example.prompt.md"
    files = {name: _digest() for name in (*_REQUIRED, authored)}
    converted = b"converted native prompt\n"
    entry = {
        **_ENTRY,
        "value": native,
        "content_hash": f"sha256:{_digest(converted)}",
    }
    report = _verify(
        _provenance(files=files),
        extra=(
            _document(authored),
            _document(native, converted),
            _lock(entry),
        ),
    )
    assert report.valid, report.findings

    tampered = _verify(
        _provenance(files=files),
        extra=(
            _document(authored),
            _document(native, b"independently changed\n"),
            _lock(entry),
        ),
    )
    assert "provenance.delivery-drift" in _codes(tampered)


@pytest.mark.parametrize(
    "native",
    [
        ".github/prompts/kit-unknown.prompt.md",
        ".github/prompts/kit-example.md",
        ".claude/commands/kit-unknown.md",
        ".claude/commands/nested/kit-example.md",
    ],
)
def test_unmatched_prompt_delivery_is_not_approved_by_its_directory(
    native: str,
) -> None:
    authored = ".apm/prompts/kit-example.prompt.md"
    files = {name: _digest() for name in (*_REQUIRED, authored)}
    entry = {**_ENTRY, "value": native}
    report = _verify(
        _provenance(files=files),
        extra=(_document(authored), _document(native), _lock(entry)),
    )
    assert "provenance.delivery" in _codes(report)
