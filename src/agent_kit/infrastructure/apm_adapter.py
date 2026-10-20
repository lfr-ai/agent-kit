"""Controlled, non-interactive invocation of the pinned APM CLI."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
from enum import StrEnum, unique
from pathlib import Path


class ApmCliError(RuntimeError):
    """A pinned APM executable or command failed without exposing its output."""


@unique
class ApmAvailabilityIssue(StrEnum):
    """Pinned executable prerequisites that can prevent an APM invocation."""

    MISSING_PACKAGE = "pinned apm-cli==0.33.0 is not installed"
    VERSION_MISMATCH = "installed apm-cli version does not match 0.33.0"
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

    def __init__(self, timeout_seconds: float = 120.0) -> None:
        """Create the process adapter.

        Args:
            timeout_seconds (float): Maximum duration for each APM command in seconds.
        """
        if timeout_seconds <= 0:
            raise InvalidApmTimeoutError
        self._timeout_seconds = timeout_seconds

    def check(self, root: Path) -> None:
        """Run explicit policy status and CI audit commands."""
        try:
            installed_version = importlib.metadata.version("apm-cli")
        except importlib.metadata.PackageNotFoundError as error:
            raise ApmAvailabilityError(ApmAvailabilityIssue.MISSING_PACKAGE) from error
        if installed_version != "0.33.0":
            raise ApmAvailabilityError(ApmAvailabilityIssue.VERSION_MISMATCH)
        executable = shutil.which("apm")
        if executable is None:
            raise ApmAvailabilityError(ApmAvailabilityIssue.MISSING_EXECUTABLE)

        environment = os.environ.copy()
        environment["APM_NO_SCRIPTS"] = "1"
        environment["APM_NON_INTERACTIVE"] = "1"
        commands = (
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
        for label, arguments in commands:
            try:
                result = subprocess.run(  # noqa: S603 -- executable and argv are constrained above
                    arguments,
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise ApmCommandError(
                    command=label, issue=ApmCommandIssue.TIMEOUT
                ) from error
            except OSError as error:
                raise ApmCommandError(
                    command=label, issue=ApmCommandIssue.START
                ) from error
            if result.returncode != 0:
                raise ApmExitError(command=label, returncode=result.returncode)
