"""Own source-repository checks: root files, documentation, links, and roles.

Covers symlinks, hidden Unicode, root documentation, bundle source mappings,
and native role assets of every effective profile.
"""

from __future__ import annotations

from posixpath import curdir
from typing import TYPE_CHECKING

from agent_kit.application.catalog.links import (
    check_hidden_unicode,
    check_links,
    link_index,
)
from agent_kit.application.catalog.planning import SkillSelection, document_selected
from agent_kit.application.catalog.schema import resolved_profiles
from agent_kit.application.findings import add_finding
from agent_kit.application.native_delivery import validate_native_assets
from agent_kit.core.errors import InputTypeError

if TYPE_CHECKING:
    from agent_kit.application.catalog.documents import SkillRecord
    from agent_kit.core.models import (
        Bundle,
        BundleSource,
        Catalog,
        CatalogSnapshot,
        Finding,
        SourceDocument,
    )


def check_root_symlinks(snapshot: CatalogSnapshot, findings: list[Finding]) -> None:
    """Report a symlinked source root and any captured root links."""
    if snapshot.root_is_symlink:
        add_finding(findings, "source.symlink", "source root is a symlink", ".")
    for relative in snapshot.root_symlinks:
        add_finding(
            findings,
            "source.symlink",
            "source root contains a symlink or junction",
            relative,
        )


def check_source_unicode(snapshot: CatalogSnapshot, findings: list[Finding]) -> None:
    """Reject hidden Unicode in catalog, policy, manifest, and bundle content."""
    if snapshot.catalog_document is not None:
        check_hidden_unicode(
            snapshot.catalog_document.text or "", "catalog.json", findings
        )
    check_hidden_unicode(snapshot.catalog, "catalog.json", findings)
    if snapshot.policy_document is not None:
        check_hidden_unicode(
            snapshot.policy_document.text or "", "apm-policy.yml", findings
        )
    check_hidden_unicode(snapshot.policy, "apm-policy.yml", findings)
    for bundle in snapshot.bundles:
        manifest_path = f"{bundle.path}/apm.yml"
        check_hidden_unicode(
            bundle.manifest_document.text or "", manifest_path, findings
        )
        check_hidden_unicode(bundle.manifest, manifest_path, findings)
        for document in bundle.files:
            path = f"{bundle.path}/.apm/{document.relative_path}"
            check_hidden_unicode(document.relative_path, path, findings)
            check_hidden_unicode(document.text or "", path, findings)
            check_hidden_unicode(document.frontmatter, path, findings)
            check_hidden_unicode(document.yaml_value, path, findings)


def check_root_files(
    root_documents: dict[str, SourceDocument],
    policy_limit: int,
    findings: list[Finding],
) -> None:
    """Require the MIT license and docs index and bound ``AGENTS.md`` lines."""
    license_document = root_documents.get("LICENSE")
    if (
        license_document is None
        or license_document.text is None
        or not license_document.text.startswith("MIT License")
    ):
        add_finding(
            findings,
            "license.read",
            "root MIT license text is missing or invalid",
            "LICENSE",
        )
    if "llms.txt" not in root_documents:
        add_finding(
            findings, "docs.index", "root llms.txt index is missing", "llms.txt"
        )
    agents = root_documents.get("AGENTS.md")
    if (
        agents is not None
        and agents.text is not None
        and len(agents.text.splitlines()) > policy_limit
    ):
        add_finding(
            findings,
            "budget.agents",
            f"AGENTS.md exceeds {policy_limit} lines",
            "AGENTS.md",
        )


def check_root_documentation(
    snapshot: CatalogSnapshot,
    root_documents: dict[str, SourceDocument],
    findings: list[Finding],
) -> None:
    """Require readable, link-safe, non-symlink root documentation."""
    root_available = link_index(
        (
            *snapshot.root_paths,
            *root_documents,
            *(
                f"{bundle.path}/.apm/{source.relative_path}"
                for bundle in snapshot.bundles
                for source in bundle.files
            ),
        )
    )
    for document in snapshot.root_documents:
        if document.is_symlink:
            add_finding(
                findings,
                "docs.symlink",
                "root documentation must not be a symlink",
                document.relative_path,
            )
        if document.parse_error or document.text is None:
            add_finding(
                findings,
                "docs.read",
                "root documentation is unreadable or not UTF-8 text",
                document.relative_path,
            )
        check_hidden_unicode(document.text or "", document.relative_path, findings)
        check_links(document, root_available, findings, base_is_bundle=False)


def _native_assets(
    bundles: tuple[BundleSource, ...], *, selection: SkillSelection | None = None
) -> dict[str, bytes]:
    """Map ``<bundle>/.apm/<path>`` to bytes, optionally filtered by ``selection``."""
    assets: dict[str, bytes] = {}
    for bundle in bundles:
        prefix = "" if bundle.path == curdir else f"{bundle.path}/"
        for document in bundle.files:
            if not document.is_directory and (
                selection is None or document_selected(document, selection)
            ):
                assets[f"{prefix}.apm/{document.relative_path}"] = document.content
    return assets


def _check_native_selection(
    assets: dict[str, bytes],
    runtimes: tuple[str, ...],
    location: str,
    findings: list[Finding],
    *,
    require_optional: bool = False,
) -> None:
    """Report native roles whose explicit dependencies cannot be rendered."""
    try:
        validate_native_assets(assets, runtimes, require_optional=require_optional)
    except (ValueError, InputTypeError) as error:
        add_finding(
            findings,
            "native.assets",
            f"native role assets are invalid: {error}",
            location,
        )


def check_native_assets(
    snapshot: CatalogSnapshot,
    catalog: Catalog,
    skills: dict[str, SkillRecord],
    findings: list[Finding],
) -> None:
    """Validate every authored asset and each effective profile's role closure."""
    _check_native_selection(
        _native_assets(snapshot.bundles),
        catalog.supported_runtimes,
        "catalog.json",
        findings,
        require_optional=True,
    )
    for profile, selected in resolved_profiles(catalog):
        bundles = tuple(item for item in snapshot.bundles if item.name in selected)
        available = {
            name: record for name, record in skills.items() if record.bundle in selected
        }
        selection = SkillSelection(
            requested=(),
            available=available,
            active=set(available),
            description_chars=sum(len(item.description) for item in available.values()),
        )
        _check_native_selection(
            _native_assets(bundles, selection=selection),
            catalog.supported_runtimes,
            f"catalog.json:profiles:{profile.name}",
            findings,
        )


def check_bundle_source(
    definition: Bundle,
    source: BundleSource,
    source_paths: dict[str, BundleSource],
    findings: list[Finding],
) -> None:
    """Require a captured bundle to match its declaration and safe ``.apm`` root."""
    if source.path != definition.path or source.kind != definition.kind:
        add_finding(
            findings,
            "bundle.mapping",
            "captured bundle does not match its catalog declaration",
            definition.path,
        )
    if source.root_is_symlink or not source.apm_exists:
        add_finding(
            findings,
            "bundle.root",
            "bundle .apm source root is missing or contains a symlink",
            f"{definition.path}/.apm",
        )
    if definition.path in source_paths and source.root_is_symlink:
        add_finding(
            findings,
            "source.symlink",
            "bundle source path contains a symlink",
            definition.path,
        )
