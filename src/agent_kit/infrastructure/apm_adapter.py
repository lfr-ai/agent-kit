"""Controlled, non-interactive invocation of the pinned APM CLI."""

from __future__ import annotations

from enum import StrEnum, unique
import importlib.metadata
import os
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_APM_VERSION = "0.33.0"
_DEFAULT_TIMEOUT_SECONDS = 300.0


class ApmCliError(RuntimeError):
    """A pinned APM executable or command failed without exposing its output."""


@unique
class ApmAvailabilityIssue(StrEnum):
    """Pinned executable prerequisites that can prevent an APM invocation."""

    MISSING_PACKAGE = f"pinned apm-cli=={_APM_VERSION} is not installed"
    VERSION_MISMATCH = f"installed apm-cli version does not match {_APM_VERSION}"
    MISSING_EXECUTABLE = "apm executable is unavailable"


class ApmAvailabilityError(ApmCliError):
    """The pinned APM toolchain is unavailable."""

    def __init__(self, issue: ApmAvailabilityIssue) -> None:
        """Identify the failed toolchain prerequisite.

        Args:
            issue (ApmAvailabilityIssue): Missing or incompatible prerequisite.
        """
        super().__init__(issue.value)


@unique
class ApmCommandIssue(StrEnum):
    """Process failures that must not expose captured subprocess output."""

    TIMEOUT = "timed out"
    START = "could not start"


class ApmCommandError(ApmCliError):
    """An APM command could not run to completion."""

    def __init__(self, *, command: str, issue: ApmCommandIssue) -> None:
        """Identify the command and its process failure.

        Args:
            command (str): Fixed command label, not subprocess output.
            issue (ApmCommandIssue): Process failure category.
        """
        super().__init__(f"apm {command} {issue}")


class ApmExitError(ApmCliError):
    """An APM command completed with an unsuccessful status."""

    def __init__(self, *, command: str, returncode: int) -> None:
        """Report only the command and exit status.

        Args:
            command (str): Fixed command label.
            returncode (int): Unsuccessful process exit code.
        """
        super().__init__(f"apm {command} failed with exit code {returncode}")


class InvalidApmTimeoutError(ValueError):
    """The process timeout would not provide a positive execution bound."""

    def __init__(self) -> None:
        """Describe the positive-timeout requirement."""
        super().__init__("timeout_seconds must be positive")


class ApmCliAdapter:
    """Run only explicit, read-oriented APM policy and audit commands."""

    def __init__(self, timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        """Create the process adapter.

        Args:
            timeout_seconds (float): Maximum duration for each APM command in seconds.
        """
        if timeout_seconds <= 0:
            raise InvalidApmTimeoutError
        self._timeout_seconds = timeout_seconds

    def check(self, root: Path) -> None:
        """Run explicit policy status and CI audit commands."""
        executable = _pinned_executable()
        environment = os.environ.copy()
        environment["APM_NO_SCRIPTS"] = "1"
        environment["APM_NON_INTERACTIVE"] = "1"
        for label, arguments in _commands(executable):
            self._run(label, arguments, root=root, environment=environment)

    def _run(
        self,
        label: str,
        arguments: list[str],
        *,
        root: Path,
        environment: dict[str, str],
    ) -> None:
        """Run one fixed APM command, reporting only its label and status."""
        try:
            result = subprocess.run(  # noqa: S603 -- executable and argv are constrained above
                arguments,
                cwd=root,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self._timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ApmCommandError(
                command=label, issue=ApmCommandIssue.TIMEOUT
            ) from error
        except OSError as error:
            raise ApmCommandError(command=label, issue=ApmCommandIssue.START) from error
        if result.returncode != 0:
            raise ApmExitError(command=label, returncode=result.returncode)


def _pinned_executable() -> str:
    """Return the ``apm`` executable after verifying the pinned package version."""
    try:
        installed_version = importlib.metadata.version("apm-cli")
    except importlib.metadata.PackageNotFoundError as error:
        raise ApmAvailabilityError(ApmAvailabilityIssue.MISSING_PACKAGE) from error
    if installed_version != _APM_VERSION:
        raise ApmAvailabilityError(ApmAvailabilityIssue.VERSION_MISMATCH)
    executable = shutil.which("apm")
    if executable is None:
        raise ApmAvailabilityError(ApmAvailabilityIssue.MISSING_EXECUTABLE)
    return executable


def _commands(executable: str) -> tuple[tuple[str, list[str]], ...]:
    """Build the fixed policy status and CI audit invocations."""
    return (
        (
            "policy status",
            [
                executable,
                "policy",
                "status",
                "--policy-source",
                "./apm-policy.yml",
                "--check",
                "--json",
            ],
        ),
        (
            "audit",
            [
                executable,
                "audit",
                "--ci",
                "--policy",
                "./apm-policy.yml",
                "--no-fail-fast",
            ],
        ),
    )
