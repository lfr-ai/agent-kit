"""Negative contracts for account-neutral open-source governance and CI."""

import json
from pathlib import Path

import pytest
from scripts.check_governance import check, publication_blockers
import yaml

_FILES = (
    ".github/CODEOWNERS",
    ".github/maintainers.json",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    ".github/workflows/codeql.yml",
    ".github/workflows/dependency-audit.yml",
    ".github/workflows/dependency-review.yml",
    ".github/workflows/scorecard.yml",
    ".github/rulesets/main.json",
    ".github/rulesets/release-tags.json",
    ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/ISSUE_TEMPLATE/capability-change.yml",
    ".github/ISSUE_TEMPLATE/feature.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/labels.yml",
    ".github/release.yml",
    ".github/dependabot.yml",
    "GOVERNANCE.md",
    "SUPPORT.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
)
_SOURCE = Path(__file__).resolve().parents[3]


@pytest.fixture
def governed_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a synthetic approved ownership configuration without real accounts."""
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    for relative in _FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((_SOURCE / relative).read_bytes())
    (tmp_path / ".github/maintainers.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repository": "example-owner/agent-kit",
                "owners": ["@example-owner"],
                "security_contact": "https://example.org/security-contact",
                "conduct_contact": "https://example.org/conduct-contact",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".github/CODEOWNERS").write_text("* @example-owner\n", encoding="utf-8")
    intake = tmp_path / ".github/ISSUE_TEMPLATE/config.yml"
    intake.write_text(
        intake.read_text().replace("lfr-ai/agent-kit", "example-owner/agent-kit"),
        encoding="utf-8",
    )
    return tmp_path


def test_approved_governance_contract_passes(governed_root: Path) -> None:
    """Known owners and least-privilege workflows satisfy local contracts."""
    assert check(governed_root) == []
    assert publication_blockers(governed_root) == []


def test_unassigned_owner_blocks_publication(governed_root: Path) -> None:
    """An empty CODEOWNERS file cannot be described as a publication-ready setup."""
    (governed_root / ".github/CODEOWNERS").write_text(
        "# Ownership not assigned.\n", encoding="utf-8"
    )

    assert any("CODEOWNERS" in item for item in check(governed_root))
    assert any("CODEOWNERS" in item for item in publication_blockers(governed_root))


def test_local_prepublication_setup_is_explicit_not_a_fake_owner(
    governed_root: Path,
) -> None:
    """No profile is inferred when publication identity is unconfigured."""
    config = governed_root / ".github/maintainers.json"
    value = json.loads(config.read_text())
    value.update(
        repository=None, owners=[], security_contact=None, conduct_contact=None
    )
    config.write_text(json.dumps(value), encoding="utf-8")
    (governed_root / ".github/CODEOWNERS").write_text(
        "# Assign approved owners before publication.\n", encoding="utf-8"
    )

    assert check(governed_root) == []
    assert len(publication_blockers(governed_root)) >= 3


@pytest.mark.parametrize(
    "change",
    [
        "uses: actions/checkout@main",
        "run: echo ${{ github.event.pull_request.title }}",
        "uses: ./.github/actions/unreviewed",
    ],
)
def test_unreviewed_ci_surface_is_rejected(governed_root: Path, change: str) -> None:
    """Mutable action pins and direct expression interpolation cannot silently enter CI."""
    path = governed_root / ".github/workflows/ci.yml"
    text = path.read_text()
    insertion = f"      - {change}\n"
    marker = "      - name: Same check-only gate as task verify"
    assert marker in text
    path.write_text(text.replace(marker, insertion + marker), encoding="utf-8")

    assert check(governed_root)


def test_untrusted_trigger_is_rejected(governed_root: Path) -> None:
    """Privileged PR execution is not an accepted verification trigger."""
    path = governed_root / ".github/workflows/ci.yml"
    path.write_text(
        path.read_text().replace("  pull_request:", "  pull_request_target:"),
        encoding="utf-8",
    )

    assert any("pull_request_target" in item for item in check(governed_root))


def test_release_needs_manual_environment_gate(governed_root: Path) -> None:
    """A tag alone cannot silently become an unprotected release write."""
    path = governed_root / ".github/workflows/release.yml"
    path.write_text(
        path.read_text().replace("    environment: release\n", ""),
        encoding="utf-8",
    )

    assert any("environment" in item for item in check(governed_root))


def test_expanded_release_permission_is_rejected(governed_root: Path) -> None:
    """A publishing job cannot acquire arbitrary additional token permissions."""
    path = governed_root / ".github/workflows/release.yml"
    path.write_text(
        path.read_text().replace(
            "      contents: write", "      issues: write\n      contents: write"
        ),
        encoding="utf-8",
    )

    assert any("permissions" in item for item in check(governed_root))


def test_release_cannot_omit_the_tag_validation(governed_root: Path) -> None:
    """Reusing verification without passing the tag would skip version readiness."""
    path = governed_root / ".github/workflows/release.yml"
    path.write_text(
        path.read_text().replace("      release-tag: ${{ github.ref_name }}\n", ""),
        encoding="utf-8",
    )

    assert any("tag" in item for item in check(governed_root))


def test_release_cannot_automatically_publish_stable_artifacts(
    governed_root: Path,
) -> None:
    """The early-adoption release contract requires an operator-reviewed draft."""
    path = governed_root / ".github/workflows/release.yml"
    path.write_text(
        path.read_text().replace("--draft ", ""),
        encoding="utf-8",
    )

    assert any("draft" in item for item in check(governed_root))


def test_unknown_maintainer_field_is_not_ignored(governed_root: Path) -> None:
    """Misspelled governance fields must fail rather than appear enforced."""
    path = governed_root / ".github/maintainers.json"
    value = json.loads(path.read_text())
    value["maintainer_profile"] = "unapproved"
    path.write_text(json.dumps(value), encoding="utf-8")

    assert any("fields" in item for item in check(governed_root))


def test_duplicate_workflow_keys_fail(governed_root: Path) -> None:
    """A later duplicate cannot override an earlier workflow permission declaration."""
    path = governed_root / ".github/workflows/ci.yml"
    path.write_text(path.read_text() + "\npermissions: write-all\n", encoding="utf-8")

    assert any("duplicate" in item for item in check(governed_root))


def test_release_upload_uses_the_verified_flat_stage(governed_root: Path) -> None:
    """Switching back to multiple source paths would break checksum verification."""
    path = governed_root / ".github/workflows/ci.yml"
    path.write_text(
        path.read_text().replace(
            "path: build/release/*", "path: build/distributions/*"
        ),
        encoding="utf-8",
    )

    assert any("artifact" in item for item in check(governed_root))


@pytest.mark.parametrize(
    ("name", "old", "new"),
    [
        (
            "main.json",
            '"require_code_owner_review": true',
            '"require_code_owner_review": false',
        ),
        ("main.json", '"bypass_mode": "pull_request"', '"bypass_mode": "always"'),
        ("main.json", '"actor_id": 5', '"actor_id": 4'),
        ("main.json", '"actor_type": "RepositoryRole"', '"actor_type": "User"'),
        (
            "release-tags.json",
            '"bypass_actors": []',
            '"bypass_actors": [{"actor_id": 5}]',
        ),
        ("main.json", '"Required toolkit checks"', '"verify"'),
        ("release-tags.json", '{ "type": "update" }', '{ "type": "creation" }'),
    ],
)
def test_weakened_ruleset_is_rejected(
    governed_root: Path, name: str, old: str, new: str
) -> None:
    """Importable repository rules cannot silently drop review or tag protection."""
    path = governed_root / ".github/rulesets" / name
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")

    assert any(name in item for item in check(governed_root))


def test_unreviewed_workflow_file_is_rejected(governed_root: Path) -> None:
    """New workflows need a reviewed policy entry before they can run."""
    (governed_root / ".github/workflows/extra.yml").write_text(
        "name: extra\n", encoding="utf-8"
    )

    assert any("inventory" in item for item in check(governed_root))


def test_scorecard_cannot_gain_write_permissions(governed_root: Path) -> None:
    """The supply-chain posture job keeps only its reviewed token permissions."""
    path = governed_root / ".github/workflows/scorecard.yml"
    text = path.read_text()
    path.write_text(
        text.replace("      actions: read", "      actions: write"), encoding="utf-8"
    )

    assert any("permissions" in item for item in check(governed_root))


def test_dependency_review_runs_only_on_pull_requests(
    governed_root: Path,
) -> None:
    """Dependency Review API checks require PR base/head commits."""
    path = governed_root / ".github/workflows/dependency-review.yml"
    text = path.read_text()
    path.write_text(
        text.replace("  pull_request:\n", "  merge_group:\n  pull_request:\n")
    )

    assert any("dependency review" in item for item in check(governed_root))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("fail-on-severity: low", "fail-on-severity: high"),
        ("license-check: true", "license-check: false"),
        ("vulnerability-check: true", "vulnerability-check: false"),
        (
            "fail-on-scopes: runtime, development, unknown",
            "fail-on-scopes: runtime",
        ),
    ],
)
def test_dependency_review_cannot_be_weakened(
    governed_root: Path, old: str, new: str
) -> None:
    """New PR dependencies are checked for vulnerabilities and licenses in every scope."""
    path = governed_root / ".github/workflows/dependency-review.yml"
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")

    assert any("every dependency scope" in item for item in check(governed_root))


def test_dependency_audit_precedes_installing_the_lock(governed_root: Path) -> None:
    """Swapping the audit after sync would install unaudited packages first."""
    path = governed_root / ".github/workflows/dependency-audit.yml"
    text = path.read_text()
    audit = "uv run --locked --no-sync python scripts/audit_dependencies.py"
    sync = "uv sync --locked\n"
    assert audit in text
    assert sync in text
    swapped = text.replace(audit, "AUDIT").replace(sync, audit + "\n")
    path.write_text(swapped.replace("AUDIT", sync.strip()), encoding="utf-8")

    assert any("audited before" in item for item in check(governed_root))


@pytest.mark.parametrize("job", ["verify", "precommit", "smoke"])
@pytest.mark.parametrize(
    "dependency",
    [
        "",
        "    needs: coverage\n",
        "    needs: audit\n    if: always()\n",
        "    needs: [audit]\n    if: ${{ !cancelled() }}\n",
    ],
)
def test_ci_consumers_require_a_successful_audit(
    governed_root: Path, job: str, dependency: str
) -> None:
    """Every full install must wait for success, not just completion, of the audit."""
    path = governed_root / ".github/workflows/ci.yml"
    text = path.read_text()
    header = f"  {job}:\n"
    text = text.replace(header + "    needs: audit\n", header, 1)
    path.write_text(text.replace(header, header + dependency, 1), encoding="utf-8")

    assert any("audited before" in item for item in check(governed_root))


def test_ci_audit_dependencies_accept_list_syntax(governed_root: Path) -> None:
    """GitHub's string and list forms express the same reviewed dependency."""
    path = governed_root / ".github/workflows/ci.yml"
    path.write_text(
        path.read_text().replace("    needs: audit\n", "    needs: [audit]\n"),
        encoding="utf-8",
    )

    assert check(governed_root) == []


@pytest.mark.parametrize("name", ["main.json", "release-tags.json"])
@pytest.mark.parametrize("exclude", [None, ["~DEFAULT_BRANCH"], ["refs/tags/v*"]])
def test_ruleset_exclusions_require_review(
    governed_root: Path, name: str, exclude: list[str] | None
) -> None:
    """An include pattern is no protection if an exclusion can remove its refs."""
    path = governed_root / ".github/rulesets" / name
    value = json.loads(path.read_text())
    refs = value["conditions"]["ref_name"]
    if exclude is None:
        del refs["exclude"]
    else:
        refs["exclude"] = exclude
    path.write_text(json.dumps(value), encoding="utf-8")

    assert any("scope" in item for item in check(governed_root))


@pytest.mark.parametrize("count", [None, 0, -1, 2, True, "1"])
def test_ruleset_review_count_is_the_reviewed_positive_integer(
    governed_root: Path, count: object
) -> None:
    """Zero, booleans, coercions and unreviewed counts cannot change approval policy."""
    path = governed_root / ".github/rulesets/main.json"
    value = json.loads(path.read_text())
    review = next(rule for rule in value["rules"] if rule["type"] == "pull_request")
    if count is None:
        del review["parameters"]["required_approving_review_count"]
    else:
        review["parameters"]["required_approving_review_count"] = count
    path.write_text(json.dumps(value), encoding="utf-8")

    assert any("review count" in item for item in check(governed_root))


@pytest.mark.parametrize("strict", [None, False, 0, "true"])
def test_ruleset_status_checks_require_strictness(
    governed_root: Path, strict: object
) -> None:
    """The required summary must be checked against the current protected branch."""
    path = governed_root / ".github/rulesets/main.json"
    value = json.loads(path.read_text())
    status = next(
        rule for rule in value["rules"] if rule["type"] == "required_status_checks"
    )
    if strict is None:
        del status["parameters"]["strict_required_status_checks_policy"]
    else:
        status["parameters"]["strict_required_status_checks_policy"] = strict
    path.write_text(json.dumps(value), encoding="utf-8")

    assert any("strict" in item for item in check(governed_root))


@pytest.mark.parametrize("name", ["main.json", "release-tags.json"])
@pytest.mark.parametrize("change", ["duplicate", "unknown", "malformed"])
def test_ruleset_rule_inventory_is_closed_and_unique(
    governed_root: Path, name: str, change: str
) -> None:
    """A dictionary projection must not hide duplicate or unreviewed rule entries."""
    path = governed_root / ".github/rulesets" / name
    value = json.loads(path.read_text())
    added = {
        "duplicate": value["rules"][0],
        "unknown": {"type": "unreviewed"},
        "malformed": {"parameters": {}},
    }
    value["rules"].append(added[change])
    path.write_text(json.dumps(value), encoding="utf-8")

    assert any("rule inventory" in item for item in check(governed_root))


@pytest.mark.parametrize("ecosystem", ["bun", "docker"])
def test_dependabot_covers_every_configured_ecosystem(
    governed_root: Path, ecosystem: str
) -> None:
    """JavaScript tooling and the container image are not optional update surfaces."""
    path = governed_root / ".github/dependabot.yml"
    value = yaml.safe_load(path.read_text())
    value["updates"] = [
        item for item in value["updates"] if item["package-ecosystem"] != ecosystem
    ]
    path.write_text(yaml.safe_dump(value), encoding="utf-8")

    assert any(
        f"{ecosystem} updates are required" in item for item in check(governed_root)
    )


@pytest.mark.parametrize("ecosystem", ["bun", "docker"])
def test_dependabot_surface_labels_are_declared(
    governed_root: Path, ecosystem: str
) -> None:
    """Each newly covered ecosystem uses the same reviewed label inventory."""
    path = governed_root / ".github/dependabot.yml"
    value = yaml.safe_load(path.read_text())
    entry = next(
        item for item in value["updates"] if item["package-ecosystem"] == ecosystem
    )
    entry["labels"] = ["undeclared-surface-label"]
    path.write_text(yaml.safe_dump(value), encoding="utf-8")

    assert any("undeclared-surface-label" in item for item in check(governed_root))


@pytest.mark.parametrize("labels", [None, [], ["undeclared-capability-label"]])
def test_capability_change_form_requires_declared_labels(
    governed_root: Path, labels: list[str] | None
) -> None:
    """The capability intake form cannot escape the other forms' label contract."""
    path = governed_root / ".github/ISSUE_TEMPLATE/capability-change.yml"
    value = yaml.safe_load(path.read_text())
    if labels is None:
        del value["labels"]
    else:
        value["labels"] = labels
    path.write_text(yaml.safe_dump(value), encoding="utf-8")

    assert any("capability-change.yml" in item for item in check(governed_root))


@pytest.mark.parametrize(
    ("relative", "old", "new", "expected"),
    [
        (
            ".github/workflows/ci.yml",
            "uses: $/.github/workflows/dependency-audit.yml",
            "uses: ./.github/workflows/dependency-audit.yml",
            "reusable",
        ),
        (
            ".github/workflows/release.yml",
            "uses: $/.github/workflows/ci.yml",
            "uses: ./.github/workflows/ci.yml",
            "reusable",
        ),
        (
            ".github/workflows/dependency-audit.yml",
            "  workflow_call:\n",
            "",
            "reusable triggers",
        ),
        (
            ".github/dependabot.yml",
            "package-ecosystem: devcontainers",
            "package-ecosystem: docker",
            "devcontainers updates are required",
        ),
    ],
)
def test_dependency_audit_wiring_cannot_drift(
    governed_root: Path, relative: str, old: str, new: str, expected: str
) -> None:
    """Self-repository calls, scheduled audits, and update coverage stay required."""
    path = governed_root / relative
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")

    assert any(expected in item for item in check(governed_root))


@pytest.mark.parametrize(
    ("relative", "old", "new", "expected"),
    [
        (
            ".github/ISSUE_TEMPLATE/config.yml",
            "blank_issues_enabled: false",
            "blank_issues_enabled: true",
            "blank issues",
        ),
        (
            ".github/ISSUE_TEMPLATE/config.yml",
            "/security/advisories/new",
            "/issues/new",
            "private security",
        ),
        (
            ".github/ISSUE_TEMPLATE/bug.yml",
            "labels: [bug]\n",
            "",
            "labels",
        ),
        (
            ".github/ISSUE_TEMPLATE/bug.yml",
            "labels: [bug]",
            "labels: [undefined-label]",
            "undefined-label",
        ),
        (
            ".github/release.yml",
            "labels: [documentation]",
            "labels: [not-in-inventory]",
            "not-in-inventory",
        ),
        (
            ".github/dependabot.yml",
            "labels: [dependencies, ci]",
            "labels: [dependencies, undeclared-bot-label]",
            "undeclared-bot-label",
        ),
        (
            ".github/dependabot.yml",
            "package-ecosystem: pre-commit",
            "package-ecosystem: npm",
            "pre-commit updates are required",
        ),
        (
            ".github/dependabot.yml",
            "version: 2",
            "version: 1",
            "version 2",
        ),
    ],
)
def test_issue_intake_and_release_labels_stay_consistent(
    governed_root: Path, relative: str, old: str, new: str, expected: str
) -> None:
    """Public intake cannot reopen blank issues or reference undefined labels."""
    path = governed_root / relative
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")

    assert any(expected in item for item in check(governed_root))


def test_security_instructions_are_valid_reporting_fallback(
    governed_root: Path,
) -> None:
    """SECURITY.md is a valid fallback while GitHub private reporting is unavailable."""
    path = governed_root / ".github/ISSUE_TEMPLATE/config.yml"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            "/security/advisories/new",
            "/blob/main/SECURITY.md",
        ),
        encoding="utf-8",
    )

    assert check(governed_root) == []


def test_security_contact_link_must_match_the_approved_repository(
    governed_root: Path,
) -> None:
    """The private reporting link cannot point at a different repository."""
    config = governed_root / ".github/maintainers.json"
    value = json.loads(config.read_text())
    value["repository"] = "example-owner/other-repo"
    config.write_text(json.dumps(value), encoding="utf-8")

    assert any("repository" in item for item in check(governed_root))


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("          version: v11.3.1\n", "", "Codecov"),
        (
            "fail_ci_if_error: false",
            "fail_ci_if_error: false\n          skip_validation: true",
            "Codecov",
        ),
        (
            "fail_ci_if_error: false",
            "fail_ci_if_error: false\n          token: ${{ secrets.CODECOV_TOKEN }}",
            "Codecov",
        ),
        (
            "name: coverage-report\n          path: build/coverage/coverage.xml",
            "name: coverage-report\n          path: build/**",
            "artifact upload",
        ),
    ],
)
def test_codecov_upload_stays_pinned_validated_and_tokenless(
    governed_root: Path, old: str, new: str, expected: str
) -> None:
    """The coverage upload cannot download a floating CLI or store a token."""
    path = governed_root / ".github/workflows/ci.yml"
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

    assert any(expected in item for item in check(governed_root))


def test_oidc_permission_is_limited_to_the_upload_job(governed_root: Path) -> None:
    """Project code in the verification matrix never receives an OIDC token."""
    path = governed_root / ".github/workflows/ci.yml"
    text = path.read_text()
    marker = "    runs-on: ${{ matrix.os }}\n    timeout-minutes: 45\n"
    assert marker in text
    path.write_text(
        text.replace(
            marker,
            marker + "    permissions:\n      contents: read\n      id-token: write\n",
            1,
        ),
        encoding="utf-8",
    )

    assert any("unapproved permissions" in item for item in check(governed_root))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "needs: [verify, precommit, smoke, audit, coverage]",
            "needs: [verify, precommit, smoke]",
        ),
        ("needs: [verify, precommit, smoke, audit, coverage]", "needs: verify"),
        ("    if: always()\n    needs:", "    needs:"),
    ],
)
def test_required_summary_must_aggregate_every_ci_job(
    governed_root: Path, old: str, new: str
) -> None:
    """A job left out of the required summary could fail without blocking merges."""
    path = governed_root / ".github/workflows/ci.yml"
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

    assert any("required summary" in item for item in check(governed_root))


def test_every_step_job_declares_a_timeout(governed_root: Path) -> None:
    """A hung job must not consume the six-hour default runner budget."""
    path = governed_root / ".github/workflows/ci.yml"
    text = path.read_text()
    marker = "    timeout-minutes: 30\n"
    assert marker in text
    path.write_text(text.replace(marker, "", 1), encoding="utf-8")

    assert any("explicit timeout" in item for item in check(governed_root))
