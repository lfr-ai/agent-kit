"""Account-neutral maintainers, CODEOWNERS, and publication prerequisites."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import TYPE_CHECKING, TypeGuard
from urllib.parse import urlsplit

from agent_kit.core.errors import DuplicateJSONFieldError
from agent_kit.core.guards import is_int, is_json_object, is_str_list
from agent_kit.infrastructure.documents import load_json
from scripts.checks.governance.inputs import GovernanceInputError, GovernanceIssue

if TYPE_CHECKING:
    from pathlib import Path

_FIELDS = {
    "schema_version",
    "repository",
    "owners",
    "security_contact",
    "conduct_contact",
}
_OWNER = re.compile(r"@[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:/[A-Za-z0-9][A-Za-z0-9_-]*)?\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+\Z")


@dataclass(frozen=True, kw_only=True, slots=True)
class _Maintainers:
    """Validated account-neutral ownership source."""

    owners: list[str]
    repository: str | None
    security_contact: str | None
    conduct_contact: str | None


def _valid_owners(owners: object) -> TypeGuard[list[str]]:
    """Return whether owners are unique GitHub account or team handles."""
    return (
        is_str_list(owners)
        and all(_OWNER.fullmatch(owner) for owner in owners)
        and len(set(owners)) == len(owners)
    )


def _contact(field: str, contact: object) -> str | None:
    """Accept an absent contact or return a private HTTPS or mailto route.

    Args:
        field (str): Maintainer field name, reported when the contact is rejected.
        contact (object): Decoded contact value.

    Returns:
        str | None: The validated contact, or ``None`` when it is absent.

    Raises:
        GovernanceInputError: The contact is not a private HTTPS or mailto route.
    """
    if contact is None:
        return None
    if not isinstance(contact, str) or any(char.isspace() for char in contact):
        raise GovernanceInputError(GovernanceIssue.INVALID_CONTACT, field=field)
    parsed = urlsplit(contact)
    allowed = (
        parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
    ) or (
        parsed.scheme == "mailto"
        and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", parsed.path))
    )
    if not allowed:
        raise GovernanceInputError(GovernanceIssue.INVALID_CONTACT, field=field)
    return contact


def _repository(value: object) -> str | None:
    """Return ``None`` or an approved ``owner/name``, else raise ``GovernanceInputError``."""
    if value is None:
        return None
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value):
        raise GovernanceInputError(GovernanceIssue.INVALID_REPOSITORY)
    return value


def maintainers(root: Path) -> _Maintainers:
    """Read account-neutral ownership, raising ``GovernanceInputError`` if malformed."""
    try:
        raw = load_json((root / ".github/maintainers.json").read_text(encoding="utf-8"))
    except DuplicateJSONFieldError as error:
        raise GovernanceInputError(
            GovernanceIssue.DUPLICATE_MAINTAINER_FIELD
        ) from error
    if not is_json_object(raw) or set(raw) != _FIELDS:
        raise GovernanceInputError(GovernanceIssue.INVALID_MAINTAINER_FIELDS)
    version = raw["schema_version"]
    if not is_int(version) or version != 1:
        raise GovernanceInputError(GovernanceIssue.INVALID_MAINTAINER_SCHEMA)
    owners = raw["owners"]
    if not _valid_owners(owners):
        raise GovernanceInputError(GovernanceIssue.INVALID_OWNERS)
    return _Maintainers(
        owners=owners,
        repository=_repository(raw["repository"]),
        security_contact=_contact("security_contact", raw["security_contact"]),
        conduct_contact=_contact("conduct_contact", raw["conduct_contact"]),
    )


def ownership(root: Path, config: _Maintainers) -> list[str]:
    """Keep ownership coverage explicit, including CODEOWNERS itself.

    Args:
        root (Path): Repository root that holds ``.github/CODEOWNERS``.
        config (_Maintainers): Approved ownership source.

    Returns:
        list[str]: Findings; empty when CODEOWNERS matches the approved owners.
    """
    rules = [
        line.partition("#")[0].strip()
        for line in (root / ".github/CODEOWNERS")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.partition("#")[0].strip()
    ]
    owners = config.owners
    if not owners:
        return [] if not rules else ["CODEOWNERS assigns an unapproved identity"]
    expected = ["*", *owners]
    if len(rules) != 1 or rules[0].split() != expected:
        return ["CODEOWNERS must contain one catch-all rule matching approved owners"]
    return []


def publication_blockers(root: Path) -> list[str]:
    """List unavailable ownership/contact prerequisites without inferring a profile."""
    try:
        config = maintainers(root)
        findings = ownership(root, config)
    except (OSError, ValueError) as error:
        return [str(error)]
    if not config.owners:
        findings.append("CODEOWNERS has no approved personal account or team")
    for field, value in (
        ("repository", config.repository),
        ("security_contact", config.security_contact),
        ("conduct_contact", config.conduct_contact),
    ):
        if value is None:
            findings.append(f"publication requires an approved {field}")
    active_repository = os.environ.get("GITHUB_REPOSITORY")
    if active_repository and config.repository != active_repository:
        findings.append(
            "approved repository does not match the active release repository"
        )
    return findings
