"""Catalog validation and profile selection contracts."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from agent_kit.application.services.catalog_service import CatalogService
from agent_kit.infrastructure.catalog_adapter import FileCatalogAdapter

if TYPE_CHECKING:
    from pathlib import Path

    from agent_kit.core.models import CheckReport


def _report(root: Path) -> CheckReport:
    return CatalogService().validate(FileCatalogAdapter().load(root))


def test_source_catalog_and_all_inactive_bundles_validate(source_root: Path) -> None:
    report = _report(source_root)

    assert report.valid
    backend = next(item for item in report.profiles if item.profile == "backend")
    assert backend.skill_count == 2
    assert backend.description_chars > 0


def test_project_documents_allow_a_valid_private_contact(source_root: Path) -> None:
    """Root security/conduct documents may link to a syntactically valid email route."""
    (source_root / "SECURITY.md").write_text(
        "# Security\n\n[Private report](mailto:maintainer@example.org)\n",
        encoding="utf-8",
    )

    assert _report(source_root).valid


@pytest.mark.parametrize(
    "target",
    [
        "mailto:invalid",
        "mailto:maintainer@example.org?subject=private",
        "mailto:maintainer@example.org%3Fsubject=private",
    ],
)
def test_project_documents_reject_ambiguous_mail_routes(
    source_root: Path, target: str
) -> None:
    """Contact links do not accept invalid addresses or injected mail headers."""
    (source_root / "SECURITY.md").write_text(
        f"# Security\n\n[Private report]({target})\n",
        encoding="utf-8",
    )

    assert any(item.code == "links.scheme" for item in _report(source_root).findings)


def test_portable_skills_do_not_embed_project_mail_contacts(source_root: Path) -> None:
    """Allowing project contacts must not relax the portable resource-link boundary."""
    skill = source_root / "packages/shared/.apm/skills/kit-shared/SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8")
        + "\n[Contact](mailto:maintainer@example.org)\n",
        encoding="utf-8",
    )

    assert any(item.code == "links.scheme" for item in _report(source_root).findings)


def test_unknown_nested_policy_field_is_rejected(source_root: Path) -> None:
    policy = source_root / "apm-policy.yml"
    policy.write_text(
        policy.read_text(encoding="utf-8") + "min-version: 1\n", encoding="utf-8"
    )

    report = _report(source_root)

    assert not report.valid
    assert any("unknown field" in finding.message for finding in report.findings)


def test_policy_booleans_do_not_accept_integer_lookalikes(source_root: Path) -> None:
    policy_path = source_root / "apm-policy.yml"
    policy = policy_path.read_text(encoding="utf-8").replace(
        "trust_transitive: false", "trust_transitive: 0"
    )
    policy_path.write_text(policy, encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any("policy value" in finding.message for finding in report.findings)


def test_boolean_budget_is_not_a_positive_integer(source_root: Path) -> None:
    catalog_path = source_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["budgets"]["policy_lines"] = True
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any(
        "'policy_lines' must be a positive integer" in item.message
        for item in report.findings
    )


def test_duplicate_json_mapping_key_fails_closed(source_root: Path) -> None:
    catalog_path = source_root / "catalog.json"
    content = catalog_path.read_text(encoding="utf-8").replace(
        '"schema_version": 1,',
        '"schema_version": 0,\n  "schema_version": 1,',
        1,
    )
    catalog_path.write_text(content, encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any(item.code == "catalog.read" for item in report.findings)


def test_duplicate_yaml_mapping_key_fails_closed(source_root: Path) -> None:
    policy_path = source_root / "apm-policy.yml"
    policy_path.write_text(
        policy_path.read_text(encoding="utf-8").replace(
            "  trust_transitive: false",
            "  trust_transitive: true\n  trust_transitive: false",
        ),
        encoding="utf-8",
    )

    report = _report(source_root)

    assert not report.valid
    assert any(item.code == "policy.read" for item in report.findings)


def test_catalog_requires_exact_approved_runtime_pair(source_root: Path) -> None:
    catalog_path = source_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["supported_runtimes"] = ["copilot"]
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any("exactly copilot and claude" in item.message for item in report.findings)


def test_policy_line_budget_accepts_exact_boundary(source_root: Path) -> None:
    policy_path = source_root / "apm-policy.yml"
    content = policy_path.read_text(encoding="utf-8")
    policy_path.write_text(
        content + "\n" * (120 - len(content.splitlines())),
        encoding="utf-8",
    )
    assert _report(source_root).valid

    policy_path.write_text(
        policy_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )

    assert not _report(source_root).valid


def test_profile_cycle_and_missing_bundle_are_reported(source_root: Path) -> None:
    catalog_path = source_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["profiles"]["backend"]["extends"] = ["fullstack"]
    catalog["profiles"]["iac"]["bundles"] = ["absent"]
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any("cycle" in finding.message for finding in report.findings)
    assert any("unknown bundle" in finding.message for finding in report.findings)


def test_bundle_path_traversal_is_rejected(source_root: Path) -> None:
    catalog_path = source_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["bundles"]["backend"]["path"] = "../outside"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any("path" in finding.message.lower() for finding in report.findings)


def test_absolute_bundle_path_is_rejected(source_root: Path) -> None:
    catalog_path = source_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["bundles"]["backend"]["path"] = "C:/outside"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    assert not _report(source_root).valid


def test_unknown_bundle_field_and_missing_path_are_rejected(
    source_root: Path,
) -> None:
    catalog_path = source_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["bundles"]["backend"] = {"pat": "packages/backend", "kind": "portable"}
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any("missing field 'path'" in item.message for item in report.findings)
    assert any("unknown field 'pat'" in item.message for item in report.findings)


def test_unknown_profile_field_and_missing_extends_are_rejected(
    source_root: Path,
) -> None:
    catalog_path = source_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["profiles"]["backend"] = {
        "extend": ["shared"],
        "bundles": ["backend"],
    }
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any("missing field 'extends'" in item.message for item in report.findings)
    assert any("unknown field 'extend'" in item.message for item in report.findings)


def test_selected_profile_description_budget_is_enforced(source_root: Path) -> None:
    catalog_path = source_root / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["budgets"]["profile_description_chars"] = 20
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any(item.code == "budget.profile_description" for item in report.findings)


def test_skill_body_line_budget_accepts_boundary_and_rejects_overflow(
    source_root: Path,
) -> None:
    skill = source_root / ".apm/skills/kit-toolkit/SKILL.md"
    header = "---\nname: kit-toolkit\ndescription: Boundary description.\n---\n"
    skill.write_text(header + "\n".join(["body"] * 300) + "\n", encoding="utf-8")

    assert _report(source_root).valid

    skill.write_text(header + "\n".join(["body"] * 301) + "\n", encoding="utf-8")

    report = _report(source_root)
    assert not report.valid
    assert any("skill body" in finding.message.lower() for finding in report.findings)


def test_skill_description_character_budget_accepts_boundary(source_root: Path) -> None:
    skill = source_root / ".apm/skills/kit-toolkit/SKILL.md"
    description = "x" * 350
    skill.write_text(
        f"---\nname: kit-toolkit\ndescription: {description}\n---\n\nBody.\n",
        encoding="utf-8",
    )

    assert _report(source_root).valid

    skill.write_text(
        f"---\nname: kit-toolkit\ndescription: {description}x\n---\n\nBody.\n",
        encoding="utf-8",
    )

    assert not _report(source_root).valid


def test_duplicate_skill_names_and_native_scope_metadata_are_rejected(
    source_root: Path,
) -> None:
    skill = source_root / "packages/shared/.apm/skills/kit-shared/SKILL.md"
    skill.write_text(
        "---\nname: kit-toolkit\ndescription: Shared skill.\napplyTo: '**/*.py'\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )

    report = _report(source_root)

    assert not report.valid
    assert any("duplicate skill name" in finding.message for finding in report.findings)
    assert any("scope metadata" in finding.message for finding in report.findings)


def test_skill_body_hidden_unicode_is_rejected(source_root: Path) -> None:
    skill = source_root / ".apm/skills/kit-toolkit/SKILL.md"
    skill.write_text(
        "---\nname: kit-toolkit\ndescription: Safe text.\n---\n\n"
        "Hidden\u200bcharacter.\n",
        encoding="utf-8",
    )

    report = _report(source_root)

    assert not report.valid
    assert any("hidden Unicode" in item.message for item in report.findings)


def test_escaped_hidden_unicode_in_skill_metadata_is_rejected(
    source_root: Path,
) -> None:
    skill = source_root / ".apm/skills/kit-toolkit/SKILL.md"
    skill.write_text(
        '---\nname: kit-toolkit\ndescription: "Safe\\u200b text."\n---\n\nBody.\n',
        encoding="utf-8",
    )

    report = _report(source_root)

    assert not report.valid
    assert any(item.code == "unicode.hidden" for item in report.findings)


def test_markdown_resource_escape_is_rejected(source_root: Path) -> None:
    skill = source_root / ".apm/skills/kit-toolkit/SKILL.md"
    skill.write_text(
        "---\nname: kit-toolkit\ndescription: Toolkit skill.\n---\n\n"
        "[outside](../../../../AGENTS.md)\n",
        encoding="utf-8",
    )

    report = _report(source_root)

    assert not report.valid
    assert any("link" in finding.message.lower() for finding in report.findings)


def test_bundle_symlink_is_rejected_without_following_it(
    source_root: Path, tmp_path: Path
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    link = source_root / "packages/backend/.apm/external"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")

    report = _report(source_root)

    assert not report.valid
    assert any("symlink" in finding.message.lower() for finding in report.findings)


def test_non_markdown_consumer_template_links_are_not_bundle_resources(
    source_root: Path,
) -> None:
    asset = source_root / ".apm/skills/kit-toolkit/assets"
    asset.mkdir()
    (asset / "llms.template.txt").write_text(
        "[Consumer facts](PROJECT.md)\n", encoding="utf-8"
    )
    (asset / "PROJECT.template.md").write_text(
        "[Consumer policy](../../AGENTS.md)\n", encoding="utf-8"
    )

    assert _report(source_root).valid


def test_source_root_symlink_is_rejected_without_reading_target(
    source_root: Path, tmp_path: Path
) -> None:
    link = tmp_path / "source-link"
    try:
        link.symlink_to(source_root, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")

    report = _report(link)

    assert not report.valid
    assert any(item.path == "." for item in report.findings)


def test_root_symlink_files_and_directories_are_rejected(
    source_root: Path, tmp_path: Path
) -> None:
    external_file = tmp_path / "external.txt"
    external_file.write_text("outside\n", encoding="utf-8")
    external_directory = tmp_path / "external-directory"
    external_directory.mkdir()
    try:
        (source_root / "linked-file.txt").symlink_to(external_file)
        (source_root / "linked-directory").symlink_to(
            external_directory, target_is_directory=True
        )
    except OSError as error:
        pytest.skip(f"symlinks are unavailable: {error}")

    report = _report(source_root)

    assert not report.valid
    assert any(item.path == "linked-file.txt" for item in report.findings)
    assert any(item.path == "linked-directory" for item in report.findings)


def test_root_document_links_must_resolve(source_root: Path) -> None:
    (source_root / "llms.txt").write_text("[Missing](not-here.md)\n", encoding="utf-8")

    report = _report(source_root)

    assert not report.valid
    assert any("not-here.md" in finding.message for finding in report.findings)


def test_unrelated_root_markdown_is_not_treated_as_project_context(
    source_root: Path,
) -> None:
    """Incidental root files do not alter the declared source documentation set."""
    (source_root / "pi_index.md").write_text(
        "[Missing](unrelated-page.md)\n", encoding="utf-8"
    )

    assert _report(source_root).valid


def test_unreadable_root_document_is_reported(source_root: Path) -> None:
    (source_root / "AGENTS.md").write_bytes(b"\xff")

    report = _report(source_root)

    assert not report.valid
    assert any(item.code == "docs.read" for item in report.findings)


def test_invalid_yaml_diagnostic_does_not_echo_source_content(
    source_root: Path,
) -> None:
    marker = "not-a-real-sensitive-marker"
    (source_root / "apm-policy.yml").write_text(
        f"private: {marker}: [\n", encoding="utf-8"
    )

    report = _report(source_root)

    assert not report.valid
    assert all(marker not in item.message for item in report.findings)
