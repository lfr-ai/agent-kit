"""Verify a captured composed workspace against its recorded provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_kit.application.findings import add_finding
from agent_kit.application.provenance.hashes import (
    actual_hashes,
    check_delivery_drift,
    check_recorded_files,
    expected_hashes,
)
from agent_kit.application.provenance.hooks import (
    check_hook_configuration,
    check_hook_source,
)
from agent_kit.application.provenance.ledger import delivery_hashes
from agent_kit.application.provenance.mcp import check_mcp_configuration
from agent_kit.application.provenance.record import (
    PROVENANCE_FILE,
    check_schema_version,
    provenance_mapping,
    source_version,
    validate_source,
)
from agent_kit.application.provenance.workspace import check_composed_links
from agent_kit.core.guards import is_json_object
from agent_kit.core.models import CheckReport

if TYPE_CHECKING:
    from agent_kit.core.models import ComposedSnapshot, Finding


class ProvenanceService:
    """Own the pure, read-only composed-workspace integrity check."""

    def __init__(self) -> None:
        """Create the stateless provenance verifier."""

    def verify(self, snapshot: ComposedSnapshot) -> CheckReport:
        """Compare all recorded hashes with the captured composed workspace.

        The report holds ordered integrity findings and the validated source
        version when available; no files are changed.
        """
        findings: list[Finding] = []
        check_composed_links(snapshot, findings)
        provenance = provenance_mapping(snapshot, findings)
        if provenance is None:
            return CheckReport(findings=tuple(findings), profiles=(), version=None)
        check_schema_version(provenance, findings)
        source = provenance.get("source")
        source_valid = validate_source(source, findings)
        expected = provenance.get("files")
        if not is_json_object(expected):
            add_finding(
                findings,
                "provenance.schema",
                "provenance files must be an object",
                PROVENANCE_FILE,
            )
            return CheckReport(findings=tuple(findings), profiles=(), version=None)

        recorded = expected_hashes(expected, findings)
        actual, native_actual = actual_hashes(snapshot, findings)
        delivery, metadata_paths = delivery_hashes(
            snapshot, findings, authored=recorded
        )
        check_delivery_drift(delivery, native_actual, findings)
        check_hook_source(native_actual, findings)
        check_hook_configuration(snapshot, findings)
        check_mcp_configuration(snapshot, findings)
        permitted = recorded.keys() | delivery.keys() | metadata_paths
        check_recorded_files(recorded, actual, permitted, findings)
        return CheckReport(
            findings=tuple(
                sorted(findings, key=lambda item: (item.path, item.code, item.message))
            ),
            profiles=(),
            version=source_version(source, source_valid=source_valid),
        )
