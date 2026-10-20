"""Check local community and workflow contracts without using a GitHub account."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from enum import Enum
from pathlib import Path
from typing import TypedDict, TypeGuard, override
from urllib.parse import urlsplit

import yaml
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
    "dependency-review.yml",
    "release.yml",
    "scorecard.yml",
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
        required=frozenset({"deletion", "non_fast_forward", "pull_request"}),
    ),
    "release-tags.json": _RulesetContract(
        target="tag",
        include=["refs/tags/v*"],
        required=frozenset({"deletion", "non_fast_forward", "update"}),
    ),
}
_REQUIRED_CHECK = "Required toolkit checks"
_DEPENDABOT_VERSION = 2
_DEPENDABOT_ECOSYSTEMS = frozenset({"uv", "github-actions", "pre-commit"})
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
        """Prevent duplicate keys from overriding earlier permission declarations."""
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise _GovernanceInputError(_GovernanceIssue.DUPLICATE_WORKFLOW_KEY)
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow decoded data without treating arbitrary values as mappings."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate maintainer fields without exposing their contents."""
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _GovernanceInputError(_GovernanceIssue.DUPLICATE_MAINTAINER_FIELD)
        value[key] = item
    return value


def _maintainers(root: Path) -> dict[str, object]:
    """Read the explicit account-neutral ownership source."""
    raw: object = json.loads(
        (root / ".github/maintainers.json").read_text(encoding="utf-8"),
        object_pairs_hook=_unique_pairs,
    )
    if not _mapping(raw) or set(raw) != _FIELDS:
        raise _GovernanceInputError(_GovernanceIssue.INVALID_MAINTAINER_FIELDS)
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise _GovernanceInputError(_GovernanceIssue.INVALID_MAINTAINER_SCHEMA)
    owners = raw["owners"]
    if (
        not isinstance(owners, list)
        or not all(
            isinstance(owner, str) and _OWNER.fullmatch(owner) for owner in owners
        )
        or len(set(owners)) != len(owners)
    ):
        raise _GovernanceInputError(_GovernanceIssue.INVALID_OWNERS)
    repository = raw["repository"]
    if repository is not None and (
        not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository)
    ):
        raise _GovernanceInputError(_GovernanceIssue.INVALID_REPOSITORY)
    for field in ("security_contact", "conduct_contact"):
        contact = raw[field]
        if contact is None:
            continue
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
    return raw


def _ownership(root: Path, config: dict[str, object]) -> list[str]:
    """Keep ownership coverage explicit, including CODEOWNERS itself."""
    rules = [
        line.partition("#")[0].strip()
        for line in (root / ".github/CODEOWNERS")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.partition("#")[0].strip()
    ]
    owners = config["owners"]
    if not isinstance(owners, list):
        return ["CODEOWNERS owner source is invalid"]
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
    if not config["owners"]:
        findings.append("CODEOWNERS has no approved personal account or team")
    for field in ("repository", "security_contact", "conduct_contact"):
        if config[field] is None:
            findings.append(f"publication requires an approved {field}")
    active_repository = os.environ.get("GITHUB_REPOSITORY")
    if active_repository and config["repository"] != active_repository:
        findings.append(
            "approved repository does not match the active release repository"
        )
    return findings


def _workflow(root: Path, name: str) -> list[str]:  # noqa: C901, PLR0912, PLR0915
    """Reject unsafe or unreviewed executable workflow surfaces."""
    path = root / ".github/workflows" / name
    loader = _WorkflowLoader(path.read_text(encoding="utf-8"))
    try:
        raw: object = loader.get_single_data()
    finally:
        loader.dispose()
    if not _mapping(raw):
        return [f"{name}: workflow must be a mapping"]
    findings: list[str] = []
    triggers = raw.get("on")
    if not _mapping(triggers):
        return [f"{name}: explicit trigger mapping is required"]
    if "pull_request_target" in triggers:
        findings.append(f"{name}: pull_request_target is not an approved trigger")
    if raw.get("permissions") != {"contents": "read"}:
        findings.append(f"{name}: root permissions must be contents: read only")
    jobs = raw.get("jobs")
    if not _mapping(jobs):
        return [*findings, f"{name}: jobs must be explicit"]
    for identifier, job in jobs.items():
        if not _mapping(job):
            findings.append(f"{name}: job {identifier} must be a mapping")
            continue
        if "steps" in job and not isinstance(job.get("timeout-minutes"), str):
            findings.append(f"{name}: job {identifier} needs an explicit timeout")
        permissions = job.get("permissions")
        permitted = {"contents": "read"}
        if name == "release.yml" and identifier == "publish":
            permitted = {
                "contents": "write",
                "id-token": "write",
                "attestations": "write",
            }
        elif name == "codeql.yml" and identifier == "analyze":
            permitted = {"contents": "read", "security-events": "write"}
        elif name == "scorecard.yml" and identifier == "analysis":
            permitted = {
                "contents": "read",
                "actions": "read",
                "id-token": "write",
                "security-events": "write",
            }
        if permissions is not None and permissions != permitted:
            findings.append(f"{name}: job {identifier} has unapproved permissions")
        if "secrets" in job:
            findings.append(f"{name}: job secrets must not be inherited or declared")
        reusable = job.get("uses")
        if reusable is not None and reusable != "./.github/workflows/ci.yml":
            findings.append(f"{name}: unapproved reusable workflow")
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            findings.append(f"{name}: steps must be a list")
            continue
        for step in steps:
            if not _mapping(step):
                findings.append(f"{name}: malformed workflow step")
                continue
            action = step.get("uses")
            if action is not None and (
                not isinstance(action, str) or not _ACTION.fullmatch(action)
            ):
                findings.append(
                    f"{name}: actions must use an immutable full commit SHA"
                )
            command = step.get("run")
            if isinstance(command, str) and "${{" in command:
                findings.append(
                    f"{name}: expressions belong in env, not interpolated run scripts"
                )
            if isinstance(action, str) and action.startswith("actions/checkout@"):
                options = step.get("with")
                if (
                    not _mapping(options)
                    or options.get("persist-credentials") != "false"
                ):
                    findings.append(
                        f"{name}: checkout must disable persistent credentials"
                    )
            if isinstance(action, str) and action.startswith(
                "actions/upload-artifact@"
            ):
                options = step.get("with")
                if (
                    not _mapping(options)
                    or options.get("name") != "release-artifacts"
                    or options.get("path") != "build/release/*"
                    or options.get("if-no-files-found") != "error"
                ):
                    findings.append(
                        f"{name}: release artifact upload must use the verified flat stage"
                    )
            if isinstance(action, str) and action.startswith(
                "actions/download-artifact@"
            ):
                options = step.get("with")
                if (
                    not _mapping(options)
                    or options.get("name") != "release-artifacts"
                    or options.get("path") != "artifacts"
                ):
                    findings.append(
                        f"{name}: release artifact download must match its flat upload"
                    )
    if name == "ci.yml":
        if not {"pull_request", "merge_group", "workflow_call"}.issubset(triggers):
            findings.append(
                "ci.yml: PR, merge queue, and reusable verification triggers are required"
            )
        summary = jobs.get("checks")
        needs = summary.get("needs") if _mapping(summary) else None
        needed = [needs] if isinstance(needs, str) else needs
        if (
            not _mapping(summary)
            or not isinstance(needed, list)
            or sorted(str(item) for item in needed) != sorted(set(jobs) - {"checks"})
            or summary.get("if") != "always()"
        ):
            findings.append(
                "ci.yml: the required summary must always run and need every other job"
            )
    if name == "dependency-review.yml" and set(triggers) != {"pull_request"}:
        findings.append(
            "dependency-review.yml: dependency review is supported only for pull_request events"
        )
    if name == "release.yml":
        publish = jobs.get("publish")
        verify = jobs.get("verify")
        if not _mapping(verify) or verify.get("uses") != "./.github/workflows/ci.yml":
            findings.append(
                "release.yml: publication must depend on the shared verification gate"
            )
        arguments = verify.get("with") if _mapping(verify) else None
        if (
            not _mapping(arguments)
            or arguments.get("release-tag") != "${{ github.ref_name }}"
        ):
            findings.append(
                "release.yml: verification must validate the actual release tag"
            )
        if (
            not _mapping(publish)
            or publish.get("needs") != "verify"
            or publish.get("environment") != "release"
            or publish.get("if") != "github.event.repository.visibility == 'public'"
        ):
            findings.append(
                "release.yml: approved release environment and verified public tag are required"
            )
        if "push" not in triggers or len(triggers) != 1:
            findings.append("release.yml: only tag push may start the release workflow")
        if _mapping(publish):
            steps = publish.get("steps")
            commands = (
                [step.get("run") for step in steps if _mapping(step)]
                if isinstance(steps, list)
                else []
            )
            release_commands = [
                command
                for command in commands
                if isinstance(command, str) and "gh release create " in command
            ]
            if len(release_commands) != 1 or any(
                flag not in release_commands[0].split()
                for flag in ("--draft", "--prerelease", "--verify-tag")
            ):
                findings.append(
                    "release.yml: draft prerelease creation must verify an existing tag"
                )
    return findings


def _ruleset(root: Path, name: str) -> list[str]:
    """Validate an importable repository ruleset without claiming it is applied."""
    expected = _RULESET_RULES[name]
    try:
        raw: object = json.loads(
            (root / ".github/rulesets" / name).read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
        )
    except (OSError, ValueError):
        return [f"rulesets/{name}: missing, invalid, or duplicate-key JSON"]
    if not _mapping(raw):
        return [f"rulesets/{name}: ruleset must be a mapping"]
    findings: list[str] = []
    conditions = raw.get("conditions")
    ref_name = conditions.get("ref_name") if _mapping(conditions) else None
    if (
        raw.get("target") != expected["target"]
        or raw.get("enforcement") != "active"
        or not _mapping(ref_name)
        or ref_name.get("include") != expected["include"]
    ):
        findings.append(f"rulesets/{name}: target, scope, and enforcement are fixed")
    if raw.get("bypass_actors") != []:
        findings.append(f"rulesets/{name}: bypass actors require explicit review")
    rules = raw.get("rules")
    typed: dict[str, object] = (
        {
            kind: rule
            for rule in rules
            if _mapping(rule) and isinstance(kind := rule.get("type"), str)
        }
        if isinstance(rules, list)
        else {}
    )
    if not expected["required"].issubset(typed):
        findings.append(f"rulesets/{name}: required protection rules are missing")
    if name == "main.json":
        findings.extend(_main_ruleset_parameters(typed))
    return findings


def _main_ruleset_parameters(rules: dict[str, object]) -> list[str]:
    """Check review and status-check parameters of the default-branch ruleset."""
    findings: list[str] = []
    review = rules.get("pull_request")
    parameters = review.get("parameters") if _mapping(review) else None
    if not _mapping(parameters) or not all(
        parameters.get(guard) is True for guard in _PULL_REQUEST_GUARDS
    ):
        findings.append("rulesets/main.json: review guards must all be enabled")
    status = rules.get("required_status_checks")
    status_parameters = status.get("parameters") if _mapping(status) else None
    checks = (
        status_parameters.get("required_status_checks")
        if _mapping(status_parameters)
        else None
    )
    if checks != [{"context": _REQUIRED_CHECK}]:
        findings.append(
            "rulesets/main.json: the stable required matrix summary is the only check"
        )
    return findings


def _labels(root: Path) -> set[str] | None:
    """Read the declarative label inventory, or None when it is invalid."""
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
            not _mapping(item)
            or set(item) != {"name", "description", "color"}
            or not isinstance(item["name"], str)
            or not isinstance(item["description"], str)
            or not isinstance(item["color"], str)
            or re.fullmatch(r"[0-9a-f]{6}", item["color"]) is None
            or item["name"] in names
        ):
            return None
        names.add(item["name"])
    return names


def _yaml_mapping(path: Path) -> dict[str, object] | None:
    """Load one YAML mapping, tolerating a missing or malformed file."""
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return raw if _mapping(raw) else None


def _intake(root: Path, repository: object) -> list[str]:  # noqa: C901
    """Keep public intake private-first and labels defined, not hosted-verified."""
    labels = _labels(root)
    if labels is None:
        return ["labels.yml: must list unique name, description, and hex color"]
    findings: list[str] = []
    config = _yaml_mapping(root / ".github/ISSUE_TEMPLATE/config.yml")
    if config is None or config.get("blank_issues_enabled") is not False:
        findings.append("issue config: blank issues must be disabled")
    links = config.get("contact_links") if config is not None else None
    urls = (
        [
            url
            for item in links
            if _mapping(item) and isinstance(url := item.get("url"), str)
        ]
        if isinstance(links, list)
        else []
    )
    advisory = [url for url in urls if url.endswith("/security/advisories/new")]
    if not advisory:
        findings.append("issue config: a private security reporting link is required")
    elif isinstance(repository, str) and not all(
        url.startswith(f"https://github.com/{repository}/") for url in urls
    ):
        findings.append("issue config: contact links must use the approved repository")
    for form in ("bug.yml", "feature.yml"):
        data = _yaml_mapping(root / ".github/ISSUE_TEMPLATE" / form)
        form_labels = data.get("labels") if data is not None else None
        if not isinstance(form_labels, list) or not form_labels:
            findings.append(f"{form}: issue form labels are required")
            continue
        findings.extend(
            f"{form}: label {label!r} is not in labels.yml"
            for label in form_labels
            if label not in labels
        )
    release = _yaml_mapping(root / ".github/release.yml")
    changelog = release.get("changelog") if release is not None else None
    categories = changelog.get("categories") if _mapping(changelog) else None
    used: set[str] = set()
    if isinstance(categories, list):
        for category in categories:
            if _mapping(category) and isinstance(
                category_labels := category.get("labels"), list
            ):
                used.update(str(label) for label in category_labels)
    if _mapping(changelog):
        exclude = changelog.get("exclude")
        if _mapping(exclude) and isinstance(
            exclude_labels := exclude.get("labels"), list
        ):
            used.update(str(label) for label in exclude_labels)
    findings.extend(
        f"release.yml: label {label!r} is not in labels.yml"
        for label in sorted(used - {"*"} - labels)
    )
    return findings


def _dependabot(root: Path) -> list[str]:
    """Require Dependabot for every manifest kind, using only declared labels."""
    config = _yaml_mapping(root / ".github/dependabot.yml")
    updates = config.get("updates") if config is not None else None
    if (
        config is None
        or config.get("version") != _DEPENDABOT_VERSION
        or not isinstance(updates, list)
    ):
        return ["dependabot.yml: version 2 with an updates list is required"]
    entries = [item for item in updates if _mapping(item)]
    ecosystems = {item.get("package-ecosystem") for item in entries}
    findings = [
        f"dependabot.yml: {ecosystem} updates are required"
        for ecosystem in sorted(_DEPENDABOT_ECOSYSTEMS - ecosystems)
    ]
    labels = _labels(root) or set()
    used = {
        str(label)
        for item in entries
        if isinstance(item_labels := item.get("labels"), list)
        for label in item_labels
    }
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
        findings.extend(_intake(root, config["repository"]))
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
        print(finding, file=sys.stderr)
    for blocker in blockers:
        print(f"Publication blocked: {blocker}", file=sys.stderr)
    if findings or (args.publication and blockers):
        return 1
    print(
        "Local governance contracts passed; publication prerequisites remain separate."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
