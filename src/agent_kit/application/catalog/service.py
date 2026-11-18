"""Own the catalog application service: source validation and composition plans.

Works on captured ``CatalogSnapshot`` values only; the infrastructure adapter
owns every file read and write.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_kit.application.catalog.documents import skill_records
from agent_kit.application.catalog.errors import CompositionError, CompositionIssue
from agent_kit.application.catalog.manifest import (
    included_paths,
    manifest_record,
    selected_mcp,
)
from agent_kit.application.catalog.planning import (
    add_output,
    check_profile_selection,
    collect_sources,
    json_bytes,
    license_content,
    require_session_resources,
    selected_runtimes,
    selection_record,
    skill_selection,
)
from agent_kit.application.catalog.policy import (
    check_policy,
    policy_content,
    policy_line_count,
)
from agent_kit.application.catalog.repository import (
    check_bundle_source,
    check_native_assets,
    check_root_documentation,
    check_root_files,
    check_root_symlinks,
    check_source_unicode,
)
from agent_kit.application.catalog.schema import (
    effective_bundles,
    parse_catalog,
    resolved_profiles,
)
from agent_kit.application.findings import add_finding
from agent_kit.application.native_delivery import render_native_agents
from agent_kit.application.provenance.record import (
    PROVENANCE_FILE,
    provenance_record,
)
from agent_kit.core.models import (
    CheckReport,
    CompositionPlan,
    PlannedFile,
    ProfileSummary,
)

if TYPE_CHECKING:
    from agent_kit.application.catalog.documents import SkillRecord
    from agent_kit.core.models import Catalog, CatalogSnapshot, Finding

_DEFAULT_POLICY_LINES = 120


class CatalogService:
    """Own pure schema validation, profile selection, and output planning."""

    def __init__(self) -> None:
        """Create the stateless catalog application service."""

    def validate(self, snapshot: CatalogSnapshot) -> CheckReport:
        """Validate every bundle, profile, and policy without filesystem access.

        The report holds ordered findings and available profile summaries; empty
        findings indicate valid source.
        """
        report, _ = self._validated(snapshot)
        return report

    def compose(
        self,
        snapshot: CatalogSnapshot,
        profile: str,
        features: tuple[str, ...],
        runtimes: tuple[str, ...],
        *,
        skills: tuple[str, ...] = (),
    ) -> CompositionPlan:
        """Build a pure, deterministic plan after source validation.

        Selection helpers propagate ``UnknownProfileError``,
        ``UnavailableSkillsError``, ``UnavailableBundleError``,
        ``CompositionCollisionError`` and ``OmittedResourceError``.

        Args:
            snapshot (CatalogSnapshot): Captured source inputs; no files are read.
            profile (str): Base profile declared in the catalog.
            features (tuple[str, ...]): Additional catalog profiles to include.
            runtimes (tuple[str, ...]): Native targets; empty uses catalog defaults.
            skills (tuple[str, ...]): Opt-in session skills; empty selects the full
                profile rather than a bounded session.

        Returns:
            CompositionPlan: Selected bundles and generated files, with files
            ordered by relative output path. Includes selection and provenance
            records; session plans omit native role generation. Writes nothing.

        Raises:
            CompositionError: The source or catalog is invalid, or the runtime
                or skill selection, policy, or license cannot be composed.
        """
        report, catalog = self._validated(snapshot)
        if not report.valid:
            raise CompositionError(CompositionIssue.SOURCE_INVALID)
        if catalog is None:
            raise CompositionError(CompositionIssue.CATALOG_INVALID)
        check_profile_selection(catalog, profile, features)
        runtime_targets = selected_runtimes(catalog, runtimes)
        selected = effective_bundles(catalog, (profile, *features))
        selection = skill_selection(snapshot, catalog, selected, skills)
        outputs = collect_sources(snapshot, catalog, selected, selection)
        if skills:
            require_session_resources(outputs)
        native_agents = (
            {} if skills else render_native_agents(outputs.files, runtime_targets)
        )
        for relative, content in native_agents.items():
            add_output(outputs, relative, content)

        add_output(
            outputs,
            ".apm/selection.json",
            json_bytes(
                selection_record(selection, outputs, len(native_agents)),
                ensure_ascii=True,
            ),
        )
        output_files = outputs.files
        mcp = [] if skills else selected_mcp(snapshot, selected)
        output_files["apm.yml"] = json_bytes(
            manifest_record(
                profile, catalog, runtime_targets, outputs.include_paths, mcp
            ),
            ensure_ascii=False,
        )
        output_files["apm-policy.yml"] = policy_content(snapshot)
        output_files["LICENSE"] = license_content(snapshot)
        output_files[PROVENANCE_FILE] = json_bytes(
            provenance_record(catalog, profile, selected, output_files),
            ensure_ascii=False,
        )
        return CompositionPlan(
            bundles=selected,
            files=tuple(
                PlannedFile(content=content, relative_path=name)
                for name, content in sorted(output_files.items())
            ),
            profile=profile,
            root=snapshot.root,
            runtimes=runtime_targets,
            source_paths=tuple((item.name, item.path) for item in catalog.bundles),
            version=catalog.version,
        )

    def _validated(
        self, snapshot: CatalogSnapshot
    ) -> tuple[CheckReport, Catalog | None]:
        """Validate ``snapshot``; return the report and the parsed catalog, if usable."""
        findings: list[Finding] = []
        catalog = parse_catalog(snapshot, findings)
        check_root_symlinks(snapshot, findings)
        check_policy(snapshot, findings)
        check_source_unicode(snapshot, findings)

        limits = dict(catalog.budgets) if catalog is not None else {}
        policy_limit = limits.get("policy_lines", _DEFAULT_POLICY_LINES)
        policy_lines = policy_line_count(snapshot)
        if policy_lines > policy_limit:
            add_finding(
                findings,
                "budget.policy",
                f"policy exceeds {policy_limit} lines",
                "apm-policy.yml",
            )
        root_documents = {item.relative_path: item for item in snapshot.root_documents}
        check_root_files(root_documents, policy_limit, findings)
        check_root_documentation(snapshot, root_documents, findings)

        records: dict[str, SkillRecord] = {}
        if catalog is not None:
            records = self._validate_bundles(snapshot, catalog, findings)
            self._validate_profile_budgets(catalog, records, findings)
            check_native_assets(snapshot, catalog, records, findings)
        deduplicated = tuple(
            sorted(
                set(findings),
                key=lambda item: (item.path, item.code, item.message),
            )
        )
        report = CheckReport(
            findings=deduplicated,
            profiles=self._summaries(catalog, records, policy_lines),
            version=catalog.version if catalog is not None else None,
        )
        return report, catalog

    def _validate_bundles(
        self,
        snapshot: CatalogSnapshot,
        catalog: Catalog,
        findings: list[Finding],
    ) -> dict[str, SkillRecord]:
        """Validate bundle sources and manifests; return valid skills by name."""
        sources = {item.name: item for item in snapshot.bundles}
        source_paths = {item.path: item for item in snapshot.bundles}
        for definition in catalog.bundles:
            source = sources.get(definition.name)
            if source is None:
                add_finding(
                    findings,
                    "bundle.missing",
                    "catalog bundle source is missing or unsafe",
                    definition.path,
                )
                continue
            check_bundle_source(definition, source, source_paths, findings)
            included_paths(
                source, findings, catalog.version, catalog.supported_runtimes
            )
        limits = dict(catalog.budgets)
        return skill_records(
            snapshot.bundles,
            findings,
            limits["description_chars"],
            limits["skill_body_lines"],
        )

    def _validate_profile_budgets(
        self,
        catalog: Catalog,
        skills: dict[str, SkillRecord],
        findings: list[Finding],
    ) -> None:
        """Require non-empty effective profiles and bound their descriptions."""
        limit = dict(catalog.budgets)["profile_description_chars"]
        for profile, selected in resolved_profiles(catalog):
            location = f"catalog.json:profiles:{profile.name}"
            if not selected:
                add_finding(
                    findings,
                    "profile.empty",
                    "effective profile must select at least one source bundle",
                    location,
                )
            description_chars = sum(
                len(record.description)
                for record in skills.values()
                if record.bundle in selected
            )
            if description_chars > limit:
                add_finding(
                    findings,
                    "budget.profile_description",
                    f"profile descriptions exceed {limit} characters",
                    location,
                )

    def _summaries(
        self,
        catalog: Catalog | None,
        skills: dict[str, SkillRecord],
        policy_lines: int,
    ) -> tuple[ProfileSummary, ...]:
        """Summarize resolvable profiles in catalog order; ``()`` with no catalog."""
        if catalog is None:
            return ()
        limits = tuple(sorted(catalog.budgets))
        summaries: list[ProfileSummary] = []
        for profile, selected in resolved_profiles(catalog):
            effective = [value for value in skills.values() if value.bundle in selected]
            summaries.append(
                ProfileSummary(
                    body_lines=sum(item.body_lines for item in effective),
                    description_chars=sum(len(item.description) for item in effective),
                    limits=limits,
                    policy_lines=policy_lines,
                    profile=profile.name,
                    skill_count=len(effective),
                )
            )
        return tuple(summaries)
