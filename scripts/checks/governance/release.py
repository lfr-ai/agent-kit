"""Tag-triggered, verified, and environment-gated release workflow contract."""

import re
from typing import Final

from agent_kit.core.guards import is_json_object
from scripts.checks.governance.ci import CI_WORKFLOW
from scripts.checks.governance.inputs import child_list, child_value, run_commands

RELEASE_WORKFLOW: Final[str] = "toolkit-release.yml"
VERIFY_CALL: Final[str] = f"$/.github/workflows/{CI_WORKFLOW}"
_ATTEST_ACTION = "actions/attest-build-provenance"
_ATTEST_PIN = re.compile(rf"{_ATTEST_ACTION}@[0-9a-f]{{40}}")
_ATTEST_SUBJECTS = frozenset(
    {
        "artifacts/*.whl",
        "artifacts/*.tar.gz",
        "artifacts/*.zip",
        "artifacts/SHA256SUMS",
    }
)


def _release_command_findings(publish: dict[str, object]) -> list[str]:
    """Require one draft prerelease creation that verifies an existing tag."""
    release_commands = [
        command for command in run_commands(publish) if "gh release create " in command
    ]
    if len(release_commands) != 1 or any(
        flag not in release_commands[0].split()
        for flag in ("--draft", "--prerelease", "--verify-tag")
    ):
        return [
            f"{RELEASE_WORKFLOW}: draft prerelease creation must verify an existing tag"
        ]
    return []


def _attestation_findings(publish: dict[str, object]) -> list[str]:
    """Require unconditional, SHA-pinned provenance for every uploaded asset."""
    uploaded = {
        token
        for command in run_commands(publish)
        if "gh release create " in command
        for token in command.split()
        if token.startswith("artifacts/")
    }
    for step in child_list(publish, "steps"):
        uses = child_value(step, "uses")
        if not isinstance(uses, str) or not uses.startswith(_ATTEST_ACTION + "@"):
            continue
        subjects = child_value(child_value(step, "with"), "subject-path")
        covered = (
            {line.strip() for line in subjects.splitlines()}
            if isinstance(subjects, str)
            else set()
        )
        if (
            covered >= _ATTEST_SUBJECTS | uploaded
            and _ATTEST_PIN.fullmatch(uses)
            and child_value(step, "if") in (None, "success()")
            and child_value(step, "continue-on-error") is None
        ):
            return []
    return [
        (
            f"{RELEASE_WORKFLOW}: an unconditional SHA-pinned attest-build-provenance step "
            "must cover every uploaded asset, including SHA256SUMS"
        )
    ]


def release_findings(triggers: dict[str, object], jobs: dict[str, object]) -> list[str]:
    """Require verified, environment-gated publication from a tag push.

    Args:
        triggers (dict[str, object]): Decoded ``on`` mapping of the release workflow.
        jobs (dict[str, object]): Decoded ``jobs`` mapping of the release workflow.

    Returns:
        list[str]: One message per violated release rule; empty when it passes.
    """
    findings: list[str] = []
    publish = jobs.get("publish")
    verify = jobs.get("verify")
    if not is_json_object(verify) or verify.get("uses") != VERIFY_CALL:
        findings.append(
            f"{RELEASE_WORKFLOW}: publication must depend on the shared verification gate"
        )
    if (
        child_value(child_value(verify, "with"), "release-tag")
        != "${{ github.ref_name }}"
    ):
        findings.append(
            f"{RELEASE_WORKFLOW}: verification must validate the actual release tag"
        )
    if (
        not is_json_object(publish)
        or publish.get("needs") != "verify"
        or publish.get("environment") != "release"
        or publish.get("if") != "github.event.repository.visibility == 'public'"
    ):
        findings.append(
            f"{RELEASE_WORKFLOW}: approved release environment and verified public tag are required"
        )
    if "push" not in triggers or len(triggers) != 1:
        findings.append(
            f"{RELEASE_WORKFLOW}: only tag push may start the release workflow"
        )
    if is_json_object(publish):
        findings.extend(_release_command_findings(publish))
        findings.extend(_attestation_findings(publish))
    return findings
