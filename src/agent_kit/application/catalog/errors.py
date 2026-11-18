"""Own the catalog composition precondition and selection errors."""

from __future__ import annotations

from enum import StrEnum, unique
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from agent_kit.core.models import Finding


@unique
class CompositionIssue(StrEnum):
    """Closed set of composition precondition failures."""

    SOURCE_INVALID = "source validation failed; composition was not planned"
    CATALOG_INVALID = "catalog is invalid"
    RUNTIME_SELECTION = "runtime targets must be non-empty and unique"
    UNSUPPORTED_RUNTIME = "runtime target is not supported by this catalog"
    DUPLICATE_SKILLS = "session skill identifiers must be unique"
    DESCRIPTION_BUDGET = "selected profile exceeds the description character budget"
    POLICY_UNAVAILABLE = "source policy cannot be copied"
    LICENSE_UNAVAILABLE = "root license cannot be copied"
    MCP_CONFLICT = "selected bundles declare one MCP server differently"


class CompositionError(ValueError):
    """A source or selection precondition prevents safe composition."""

    def __init__(self, issue: CompositionIssue) -> None:
        """Record the failed precondition with its stable diagnostic.

        Args:
            issue (CompositionIssue): Failed composition invariant.
        """
        self.issue = issue
        super().__init__(issue.value)


class UnknownProfileError(ValueError):
    """A selected profile does not exist in the validated catalog."""

    def __init__(
        self, name: str, *, kind: Literal["profile", "feature profile"] = "profile"
    ) -> None:
        """Identify the unknown selection.

        Args:
            name (str): Selected profile name.
            kind (Literal["profile", "feature profile"]): Profile selection category.
        """
        super().__init__(f"unknown {kind} '{name}'")


class UnavailableSkillsError(ValueError):
    """Requested session skills are absent from the selected profile."""

    def __init__(self, skills: set[str]) -> None:
        """List unavailable identifiers in deterministic order.

        Args:
            skills (set[str]): Unavailable skill identifiers.
        """
        super().__init__(
            f"skills unavailable in selected profile: {', '.join(sorted(skills))}"
        )


class UnavailableBundleError(ValueError):
    """The source snapshot is missing a selected bundle."""

    def __init__(self, name: str) -> None:
        """Identify the unavailable source.

        Args:
            name (str): Selected bundle name.
        """
        super().__init__(f"source bundle '{name}' is unavailable")


class CompositionCollisionError(ValueError):
    """Multiple sources would occupy the same case-insensitive output path."""

    def __init__(self, *, previous: str, relative: str) -> None:
        """Identify conflicting destinations.

        Args:
            previous (str): First source destination.
            relative (str): Colliding source destination.
        """
        super().__init__(
            f"case-insensitive composition collision: '{previous}' and '{relative}'"
        )


class OmittedResourceError(ValueError):
    """A session selection omits a resource needed by one of its skills."""

    def __init__(self, finding: Finding) -> None:
        """Retain the actionable resource finding.

        Args:
            finding (Finding): First missing resource dependency.
        """
        self.finding = finding
        super().__init__(
            f"session selection has an omitted resource: {finding.path}: "
            f"{finding.message}; add its owning skill explicitly"
        )
