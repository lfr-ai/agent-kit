"""Own authored document validation for skills, prompts, instructions, and hooks.

Validates captured ``.apm`` documents and records valid skills for budgets and
profile summaries; it never reads files.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto, unique
from pathlib import PurePosixPath
import re
from typing import TYPE_CHECKING, TypeGuard

from agent_kit.application.catalog.links import (
    check_links,
    is_markdown_source,
    link_index,
)
from agent_kit.application.catalog.schema import is_text
from agent_kit.application.findings import add_finding
from agent_kit.core.executables import hook_issues, script_issue
from agent_kit.core.guards import is_json_object, is_nonempty_text
from agent_kit.core.primitives import (
    FRONTMATTER_DELIMITER,
    INSTRUCTION_SUFFIX,
    KIT_NAME_PATTERN,
    PROMPT_SUFFIX,
    SKILL_FILE,
)

if TYPE_CHECKING:
    from agent_kit.core.guards import JSONObject
    from agent_kit.core.models import BundleSource, Finding, SourceDocument

_SKILL_NAME = re.compile(rf"{KIT_NAME_PATTERN}\Z")
_MAX_SKILL_NAME_CHARS = 64
_SKILL_PATH_DEPTH = 3  # skills/<name>/SKILL.md
_PROMPT_PATH_DEPTH = 2  # prompts/<name>.prompt.md
_HOOK_REGISTRATION_DEPTH = 2  # hooks/<name>.json
_PROMPT_FIELDS = frozenset({"description", "argument-hint", "agent"})
_SKILL_SCOPE_KEYS = frozenset({"applyto", "apply_to", "scope", "paths"})


@dataclass(frozen=True, kw_only=True, slots=True)
class SkillRecord:
    """Validated skill facts used by budget and profile summaries.

    Attributes:
        description (str): Skill discovery description.
        body_lines (int): Line count of the body after frontmatter.
        bundle (str): Name of the owning source bundle.
    """

    description: str
    body_lines: int
    bundle: str


@unique
class ResourceRoot(StrEnum):
    """Top-level ``.apm`` directories that hold authored primitives."""

    SKILLS = auto()
    INSTRUCTIONS = auto()
    PROMPTS = auto()
    HOOKS = auto()


def body_text(text: str) -> str | None:
    """Extract skill body following its YAML frontmatter delimiters."""
    lines = text.splitlines()
    if not lines or lines[0] != FRONTMATTER_DELIMITER:
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line == FRONTMATTER_DELIMITER:
            return "\n".join(lines[index + 1 :])
    return None


def _usable_document(
    document: SourceDocument, bundle: BundleSource, findings: list[Finding]
) -> bool:
    """Report bad documents; ``False`` (skip) only for symlinks and misplaced roots."""
    location = f"{bundle.path}/.apm/{document.relative_path}"
    if document.is_symlink:
        add_finding(
            findings, "source.symlink", "source bundle contains a symlink", location
        )
        return False
    if document.relative_path in ResourceRoot and not document.is_directory:
        add_finding(
            findings,
            "source.root",
            "resource root must be a directory",
            location,
        )
        return False
    if document.parse_error:
        add_finding(
            findings,
            "source.parse",
            "source metadata is malformed or unreadable",
            location,
        )
    if document.frontmatter_error:
        add_finding(
            findings,
            "frontmatter.parse",
            "Markdown frontmatter is malformed",
            location,
        )
    return True


def _validate_hook_file(
    document: SourceDocument, bundle: BundleSource, findings: list[Finding]
) -> None:
    """Validate a hook registration or script beneath ``.apm/hooks``."""
    location = f"{bundle.path}/.apm/{document.relative_path}"
    parts = PurePosixPath(document.relative_path).parts
    if document.is_directory:
        return
    if len(parts) == _HOOK_REGISTRATION_DEPTH and parts[1].endswith(".json"):
        scripts = frozenset(
            PurePosixPath(item.relative_path).name
            for item in bundle.files
            if item.relative_path.startswith("hooks/scripts/") and not item.is_directory
        )
        for issue in hook_issues(document.text or "", scripts):
            add_finding(findings, "hooks.registration", issue, location)
    elif len(parts) > _HOOK_REGISTRATION_DEPTH and parts[1] == "scripts":
        issue = script_issue("/".join(parts[_HOOK_REGISTRATION_DEPTH:]))
        if issue is not None:
            add_finding(findings, "hooks.script", issue, location)
    else:
        add_finding(
            findings,
            "hooks.layout",
            "hooks hold registration JSON files and a scripts directory",
            location,
        )


def _validate_metadata(
    document: SourceDocument,
    bundle: BundleSource,
    records: dict[str, SkillRecord],
    prompts: set[str],
    findings: list[Finding],
    description_limit: int,
    body_limit: int,
) -> None:
    """Dispatch a document to its validator, recording skills and prompt names."""
    relative = document.relative_path
    if relative.startswith("hooks/"):
        _validate_hook_file(document, bundle, findings)
    if relative.endswith(INSTRUCTION_SUFFIX):
        _validate_instruction(document, bundle, findings)
    if relative.startswith("prompts/"):
        _validate_prompt(document, bundle, prompts, findings, description_limit)
    if relative.endswith(f"/{SKILL_FILE}") or relative == SKILL_FILE:
        _validate_skill(
            document, bundle, records, findings, description_limit, body_limit
        )


def skill_records(
    bundles: tuple[BundleSource, ...],
    findings: list[Finding],
    description_limit: int,
    body_limit: int,
) -> dict[str, SkillRecord]:
    """Validate bundle documents and links; return valid skills keyed by name."""
    records: dict[str, SkillRecord] = {}
    prompts: set[str] = set()
    for bundle in bundles:
        index = link_index(
            item.relative_path for item in bundle.files if not item.is_directory
        )
        for document in bundle.files:
            if not _usable_document(document, bundle, findings):
                continue
            _validate_metadata(
                document,
                bundle,
                records,
                prompts,
                findings,
                description_limit,
                body_limit,
            )
            if is_markdown_source(document.relative_path):
                check_links(document, index, findings, base_is_bundle=True)
    return records


def _validate_instruction(
    document: SourceDocument,
    bundle: BundleSource,
    findings: list[Finding],
) -> None:
    """Require portable instruction discovery metadata."""
    location = f"{bundle.path}/.apm/{document.relative_path}"
    metadata = document.frontmatter
    if not is_json_object(metadata):
        add_finding(
            findings,
            "instruction.frontmatter",
            "instruction metadata is required",
            location,
        )
        return
    for key in ("description", "applyTo"):
        if not is_text(metadata.get(key)):
            add_finding(
                findings,
                "instruction.metadata",
                f"instructions require non-empty '{key}' metadata",
                location,
            )


def _prompt_name(relative_path: str) -> str | None:
    """Return a legal flat ``prompts/kit-<name>.prompt.md`` name, if any."""
    parts = PurePosixPath(relative_path).parts
    name = parts[-1].removesuffix(PROMPT_SUFFIX)
    if (
        len(parts) != _PROMPT_PATH_DEPTH
        or not parts[-1].endswith(PROMPT_SUFFIX)
        or _SKILL_NAME.fullmatch(name) is None
    ):
        return None
    return name


def one_line(value: object, limit: int) -> TypeGuard[str]:
    """Check for a non-blank, single-line string within ``limit`` characters."""
    return is_nonempty_text(value) and "\n" not in value and len(value) <= limit


def _check_prompt_metadata(
    metadata: JSONObject,
    location: str,
    findings: list[Finding],
    description_limit: int,
) -> None:
    """Allow only discovery metadata and a bounded one-line description."""
    for field in sorted(set(metadata) - _PROMPT_FIELDS):
        add_finding(
            findings,
            "prompt.metadata",
            f"prompt metadata '{field}' is not allowed; tools and models stay native",
            location,
        )
    if not one_line(metadata.get("description"), description_limit):
        add_finding(
            findings,
            "prompt.description",
            f"prompt description must be one line of at most {description_limit} characters",
            location,
        )


def _validate_prompt(
    document: SourceDocument,
    bundle: BundleSource,
    names: set[str],
    findings: list[Finding],
    description_limit: int,
) -> None:
    """Require a flat, uniquely named prompt with discovery-only metadata."""
    location = f"{bundle.path}/.apm/{document.relative_path}"
    if document.is_directory:
        return
    name = _prompt_name(document.relative_path)
    if name is None:
        add_finding(
            findings,
            "prompt.name",
            f"prompts must be prompts/kit-<name>{PROMPT_SUFFIX}",
            location,
        )
        return
    if name in names:
        add_finding(
            findings, "prompt.duplicate", f"duplicate prompt '{name}'", location
        )
    names.add(name)
    metadata = document.frontmatter
    if not is_json_object(metadata):
        add_finding(
            findings, "prompt.frontmatter", "prompt metadata is required", location
        )
        return
    _check_prompt_metadata(metadata, location, findings, description_limit)


def legal_skill_name(name: object) -> TypeGuard[str]:
    """Check the bounded ``kit-`` skill identifier grammar."""
    return (
        isinstance(name, str)
        and len(name) <= _MAX_SKILL_NAME_CHARS
        and _SKILL_NAME.fullmatch(name) is not None
    )


def _check_skill_identity(
    name: str,
    metadata: JSONObject,
    relative_path: str,
    records: dict[str, SkillRecord],
    location: str,
    findings: list[Finding],
) -> None:
    """Check skill placement, uniqueness, and absence of native scope metadata."""
    parts = PurePosixPath(relative_path).parts
    if (
        len(parts) != _SKILL_PATH_DEPTH
        or parts[0] != ResourceRoot.SKILLS
        or parts[-1] != SKILL_FILE
    ):
        add_finding(
            findings,
            "skill.parent",
            f"{SKILL_FILE} must be directly beneath skills/<name>",
            location,
        )
    elif name != parts[1]:
        add_finding(
            findings,
            "skill.parent",
            "skill name must match its parent directory",
            location,
        )
    if name in records:
        add_finding(
            findings, "skill.duplicate", f"duplicate skill name '{name}'", location
        )
    if any(key.casefold() in _SKILL_SCOPE_KEYS for key in metadata):
        add_finding(
            findings,
            "skill.scope",
            "native scope metadata is not allowed in skill frontmatter",
            location,
        )


def _skill_description(
    metadata: JSONObject,
    description_limit: int,
    location: str,
    findings: list[Finding],
) -> str | None:
    """Return a required skill description, reporting budget overruns."""
    description = metadata.get("description")
    if not is_text(description):
        add_finding(
            findings, "skill.description", "skill description is required", location
        )
        return None
    if len(description) > description_limit:
        add_finding(
            findings,
            "budget.description",
            f"skill description exceeds {description_limit} characters",
            location,
        )
    return description


def _skill_body_lines(
    document: SourceDocument, body_limit: int, location: str, findings: list[Finding]
) -> int | None:
    """Return the skill body line count, reporting delimiters and budget."""
    body = body_text(document.text or "")
    if body is None:
        add_finding(
            findings, "skill.body", "skill frontmatter delimiters are invalid", location
        )
        return None
    lines = len(body.splitlines())
    if lines > body_limit:
        add_finding(
            findings,
            "budget.skill_body",
            f"skill body exceeds {body_limit} lines",
            location,
        )
    return lines


def _validate_skill(
    document: SourceDocument,
    bundle: BundleSource,
    records: dict[str, SkillRecord],
    findings: list[Finding],
    description_limit: int,
    body_limit: int,
) -> None:
    """Validate a skill name, description, body, and portable metadata."""
    location = f"{bundle.path}/.apm/{document.relative_path}"
    metadata = document.frontmatter
    if not is_json_object(metadata):
        add_finding(
            findings, "skill.frontmatter", "skill metadata is required", location
        )
        return
    name = metadata.get("name")
    if not legal_skill_name(name):
        add_finding(findings, "skill.name", "skill name is not legal", location)
        return
    _check_skill_identity(
        name, metadata, document.relative_path, records, location, findings
    )
    description = _skill_description(metadata, description_limit, location, findings)
    if description is None:
        return
    lines = _skill_body_lines(document, body_limit, location, findings)
    if lines is not None:
        records[name] = SkillRecord(
            description=description, body_lines=lines, bundle=bundle.name
        )
