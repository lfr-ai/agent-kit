"""Exercise the shipped opt-in Trivy runner, not a real container scan."""

import ast
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_SKILL = _ROOT / "packages/iac/.apm/skills/kit-containers"
_ASSET = _SKILL / "assets/templates/trivy_image_scan.py.template"
_RUNNER = runpy.run_path(str(_ASSET))
_MAIN = _RUNNER["main"]
_IMAGE = "sha256:" + "a" * 64
_VERSION = "0.69.1"  # Test fixture only, not a scanner adoption recommendation.
_BINARY = b"reviewed scanner fixture: never executed"
_DIGEST = hashlib.sha256(_BINARY).hexdigest()
_DATABASE = {
    "Version": 2,
    "UpdatedAt": "2026-10-24T00:00:00Z",
    "NextUpdate": "2026-10-25T00:00:00Z",
    "DownloadedAt": "2026-10-24T08:00:00Z",
}
_VERSION_JSON = json.dumps({"Version": _VERSION, "VulnerabilityDB": _DATABASE})
_REPORT = json.dumps(
    {"SchemaVersion": 2, "Metadata": {"ImageID": _IMAGE}, "Results": []}
)


@dataclass(kw_only=True, slots=True)
class _Scanner:
    before: str = json.dumps({"Version": _VERSION})
    after: str = _VERSION_JSON
    report: str = _REPORT
    before_exit: int = 0
    scan_exit: int = 0
    after_exit: int = 0
    calls: list[tuple[list[str], dict[str, object]]] = field(default_factory=list)

    def run(
        self, command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        if "image" in command:
            return subprocess.CompletedProcess(
                command, self.scan_exit, self.report, "scan diagnostic"
            )
        is_before = len(self.calls) == 1
        return subprocess.CompletedProcess(
            command,
            self.before_exit if is_before else self.after_exit,
            self.before if is_before else self.after,
            "version diagnostic",
        )


@pytest.fixture
def scanner(monkeypatch: pytest.MonkeyPatch) -> _Scanner:
    fake = _Scanner()
    monkeypatch.setattr(subprocess, "run", fake.run)
    return fake


def _arguments(tmp_path: Path) -> list[str]:
    binary = tmp_path / "reviewed-trivy"
    binary.write_bytes(_BINARY)
    return [
        "--scanner",
        str(binary),
        "--scanner-version",
        _VERSION,
        "--scanner-sha256",
        _DIGEST,
        "--image-id",
        _IMAGE,
        "--evidence",
        str(tmp_path / "evidence"),
    ]


def _replace(arguments: list[str], flag: str, value: str) -> list[str]:
    arguments[arguments.index(flag) + 1] = value
    return arguments


def test_runner_is_linked_and_skill_body_does_not_grow() -> None:
    skill = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "[Trivy runner](assets/templates/trivy_image_scan.py.template)" in skill
    assert len(skill.splitlines()) <= 70
    assert (
        "description: Use when writing or reviewing Dockerfiles, container images, "
        "Compose files, or container runtime settings."
    ) in skill
    reference = (_SKILL / "references/supply-chain.md").read_text(encoding="utf-8")
    assert "../assets/templates/trivy_image_scan.py.template" in reference
    assert "`kit-supply-chain`" in reference
    assert "2026-10-24" in reference
    for document in (skill, reference):
        for target in re.findall(r"\]\(([^)#\s]+)", document):
            if ":" not in target:
                parent = _SKILL if document == skill else _SKILL / "references"
                assert (parent / target).is_file(), target
    ast.parse(_ASSET.read_text(encoding="utf-8"))


def test_terraform_scanner_is_misconfiguration_only() -> None:
    template = (
        _ROOT
        / "packages/terraform/.apm/skills/kit-terraform-validation"
        / "assets/blueprint/trivy.yaml.template"
    )
    configuration = yaml.safe_load(template.read_text(encoding="utf-8"))
    assert configuration["scan"]["scanners"] == ["misconfig"]
    assert configuration["misconfiguration"]["scanners"] == ["terraform"]
    assert configuration["severity"] == ["HIGH", "CRITICAL"]
    assert configuration["exit-code"] == 1


def test_clean_scan_records_actual_identity_scanner_and_database(
    tmp_path: Path, scanner: _Scanner
) -> None:
    assert _MAIN(_arguments(tmp_path)) == 0
    evidence = tmp_path / "evidence"
    identity = json.loads((evidence / "identity.json").read_text(encoding="utf-8"))
    assert identity["image_id"] == _IMAGE
    assert identity["scanner_sha256"] == _DIGEST
    assert identity["scanner_version"] == _VERSION
    assert identity["database_sources"] == [
        "ghcr.io/aquasecurity/trivy-db:2",
        "ghcr.io/aquasecurity/trivy-java-db:1",
    ]
    assert json.loads(
        (evidence / "version-after.json").read_text(encoding="utf-8")
    ) == json.loads(scanner.after)
    assert (evidence / "scan.json").read_text(encoding="utf-8") == scanner.report
    assert (evidence / "scan.stderr.txt").read_text(
        encoding="utf-8"
    ) == "scan diagnostic"
    assert len(scanner.calls) == 3
    work = scanner.calls[0][1]["cwd"]
    assert isinstance(work, Path)
    assert not work.exists()


def test_actual_scan_command_pins_source_and_explicit_failure_policy(
    tmp_path: Path, scanner: _Scanner
) -> None:
    assert _MAIN(_arguments(tmp_path)) == 0
    command = scanner.calls[1][0]
    start = command.index("image")
    assert command[start:] == [
        "image",
        "--image-src=docker",
        "--scanners=vuln",
        "--pkg-types=os,library",
        "--detection-priority=precise",
        "--vuln-severity-source=auto",
        "--severity=HIGH,CRITICAL",
        "--ignore-unfixed",
        "--exit-code=1",
        "--exit-on-eol=2",
        "--format=json",
        "--ignorefile=",
        "--ignore-policy=",
        "--ignore-status=",
        "--vex=",
        "--db-repository=ghcr.io/aquasecurity/trivy-db:2",
        "--java-db-repository=ghcr.io/aquasecurity/trivy-java-db:1",
        "--skip-db-update=false",
        "--skip-java-db-update=false",
        "--offline-scan",
        "--disable-telemetry",
        "--no-progress",
        _IMAGE,
    ]
    assert command[0] == str((tmp_path / "reviewed-trivy").resolve())
    assert "--config" in command
    assert "--cache-dir" in command
    assert not {"push", "login", "deploy", "sbom", "--server"} & set(command)


@pytest.mark.parametrize(
    ("severity", "fixed_version", "expected"),
    [
        ("HIGH", "1.2.3", 1),
        ("CRITICAL", "1.2.3", 1),
        ("HIGH", "", 0),
        ("CRITICAL", "", 0),
        ("MEDIUM", "1.2.3", 0),
        ("LOW", "1.2.3", 0),
        ("UNKNOWN", "1.2.3", 0),
    ],
)
def test_shipped_json_policy_defends_against_false_zero_exit(
    tmp_path: Path,
    scanner: _Scanner,
    severity: str,
    fixed_version: str,
    expected: int,
) -> None:
    report = json.loads(_REPORT)
    report["Results"] = [
        {"Vulnerabilities": [{"Severity": severity, "FixedVersion": fixed_version}]}
    ]
    scanner.report = json.dumps(report)
    assert _MAIN(_arguments(tmp_path)) == expected


def test_configuration_and_suppression_overrides_cannot_leak(
    tmp_path: Path, scanner: _Scanner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRIVY_EXIT_CODE", "0")
    monkeypatch.setenv("TRIVY_SEVERITY", "LOW")
    monkeypatch.setenv("TRIVY_IGNORE_UNFIXED", "false")
    monkeypatch.setenv("TRIVY_CONFIG", "untrusted.yaml")
    monkeypatch.setenv("TRIVY_VEX", "suppress.json")
    monkeypatch.setenv("DOCKER_HOST", "unix:///approved/docker.sock")
    (tmp_path / ".trivyignore").write_text("CVE-EXAMPLE", encoding="utf-8")
    assert _MAIN(_arguments(tmp_path)) == 0
    for command, kwargs in scanner.calls:
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert not any(key.startswith("TRIVY_") for key in env)
        assert env["DOCKER_HOST"] == "unix:///approved/docker.sock"
        work = kwargs["cwd"]
        assert isinstance(work, Path)
        assert str(work) != str(tmp_path)
        assert env["HOME"] == str(work)
        assert env["USERPROFILE"] == str(work)
        assert env["XDG_CONFIG_HOME"] == str(work)
        assert command[command.index("--config") + 1] == str(work / "empty.yaml")
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 600
        assert kwargs.get("shell", False) is False


@pytest.mark.parametrize("code", [1, 2, 7, 42, -9])
def test_findings_eol_and_scanner_database_failures_remain_nonzero(
    tmp_path: Path, scanner: _Scanner, code: int
) -> None:
    scanner.scan_exit = code
    scanner.report = ""  # Error output must not be mistaken for a clean report.
    assert _MAIN(_arguments(tmp_path)) == (2 if code < 0 else code)
    assert len(scanner.calls) == 3  # Still attempt to retain actual DB metadata.
    assert (tmp_path / "evidence/scan.stderr.txt").is_file()
    assert (tmp_path / "evidence/version-after.json").is_file()


@pytest.mark.parametrize("phase", ["before", "after"])
def test_version_command_failure_is_propagated(
    tmp_path: Path, scanner: _Scanner, phase: str
) -> None:
    setattr(scanner, f"{phase}_exit", 23)
    assert _MAIN(_arguments(tmp_path)) == 23
    assert len(scanner.calls) == (1 if phase == "before" else 3)


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--image-id", "example:latest"),
        ("--image-id", "example@sha256:" + "a" * 64),
        ("--image-id", "sha256:" + "A" * 64),
        ("--image-id", "sha256:short"),
        ("--scanner-version", "REVIEWED_EXACT_VERSION"),
        ("--scanner-version", "latest"),
        ("--scanner-sha256", "REVIEWED_BINARY_SHA256"),
        ("--scanner-sha256", "a" * 63),
    ],
)
def test_mutable_or_placeholder_inputs_never_execute_scanner(
    tmp_path: Path, scanner: _Scanner, flag: str, value: str
) -> None:
    with pytest.raises(SystemExit) as error:
        _MAIN(_replace(_arguments(tmp_path), flag, value))
    assert error.value.code == 2
    assert scanner.calls == []


def test_binary_digest_is_checked_before_any_execution(
    tmp_path: Path, scanner: _Scanner
) -> None:
    assert _MAIN(_replace(_arguments(tmp_path), "--scanner-sha256", "0" * 64)) == 2
    assert scanner.calls == []
    assert not (tmp_path / "evidence").exists()


@pytest.mark.parametrize("version", ['{"Version":"0.0.0"}', "{}", "[]", "not JSON"])
def test_actual_version_must_match_reviewed_pin(
    tmp_path: Path, scanner: _Scanner, version: str
) -> None:
    scanner.before = version
    assert _MAIN(_arguments(tmp_path)) == 2
    assert len(scanner.calls) == 1


@pytest.mark.parametrize(
    "version",
    [
        json.dumps({"Version": _VERSION}),
        json.dumps({"Version": _VERSION, "VulnerabilityDB": {}}),
        json.dumps({"Version": _VERSION, "VulnerabilityDB": {"Version": 2}}),
        json.dumps({"Version": "0.0.0", "VulnerabilityDB": _DATABASE}),
        "[]",
        "invalid JSON",
    ],
)
def test_success_requires_actual_database_evidence(
    tmp_path: Path, scanner: _Scanner, version: str
) -> None:
    scanner.after = version
    assert _MAIN(_arguments(tmp_path)) == 2


@pytest.mark.parametrize(
    "report",
    [
        "",
        "[]",
        "{}",
        json.dumps({"SchemaVersion": 2, "Metadata": {"ImageID": "other"}}),
        json.dumps({"SchemaVersion": 1, "Metadata": {"ImageID": _IMAGE}}),
    ],
)
def test_empty_invalid_or_mismatched_success_report_fails_closed(
    tmp_path: Path, scanner: _Scanner, report: str
) -> None:
    scanner.report = report
    assert _MAIN(_arguments(tmp_path)) == 2


@pytest.mark.parametrize(
    "results",
    [
        {},
        [None],
        [{"Vulnerabilities": {}}],
        [{"Vulnerabilities": [None]}],
        [{"Vulnerabilities": [{"Severity": "HIGH", "FixedVersion": 123}]}],
        [{"Vulnerabilities": [{"Severity": "unrecognized"}]}],
    ],
)
def test_malformed_finding_policy_input_is_not_a_clean_scan(
    tmp_path: Path, scanner: _Scanner, results: object
) -> None:
    report = json.loads(_REPORT)
    report["Results"] = results
    scanner.report = json.dumps(report)
    assert _MAIN(_arguments(tmp_path)) == 2


def test_existing_evidence_is_not_overwritten(
    tmp_path: Path, scanner: _Scanner
) -> None:
    arguments = _arguments(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    previous = evidence / "scan.json"
    previous.write_text("prior evidence", encoding="utf-8")
    assert _MAIN(arguments) == 2
    assert previous.read_text(encoding="utf-8") == "prior evidence"
    assert scanner.calls == []


@pytest.mark.parametrize("failure", [OSError("cannot start scanner"), "timeout"])
def test_execution_and_timeout_errors_are_not_clean_scans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: OSError | str
) -> None:
    def fail(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if isinstance(failure, OSError):
            raise failure
        raise subprocess.TimeoutExpired(command, 600)

    monkeypatch.setattr(subprocess, "run", fail)
    assert _MAIN(_arguments(tmp_path)) == 2


def test_unreviewed_extra_scanner_arguments_are_rejected(
    tmp_path: Path, scanner: _Scanner
) -> None:
    with pytest.raises(SystemExit) as error:
        _MAIN([*_arguments(tmp_path), "--ignorefile=exceptions"])
    assert error.value.code == 2
    assert scanner.calls == []
