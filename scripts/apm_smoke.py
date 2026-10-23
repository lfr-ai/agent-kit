"""Exercise pinned APM against selected packages in disposable workspaces."""

import argparse
from enum import Enum
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

_ROOT = Path(__file__).resolve().parents[1]
_VERSION = "0.33.0"
_TIMEOUT_SECONDS = 600
_RUNTIMES = "copilot,claude"
_SMOKE_SELECTIONS = (("fullstack", ("iac", "workflows", "ai")),)


class _SmokeIssue(Enum):
    """Stable diagnostics for selected-source smoke contracts."""

    UNSELECTED_SESSION_SKILLS = "session source contains unselected skills"
    UNEXPECTED_NATIVE_ROLES = "session source unexpectedly projects native roles"


class _SmokeContractError(ValueError):
    """Report a fixed source-selection contract failure."""

    def __init__(self, issue: _SmokeIssue) -> None:
        self.issue = issue
        super().__init__(issue.value)


class _SmokeCommandTimeout(SystemExit):
    """Exit with an actionable timeout diagnostic while retaining its cause."""

    def __init__(self, timeout: int, command: list[str]) -> None:
        self.timeout = timeout
        self.command = tuple(command)
        super().__init__(f"Timed out after {timeout}s: {' '.join(command[1:])}")


def resource_failures(expected: dict[str, bytes], *, destination: Path) -> list[str]:
    """Reject absent, altered or injected resources, not merely skill identities."""
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
    """Keep APM's user-wide lock, cache and trust data inside the test fixture."""
    return {
        **parent,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APM_HOME": str(home / ".apm"),
    }


def delivery_failures(
    package: Path,
    *,
    skills: set[str],
    roles: set[str],
    resources: dict[str, bytes],
) -> list[str]:
    """Compare canonical and installed source/resources plus both native rosters."""
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


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    """Run a controlled boundary command and surface its exact failure."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed executables and validated paths
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            check=False,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise _SmokeCommandTimeout(_TIMEOUT_SECONDS, command) from error
    if result.returncode:
        print(result.stdout.decode("utf-8", errors="backslashreplace"), file=sys.stderr)
        print(result.stderr.decode("utf-8", errors="backslashreplace"), file=sys.stderr)
        raise SystemExit(result.returncode)
    print(f"Passed: {' '.join(command[1:])}", flush=True)


def _compose_command(
    toolkit: str,
    profile: str,
    *,
    package: Path,
    features: tuple[str, ...],
    session_skills: tuple[str, ...],
) -> list[str]:
    """Build the bounded ``compose`` command for one disposable selection."""
    return [
        toolkit,
        "compose",
        profile,
        "--root",
        str(_ROOT),
        "--output",
        str(package),
        *[argument for feature in features for argument in ("--feature", feature)],
        *[argument for skill in session_skills for argument in ("--skill", skill)],
    ]


def _selected_source(
    package: Path, *, session_skills: tuple[str, ...]
) -> tuple[set[str], set[str], dict[str, bytes]]:
    """Return the composed skill roster, native roles and skill resources."""
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
    """Report delivery failures on stderr and return whether delivery held."""
    failures = delivery_failures(
        package, skills=skills, roles=roles, resources=resources
    )
    if failures:
        print("\n".join(failures), file=sys.stderr)
    return not failures


def smoke_profile(
    profile: str,
    features: tuple[str, ...],
    *,
    apm: str,
    toolkit: str,
    env: dict[str, str],
    session_skills: tuple[str, ...],
) -> int:
    """Install, compile, audit and verify one bounded disposable selection."""
    with TemporaryDirectory(prefix="agent-kit-apm-") as temporary:
        home = Path(temporary) / "home"
        home.mkdir()
        env = fixture_environment(env, home=home)
        package = Path(temporary) / profile
        run(
            _compose_command(
                toolkit,
                profile,
                package=package,
                features=features,
                session_skills=session_skills,
            ),
            cwd=_ROOT,
            env=env,
        )
        run([toolkit, "provenance", "--root", str(package)], cwd=package, env=env)
        expected_skills, expected_roles, resources = _selected_source(
            package, session_skills=session_skills
        )
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
        )
        run(
            [
                apm,
                "install",
                "--only=apm",
                "--target",
                _RUNTIMES,
                "--no-trust-bin",
            ],
            cwd=package,
            env=env,
        )
        for runtime in _RUNTIMES.split(","):
            run([apm, "compile", "--target", runtime], cwd=package, env=env)
        if not _delivered(
            package, skills=expected_skills, roles=expected_roles, resources=resources
        ):
            return 1
        run([toolkit, "apm-check", "--root", str(package)], cwd=package, env=env)
        if not session_skills and not expected_roles:
            print("Selected project has no native roles.", file=sys.stderr)
            return 1
        if not (package / "apm.lock.yaml").is_file():
            print("APM did not create its lockfile.", file=sys.stderr)
            return 1
        run(
            [
                apm,
                "install",
                "--frozen",
                "--only=apm",
                "--target",
                _RUNTIMES,
                "--no-trust-bin",
            ],
            cwd=package,
            env=env,
        )
        run([toolkit, "provenance", "--root", str(package)], cwd=package, env=env)
        if not _delivered(
            package, skills=expected_skills, roles=expected_roles, resources=resources
        ):
            return 1
    return 0


def main() -> int:
    """Verify the portable library in bounded packages, or one narrow session."""
    parser = argparse.ArgumentParser(description=__doc__)
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
    if arguments.session_skill and not arguments.session:
        parser.error("--session-skill requires --session")
    session_skills = (
        tuple(arguments.session_skill or ["kit-python-service"])
        if arguments.session
        else ()
    )
    if importlib.metadata.version("apm-cli") != _VERSION:
        print(f"APM {_VERSION} is required.", file=sys.stderr)
        return 1
    apm = shutil.which("apm")
    toolkit = shutil.which("agent-kit")
    if apm is None or toolkit is None:
        print("Use the locked toolkit environment.", file=sys.stderr)
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
    run([toolkit, "check", "--root", str(_ROOT)], cwd=_ROOT, env=env)
    selections = (("backend", ()),) if arguments.session else _SMOKE_SELECTIONS
    for profile, features in selections:
        result = smoke_profile(
            profile,
            features,
            apm=apm,
            toolkit=toolkit,
            env=env,
            session_skills=session_skills,
        )
        if result:
            return result
    print("Released APM smoke passed; no live agent session is certified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
