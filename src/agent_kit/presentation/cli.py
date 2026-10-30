"""Argparse presentation for the local Agent Kit workflows."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING, TextIO

from agent_kit.core.errors import InputTypeError

if TYPE_CHECKING:
    from collections.abc import Callable

    from agent_kit.core.models import CheckReport, Selection, SessionContext

_MAX_CONTEXT_CHARS = 1_000_000
_JSON_INDENT = 2
_USAGE_ERROR = 2


@dataclass(frozen=True, kw_only=True, slots=True)
class CliActions:
    """Injected command operations owned by the composition root."""

    apm_check: Callable[[Path], CheckReport | None]
    check: Callable[[Path], CheckReport]
    compose: Callable[
        [Path, str, tuple[str, ...], tuple[str, ...], Path, tuple[str, ...]], Path
    ]
    default_root: Callable[[], Path]
    context: Callable[[object], SessionContext]
    load_selection: Callable[[Path], Selection]
    provenance: Callable[[Path], CheckReport]


def _parser() -> argparse.ArgumentParser:
    """Build the public command grammar."""
    parser = argparse.ArgumentParser(
        prog="agent-kit",
        description="Validate and compose first-party Agent Kit capabilities.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="validate all source bundles")
    check.add_argument("--root", type=Path)
    check.add_argument("--json", action="store_true", help="print a structured report")

    compose = commands.add_parser("compose", help="create a new profile workspace")
    compose.add_argument("profile", nargs="?")
    compose.add_argument(
        "--selection",
        type=Path,
        help="JSON selection file with profile, features, runtimes, and skills",
    )
    compose.add_argument("--root", type=Path)
    compose.add_argument("--output", type=Path, required=True)
    compose.add_argument(
        "--runtime",
        choices=("copilot", "claude"),
        action="append",
        dest="runtimes",
    )
    compose.add_argument("--feature", action="append", default=[])
    compose.add_argument(
        "--skill",
        action="append",
        default=[],
        help="explicit session skill allowlist; repeat as needed; omits native roles",
    )

    provenance = commands.add_parser(
        "provenance", help="verify composed output integrity"
    )
    provenance.add_argument("--root", type=Path, required=True)

    apm_check = commands.add_parser(
        "apm-check", help="run explicit pinned APM policy and audit commands"
    )
    apm_check.add_argument("--root", type=Path, required=True)

    commands.add_parser("context", help="report bounded session-entry health as JSON")
    return parser


def _emit_findings(report: CheckReport, stream: TextIO) -> None:
    """Write safe source-relative findings to a text stream."""
    stream.writelines(
        f"{finding.path}: {finding.message} [{finding.code}]\n"
        for finding in report.findings
    )


def _report_dict(report: CheckReport) -> dict[str, object]:
    """Build the stable JSON-facing validation report."""
    return {
        "valid": report.valid,
        "version": report.version,
        "findings": [
            {"code": item.code, "message": item.message, "path": item.path}
            for item in report.findings
        ],
        "profiles": {
            item.profile: {
                "skill_count": item.skill_count,
                "body_lines": item.body_lines,
                "description_chars": item.description_chars,
                "policy_lines": item.policy_lines,
                "limits": dict(item.limits),
            }
            for item in report.profiles
        },
    }


def _context(actions: CliActions) -> int:
    """Emit bounded advisory context without authorizing or denying tool calls."""
    raw = sys.stdin.read(_MAX_CONTEXT_CHARS + 1)
    if len(raw) > _MAX_CONTEXT_CHARS:
        sys.stderr.write("session context input is too large\n")
        return 1
    try:
        payload: object = json.loads(raw)
        context = actions.context(payload)
    except (RecursionError, OSError, ValueError, InputTypeError) as error:
        sys.stderr.write(f"session context could not be checked: {error}\n")
        return 1
    text = f"Active workspace: {context.workspace}\nAgent entry points: AGENTS.md, PROJECT.md, llms.txt."
    if context.missing:
        text += f"\nMissing agent context files: {', '.join(context.missing)}."
    response = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        },
    }
    sys.stdout.write(f"{json.dumps(response, ensure_ascii=True)}\n")
    return 0


def _check(actions: CliActions, arguments: argparse.Namespace) -> int:
    """Validate the source catalog and print a text or JSON report."""
    report = actions.check(arguments.root or actions.default_root())
    if arguments.json:
        rendered = json.dumps(
            _report_dict(report), indent=_JSON_INDENT, ensure_ascii=True
        )
        sys.stdout.write(f"{rendered}\n")
    elif report.valid:
        sys.stdout.write(f"source catalog valid: {report.version}\n")
    else:
        _emit_findings(report, sys.stderr)
    return 0 if report.valid else 1


def _requested_selection(
    actions: CliActions, arguments: argparse.Namespace
) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    """Return profile, features, runtimes, and skills from one input source."""
    flags = (arguments.feature, arguments.runtimes, arguments.skill)
    if arguments.selection is None:
        if arguments.profile is None:
            sys.stderr.write("compose requires a profile or --selection\n")
            return None
        return (
            arguments.profile,
            tuple(arguments.feature),
            tuple(arguments.runtimes or ()),
            tuple(arguments.skill),
        )
    if arguments.profile is not None or any(flags):
        sys.stderr.write(
            "--selection cannot be combined with a profile, --feature, "
            "--runtime, or --skill\n"
        )
        return None
    selection = actions.load_selection(arguments.selection)
    return (
        selection.profile,
        selection.features,
        selection.runtimes,
        selection.skills,
    )


def _compose(actions: CliActions, arguments: argparse.Namespace) -> int:
    """Refuse invalid sources, then write one profile workspace."""
    requested = _requested_selection(actions, arguments)
    if requested is None:
        return _USAGE_ERROR
    profile, features, runtimes, skills = requested
    root = arguments.root or actions.default_root()
    report = actions.check(root)
    if not report.valid:
        _emit_findings(report, sys.stderr)
        return 1
    output = actions.compose(
        root, profile, features, runtimes, arguments.output, skills
    )
    sys.stdout.write(f"composed {profile} profile: {output}\n")
    if skills:
        sys.stdout.write(
            "Session skills only; project instructions retained; native roles omitted.\n"
        )
    sys.stdout.write(
        "Source footprint: .apm/selection.json (characters, not billed tokens).\n"
    )
    return 0


def _provenance(actions: CliActions, arguments: argparse.Namespace) -> int:
    """Verify composed output integrity."""
    report = actions.provenance(arguments.root)
    if not report.valid:
        _emit_findings(report, sys.stderr)
        return 1
    sys.stdout.write("composed output provenance verified\n")
    return 0


def _apm_check(actions: CliActions, arguments: argparse.Namespace) -> int:
    """Run the pinned APM policy and audit commands after provenance passes."""
    report = actions.apm_check(arguments.root)
    if report is not None and not report.valid:
        _emit_findings(report, sys.stderr)
        return 1
    sys.stdout.write("APM policy and audit checks passed\n")
    return 0


_COMMANDS = {
    "check": _check,
    "compose": _compose,
    "provenance": _provenance,
    "apm-check": _apm_check,
}


def main(actions: CliActions, argv: list[str] | None = None) -> int:
    """Parse one command, dispatch its injected operation, and report results."""
    arguments = _parser().parse_args(argv)
    if arguments.command == "context":
        return _context(actions)
    try:
        return _COMMANDS[arguments.command](actions, arguments)
    except (OSError, RuntimeError, ValueError, InputTypeError) as error:
        sys.stderr.write(f"{error}\n")
        return 1
