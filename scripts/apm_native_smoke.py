"""Install generated profile dependencies with released APM in relocated consumers."""

import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from typing import Protocol

import yaml

from agent_kit.application.native_delivery import render_native_agents
from agent_kit.core.primitives import JSON_INDENT, NativeRuntime
from scripts.build_profiles import LICENSE, PACKAGE_GIT, PACKAGE_SOURCE, check

_ROLE_COUNT = 18
_TARGET_SELECTIONS = (*((runtime,) for runtime in NativeRuntime), tuple(NativeRuntime))
_PACKAGE_PATHS = (
    "profiles/shared",
    "packages/shared",
    "profiles/native/copilot",
    "profiles/native/claude",
)


class CommandRunner(Protocol):
    """Bounded process port supplied by the existing smoke composition root."""

    def __call__(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> None:
        """Run ``command`` in ``cwd`` with ``env`` and the supplied deadline."""
        ...


class EnvironmentFactory(Protocol):
    """Fixture isolation port shared with the existing source smoke."""

    def __call__(self, parent: dict[str, str], *, home: Path) -> dict[str, str]:
        """Return an environment confined to ``home`` from the parent environment."""
        ...


def native_delivery_failures(
    consumer: Path, *, expected: dict[str, bytes]
) -> list[str]:
    """Return missing, injected or changed native paths, including metadata drift.

    Args:
        consumer (Path): Disposable consumer installed by APM, not a composed root.
        expected (dict[str, bytes]): Canonical target-relative rendered bytes.

    Returns:
        list[str]: Sorted mismatching paths across both runtime discovery roots.
    """
    actual = {
        path.relative_to(consumer).as_posix()
        for runtime in NativeRuntime
        for path in (consumer / runtime.agent_directory).rglob("*.md")
    }
    changed = {
        name
        for name, content in expected.items()
        if not (consumer / name).is_file() or (consumer / name).read_bytes() != content
    }
    return sorted(changed | (actual - expected.keys()))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=JSON_INDENT) + "\n", encoding="utf-8")


def prepare_fixture(root: Path, *, workspace: Path, targets: tuple[str, ...]) -> Path:
    """Copy package sources, not installed consumer files, and return a consumer.

    Args:
        root (Path): Checkout whose generated profiles have passed their audit.
        workspace (Path): Disposable fixture root, relocated before installation.
        targets (tuple[str, ...]): Supported native targets selected for this run.

    Returns:
        Path: Consumer with one pinned profile reference and root-local replacements.
    """
    for relative in _PACKAGE_PATHS:
        shutil.copytree(root / relative, workspace / "catalog" / relative)
    profile = json.loads((root / "profiles/shared/apm.yml").read_text(encoding="utf-8"))
    consumer = workspace / "consumer"
    _write_json(
        consumer / "apm.yml",
        {
            "$schema": (
                "https://microsoft.github.io/apm/specs/schemas/"
                "manifest-source-replacements-v1.schema.json"
            ),
            "name": "native-profile-consumer",
            "version": "0.0.0",
            "license": LICENSE,
            "includes": [],
            "targets": list(targets),
            "dependencies": {
                "apm": [f"{PACKAGE_SOURCE}/profiles/shared#v{profile['version']}"],
                "mcp": profile["dependencies"]["mcp"],
            },
            "replace": [
                {
                    "for": {"git": PACKAGE_GIT, "path": relative},
                    "with": {"path": f"../catalog/{relative}"},
                }
                for relative in _PACKAGE_PATHS
            ],
        },
    )
    # A source-free consumer consents with includes: []; the dedicated explicit
    # includes rule enforces that, not required_fields' nonempty-value check.
    policy = yaml.safe_load((root / "apm-policy.yml").read_text(encoding="utf-8"))
    policy["dependencies"]["allow"] = [
        f"{PACKAGE_SOURCE}/{relative}" for relative in _PACKAGE_PATHS
    ]
    policy["manifest"]["required_fields"] = [
        field for field in policy["manifest"]["required_fields"] if field != "includes"
    ]
    _write_json(consumer / "apm-policy.yml", policy)
    return consumer


def _canonical_roles(root: Path, targets: tuple[str, ...]) -> dict[str, bytes]:
    assets = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.glob("packages/*/.apm/skills/*/assets/agents.json"))
    }
    return render_native_agents(assets, targets)


def _check_delivery(consumer: Path, expected: dict[str, bytes]) -> bool:
    failures = native_delivery_failures(consumer, expected=expected)
    for failure in failures:
        sys.stderr.write(f"Native profile delivery differs: {failure}\n")
    return not failures


def _exercise(
    consumer: Path,
    *,
    apm: str,
    env: dict[str, str],
    targets: tuple[str, ...],
    expected: dict[str, bytes],
    timeout_seconds: int,
    run_command: CommandRunner,
) -> bool:
    def command(*arguments: str) -> None:
        run_command(
            [apm, *arguments], cwd=consumer, env=env, timeout_seconds=timeout_seconds
        )

    command(
        "policy", "status", "--policy-source", "./apm-policy.yml", "--check", "--json"
    )
    selected = ",".join(targets)
    command("install", "--target", selected, "--no-trust-bin")
    for target in targets:
        command("compile", "--target", target)
    if not _check_delivery(consumer, expected):
        return False
    command("audit", "--ci", "--policy", "./apm-policy.yml")
    lock = (consumer / "apm.lock.yaml").read_bytes()
    command("install", "--frozen", "--target", selected, "--no-trust-bin")
    command("audit", "--ci", "--policy", "./apm-policy.yml")
    if (consumer / "apm.lock.yaml").read_bytes() != lock:
        sys.stderr.write("Frozen profile replay changed the APM lock.\n")
        return False
    return _check_delivery(consumer, expected)


def smoke_native_profiles(
    root: Path,
    *,
    apm: str,
    env: dict[str, str],
    timeout_seconds: int,
    run_command: CommandRunner,
    isolate_environment: EnvironmentFactory,
) -> int:
    """Verify recursive native delivery, audit and frozen replay for three selections.

    Args:
        root (Path): Source checkout with current ledger-owned generated packages.
        apm (str): Released, pinned APM executable.
        env (dict[str, str]): Parent environment, isolated separately for each consumer.
        timeout_seconds (int): Positive per-command deadline.
        run_command (CommandRunner): Released-APM process boundary with bounded
            cleanup; its exit on APM failure or deadline overrun propagates.
        isolate_environment (EnvironmentFactory): Home, cache and Git isolation boundary.

    Returns:
        int: Zero for all three passing selections; one for source or delivery drift.
    """
    sys.stdout.write("Checking generated native profile packages...\n")
    sys.stdout.flush()
    failures = check(root)
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        return 1
    for targets in _TARGET_SELECTIONS:
        expected = _canonical_roles(root, targets)
        if len(expected) != _ROLE_COUNT * len(targets):
            sys.stderr.write(
                f"Canonical native roster must contain {_ROLE_COUNT} roles per target.\n"
            )
            return 1
        # APM's replacement staging adds path components. Keep this fixture in
        # system temp, away from a potentially deep checkout (Windows MAX_PATH).
        sys.stdout.write(f"Preparing relocated native consumer: {','.join(targets)}\n")
        sys.stdout.flush()
        with TemporaryDirectory(prefix="akn-") as temporary:
            fixture = Path(temporary)
            prepare_fixture(root, workspace=fixture / "staging", targets=targets)
            relocated = fixture / "relocated"
            (fixture / "staging").rename(relocated)
            home = relocated / "home"
            home.mkdir()
            if not _exercise(
                relocated / "consumer",
                apm=apm,
                env=isolate_environment(env, home=home),
                targets=targets,
                expected=expected,
                timeout_seconds=timeout_seconds,
                run_command=run_command,
            ):
                return 1
        sys.stdout.write(
            f"Native profile passed: {','.join(targets)} ({len(expected)} roles).\n"
        )
    return 0
