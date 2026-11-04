"""Check local community and workflow contracts without using a GitHub account."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, TypedDict, TypeGuard, override
from urllib.parse import urlsplit

import yaml

from agent_kit.core.guards import is_int, is_json_object, is_str_list

if TYPE_CHECKING:
    from yaml.nodes import MappingNode

_ROOT = Path(__file__).resolve().parents[1]
_FIELDS = {
    "schema_version",
    "repository",
    "owners",
    "security_contact",
    "conduct_contact",
}
_OWNER = re.compile(r"@[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:/[A-Za-z0-9][A-Za-z0-9_-]*)?\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+\Z")
_ACTION = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}\Z")
_DOCS = (
    "GOVERNANCE.md",
    "SUPPORT.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
)
_WORKFLOWS = {
    "ci.yml",
    "codeql.yml",
    "dependency-audit.yml",
    "dependency-review.yml",
    "release.yml",
    "scorecard.yml",
}
_REUSABLE = {
    "ci.yml": "$/.github/workflows/dependency-audit.yml",
    "release.yml": "$/.github/workflows/ci.yml",
}


class _RulesetContract(TypedDict):
    """Fixed target, scope, and protection rules of one importable ruleset."""

    target: str
    include: list[str]
    required: frozenset[str]


_RULESET_RULES = {
    "main.json": _RulesetContract(
        target="branch",
        include=["~DEFAULT_BRANCH"],
        required=frozenset(
            {"deletion", "non_fast_forward", "pull_request", "required_status_checks"}
        ),
    ),
    "release-tags.json": _RulesetContract(
        target="tag",
        include=["refs/tags/v*"],
        required=frozenset({"deletion", "non_fast_forward", "update"}),
    ),
}
_REQUIRED_CHECK = "Required toolkit checks"
_REQUIRED_APPROVALS = 1
# Pull-request-only bypass covers the entire main ruleset, including status checks,
# not just approval. It does not authorize direct pushes; agents use a write role.
_ADMIN_ROLE_ID = 5
_BYPASS_ACTORS = {
    "main.json": [
        {
            "actor_id": _ADMIN_ROLE_ID,
            "actor_type": "RepositoryRole",
            "bypass_mode": "pull_request",
        }
    ],
    "release-tags.json": [],
}
_DEPENDABOT_VERSION = 2
_DEPENDABOT_ECOSYSTEMS = frozenset(
    {"uv", "bun", "docker", "github-actions", "pre-commit", "devcontainers"}
)
_AUDIT_COMMAND = "uv run --no-project python scripts/audit_dependencies.py"
_SYNC_COMMAND = "uv sync --locked"
_REVIEW_SCOPES = {"runtime", "development", "unknown"}
_OIDC_READ = {"contents": "read", "id-token": "write"}
_PERMISSIONS = {
    ("release.yml", "publish"): {
        "contents": "write",
        "id-token": "write",
        "attestations": "write",
    },
    # Caller grant for the reusable gate's Codecov OIDC upload job.
    ("release.yml", "verify"): _OIDC_READ,
    ("ci.yml", "coverage"): _OIDC_READ,
    ("codeql.yml", "analyze"): {"contents": "read", "security-events": "write"},
    ("scorecard.yml", "analysis"): {
        "contents": "read",
        "actions": "read",
        "id-token": "write",
        "security-events": "write",
    },
}
_UPLOADS = {
    ("release-artifacts", "build/release/*", "error"),
    ("coverage-report", "build/coverage/coverage.xml", "error"),
}
_DOWNLOADS = {("release-artifacts", "artifacts"), ("coverage-report", "build/coverage")}
_PULL_REQUEST_GUARDS = (
    "dismiss_stale_reviews_on_push",
    "require_code_owner_review",
    "require_last_push_approval",
    "required_review_thread_resolution",
)


class _GovernanceIssue(Enum):
    """Stable diagnostics for malformed governance input."""

    DUPLICATE_WORKFLOW_KEY = "workflow contains a duplicate or non-string key"
    DUPLICATE_MAINTAINER_FIELD = "maintainer configuration contains duplicate fields"
    INVALID_MAINTAINER_FIELDS = "maintainer configuration has missing or unknown fields"
    INVALID_MAINTAINER_SCHEMA = "maintainer schema_version must be 1"
    INVALID_OWNERS = "owners must be unique GitHub account or team handles"
    INVALID_REPOSITORY = "repository must be an approved owner/name coordinate"
    INVALID_CONTACT = "must be a private HTTPS or mailto contact route"


class _GovernanceInputError(ValueError):
    """Report one known governance input contract failure."""

    def __init__(self, issue: _GovernanceIssue, *, field: str | None = None) -> None:
        """Prefix a contact ``issue`` with optional ``field``; retain both."""
        self.issue = issue
        self.field = field
        message = (
            f"{field} {issue.value}"
            if issue is _GovernanceIssue.INVALID_CONTACT and field is not None
            else issue.value
        )
        super().__init__(message)


class _WorkflowLoader(yaml.BaseLoader):
    """Parse workflow scalars as strings and reject duplicate mapping keys."""

    @override
    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[str, object]:
        """Prevent duplicate keys from overriding earlier permission declarations.

        Raises:
            _GovernanceInputError: A workflow key is repeated.
        """
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise _GovernanceInputError(_GovernanceIssue.DUPLICATE_WORKFLOW_KEY)
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _child(value: object, key: str) -> object:
    """Return a decoded object's field.

    Args:
        value (object): Decoded value that may be an object.
        key (str): Field name to read.

    Returns:
        object: ``value[key]``, or ``None`` when ``value`` is not an object or lacks the key.
    """
    return value.get(key) if is_json_object(value) else None


def _job_needs(job: object) -> list[object] | None:
    """Return a job's ``needs`` as a list, accepting the one-string shorthand."""
    needs = _child(job, "needs")
    if isinstance(needs, str):
        return [needs]
    return needs if isinstance(needs, list) else None


@dataclass(frozen=True, kw_only=True, slots=True)
class _Maintainers:
    """Validated account-neutral ownership source."""

    owners: list[str]
    repository: str | None
    security_contact: str | None
    conduct_contact: str | None


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate maintainer fields without exposing their contents.

    Args:
        pairs (list[tuple[str, object]]): Decoded ``(field, value)`` pairs in file order.

    Returns:
        dict[str, object]: The fields of one maintainer object keyed by name.

    Raises:
        _GovernanceInputError: A maintainer field is repeated.
    """
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _GovernanceInputError(_GovernanceIssue.DUPLICATE_MAINTAINER_FIELD)
        value[key] = item
    return value


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
        _GovernanceInputError: The contact is not a private HTTPS or mailto route.
    """
    if contact is None:
        return None
    if not isinstance(contact, str) or any(char.isspace() for char in contact):
        raise _GovernanceInputError(_GovernanceIssue.INVALID_CONTACT, field=field)
    parsed = urlsplit(contact)
    allowed = (
        parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
    ) or (
        parsed.scheme == "mailto"
        and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", parsed.path))
    )
    if not allowed:
        raise _GovernanceInputError(_GovernanceIssue.INVALID_CONTACT, field=field)
    return contact


def _repository(value: object) -> str | None:
    """Accept an absent repository or return an approved ``owner/name`` coordinate.

    Raises:
        _GovernanceInputError: The value is not an approved coordinate.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not _REPOSITORY.fullmatch(value):
        raise _GovernanceInputError(_GovernanceIssue.INVALID_REPOSITORY)
    return value


def _maintainers(root: Path) -> _Maintainers:
    """Read the explicit account-neutral ownership source.

    Raises:
        _GovernanceInputError: The maintainer source is malformed.
    """
    raw: object = json.loads(
        (root / ".github/maintainers.json").read_text(encoding="utf-8"),
        object_pairs_hook=_unique_pairs,
    )
    if not is_json_object(raw) or set(raw) != _FIELDS:
        raise _GovernanceInputError(_GovernanceIssue.INVALID_MAINTAINER_FIELDS)
    version = raw["schema_version"]
    if not is_int(version) or version != 1:
        raise _GovernanceInputError(_GovernanceIssue.INVALID_MAINTAINER_SCHEMA)
    owners = raw["owners"]
    if not _valid_owners(owners):
        raise _GovernanceInputError(_GovernanceIssue.INVALID_OWNERS)
    return _Maintainers(
        owners=owners,
        repository=_repository(raw["repository"]),
        security_contact=_contact("security_contact", raw["security_contact"]),
        conduct_contact=_contact("conduct_contact", raw["conduct_contact"]),
    )


def _ownership(root: Path, config: _Maintainers) -> list[str]:
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
        config = _maintainers(root)
        findings = _ownership(root, config)
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


def _load_workflow(path: Path) -> object:
    """Parse one workflow with string scalars and unique mapping keys."""
    loader = _WorkflowLoader(path.read_text(encoding="utf-8"))
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def _checkout_reviewed(options: object) -> bool:
    """Return whether checkout disables persistent credentials."""
    return is_json_object(options) and options.get("persist-credentials") == "false"


def _upload_reviewed(options: object) -> bool:
    """Return whether an artifact upload uses a reviewed name and path."""
    return (
        is_json_object(options)
        and (
            options.get("name"),
            options.get("path"),
            options.get("if-no-files-found"),
        )
        in _UPLOADS
    )


def _download_reviewed(options: object) -> bool:
    """Return whether an artifact download matches a reviewed upload."""
    return (
        is_json_object(options)
        and (options.get("name"), options.get("path")) in _DOWNLOADS
    )


def _codecov_reviewed(options: object) -> bool:
    """Return whether Codecov pins its CLI, keeps validation, and uses OIDC."""
    return (
        is_json_object(options)
        and str(options.get("version", "")).startswith("v")
        and options.get("skip_validation") in {None, "false"}
        and "token" not in options
    )


_ACTION_OPTION_RULES = (
    (
        "actions/checkout@",
        _checkout_reviewed,
        "checkout must disable persistent credentials",
    ),
    (
        "actions/upload-artifact@",
        _upload_reviewed,
        "artifact upload must use a reviewed name and path",
    ),
    (
        "actions/download-artifact@",
        _download_reviewed,
        "artifact download must match a reviewed upload",
    ),
    (
        "codecov/codecov-action@",
        _codecov_reviewed,
        "Codecov must pin its CLI, keep validation, and use OIDC",
    ),
)


def _step_findings(name: str, step: object) -> list[str]:
    """Reject mutable actions, interpolated scripts, and unreviewed options.

    Args:
        name (str): Workflow file name used to prefix each finding.
        step (object): Decoded workflow step.

    Returns:
        list[str]: One message per violated step rule; empty when the step passes.
    """
    if not is_json_object(step):
        return [f"{name}: malformed workflow step"]
    findings: list[str] = []
    action = step.get("uses")
    if action is not None and (
        not isinstance(action, str) or not _ACTION.fullmatch(action)
    ):
        findings.append(f"{name}: actions must use an immutable full commit SHA")
    command = step.get("run")
    if isinstance(command, str) and "${{" in command:
        findings.append(
            f"{name}: expressions belong in env, not interpolated run scripts"
        )
    if isinstance(action, str):
        findings.extend(
            f"{name}: {message}"
            for prefix, reviewed, message in _ACTION_OPTION_RULES
            if action.startswith(prefix) and not reviewed(step.get("with"))
        )
    return findings


def _job_policy_findings(
    name: str, identifier: str, job: dict[str, object]
) -> list[str]:
    """Require timeouts, approved permissions, no secrets, and reviewed reuse.

    Args:
        name (str): Workflow file name used to prefix each finding.
        identifier (str): Job key within the workflow.
        job (dict[str, object]): Decoded job mapping.

    Returns:
        list[str]: One message per violated job rule; empty when the job passes.
    """
    findings: list[str] = []
    if "steps" in job and not isinstance(job.get("timeout-minutes"), str):
        findings.append(f"{name}: job {identifier} needs an explicit timeout")
    permissions = job.get("permissions")
    permitted = _PERMISSIONS.get((name, identifier), {"contents": "read"})
    if permissions is not None and permissions != permitted:
        findings.append(f"{name}: job {identifier} has unapproved permissions")
    if "secrets" in job:
        findings.append(f"{name}: job secrets must not be inherited or declared")
    reusable = job.get("uses")
    if reusable is not None and reusable != _REUSABLE.get(name):
        findings.append(f"{name}: unapproved reusable workflow")
    return findings


def _job_findings(name: str, identifier: str, job: object) -> list[str]:
    """Check one job's policy and every step it runs.

    Args:
        name (str): Workflow file name used to prefix each finding.
        identifier (str): Job key within the workflow.
        job (object): Decoded job value.

    Returns:
        list[str]: Policy and step findings; empty when the job passes.
    """
    if not is_json_object(job):
        return [f"{name}: job {identifier} must be a mapping"]
    findings = _job_policy_findings(name, identifier, job)
    steps = job.get("steps", [])
    if not isinstance(steps, list):
        findings.append(f"{name}: steps must be a list")
        return findings
    for step in steps:
        findings.extend(_step_findings(name, step))
    return findings


def _root_findings(
    name: str, raw: dict[str, object], triggers: dict[str, object]
) -> list[str]:
    """Reject privileged triggers and broader default permissions.

    Args:
        name (str): Workflow file name used to prefix each finding.
        raw (dict[str, object]): Decoded workflow document.
        triggers (dict[str, object]): Decoded ``on`` mapping of the workflow.

    Returns:
        list[str]: One message per violated root rule; empty when the root passes.
    """
    findings: list[str] = []
    if "pull_request_target" in triggers:
        findings.append(f"{name}: pull_request_target is not an approved trigger")
    if raw.get("permissions") != {"contents": "read"}:
        findings.append(f"{name}: root permissions must be contents: read only")
    return findings


def _ci_audit_consumers(jobs: dict[str, object]) -> list[str]:
    """Keep full-install jobs behind a successful audit with no failure override."""
    findings: list[str] = []
    for identifier in ("verify", "precommit", "smoke"):
        job = jobs.get(identifier)
        needed = _job_needs(job)
        if (
            not is_json_object(job)
            or needed is None
            or "audit" not in needed
            or job.get("if") not in (None, "success()")
        ):
            findings.append(
                f"ci.yml: {identifier} dependencies must be audited before installation; "
                "need audit with success-only execution"
            )
    return findings


def _ci_findings(triggers: dict[str, object], jobs: dict[str, object]) -> list[str]:
    """Require gate triggers, a complete summary, and audit-before-install edges.

    Args:
        triggers (dict[str, object]): Decoded ``on`` mapping of ``ci.yml``.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of ``ci.yml``.

    Returns:
        list[str]: One message per violated CI rule; empty when the workflow passes.
    """
    findings: list[str] = []
    if not {"pull_request", "merge_group", "workflow_call"}.issubset(triggers):
        findings.append(
            "ci.yml: PR, merge queue, and reusable verification triggers are required"
        )
    summary = jobs.get("checks")
    needed = _job_needs(summary)
    if (
        not is_json_object(summary)
        or needed is None
        or sorted(str(item) for item in needed) != sorted(set(jobs) - {"checks"})
        or summary.get("if") != "always()"
    ):
        findings.append(
            "ci.yml: the required summary must always run and need every other job"
        )
    audit = jobs.get("audit")
    if not is_json_object(audit) or audit.get("uses") != _REUSABLE["ci.yml"]:
        findings.append("ci.yml: the dependency audit must be a required job")
    findings.extend(_ci_audit_consumers(jobs))
    return findings


def _release_command_findings(publish: dict[str, object]) -> list[str]:
    """Require one draft prerelease creation that verifies an existing tag."""
    release_commands = [
        command for command in _run_commands(publish) if "gh release create " in command
    ]
    if len(release_commands) != 1 or any(
        flag not in release_commands[0].split()
        for flag in ("--draft", "--prerelease", "--verify-tag")
    ):
        return ["release.yml: draft prerelease creation must verify an existing tag"]
    return []


def _release_findings(
    triggers: dict[str, object], jobs: dict[str, object]
) -> list[str]:
    """Require verified, environment-gated publication from a tag push.

    Args:
        triggers (dict[str, object]): Decoded ``on`` mapping of ``release.yml``.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of ``release.yml``.

    Returns:
        list[str]: One message per violated release rule; empty when it passes.
    """
    findings: list[str] = []
    publish = jobs.get("publish")
    verify = jobs.get("verify")
    if not is_json_object(verify) or verify.get("uses") != _REUSABLE["release.yml"]:
        findings.append(
            "release.yml: publication must depend on the shared verification gate"
        )
    if _child(_child(verify, "with"), "release-tag") != "${{ github.ref_name }}":
        findings.append(
            "release.yml: verification must validate the actual release tag"
        )
    if (
        not is_json_object(publish)
        or publish.get("needs") != "verify"
        or publish.get("environment") != "release"
        or publish.get("if") != "github.event.repository.visibility == 'public'"
    ):
        findings.append(
            "release.yml: approved release environment and verified public tag are required"
        )
    if "push" not in triggers or len(triggers) != 1:
        findings.append("release.yml: only tag push may start the release workflow")
    if is_json_object(publish):
        findings.extend(_release_command_findings(publish))
    return findings


def _dependency_review_workflow(
    triggers: dict[str, object], jobs: dict[str, object]
) -> list[str]:
    """Require complete dependency review limited to pull requests.

    Args:
        triggers (dict[str, object]): Decoded ``on`` mapping of the workflow.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of the workflow.

    Returns:
        list[str]: Review-scope and trigger findings; empty when the workflow passes.
    """
    findings = _dependency_review(jobs)
    if set(triggers) != {"pull_request"}:
        findings.append(
            "dependency-review.yml: dependency review is supported only for pull_request events"
        )
    return findings


def _workflow_specific(
    name: str, triggers: dict[str, object], jobs: dict[str, object]
) -> list[str]:
    """Apply the contract owned by one named workflow, if any.

    Args:
        name (str): Workflow file name that selects the contract.
        triggers (dict[str, object]): Decoded ``on`` mapping of the workflow.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of the workflow.

    Returns:
        list[str]: Workflow-specific findings; empty for workflows without one.
    """
    if name == "ci.yml":
        return _ci_findings(triggers, jobs)
    if name == "dependency-audit.yml":
        return _dependency_audit(triggers, jobs)
    if name == "dependency-review.yml":
        return _dependency_review_workflow(triggers, jobs)
    if name == "release.yml":
        return _release_findings(triggers, jobs)
    return []


def _workflow(root: Path, name: str) -> list[str]:
    """Reject unsafe or unreviewed executable workflow surfaces.

    Args:
        root (Path): Repository root that holds ``.github/workflows``.
        name (str): Workflow file name to check.

    Returns:
        list[str]: Root, job, and workflow-specific findings; empty when it passes.
    """
    raw = _load_workflow(root / ".github/workflows" / name)
    if not is_json_object(raw):
        return [f"{name}: workflow must be a mapping"]
    triggers = raw.get("on")
    if not is_json_object(triggers):
        return [f"{name}: explicit trigger mapping is required"]
    findings = _root_findings(name, raw, triggers)
    jobs = raw.get("jobs")
    if not is_json_object(jobs):
        return [*findings, f"{name}: jobs must be explicit"]
    for identifier, job in jobs.items():
        findings.extend(_job_findings(name, identifier, job))
    findings.extend(_workflow_specific(name, triggers, jobs))
    return findings


def _list_child(value: object, key: str) -> list[object]:
    """Return a decoded object's list field.

    Args:
        value (object): Decoded value that may be an object.
        key (str): Field name to read.

    Returns:
        list[object]: ``value[key]`` when it is a list, otherwise an empty list.
    """
    child = _child(value, key)
    return child if isinstance(child, list) else []


def _run_commands(job: object) -> list[str]:
    """Return a job's literal shell commands in step order."""
    return [
        command
        for step in _list_child(job, "steps")
        if is_json_object(step) and isinstance(command := step.get("run"), str)
    ]


def _dependency_audit(
    triggers: dict[str, object], jobs: dict[str, object]
) -> list[str]:
    """Require scheduled, reusable auditing that precedes installing the lock.

    Args:
        triggers (dict[str, object]): Decoded ``on`` mapping of the workflow.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of the workflow.

    Returns:
        list[str]: Trigger and ordering findings; empty when the workflow passes.
    """
    findings: list[str] = []
    if not {"schedule", "workflow_call"}.issubset(triggers):
        findings.append(
            "dependency-audit.yml: scheduled and reusable triggers are required"
        )
    commands = _run_commands(jobs.get("audit"))
    if (
        _AUDIT_COMMAND not in commands
        or _SYNC_COMMAND not in commands
        or commands.index(_AUDIT_COMMAND) > commands.index(_SYNC_COMMAND)
    ):
        findings.append(
            "dependency-audit.yml: the lock must be audited before it is installed"
        )
    return findings


def _dependency_review(jobs: dict[str, object]) -> list[str]:
    """Require vulnerability and license review for every dependency scope."""
    job = jobs.get("review")
    options = next(
        (
            step.get("with")
            for step in _list_child(job, "steps")
            if is_json_object(step)
            and str(step.get("uses", "")).startswith(
                "actions/dependency-review-action@"
            )
        ),
        None,
    )
    scopes = (
        {scope.strip() for scope in str(options.get("fail-on-scopes", "")).split(",")}
        if is_json_object(options)
        else set()
    )
    if (
        not is_json_object(options)
        or options.get("vulnerability-check") != "true"
        or options.get("license-check") != "true"
        or options.get("fail-on-severity") != "low"
        or not str(options.get("allow-licenses", "")).strip()
        or scopes != _REVIEW_SCOPES
    ):
        return [
            "dependency-review.yml: vulnerability and license review must cover every dependency scope"
        ]
    return []


def _ruleset(root: Path, name: str) -> list[str]:
    """Validate an importable repository ruleset without claiming it is applied.

    Args:
        root (Path): Repository root that holds ``.github/rulesets``.
        name (str): Ruleset file name, a key of the reviewed contracts.

    Returns:
        list[str]: Scope, inventory, and parameter findings; empty when it passes.
    """
    expected = _RULESET_RULES[name]
    try:
        raw: object = json.loads(
            (root / ".github/rulesets" / name).read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
        )
    except (OSError, ValueError):
        return [f"rulesets/{name}: missing, invalid, or duplicate-key JSON"]
    if not is_json_object(raw):
        return [f"rulesets/{name}: ruleset must be a mapping"]
    findings = _ruleset_scope_findings(name, raw, expected)
    rules = raw.get("rules")
    entries = rules if isinstance(rules, list) else []
    typed: dict[str, object] = {
        kind: rule
        for rule in entries
        if is_json_object(rule) and isinstance(kind := rule.get("type"), str)
    }
    if len(typed) != len(entries) or set(typed) != expected["required"]:
        findings.append(
            f"rulesets/{name}: rule inventory must contain each reviewed type exactly once"
        )
    if name == "main.json":
        findings.extend(_main_ruleset_parameters(typed))
    return findings


def _ruleset_scope_findings(
    name: str, raw: dict[str, object], expected: _RulesetContract
) -> list[str]:
    """Require the fixed target, scope, enforcement, and reviewed bypass actors.

    Args:
        name (str): Ruleset file name used to prefix each finding.
        raw (dict[str, object]): Decoded ruleset document.
        expected (_RulesetContract): Reviewed target, include refs, and required rule types.

    Returns:
        list[str]: Scope and bypass findings; empty when both match the contract.
    """
    findings: list[str] = []
    ref_name = _child(raw.get("conditions"), "ref_name")
    if (
        raw.get("target") != expected["target"]
        or raw.get("enforcement") != "active"
        or not is_json_object(ref_name)
        or ref_name.get("include") != expected["include"]
        or ref_name.get("exclude") != []
    ):
        findings.append(f"rulesets/{name}: target, scope, and enforcement are fixed")
    if raw.get("bypass_actors") != _BYPASS_ACTORS[name]:
        findings.append(f"rulesets/{name}: bypass actors require explicit review")
    return findings


def _review_parameter_findings(parameters: object) -> list[str]:
    """Require the reviewed positive approval count and all review guards."""
    if not is_json_object(parameters):
        return ["rulesets/main.json: review parameters are required"]
    findings: list[str] = []
    if not all(parameters.get(guard) is True for guard in _PULL_REQUEST_GUARDS):
        findings.append("rulesets/main.json: review guards must all be enabled")
    count = parameters.get("required_approving_review_count")
    if not is_int(count) or count != _REQUIRED_APPROVALS:
        findings.append(
            "rulesets/main.json: review count must remain the reviewed positive integer"
        )
    return findings


def _main_ruleset_parameters(rules: dict[str, object]) -> list[str]:
    """Check review and status-check parameters of the default-branch ruleset."""
    findings = _review_parameter_findings(
        _child(rules.get("pull_request"), "parameters")
    )
    status_parameters = _child(rules.get("required_status_checks"), "parameters")
    checks = _child(status_parameters, "required_status_checks")
    if checks != [{"context": _REQUIRED_CHECK}]:
        findings.append(
            "rulesets/main.json: the stable required matrix summary is the only check"
        )
    if (
        not is_json_object(status_parameters)
        or status_parameters.get("strict_required_status_checks_policy") is not True
    ):
        findings.append("rulesets/main.json: required status checks must be strict")
    return findings


def _labels(root: Path) -> set[str] | None:
    """Return unique label names from the inventory, or ``None`` when it is invalid."""
    try:
        raw: object = yaml.safe_load(
            (root / ".github/labels.yml").read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, list):
        return None
    names: set[str] = set()
    for item in raw:
        if (
            not is_json_object(item)
            or set(item) != {"name", "description", "color"}
            or not all(isinstance(value, str) for value in item.values())
            or re.fullmatch(r"[0-9a-f]{6}", str(item["color"])) is None
            or item["name"] in names
        ):
            return None
        names.add(str(item["name"]))
    return names


def _yaml_mapping(path: Path) -> dict[str, object] | None:
    """Load one YAML mapping, tolerating a missing or malformed file.

    Returns:
        dict[str, object] | None: The decoded mapping, or ``None`` when unreadable or not a mapping.
    """
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return raw if is_json_object(raw) else None


def _issue_config_findings(root: Path, repository: str | None) -> list[str]:
    """Require disabled blank issues and a private security route.

    Args:
        root (Path): Repository root that holds ``.github/ISSUE_TEMPLATE``.
        repository (str | None): Approved ``owner/name`` coordinate, if any.

    Returns:
        list[str]: Findings; empty when the issue config passes.
    """
    findings: list[str] = []
    config = _yaml_mapping(root / ".github/ISSUE_TEMPLATE/config.yml")
    if config is None or config.get("blank_issues_enabled") is not False:
        findings.append("issue config: blank issues must be disabled")
    urls = [
        url
        for item in _list_child(config, "contact_links")
        if is_json_object(item) and isinstance(url := item.get("url"), str)
    ]
    security_routes = [
        url
        for url in urls
        if url.endswith(("/security/advisories/new", "/blob/main/SECURITY.md"))
    ]
    if not security_routes:
        findings.append(
            "issue config: private security reporting or SECURITY.md instructions are required"
        )
    elif repository is not None and not all(
        url.startswith(f"https://github.com/{repository}/") for url in urls
    ):
        findings.append("issue config: contact links must use the approved repository")
    return findings


def _issue_form_findings(root: Path, labels: set[str]) -> list[str]:
    """Require issue forms to apply only declared labels.

    Args:
        root (Path): Repository root that holds ``.github/ISSUE_TEMPLATE``.
        labels (set[str]): Label names declared in ``labels.yml``.

    Returns:
        list[str]: Findings; empty when every form uses declared labels.
    """
    findings: list[str] = []
    for form in ("bug.yml", "capability-change.yml", "feature.yml"):
        data = _yaml_mapping(root / ".github/ISSUE_TEMPLATE" / form)
        form_labels = _list_child(data, "labels")
        if not form_labels:
            findings.append(f"{form}: issue form labels are required")
            continue
        findings.extend(
            f"{form}: label {label!r} is not in labels.yml"
            for label in form_labels
            if label not in labels
        )
    return findings


def _release_labels(changelog: object) -> set[str]:
    """Collect labels named by release-note categories and exclusions."""
    used = {str(label) for label in _list_child(_child(changelog, "exclude"), "labels")}
    for category in _list_child(changelog, "categories"):
        used.update(str(label) for label in _list_child(category, "labels"))
    return used


def _intake(root: Path, repository: str | None) -> list[str]:
    """Require a private security route and valid labels without claiming host state.

    Args:
        root (Path): Repository root that holds the ``.github`` intake files.
        repository (str | None): Approved ``owner/name`` coordinate, if any.

    Returns:
        list[str]: Findings; empty when intake configuration passes.
    """
    labels = _labels(root)
    if labels is None:
        return ["labels.yml: must list unique name, description, and hex color"]
    findings = _issue_config_findings(root, repository)
    findings.extend(_issue_form_findings(root, labels))
    release = _yaml_mapping(root / ".github/release.yml")
    used = _release_labels(_child(release, "changelog"))
    findings.extend(
        f"release.yml: label {label!r} is not in labels.yml"
        for label in sorted(used - {"*"} - labels)
    )
    return findings


def _dependabot(root: Path) -> list[str]:
    """Require Dependabot for every manifest kind, using only declared labels."""
    config = _yaml_mapping(root / ".github/dependabot.yml")
    updates = _child(config, "updates")
    if (
        config is None
        or config.get("version") != _DEPENDABOT_VERSION
        or not isinstance(updates, list)
    ):
        return ["dependabot.yml: version 2 with an updates list is required"]
    entries = [item for item in updates if is_json_object(item)]
    ecosystems = {item.get("package-ecosystem") for item in entries}
    findings = [
        f"dependabot.yml: {ecosystem} updates are required"
        for ecosystem in sorted(_DEPENDABOT_ECOSYSTEMS - ecosystems)
    ]
    labels = _labels(root) or set()
    used = {str(label) for item in entries for label in _list_child(item, "labels")}
    findings.extend(
        f"dependabot.yml: label {label!r} is not in labels.yml"
        for label in sorted(used - labels)
    )
    return findings


def check(root: Path) -> list[str]:
    """Validate local readiness without claiming hosted controls are configured."""
    findings = [
        f"missing community file: {name}"
        for name in _DOCS
        if not (root / name).is_file()
    ]
    findings.extend(_dependabot(root))
    try:
        config = _maintainers(root)
        findings.extend(_ownership(root, config))
        findings.extend(_intake(root, config.repository))
    except (OSError, ValueError) as error:
        findings.append(str(error))
    workflow_root = root / ".github/workflows"
    actual = (
        {
            path.name
            for path in workflow_root.iterdir()
            if path.suffix in {".yml", ".yaml"}
        }
        if workflow_root.is_dir()
        else set()
    )
    if actual != _WORKFLOWS:
        findings.append(
            "workflow inventory differs from the reviewed verification/release/scanning contract"
        )
    for name in sorted(actual & _WORKFLOWS):
        try:
            findings.extend(_workflow(root, name))
        except (OSError, ValueError, yaml.YAMLError):
            findings.append(f"{name}: invalid workflow or duplicate keys")
    for name in _RULESET_RULES:
        findings.extend(_ruleset(root, name))
    return findings


def main() -> int:
    """Report local failures and explicit publication blockers separately."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", action="store_true")
    args = parser.parse_args()
    findings = check(_ROOT)
    blockers = publication_blockers(_ROOT)
    for finding in findings:
        sys.stderr.write(f"{finding}\n")
    for blocker in blockers:
        sys.stderr.write(f"Publication blocked: {blocker}\n")
    if findings or (args.publication and blockers):
        return 1
    sys.stdout.write(
        "Local governance contracts passed; publication prerequisites remain separate.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
