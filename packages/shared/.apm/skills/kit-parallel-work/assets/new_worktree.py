"""Plan, and optionally create, one Git worktree and branch for a parallel agent.

By default the tool only prints the Git commands it would run, so the plan can
be reviewed or pasted into an approved workflow. Pass ``--execute`` to run them.
Every command is a fixed argument vector run without a shell; branch, base and
path values are validated before any command is built.

Exit status: 0 on success, 1 when validation or a Git command fails, 2 on
usage errors.
"""

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

_FORBIDDEN_REF_CHARS = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]")
_FORBIDDEN_BASE_CHARS = re.compile(r"[\x00-\x20\x7f:?*\[\\]")
_SLUG = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_REF_LENGTH = 200
_C0_CONTROL_END = 0x20  # code points below SPACE are control characters
_GIT_FATAL_EXIT = 128
_SELF_TEST_FAILING_CALL = 2


@dataclass(frozen=True, kw_only=True, slots=True)
class Plan:
    """Validated inputs and the commands that realize them.

    Attributes:
        repository: The existing repository working directory.
        branch: The new branch name.
        base: The commit-ish the branch starts from.
        path: The new worktree directory.
        commands: Argument vectors to run in order.
        cleanup: Argument vectors that remove the worktree and branch later.
    """

    repository: Path
    branch: str
    base: str
    path: Path
    commands: tuple[tuple[str, ...], ...]
    cleanup: tuple[tuple[str, ...], ...]


def ref_problems(name: str, *, label: str, ancestry: bool = False) -> list[str]:
    """Describe why a name is not a safe Git reference name.

    The rules follow ``git check-ref-format`` and additionally reject names that
    start with ``-``, which Git would read as an option.

    Args:
        name: The proposed branch or base reference name.
        label: The argument name used in messages.
        ancestry: Allow ``~`` and ``^`` suffixes such as ``HEAD~2`` in a commit-ish.

    Returns:
        Human-readable problems; empty when the name is acceptable.
    """
    if not name:
        return [f"{label} is empty"]
    forbidden = _FORBIDDEN_BASE_CHARS if ancestry else _FORBIDDEN_REF_CHARS
    checks = (
        (
            len(name) > _MAX_REF_LENGTH,
            f"is longer than {_MAX_REF_LENGTH} characters",
        ),
        (name.startswith("-"), "must not start with '-'"),
        (name == "@", "must not be '@'"),
        (
            forbidden.search(name) is not None,
            "contains a space, control or reserved character",
        ),
        (
            ".." in name or "@{" in name or "//" in name,
            "contains '..', '@{' or '//'",
        ),
        (
            name.startswith("/") or name.endswith(("/", ".", ".lock")),
            "has an invalid start or end",
        ),
        (
            any(part.startswith(".") for part in name.split("/")),
            "has a component starting with '.'",
        ),
    )
    return [f"{label} {message}" for failed, message in checks if failed]


def path_problems(path: Path, *, repository: Path) -> list[str]:
    """Describe why a worktree path cannot be used.

    Args:
        path: The proposed worktree directory.
        repository: The repository working directory.

    Returns:
        Human-readable problems; empty when the path is acceptable.
    """
    problems: list[str] = []
    text = str(path)
    if text.startswith("-"):
        problems.append("path must not start with '-'")
    resolved = path.resolve()
    if resolved == repository.resolve() or resolved.is_relative_to(
        repository.resolve()
    ):
        problems.append("path must be outside the repository working tree")
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        problems.append("path already exists and is not an empty directory")
    if any(ord(char) < _C0_CONTROL_END for char in text):
        problems.append("path contains a control character")
    return problems


def default_path(repository: Path, branch: str) -> Path:
    """Place a worktree beside the repository, named after the branch.

    Args:
        repository: The repository working directory.
        branch: The validated branch name.

    Returns:
        A sibling directory such as ``../project-agent-docs``.
    """
    slug = _SLUG.sub("-", branch.replace("/", "-")).strip("-.") or "worktree"
    resolved = repository.resolve()
    return resolved.parent / f"{resolved.name}-{slug}"


def build_plan(
    *, repository: Path, branch: str, base: str, path: Path | None, git: str = "git"
) -> Plan:
    """Validate inputs and build the command vectors.

    Args:
        repository: The repository working directory.
        branch: The new branch name.
        base: The commit-ish to branch from.
        path: The worktree directory, or None to derive a sibling path.
        git: The Git executable to place in each command.

    Returns:
        The validated plan.

    Raises:
        ValueError: An input is unsafe; the message lists every problem.
    """
    problems = [
        *ref_problems(branch, label="branch"),
        *ref_problems(base, label="base", ancestry=True),
    ]
    target = path if path is not None else default_path(repository, branch)
    problems.extend(path_problems(target, repository=repository))
    if problems:
        raise ValueError("; ".join(problems))
    repo = str(repository)
    where = str(target)
    commands = (
        (git, "-C", repo, "check-ref-format", "--branch", branch),
        (git, "-C", repo, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"),
        (git, "-C", repo, "worktree", "add", "-b", branch, "--", where, base),
    )
    cleanup = (
        (git, "-C", repo, "worktree", "remove", "--", where),
        (git, "-C", repo, "branch", "--delete", branch),
    )
    return Plan(
        repository=repository,
        branch=branch,
        base=base,
        path=target,
        commands=commands,
        cleanup=cleanup,
    )


def render(commands: Sequence[Sequence[str]]) -> list[str]:
    """Render argument vectors as POSIX-quoted lines for review.

    Args:
        commands: The argument vectors.

    Returns:
        One display line per command.
    """
    return [shlex.join(command) for command in commands]


def _run(command: Sequence[str]) -> int:
    """Run one fixed argument vector without a shell."""
    completed = subprocess.run(  # noqa: S603 - validated fixed argument vector
        list(command), check=False
    )
    return completed.returncode


def execute(
    plan: Plan, *, runner: Callable[[Sequence[str]], int] = _run
) -> tuple[int, str | None]:
    """Run the plan's commands in order and stop at the first failure.

    Args:
        plan: The validated plan.
        runner: Runs one argument vector and returns its exit status.

    Returns:
        The failing exit status and its rendered command, or (0, None).
    """
    for command in plan.commands:
        status = runner(command)
        if status != 0:
            return status, shlex.join(command)
    return 0, None


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    VALID_BRANCH_REJECTED = "valid branch rejected: {good}"
    INVALID_BRANCH_ACCEPTED = "invalid branch accepted: {bad}"
    ANCESTRY_BASE_REJECTED = "an ancestry commit-ish must be accepted as a base"
    DEFAULT_PATH = "default path must be a sibling of the repository"
    OPTION_SEPARATOR = "worktree command must separate options from paths"
    INTERNAL_PATH_ACCEPTED = "a path inside the repository must be rejected"
    EXECUTION_CONTINUED = "execution must stop at the first failing command"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self, issue: SelfTestIssue, *, good: str | None = None, bad: str | None = None
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            good: Observed good for the failing case.
            bad: Observed bad for the failing case.
        """
        super().__init__(issue.value.format(good=good, bad=bad))


def self_test() -> None:
    """Exercise validation, planning and execution with in-memory fakes.

    Raises:
        AssertionError: A synthetic case produced an unexpected result.
    """
    _self_test_ref_names()
    plan = _self_test_plan()
    _self_test_execute(plan)


def _self_test_ref_names() -> None:
    """Check accepted and rejected branch and base names."""
    for good in ("agent/docs-update", "feature/orders-42", "fix_invoice.total"):
        if ref_problems(good, label="branch"):
            raise SelfTestError(SelfTestIssue.VALID_BRANCH_REJECTED, good=good)
    for bad in ("-x", "a..b", "a b", "a~1", "x.lock", "a//b", ".hidden", "a/", "@"):
        if not ref_problems(bad, label="branch"):
            raise SelfTestError(SelfTestIssue.INVALID_BRANCH_ACCEPTED, bad=bad)
    if ref_problems("HEAD~2", label="base", ancestry=True):
        raise SelfTestError(SelfTestIssue.ANCESTRY_BASE_REJECTED)


def _self_test_plan() -> Plan:
    """Check default paths, option separation and in-repository rejection."""
    repository = Path.cwd()
    plan = build_plan(
        repository=repository, branch="agent/docs", base="HEAD", path=None
    )
    if plan.path.parent != repository.resolve().parent:
        raise SelfTestError(SelfTestIssue.DEFAULT_PATH)
    expected_tail = ("--", str(plan.path), "HEAD")
    if plan.commands[-1][-len(expected_tail) :] != expected_tail:
        raise SelfTestError(SelfTestIssue.OPTION_SEPARATOR)
    try:
        build_plan(repository=repository, branch="ok", base="HEAD", path=repository)
    except ValueError:
        return plan
    raise SelfTestError(SelfTestIssue.INTERNAL_PATH_ACCEPTED)


def _self_test_execute(plan: Plan) -> None:
    """Check that execution stops at the first failing command."""
    calls: list[Sequence[str]] = []

    def failing(command: Sequence[str]) -> int:
        calls.append(command)
        return 0 if len(calls) == 1 else _GIT_FATAL_EXIT

    status, failed = execute(plan, runner=failing)
    if (
        status != _GIT_FATAL_EXIT
        or len(calls) != _SELF_TEST_FAILING_CALL
        or failed is None
    ):
        raise SelfTestError(SelfTestIssue.EXECUTION_CONTINUED)


def main(argv: list[str] | None = None) -> int:
    """Print or run the worktree plan.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 on success, 1 on validation or Git failure, 2 on usage errors.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--branch", help="new branch, for example 'agent/docs'")
    parser.add_argument("--base", default="HEAD", help="commit-ish to branch from")
    parser.add_argument(
        "--path", type=Path, help="worktree directory (default: sibling)"
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--execute", action="store_true", help="run the commands instead of printing"
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Worktree planner self-test passed.")
        return 0
    if not args.branch:
        parser.error("--branch is required")
    plan = _plan_or_report(args)
    if plan is None:
        return 1
    if not args.execute:
        _print_dry_run(plan)
        return 0
    status, failed = execute(plan)
    if status != 0:
        print(f"Command failed with exit status {status}: {failed}", file=sys.stderr)
        return 1
    print(f"Created worktree {plan.path} on branch {plan.branch} from {plan.base}.")
    return 0


def _plan_or_report(args: argparse.Namespace) -> Plan | None:
    """Build the plan from parsed arguments, printing why it cannot be built."""
    git = shutil.which("git") if args.execute else "git"
    if git is None:
        print("git executable not found on PATH", file=sys.stderr)
        return None
    try:
        return build_plan(
            repository=args.repo,
            branch=args.branch,
            base=args.base,
            path=args.path,
            git=git,
        )
    except ValueError as error:
        print(f"Refusing to plan worktree: {error}", file=sys.stderr)
        return None


def _print_dry_run(plan: Plan) -> None:
    """Print the commands to review and the commented cleanup commands."""
    print("# Dry run. Review, then re-run with --execute to apply:")
    for line in render(plan.commands):
        print(line)
    print("# Cleanup after the branch is merged or abandoned:")
    for line in render(plan.cleanup):
        print(f"# {line}")


if __name__ == "__main__":
    raise SystemExit(main())
