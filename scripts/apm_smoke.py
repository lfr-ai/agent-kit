"""Exercise Microsoft's pinned APM against composed source-package selections."""

import argparse
from contextlib import suppress
from enum import Enum
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from agent_kit.composition.root import (
    compose_workspace,
    validate_source,
    verify_provenance,
)
from agent_kit.infrastructure import apm_adapter

_ROOT = Path(__file__).resolve().parents[1]
_TIMEOUT_SECONDS = 120
_CLEANUP_TIMEOUT_SECONDS = 30
_RUNTIMES = "copilot,claude"
# Each selection must fit the profile description budget; together they cover
# every portable bundle.
_SMOKE_SELECTIONS = (
    ("fullstack", ()),
    ("ai", ("terraform", "bicep", "remote-access")),
    ("workflows", ()),
    ("backend", ("temporal", "identity")),
)


class _SmokeIssue(Enum):
    """Stable diagnostics for selected-source smoke contracts."""

    UNSELECTED_SESSION_SKILLS = "session source contains unselected skills"
    UNEXPECTED_NATIVE_ROLES = "session source unexpectedly projects native roles"


class _SmokeContractError(ValueError):
    """Report a fixed source-selection contract failure."""

    def __init__(self, issue: _SmokeIssue) -> None:
        """Retain ``issue`` and use its fixed diagnostic as the message."""
        self.issue = issue
        super().__init__(issue.value)


class _SmokeCommandTimeout(SystemExit):
    """Exit with an actionable timeout diagnostic while retaining its cause."""

    def __init__(self, timeout: int, command: list[str]) -> None:
        """Retain ``timeout`` seconds and ``command`` argv for inspection.

        The timeout message displays the command without its launcher.
        """
        self.timeout = timeout
        self.command = tuple(command)
        super().__init__(f"Timed out after {timeout}s: {' '.join(command[1:])}")


def resource_failures(expected: dict[str, bytes], *, destination: Path) -> list[str]:
    """Reject absent, altered or injected resources, not merely skill identities.

    Args:
        expected (dict[str, bytes]): Destination-relative path to expected file bytes.
        destination (Path): Installed skills directory to inspect.

    Returns:
        list[str]: Sorted relative paths that are missing, altered, or unexpected.
    """
    changed = {
        relative
        for relative, content in expected.items()
        if not (destination / relative).is_file()
        or (destination / relative).read_bytes() != content
    }
    actual = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file() and path.name != "SKILL.md"
    }
    return sorted(changed | (actual - set(expected)))


def fixture_environment(parent: dict[str, str], *, home: Path) -> dict[str, str]:
    """Keep APM state and Git discovery inside the synthetic test fixture.

    Args:
        parent (dict[str, str]): Environment to extend.
        home (Path): Fixture directory that replaces the user home.

    Returns:
        dict[str, str]: Isolated home, APM state and Git repository discovery.
    """
    return {
        **{
            key: value
            for key, value in parent.items()
            if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"}
        },
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APM_HOME": str(home / ".apm"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        # A fixture beneath build/ must not discover this checkout's remote and
        # start fetching its organization's policy or probing personal gh auth.
        "GIT_CEILING_DIRECTORIES": str(home.parent),
    }


def delivery_failures(
    package: Path,
    *,
    skills: set[str],
    roles: set[str],
    resources: dict[str, bytes],
) -> list[str]:
    """Compare canonical and installed source/resources plus both native rosters.

    Args:
        package (Path): Composed package directory that APM installed into.
        skills (set[str]): Expected skill names in every skill location.
        roles (set[str]): Expected native role paths relative to ``package``.
        resources (dict[str, bytes]): Skill-relative resource path to expected bytes.

    Returns:
        list[str]: One message per changed roster or altered resource.
    """
    failures: list[str] = []
    for location in (".apm/skills", ".agents/skills", ".claude/skills"):
        actual_skills = {
            path.parent.name for path in (package / location).rglob("SKILL.md")
        }
        if actual_skills != skills:
            failures.append(f"{location}: selected skill roster changed")
        failures.extend(
            f"{location}: missing, altered or injected resource {relative}"
            for relative in resource_failures(resources, destination=package / location)
        )
    actual_roles = {
        path.relative_to(package).as_posix()
        for location in (".github/agents", ".claude/agents")
        for path in (package / location).rglob("*.md")
    }
    if actual_roles != roles:
        failures.append("native role roster changed")
    return failures


def executable_failures(package: Path, *, servers: set[str]) -> list[str]:
    """Check the installed Git-guard hook for both hosts and the declared servers.

    Args:
        package (Path): Composed package directory that APM installed into.
        servers (set[str]): MCP server names declared in the package manifest.

    Returns:
        list[str]: One message per missing hook registration, altered script, or server mismatch.
    """
    source = _ROOT / "packages/shared/.apm/hooks/scripts"
    name = json.loads((package / "apm.yml").read_text(encoding="utf-8"))["name"]
    failures: list[str] = []
    registration = package / f".github/hooks/{name}-git-guard.json"
    if "git_guard.py" not in _read(registration):
        failures.append("Copilot Git-guard hook registration is missing")
    if "git_guard.py" not in _read(package / ".claude/settings.json"):
        failures.append("Claude Git-guard hook registration is missing")
    for root in (
        package / f".github/hooks/scripts/{name}/scripts",
        package / f".claude/hooks/{name}/scripts",
    ):
        failures.extend(
            f"{root.relative_to(package).as_posix()}: {item.name} is missing or altered"
            for item in sorted(source.iterdir())
            if not (root / item.name).is_file()
            or (root / item.name).read_bytes() != item.read_bytes()
        )
    for manifest, key in (
        (".mcp.json", "mcpServers"),
        (".github/mcp.json", "mcpServers"),
    ):
        found = set(json.loads(_read(package / manifest) or "{}").get(key, {}))
        if found != servers:
            failures.append(
                f"{manifest}: delivered MCP servers differ from the manifest"
            )
    return failures


def _read(path: Path) -> str:
    """Return a file's text, or an empty string when it is absent."""
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate this command's descendants before reaping its launcher."""
    if sys.platform == "win32":
        # APM's Windows console launcher spawns Python; killing only the launcher
        # leaves that interpreter running (and holding fixture files open).
        powershell = (
            Path(os.environ["SYSTEMROOT"])
            / "System32/WindowsPowerShell/v1.0/powershell.exe"
        )
        script = (
            "$ErrorActionPreference = 'Stop'; "
            "$all = @(Get-CimInstance Win32_Process); "
            "function Stop-Tree($parentId) { "
            "foreach ($child in $all) { "
            "if ($child.ParentProcessId -eq $parentId) { "
            "Stop-Tree $child.ProcessId } }; "
            "Stop-Process -Id $parentId -Force -ErrorAction SilentlyContinue }; "
            f"Stop-Tree {process.pid}"
        )
        try:
            subprocess.run(  # noqa: S603 - fixed system executable, integer PID only
                [str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
                stdin=subprocess.DEVNULL,
                check=True,
                timeout=_CLEANUP_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as error:
            sys.stderr.write(f"Process-tree cleanup failed: {error}\n")
    else:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    with suppress(ProcessLookupError):
        process.kill()
    process.wait(timeout=_CLEANUP_TIMEOUT_SECONDS)


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int = _TIMEOUT_SECONDS,
) -> None:
    """Run a controlled boundary command and surface its exact failure.

    Args:
        command (list[str]): Executable followed by its arguments.
        cwd (Path): Working directory for the command.
        env (dict[str, str]): Complete environment for the command.
        timeout_seconds (int): Positive per-command execution deadline.

    Raises:
        _SmokeCommandTimeout: The command exceeds the timeout.
        SystemExit: The command exits with a non-zero status.
        apm_adapter.InvalidApmTimeoutError: The deadline is not positive.
        KeyboardInterrupt: Execution is interrupted, after process-tree cleanup.
    """
    if timeout_seconds <= 0:
        raise apm_adapter.InvalidApmTimeoutError
    label = " ".join(command[1:])
    sys.stdout.write(f"Running (limit {timeout_seconds}s): {label}\n")
    sys.stdout.flush()
    started = time.monotonic()
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed executables and validated paths
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            start_new_session=sys.platform != "win32",
        )
    except OSError as error:
        sys.stderr.write(f"Could not start: {label}: {error}\n")
        raise SystemExit(1) from error
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        _stop_process_tree(process)
        raise _SmokeCommandTimeout(timeout_seconds, command) from error
    except KeyboardInterrupt:
        _stop_process_tree(process)
        raise
    elapsed = time.monotonic() - started
    if returncode:
        sys.stderr.write(f"Failed (exit {returncode}): {label}\n")
        raise SystemExit(returncode)
    sys.stdout.write(f"Passed ({elapsed:.1f}s): {label}\n")
    sys.stdout.flush()


def _selected_source(
    package: Path, *, session_skills: tuple[str, ...]
) -> tuple[set[str], set[str], dict[str, bytes]]:
    """Return the composed skill roster, native roles and skill resources.

    Args:
        package (Path): Composed package directory.
        session_skills (tuple[str, ...]): Explicit skill allowlist, or empty for the full profile.

    Returns:
        tuple[set[str], set[str], dict[str, bytes]]: Composed skill names, native role
            paths, and skill-relative resource path mapped to its bytes.

    Raises:
        _SmokeContractError: Skills or native roles differ from the contract.
    """
    expected_skills = {
        path.parent.name for path in (package / ".apm/skills").rglob("SKILL.md")
    }
    if session_skills and expected_skills != set(session_skills):
        raise _SmokeContractError(_SmokeIssue.UNSELECTED_SESSION_SKILLS)
    authored = json.loads((package / "provenance.json").read_text(encoding="utf-8"))[
        "files"
    ]
    resources = {
        name.removeprefix(".apm/skills/"): (package / name).read_bytes()
        for name in authored
        if name.startswith(".apm/skills/") and not name.endswith("/SKILL.md")
    }
    expected_roles = {
        name
        for name in authored
        if name.startswith((".github/agents/", ".claude/agents/"))
    }
    if session_skills and expected_roles:
        raise _SmokeContractError(_SmokeIssue.UNEXPECTED_NATIVE_ROLES)
    return expected_skills, expected_roles, resources


def _delivered(
    package: Path,
    *,
    skills: set[str],
    roles: set[str],
    resources: dict[str, bytes],
) -> bool:
    """Report delivery failures on stderr and return whether delivery held.

    Args:
        package (Path): Composed package directory that APM installed into.
        skills (set[str]): Expected skill names.
        roles (set[str]): Expected native role paths.
        resources (dict[str, bytes]): Skill-relative resource path to expected bytes.

    Returns:
        bool: ``True`` when no delivery failure was found.
    """
    manifest = json.loads((package / "apm.yml").read_text(encoding="utf-8"))
    servers = {entry["name"] for entry in manifest["dependencies"].get("mcp", [])}
    failures = [
        *delivery_failures(package, skills=skills, roles=roles, resources=resources),
        *executable_failures(package, servers=servers),
    ]
    if failures:
        sys.stderr.write(f"{'\n'.join(failures)}\n")
    return not failures


def _report_provenance(package: Path, *, stage: str) -> bool:
    """Report one composed package's provenance result."""
    report = verify_provenance(package)
    if report.valid:
        sys.stdout.write(f"Passed: {stage}\n")
        sys.stdout.flush()
        return True
    for finding in report.findings:
        sys.stderr.write(f"{finding.path}: {finding.message} [{finding.code}]\n")
    return False


def _compose_source(
    package: Path,
    *,
    profile: str,
    features: tuple[str, ...],
    session_skills: tuple[str, ...],
) -> bool:
    """Create and verify the source workspace before invoking APM."""
    sys.stdout.write(f"Composing source selection: {profile}\n")
    sys.stdout.flush()
    try:
        compose_workspace(_ROOT, profile, features, (), package, skills=session_skills)
    except (OSError, ValueError) as error:
        sys.stderr.write(f"Source composition failed: {error}\n")
        return False
    return _report_provenance(package, stage="composition provenance verification")


def _install_and_audit(
    package: Path,
    *,
    apm: str,
    env: dict[str, str],
    expected_skills: set[str],
    expected_roles: set[str],
    resources: dict[str, bytes],
    session_skills: tuple[str, ...],
    timeout_seconds: int,
) -> bool:
    """Install and inspect the initial APM delivery."""
    run(
        [
            apm,
            "policy",
            "status",
            "--policy-source",
            "./apm-policy.yml",
            "--check",
            "--json",
        ],
        cwd=package,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    run(
        [apm, "install", "--target", _RUNTIMES, "--no-trust-bin"],
        cwd=package,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    for runtime in _RUNTIMES.split(","):
        run(
            [apm, "compile", "--target", runtime],
            cwd=package,
            env=env,
            timeout_seconds=timeout_seconds,
        )
    if not _delivered(
        package, skills=expected_skills, roles=expected_roles, resources=resources
    ):
        return False
    for _, command in apm_adapter.check_commands(apm):
        run(
            command,
            cwd=package,
            env=env,
            timeout_seconds=timeout_seconds,
        )
    if not session_skills and not expected_roles:
        sys.stderr.write("Selected project has no native roles.\n")
        return False
    if not (package / "apm.lock.yaml").is_file():
        sys.stderr.write("APM did not create its lockfile.\n")
        return False
    return True


def _frozen_install(
    package: Path,
    *,
    apm: str,
    env: dict[str, str],
    expected_skills: set[str],
    expected_roles: set[str],
    resources: dict[str, bytes],
    timeout_seconds: int,
) -> bool:
    """Replay the APM lock and recheck provenance and installed resources."""
    run(
        [
            apm,
            "install",
            "--frozen",
            "--target",
            _RUNTIMES,
            "--no-trust-bin",
        ],
        cwd=package,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    if not _report_provenance(package, stage="frozen install provenance verification"):
        return False
    return _delivered(
        package, skills=expected_skills, roles=expected_roles, resources=resources
    )


def smoke_profile(
    profile: str,
    features: tuple[str, ...],
    *,
    apm: str,
    env: dict[str, str],
    session_skills: tuple[str, ...],
    timeout_seconds: int = _TIMEOUT_SECONDS,
) -> int:
    """Install, compile, audit and verify one bounded disposable selection.

    Args:
        profile (str): Profile to compose and install.
        features (tuple[str, ...]): Optional features to add to the profile.
        apm (str): Path of the pinned APM launcher.
        env (dict[str, str]): Base environment for every command.
        session_skills (tuple[str, ...]): Explicit skill allowlist, or empty for the full profile.
        timeout_seconds (int): Deadline for every APM command, including audit.

    Returns:
        int: ``0`` when delivery held, otherwise ``1``.
    """
    build = _ROOT / "build"
    build.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="agent-kit-apm-", dir=build) as temporary:
        home = Path(temporary) / "home"
        home.mkdir()
        env = fixture_environment(env, home=home)
        package = Path(temporary) / profile
        if not _compose_source(
            package,
            profile=profile,
            features=features,
            session_skills=session_skills,
        ):
            return 1
        expected_skills, expected_roles, resources = _selected_source(
            package, session_skills=session_skills
        )
        if not _install_and_audit(
            package,
            apm=apm,
            env=env,
            expected_skills=expected_skills,
            expected_roles=expected_roles,
            resources=resources,
            timeout_seconds=timeout_seconds,
            session_skills=session_skills,
        ):
            return 1
        if not _frozen_install(
            package,
            apm=apm,
            env=env,
            expected_skills=expected_skills,
            expected_roles=expected_roles,
            resources=resources,
            timeout_seconds=timeout_seconds,
        ):
            return 1
    return 0


def _smoke_apm_executable() -> str | None:
    """Resolve Microsoft's pinned APM launcher with smoke-runner diagnostics."""
    try:
        return apm_adapter.pinned_apm_executable()
    except apm_adapter.ApmAvailabilityError as error:
        if error.issue is apm_adapter.ApmAvailabilityIssue.MISSING_EXECUTABLE:
            sys.stderr.write("Use the locked APM environment.\n")
        else:
            sys.stderr.write(f"APM {apm_adapter.APM_VERSION} is required.\n")
        return None


def _session_selection(
    arguments: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[str, ...]:
    """Resolve the optional, explicit session skill allowlist."""
    if arguments.session_skill and not arguments.session:
        parser.error("--session-skill requires --session")
    if not arguments.session:
        return ()
    return tuple(arguments.session_skill or ["kit-python-service"])


def _source_is_valid() -> bool:
    """Validate the checkout before any APM install or compile command."""
    sys.stdout.write("Checking source catalog...\n")
    sys.stdout.flush()
    try:
        report = validate_source(_ROOT)
    except (OSError, ValueError) as error:
        sys.stderr.write(f"Source validation failed: {error}\n")
        return False
    if not report.valid:
        for finding in report.findings:
            sys.stderr.write(f"{finding.path}: {finding.message} [{finding.code}]\n")
        return False
    sys.stdout.write("Passed: source catalog validation\n")
    sys.stdout.flush()
    return True


def main() -> int:
    """Verify the portable library in bounded packages, or one narrow session."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=_TIMEOUT_SECONDS,
        help="positive deadline for each APM command (default: %(default)s)",
    )
    parser.add_argument(
        "--session",
        action="store_true",
        help="test an explicit backend skill allowlist without native agents",
    )
    parser.add_argument(
        "--session-skill",
        action="append",
        default=[],
        help="skill allowed in a session package; repeat as needed",
    )
    arguments = parser.parse_args()
    if arguments.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    session_skills = _session_selection(arguments, parser)
    apm = _smoke_apm_executable()
    if apm is None:
        return 1
    if not _source_is_valid():
        return 1
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_CONFIG_")
    }
    env.update(
        {
            "APM_NO_SCRIPTS": "1",
            "APM_NON_INTERACTIVE": "1",
            # Suppress the vendor's update probe, not its audit or trust checks.
            "APM_E2E_TESTS": "1",
        }
    )
    selections = (("backend", ()),) if arguments.session else _SMOKE_SELECTIONS
    for profile, features in selections:
        result = smoke_profile(
            profile,
            features,
            apm=apm,
            env=env,
            session_skills=session_skills,
            timeout_seconds=arguments.timeout_seconds,
        )
        if result:
            return result
    sys.stdout.write("Released APM smoke passed; no live agent session is certified.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
