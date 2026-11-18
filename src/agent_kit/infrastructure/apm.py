"""Maintainer checks using Microsoft's pinned external APM executable.

This adapter invokes APM policy and audit commands; it does not expose an
Agent Kit CLI. Consumer installation is owned by APM, not this Python module.
"""

from __future__ import annotations

from enum import StrEnum, unique
import importlib.metadata
import logging
import math
import os
from pathlib import Path
import subprocess
import sysconfig
import time
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

APM_VERSION: Final[str] = "0.35.0"
APM_ENVIRONMENT_FLAGS: Final[Mapping[str, str]] = MappingProxyType(
    {"APM_NO_SCRIPTS": "1", "APM_NON_INTERACTIVE": "1"}
)
_DEFAULT_TIMEOUT_SECONDS = 900.0
_DISTRIBUTION = "apm-cli"
_LAUNCHER = "apm"  # console-script name, without the platform suffix
_LOGGER = logging.getLogger(__name__)


class APMCLIError(RuntimeError):
    """A pinned APM executable or command failed without exposing its output."""


@unique
class APMAvailabilityIssue(StrEnum):
    """Pinned executable prerequisites that can prevent an APM invocation."""

    MISSING_PACKAGE = f"pinned apm-cli=={APM_VERSION} is not installed"
    VERSION_MISMATCH = f"installed apm-cli version does not match {APM_VERSION}"
    MISSING_EXECUTABLE = "apm executable is unavailable"


class APMAvailabilityError(APMCLIError):
    """The pinned APM toolchain is unavailable."""

    def __init__(self, issue: APMAvailabilityIssue) -> None:
        """Identify the failed toolchain prerequisite.

        Args:
            issue (APMAvailabilityIssue): Missing or incompatible prerequisite.
        """
        self.issue = issue
        super().__init__(issue.value)


@unique
class APMCommandIssue(StrEnum):
    """Process failures reported without exposing vendor subprocess output."""

    TIMEOUT = "timed out"
    START = "could not start"


class APMCommandError(APMCLIError):
    """An APM command could not run to completion."""

    def __init__(self, *, command: str, issue: APMCommandIssue) -> None:
        """Identify the command and its process failure.

        Args:
            command (str): Fixed command label, not subprocess output.
            issue (APMCommandIssue): Process failure category.
        """
        super().__init__(f"apm {command} {issue}")


class APMExitError(APMCLIError):
    """An APM command completed with an unsuccessful status."""

    def __init__(self, *, command: str, returncode: int) -> None:
        """Report only the command and exit status.

        Args:
            command (str): Fixed command label.
            returncode (int): Unsuccessful process exit code.
        """
        super().__init__(f"apm {command} failed with exit code {returncode}")


class InvalidAPMTimeoutError(ValueError):
    """The process timeout would not provide a finite positive execution bound."""

    def __init__(self) -> None:
        """Describe the finite positive-timeout requirement."""
        super().__init__("timeout_seconds must be finite and positive")


class APMCLIAdapter:
    """Invoke Microsoft's APM policy and audit commands for maintainer checks."""

    def __init__(self, timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        """Create the process adapter.

        Args:
            timeout_seconds (float): Maximum duration for each APM command in seconds.

        Raises:
            InvalidAPMTimeoutError: ``timeout_seconds`` is not finite and positive.
        """
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise InvalidAPMTimeoutError
        self._timeout_seconds = timeout_seconds

    def check(
        self, root: Path, *, parent_environment: Mapping[str, str] | None = None
    ) -> None:
        """Run explicit policy status and CI audit commands.

        Failures raise ``APMCLIError`` subclasses: an unavailable pinned APM, a
        command that cannot start or times out, or an unsuccessful exit status.

        Args:
            root (Path): Composed workspace to check.
            parent_environment (Mapping[str, str] | None): Parent process
                environment to copy; defaults to the current process environment.
        """
        executable = pinned_apm_executable()
        environment = dict(
            os.environ if parent_environment is None else parent_environment
        )
        environment.update(APM_ENVIRONMENT_FLAGS)
        for label, arguments in check_commands(executable):
            self._run(label, arguments, root=root, environment=environment)

    def _run(
        self,
        label: str,
        arguments: list[str],
        *,
        root: Path,
        environment: dict[str, str],
    ) -> None:
        """Run one fixed APM command, reporting only its label and status.

        Args:
            label (str): Fixed command label used in diagnostics.
            arguments (list[str]): Full argv, starting with the pinned executable.
            root (Path): Working directory for the process.
            environment (dict[str, str]): Process environment.

        Raises:
            APMCommandError: The command cannot start or times out.
            APMExitError: The command exits with a non-zero status.
        """
        _LOGGER.debug("running apm %s in %s", label, root)
        started = time.perf_counter()
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
            raise APMCommandError(
                command=label, issue=APMCommandIssue.TIMEOUT
            ) from error
        except OSError as error:
            raise APMCommandError(command=label, issue=APMCommandIssue.START) from error
        _LOGGER.debug(
            "apm %s exited %d after %.1fs",
            label,
            result.returncode,
            time.perf_counter() - started,
        )
        if result.returncode != 0:
            raise APMExitError(command=label, returncode=result.returncode)


def pinned_apm_executable() -> str:
    """Return the pinned launcher's absolute path or raise ``APMAvailabilityError``.

    The launcher must be an executable recorded by the installed pinned APM
    distribution in this environment's scripts directory.
    """
    try:
        distribution = importlib.metadata.distribution(_DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError as error:
        raise APMAvailabilityError(APMAvailabilityIssue.MISSING_PACKAGE) from error
    if distribution.version != APM_VERSION:
        raise APMAvailabilityError(APMAvailabilityIssue.VERSION_MISMATCH)
    scripts = Path(sysconfig.get_path("scripts")).resolve()
    # The recorded file name carries the platform suffix, such as .exe on Windows.
    recorded = (
        Path(str(distribution.locate_file(item))).resolve()
        for item in distribution.files or ()
    )
    executable = next(
        (
            path
            for path in recorded
            if path.parent == scripts and path.stem == _LAUNCHER
        ),
        None,
    )
    if executable is None or not (
        executable.is_file() and os.access(executable, os.X_OK)
    ):
        raise APMAvailabilityError(APMAvailabilityIssue.MISSING_EXECUTABLE)
    return str(executable)


def check_commands(executable: str) -> tuple[tuple[str, list[str]], ...]:
    """Return ``(label, argv)`` pairs for the policy status check, then the CI audit."""
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
