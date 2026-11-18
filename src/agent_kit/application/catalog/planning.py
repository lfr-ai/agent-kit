"""Own composition selection: profiles, runtimes, skills, and planned outputs.

Selection works on a validated catalog and captured sources and plans bytes in
memory; writing them belongs to the infrastructure adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from agent_kit.application.catalog.documents import ResourceRoot, skill_records
from agent_kit.application.catalog.errors import (
    CompositionCollisionError,
    CompositionError,
    CompositionIssue,
    OmittedResourceError,
    UnavailableBundleError,
    UnavailableSkillsError,
    UnknownProfileError,
)
from agent_kit.application.catalog.links import check_links, link_index
from agent_kit.application.catalog.manifest import included_paths
from agent_kit.core.primitives import INSTRUCTION_SUFFIX, JSON_INDENT

if TYPE_CHECKING:
    from agent_kit.application.catalog.documents import SkillRecord
    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import (
        Catalog,
        CatalogSnapshot,
        Finding,
        SourceDocument,
    )

_SKILL_MEMBER_MIN_DEPTH = 2  # skills/<name>


@dataclass(frozen=True, kw_only=True, slots=True)
class SkillSelection:
    """Skills available to a composition and the subset made active.

    Attributes:
        requested (tuple[str, ...]): Session skills requested; empty for a project.
        available (dict[str, SkillRecord]): Skills in the selected bundles by name.
        active (set[str]): Names of the skills delivered by the composition.
        description_chars (int): Total description characters of active skills.
    """

    requested: tuple[str, ...]
    available: dict[str, SkillRecord]
    active: set[str]
    description_chars: int


@dataclass(kw_only=True, slots=True)
class Outputs:
    """Mutable accumulator of planned output files and their include roots.

    Attributes:
        files (dict[str, bytes]): Planned content keyed by output path.
        folded (dict[str, str]): First output path keyed by its case-folded form.
        include_paths (set[str]): Retained ``.apm`` include roots.
        documents (list[SourceDocument]): Retained authored source documents.
    """

    files: dict[str, bytes]
    folded: dict[str, str]
    include_paths: set[str]
    documents: list[SourceDocument]


def check_profile_selection(
    catalog: Catalog, profile: str, features: tuple[str, ...]
) -> None:
    """Reject an unknown base profile or feature profile.

    Raises:
        UnknownProfileError: The base or a feature profile is unknown.
    """
    profile_names = {item.name for item in catalog.profiles}
    if profile not in profile_names:
        raise UnknownProfileError(profile)
    unknown = next((name for name in features if name not in profile_names), None)
    if unknown is not None:
        raise UnknownProfileError(unknown, kind="feature profile")


def selected_runtimes(catalog: Catalog, runtimes: tuple[str, ...]) -> tuple[str, ...]:
    """Default to every supported runtime and reject invalid selections.

    Args:
        catalog (Catalog): Validated catalog.
        runtimes (tuple[str, ...]): Requested runtimes; empty selects all.

    Returns:
        tuple[str, ...]: Unique runtimes in request order, or the catalog's
        supported runtimes when none were requested.

    Raises:
        CompositionError: The selection is empty, repeated, or unsupported.
    """
    selected = runtimes or catalog.supported_runtimes
    if not selected or len(set(selected)) != len(selected):
        raise CompositionError(CompositionIssue.RUNTIME_SELECTION)
    if any(runtime not in catalog.supported_runtimes for runtime in selected):
        raise CompositionError(CompositionIssue.UNSUPPORTED_RUNTIME)
    return selected


def skill_selection(
    snapshot: CatalogSnapshot,
    catalog: Catalog,
    selected: tuple[str, ...],
    skills: tuple[str, ...],
) -> SkillSelection:
    """Resolve requested session skills within the selected bundles' budget.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        catalog (Catalog): Validated catalog.
        selected (tuple[str, ...]): Effective bundle names.
        skills (tuple[str, ...]): Requested session skills; empty selects every
            skill in the selected bundles.

    Returns:
        SkillSelection: Requested skills, skills available in the selected
        bundles, the active subset, and the active description character total.

    Raises:
        CompositionError: Skills repeat or exceed the description budget.
        UnavailableSkillsError: A skill is outside the selected bundles.
    """
    limits = dict(catalog.budgets)
    records = skill_records(
        snapshot.bundles, [], limits["description_chars"], limits["skill_body_lines"]
    )
    available = {
        name: record for name, record in records.items() if record.bundle in selected
    }
    if len(skills) != len(set(skills)):
        raise CompositionError(CompositionIssue.DUPLICATE_SKILLS)
    if unavailable := set(skills) - available.keys():
        raise UnavailableSkillsError(unavailable)
    active = set(skills) if skills else set(available)
    description_chars = sum(len(available[name].description) for name in active)
    if description_chars > limits["profile_description_chars"]:
        raise CompositionError(CompositionIssue.DESCRIPTION_BUDGET)
    return SkillSelection(
        requested=skills,
        available=available,
        active=active,
        description_chars=description_chars,
    )


def _instruction_name(document: SourceDocument) -> str:
    """Return the instruction identifier without its ``.instructions.md`` suffix."""
    return PurePosixPath(document.relative_path).name.removesuffix(INSTRUCTION_SUFFIX)


def _is_instruction(document: SourceDocument) -> bool:
    """Check whether a document lives in the ``instructions`` directory."""
    return document.relative_path.startswith("instructions/")


def document_selected(document: SourceDocument, selection: SkillSelection) -> bool:
    """Select a source file for the composition's project or session mode."""
    if document.is_symlink or document.is_directory:
        return False
    parts = PurePosixPath(document.relative_path).parts
    if not parts:
        return False
    if parts[0] == ResourceRoot.SKILLS and (
        len(parts) < _SKILL_MEMBER_MIN_DEPTH or parts[1] not in selection.active
    ):
        return False
    # Prompts are project workflows that may link any selected skill.
    if selection.requested and parts[0] == ResourceRoot.PROMPTS:
        return False
    if not selection.requested or not _is_instruction(document):
        return True
    name = _instruction_name(document)
    return name not in selection.available or name in selection.active


def add_output(outputs: Outputs, relative: str, content: bytes) -> None:
    """Plan one output file, rejecting case-insensitive destination collisions.

    Args:
        outputs (Outputs): Planned outputs; extended in place.
        relative (str): Output path relative to the composition root.
        content (bytes): File content.

    Raises:
        CompositionCollisionError: Two outputs share a case-insensitive destination.
    """
    folded = relative.casefold()
    previous = outputs.folded.get(folded)
    if previous is not None:
        raise CompositionCollisionError(previous=previous, relative=relative)
    outputs.folded[folded] = relative
    outputs.files[relative] = content


def _retained_includes(
    included: tuple[str, ...], documents: tuple[SourceDocument, ...]
) -> set[str]:
    """Return ``.apm/`` includes backed by retained files; directories end in ``/``."""
    paths = {item.relative_path for item in documents}
    retained: set[str] = set()
    for prefix in included:
        if prefix in paths:
            retained.add(f".apm/{prefix}")
        elif any(path.startswith(f"{prefix}/") for path in paths):
            retained.add(f".apm/{prefix}/")
    return retained


def collect_sources(
    snapshot: CatalogSnapshot,
    catalog: Catalog,
    selected: tuple[str, ...],
    selection: SkillSelection,
) -> Outputs:
    """Plan every selected bundle file and its manifest include roots.

    Args:
        snapshot (CatalogSnapshot): Captured source inputs.
        catalog (Catalog): Validated catalog.
        selected (tuple[str, ...]): Effective bundle names.
        selection (SkillSelection): Resolved skills for the composition.

    Returns:
        Outputs: Planned authored files, their documents, and include roots.

    Raises:
        UnavailableBundleError: A selected bundle is not available.
    """
    source_bundles = {item.name: item for item in snapshot.bundles}
    outputs = Outputs(files={}, folded={}, include_paths=set(), documents=[])
    for name in selected:
        source = source_bundles.get(name)
        if source is None:
            raise UnavailableBundleError(name)
        included = included_paths(
            source, [], catalog.version, catalog.supported_runtimes
        )
        retained = tuple(
            item for item in source.files if document_selected(item, selection)
        )
        outputs.include_paths.update(_retained_includes(included, retained))
        for document in retained:
            add_output(outputs, f".apm/{document.relative_path}", document.content)
            outputs.documents.append(document)
    return outputs


def require_session_resources(outputs: Outputs) -> None:
    """Reject session links to omitted resources with ``OmittedResourceError``."""
    index = link_index(name.removeprefix(".apm/") for name in outputs.files)
    missing_links: list[Finding] = []
    for document in outputs.documents:
        check_links(document, index, missing_links, base_is_bundle=True)
    if missing_links:
        raise OmittedResourceError(missing_links[0])


def json_bytes(value: object, *, ensure_ascii: bool) -> bytes:
    """Serialize deterministic, newline-terminated, indented JSON."""
    text = json.dumps(value, indent=JSON_INDENT, ensure_ascii=ensure_ascii)
    return f"{text}\n".encode()


def selection_record(
    selection: SkillSelection, outputs: Outputs, native_role_files: int
) -> JSONObject:
    """Describe the composition mode, active skills, and instruction budget.

    Returns:
        JSONObject: ``mode`` (``session`` or ``project``), sorted ``skills`` and
        ``instructions`` names, ``description_chars`` and ``instruction_chars``
        totals, and ``native_role_files``.
    """
    instructions = {
        _instruction_name(item) for item in outputs.documents if _is_instruction(item)
    }
    return {
        "mode": "session" if selection.requested else "project",
        "skills": sorted(selection.active),
        "instructions": sorted(instructions),
        "description_chars": selection.description_chars,
        "instruction_chars": sum(
            len(item.text or "") for item in outputs.documents if _is_instruction(item)
        ),
        "native_role_files": native_role_files,
    }


def license_content(snapshot: CatalogSnapshot) -> bytes:
    """Return the root ``LICENSE`` bytes; raise ``CompositionError`` when missing."""
    license_document = next(
        (item for item in snapshot.root_documents if item.relative_path == "LICENSE"),
        None,
    )
    if license_document is None:
        raise CompositionError(CompositionIssue.LICENSE_UNAVAILABLE)
    return license_document.content
