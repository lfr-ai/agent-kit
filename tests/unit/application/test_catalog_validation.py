"""Focused behavioral and negative tests for catalog validation helpers and compose errors."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import pytest

from agent_kit.application.services.catalog_service import (
    CatalogService,
    _body_text,
    _check_hidden_unicode,
    _check_links,
    _check_profile_cycles,
    _check_references,
    _contained_catalog_path,
    _contains_hidden_unicode,
    _document_text,
    _effective_bundles,
    _exact_mapping,
    _included_paths,
    _link_target,
    _parse_bundles,
    _parse_profiles,
    _policy_mapping,
    _same_value,
    _skill_records,
    _string_list,
)
from agent_kit.core.models import (
    Bundle,
    BundleSource,
    Catalog,
    Finding,
    Profile,
    SourceDocument,
)
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", None),
        (".", "."),
        ("packages/backend", "packages/backend"),
        ("..", None),
        ("C:/drive", None),
        ("nested\\windows.md", None),
    ],
)
def test_contained_catalog_path_accepts_normal_and_rejects_unsafe(
    value: str, expected: str | None
) -> None:
    """Containment validation accepts normalized relative paths and rejects unsafe ones."""
    assert _contained_catalog_path(value) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("no frontmatter here", None),
        ("---\nonly header\n", None),
        ("---\nmeta: yes\n---\nbody line\nmore\n", "body line\nmore"),
    ],
)
def test_body_text_extracts_and_rejects_incorrect_frontmatter(
    text: str, expected: str | None
) -> None:
    """SKILL.md body extraction returns the text after YAML frontmatter or None when invalid."""
    assert _body_text(text) == expected


def test_hidden_unicode_detection_finds_control_chars() -> None:
    """Hidden Unicode controls are detected even when nested in mappings or lists."""
    value = {"a": "visible", "b": ["ok", {"c": "bad\u200bchar"}]}
    assert _contains_hidden_unicode(value)
    findings: list[Finding] = []
    _check_hidden_unicode(value, "some/path", findings)
    assert any(item.code == "unicode.hidden" for item in findings)


@pytest.mark.parametrize(
    ("link", "base_is_bundle", "expected_code"),
    [
        ("https://example.org/resource", True, None),
        ("mailto:maintainer@example.org", False, None),
        ("a\\b", True, "links.path"),
        ("/absolute.md", True, "links.escape"),
        ("not-here.md", False, "links.missing"),
    ],
)
def test_link_target_various_behaviors(
    link: str, base_is_bundle: bool, expected_code: str | None
) -> None:
    """Different link targets produce no findings for allowed cases and diagnostics for invalid targets."""
    findings: list[Finding] = []
    _link_target(link, "llms.txt", set(), findings, base_is_bundle=base_is_bundle)
    if expected_code is None:
        assert not findings
    else:
        assert any(f.code == expected_code for f in findings)


def test_policy_mapping_rejects_modified_policy_values() -> None:
    """Any deviation from the strict policy contract is reported as a policy.value finding."""
    from agent_kit.application.services import catalog_service as cs

    modified: dict[str, object] = dict(copy.deepcopy(cs._POLICY))
    # mutate an expected nested child to provoke a mismatch
    manifest = modified["manifest"]
    assert isinstance(manifest, dict)
    manifest["require_explicit_includes"] = False
    findings: list[Finding] = []
    assert not _policy_mapping(modified, "apm-policy.yml", findings)
    assert any(item.code == "policy.value" for item in findings)


def test_compose_raises_for_unknown_profile_and_features_and_skill_availability(
    source_root: Path,
) -> None:
    """Compose reports clear errors for unknown profiles, unknown features, and unavailable skills."""
    snapshot = FileCatalogAdapter().load(source_root)
    svc = CatalogService()
    with pytest.raises(ValueError, match="unknown profile 'missing'"):
        svc.compose(snapshot, "missing", (), ("copilot",))
    # unknown feature
    with pytest.raises(ValueError, match="unknown feature profile 'missingfeature'"):
        svc.compose(snapshot, "shared", ("missingfeature",), ("copilot",))
    # duplicate session skills
    with pytest.raises(ValueError, match="session skill identifiers must be unique"):
        svc.compose(
            snapshot, "shared", (), ("copilot",), skills=("kit-shared", "kit-shared")
        )
    # unavailable skill not part of the selected profile
    with pytest.raises(ValueError, match="skills unavailable in selected profile"):
        svc.compose(snapshot, "shared", (), ("copilot",), skills=("kit-backend",))


def test_parse_catalog_and_manifest_issues_are_reported(source_root: Path) -> None:
    """Malformed bundle declarations and manifest includes produce clear diagnostics."""
    import json as _json

    root = source_root
    catalog_path = root / "catalog.json"
    catalog = _json.loads(catalog_path.read_text(encoding="utf-8"))
    # add a declared but absent bundle to exercise bundle.missing
    catalog["bundles"]["ghost"] = {"path": "packages/ghost", "kind": "portable"}
    catalog_path.write_text(_json.dumps(catalog, indent=2), encoding="utf-8")

    # corrupt a manifest to exercise manifest.includes and manifest.dependencies checks
    manifest_path = root / "packages/backend/apm.yml"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["includes"] = []
    manifest["dependencies"] = {"unexpected": True}
    manifest_path.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")

    report = CatalogService().validate(FileCatalogAdapter().load(root))
    codes = {f.code for f in report.findings}
    # either an explicit missing bundle finding or a bundle root complaint is acceptable
    assert "bundle.missing" in codes or "bundle.root" in codes
    assert any(
        "manifest.includes" in f.code or "manifest.includes" in f.message
        for f in report.findings
    )
    assert any(
        "manifest.dependencies" in f.code or "manifest.dependencies" in f.message
        for f in report.findings
    )


def test_validate_skill_frontmatter_and_body_errors(source_root: Path) -> None:
    """SKILL.md frontmatter shape, parent path, and body delimiters are validated."""
    skill = source_root / "packages/shared/.apm/skills/kit-shared/SKILL.md"
    # remove YAML delimiters to provoke a skill.body error
    skill.write_text(
        "name: kit-shared\ndescription: Shared skill.\n\nBody without frontmatter.\n",
        encoding="utf-8",
    )

    report = CatalogService().validate(FileCatalogAdapter().load(source_root))
    assert any(
        item.code in {"skill.frontmatter", "skill.body"} for item in report.findings
    )


def test_effective_bundles_raises_for_unknown_profile() -> None:
    """Effective bundle resolution raises when a requested profile is unknown."""
    catalog = Catalog(
        budgets=(
            ("policy_lines", 120),
            ("skill_body_lines", 300),
            ("description_chars", 350),
            ("profile_description_chars", 6500),
        ),
        bundles=(Bundle(kind="portable", name="b", path="packages/b"),),
        profiles=(Profile(bundles=("b",), extends=(), name="p"),),
        schema_version=1,
        supported_runtimes=("copilot", "claude"),
        version="0.1.0",
    )
    with pytest.raises(ValueError, match=r"unknown profile 'x'"):
        _effective_bundles(catalog, ("x",))


def test_exact_mapping_string_list_and_same_value_helpers() -> None:
    """_exact_mapping, _string_list and _same_value validate shapes and values."""
    findings: list[Finding] = []
    # non-mapping value
    assert _exact_mapping(1, {"a"}, "p", findings) is None
    assert any(f.code == "schema.mapping" for f in findings)

    findings.clear()
    # missing and unknown fields
    value = {"known": 1}
    res = _exact_mapping(value, {"expected"}, "p", findings)
    assert res is not None
    assert any(f.code == "schema.missing" for f in findings)
    findings.clear()
    res = _exact_mapping({"expected": 1, "extra": 2}, {"expected"}, "p", findings)
    assert any(f.code == "schema.unknown" for f in findings)

    findings.clear()
    # string list validations
    assert _string_list("nope", "p", findings) is None
    assert any(f.code == "schema.list" for f in findings)
    findings.clear()
    assert _string_list(["ok", ""], "p", findings) is None
    assert any(f.code == "schema.string" for f in findings)
    findings.clear()
    assert _string_list(["dup", "dup"], "p", findings) == ("dup", "dup")
    assert any(f.code == "schema.duplicate" for f in findings)

    # same value comparisons
    assert _same_value({"a": [1, 2]}, {"a": [1, 2]})
    assert not _same_value({"a": [1]}, {"a": [1, 2]})
    assert not _same_value(1, "1")


def test_policy_mapping_nested_security_mismatch_reports() -> None:
    """_policy mapping reports when nested security child values differ from expectation."""
    from agent_kit.application.services import catalog_service as cs

    modified: dict[str, object] = dict(cs._POLICY)
    assert isinstance(modified, dict)
    security_value = modified.get("security")
    if isinstance(security_value, dict):
        nested = dict(security_value)
    else:
        nested: dict[str, object] = {}
    nested["integrity"] = {"require_hashes": False}
    modified["security"] = nested
    findings: list[Finding] = []
    assert not _policy_mapping(modified, "apm-policy.yml", findings)
    assert any(f.code == "policy.value" for f in findings)


def make_doc(
    relative_path: str,
    text: str | None = None,
    frontmatter: object | None = None,
    *,
    is_symlink: bool = False,
    parse_error: bool = False,
    frontmatter_error: bool = False,
) -> SourceDocument:
    """Helper to build SourceDocument records for bundle tests."""
    return SourceDocument(
        content=(text or "").encode("utf-8"),
        frontmatter=frontmatter,
        frontmatter_error=frontmatter_error,
        is_directory=False,
        is_symlink=is_symlink,
        parse_error=parse_error,
        relative_path=relative_path,
        text=text,
        yaml_value=None,
    )


def make_bundle(
    name: str, files: list[SourceDocument], manifest: object | None
) -> BundleSource:
    """Helper to build a minimal BundleSource for included/skill record tests."""
    manifest_doc = files[0] if files else make_doc("apm.yml", "---\nname: x\n---")
    return BundleSource(
        apm_exists=True,
        files=tuple(files),
        kind="portable",
        manifest=manifest,
        manifest_document=manifest_doc,
        manifest_error=False,
        manifest_is_symlink=False,
        name=name,
        path=f"packages/{name}",
        root_is_symlink=False,
    )


def test_included_paths_various_edge_cases() -> None:
    """_included_paths reports manifest shape and include path problems in many scenarios."""
    findings: list[Finding] = []
    # use a BundleSource with manifest_error True
    bs = BundleSource(
        apm_exists=True,
        files=(),
        kind="portable",
        manifest=None,
        manifest_document=make_doc("apm.yml", ""),
        manifest_error=True,
        manifest_is_symlink=False,
        name="x",
        path="packages/x",
        root_is_symlink=False,
    )
    findings.clear()
    assert _included_paths(bs, findings, "0.1.0", ("copilot",)) == ()
    assert any(f.code == "manifest.read" for f in findings)

    # manifest not an object
    bs = make_bundle("x", [], 1)
    findings.clear()
    assert _included_paths(bs, findings, "0.1.0", ("copilot",)) == ()
    assert any(f.code == "manifest.schema" for f in findings)

    # includes empty list
    manifest = {
        "name": "x",
        "version": "0.1.0",
        "targets": ["copilot"],
        "includes": [],
        "dependencies": {},
        "executables": {},
        "license": "MIT",
    }
    sd = make_doc("references/guide.md", "content")
    bs = make_bundle("x", [sd], manifest)
    findings.clear()
    assert _included_paths(bs, findings, "0.1.0", ("copilot",)) == ()
    assert any(f.code == "manifest.includes" for f in findings)

    # include not beneath .apm
    manifest["includes"] = ["apm/bad"]
    bs = make_bundle("x", [sd], manifest)
    findings.clear()
    _included_paths(bs, findings, "0.1.0", ("copilot",))
    assert any("beneath .apm" in f.message for f in findings)

    # include escapes .apm
    manifest["includes"] = [".apm/../escape"]
    bs = make_bundle("x", [sd], manifest)
    findings.clear()
    _included_paths(bs, findings, "0.1.0", ("copilot",))
    assert any("escapes .apm" in f.message for f in findings)

    # include has no resources
    manifest["includes"] = [".apm/nothing"]
    bs = make_bundle("x", [sd], manifest)
    findings.clear()
    _included_paths(bs, findings, "0.1.0", ("copilot",))
    assert any("has no resources" in f.message for f in findings)


def test_skill_records_detects_various_document_issues() -> None:
    """_skill_records flags symlinks, parse/frontmatter errors, instruction and skill problems."""

    sd1 = make_doc("apm/links.md", "text", is_symlink=True)
    sd2 = make_doc("apm/broken.md", "text", parse_error=True)
    sd3 = make_doc(
        "apm/inst.instructions.md", "text", frontmatter=None, frontmatter_error=True
    )
    sd4 = make_doc(
        "skills/kit-bad/SKILL.md",
        "name: kit-bad\ndescription: x\n---\nbody",
        frontmatter={"name": "not-a-kit", "description": "x"},
    )
    sd5 = make_doc(
        "skills/kit-good/SKILL.md",
        "---\nmeta: yes\n---\nbodyline1\nbodyline2",
        frontmatter={"name": "kit-good", "description": "ok"},
    )
    bs = BundleSource(
        apm_exists=True,
        files=(sd1, sd2, sd3, sd4, sd5),
        kind="portable",
        manifest=None,
        manifest_document=make_doc("apm.yml", ""),
        manifest_error=False,
        manifest_is_symlink=False,
        name="x",
        path="packages/x",
        root_is_symlink=False,
    )
    findings: list[Finding] = []
    records = _skill_records((bs,), findings, description_limit=1, body_limit=1)
    codes = {f.code for f in findings}
    assert "source.symlink" in codes
    assert "source.parse" in codes
    assert "instruction.frontmatter" in codes or "frontmatter.parse" in codes
    assert (
        "skill.name" in codes or "skill.parent" in codes or "skill.description" in codes
    )
    # valid skill should be in records
    assert "kit-good" in records


def test_validate_reports_invalid_native_assets(source_root: Path) -> None:
    """Catalog validation reports when native assets are malformed in a bundle."""
    asset_path = (
        source_root
        / "packages"
        / "shared"
        / ".apm"
        / "skills"
        / "kit-shared"
        / "assets"
        / "agents.json"
    )
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    # write an object missing the required 'roles' field
    asset_path.write_text('{"schema_version": 1}', encoding="utf-8")

    report = CatalogService().validate(FileCatalogAdapter().load(source_root))
    assert any(f.code == "native.assets" for f in report.findings)


def test_parse_bundles_and_profiles_and_references_and_cycles() -> None:
    """Low-level parsing helpers report schema and reference errors for bundles and profiles."""
    findings: list[Finding] = []
    # non-mapping bundles/profiles
    assert _parse_bundles(1, findings) is None
    assert any(f.code == "catalog.bundles" for f in findings)
    findings.clear()
    assert _parse_profiles(1, findings) is None
    assert any(f.code == "catalog.profiles" for f in findings)

    findings.clear()
    # check references for unknown bundles and profiles
    bundles = (Bundle(kind="portable", name="b1", path="p1"),)
    profiles = (Profile(bundles=("missing",), extends=("x",), name="p"),)
    _check_references(bundles, profiles, findings)
    assert any(
        "unknown bundle" in f.message or "extends unknown" in f.message
        for f in findings
    )
    findings.clear()

    # detect cycles
    profiles_cycle = (
        Profile(bundles=("b1",), extends=("p2",), name="p1"),
        Profile(bundles=("b1",), extends=("p1",), name="p2"),
    )
    _check_profile_cycles(profiles_cycle, findings)
    assert any(f.code == "profile.cycle" for f in findings)


def test_link_target_unsupported_scheme_and_empty_path() -> None:
    """_links with unsupported schemes produce a scheme finding; empty paths are ignored."""
    findings: list[Finding] = []
    _link_target(
        "ftp://example.com/resource", "doc.md", set(), findings, base_is_bundle=True
    )
    assert any(f.code == "links.scheme" for f in findings)

    findings.clear()
    # empty path produces no finding
    _link_target("", "doc.md", set(), findings, base_is_bundle=True)
    assert not findings


def test_document_text_and_check_links_handle_none_text() -> None:
    """_document_text returns empty for non-text docs and _check_links ignores None text."""
    doc = SourceDocument(
        content=b"",
        frontmatter=None,
        frontmatter_error=False,
        is_directory=False,
        is_symlink=False,
        parse_error=False,
        relative_path="README.md",
        text=None,
        yaml_value=None,
    )
    assert _document_text(doc) == ""
    findings: list[Finding] = []
    _check_links(doc, set(), findings, base_is_bundle=True)
    assert findings == []


def test_policy_mapping_rejects_non_mapping() -> None:
    """Non-mapping policy values are rejected with a schema.mapping finding."""
    findings: list[Finding] = []
    assert not _policy_mapping(1, "apm-policy.yml", findings)
    assert any(f.code == "schema.mapping" for f in findings)
