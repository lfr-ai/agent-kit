# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Stdlib preflight for an explicitly bounded Activity policy; no SDK simulation."""

import argparse
from dataclasses import dataclass
from datetime import timedelta
import sys

_ZERO = timedelta(0)
_SELF_TEST_STEP = timedelta(seconds=1)
_SELF_TEST_ATTEMPT = timedelta(seconds=10)
_SELF_TEST_BUDGET = timedelta(minutes=1)
_SELF_TEST_ATTEMPTS = 3


class InvalidPolicyError(ValueError):
    """The configured Activity timeouts or retry bounds are incoherent."""


@dataclass(frozen=True, kw_only=True, slots=True)
class ActivityPolicy:
    """Validate durations and attempt count before constructing SDK options.

    Attributes:
        start_to_close (timedelta): Positive duration for one attempt.
        schedule_to_close (timedelta): Overall queue, execution and retry budget.
        heartbeat (timedelta): Positive heartbeat timeout below the attempt timeout.
        retry_initial (timedelta): Positive initial retry delay.
        retry_maximum (timedelta): Maximum retry delay, at least the initial delay.
        maximum_attempts (int): Positive finite total attempts, including the first.

    Raises:
        InvalidPolicyError: A duration or attempt bound is invalid.
    """

    start_to_close: timedelta
    schedule_to_close: timedelta
    heartbeat: timedelta
    retry_initial: timedelta
    retry_maximum: timedelta
    maximum_attempts: int

    def __post_init__(self) -> None:
        """Reject invalid budgets.

        Raises:
            InvalidPolicyError: A duration or retry bound is incoherent.
        """
        durations = (
            self.start_to_close,
            self.schedule_to_close,
            self.heartbeat,
            self.retry_initial,
            self.retry_maximum,
        )
        if min(durations) <= _ZERO or self.maximum_attempts <= 0:
            message = "durations and maximum_attempts must be positive"
            raise InvalidPolicyError(message)
        if not self.heartbeat < self.start_to_close <= self.schedule_to_close:
            message = "require heartbeat < start_to_close <= schedule_to_close"
            raise InvalidPolicyError(message)
        if not self.retry_initial <= self.retry_maximum <= self.schedule_to_close:
            message = "require retry_initial <= retry_maximum <= schedule_to_close"
            raise InvalidPolicyError(message)


def _synthetic_policy(heartbeat: timedelta) -> ActivityPolicy:
    """Build a synthetic policy around ``heartbeat`` with otherwise valid bounds."""
    return ActivityPolicy(
        start_to_close=_SELF_TEST_ATTEMPT,
        schedule_to_close=_SELF_TEST_BUDGET,
        heartbeat=heartbeat,
        retry_initial=_SELF_TEST_STEP,
        retry_maximum=_SELF_TEST_ATTEMPT,
        maximum_attempts=_SELF_TEST_ATTEMPTS,
    )


def self_test() -> None:
    """Accept a bounded synthetic policy and reject a heartbeat beyond the attempt.

    Raises:
        InvalidPolicyError: If the bounded synthetic policy is rejected.
        RuntimeError: If the incoherent synthetic policy is accepted.
    """
    _synthetic_policy(_SELF_TEST_STEP)
    try:
        _synthetic_policy(_SELF_TEST_BUDGET)
    except InvalidPolicyError:
        return
    message = "a heartbeat beyond the attempt timeout must be rejected"
    raise RuntimeError(message)


def main(argv: list[str] | None = None) -> int:
    """Run the synthetic ``--self-test``; import ``ActivityPolicy`` for settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test", action="store_true", help="run synthetic regressions"
    )
    args = parser.parse_args(argv)
    if not args.self_test:
        parser.error("pass --self-test; import ActivityPolicy to check real settings")
    self_test()
    sys.stdout.write("Activity policy self-test passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
