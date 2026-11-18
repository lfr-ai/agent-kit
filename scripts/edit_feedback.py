"""Return lint and convention findings for a Python file an agent just edited."""

import argparse
from enum import StrEnum, auto, unique
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

from scripts.checks.conventions import CHECKER, file_options

_ROOT = Path(__file__).resolve().parents[1]
_MAX_INPUT_CHARS = 1_000_000
# Copilot caps hook context at 10 KB; stay well below so findings are not dropped.
_MAX_FEEDBACK_CHARS = 4_000
# Claude uses ``tool_input.file_path``; Copilot and VS Code tools use these spellings.
_ARGUMENT_FIELDS = ("tool_input", "toolArgs")
_PATH_FIELDS = ("file_path", "filePath", "path")
_PYTHON_SUFFIX = ".py"
_TEMPLATE_SUFFIX = ".py.template"
_TRUNCATED = "\n[findings truncated]"


@unique
class Host(StrEnum):
    """Native hook protocol that receives the feedback."""

    CLAUDE = auto()
    COPILOT = auto()


def edited_file(payload: object) -> Path | None:
    """Return the edited file named by a post-tool hook payload, if it names one."""
    if not isinstance(payload, dict):
        return None
    arguments = next(
        (payload[field] for field in _ARGUMENT_FIELDS if field in payload), None
    )
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return None
    if not isinstance(arguments, dict):
        return None
    value = next((arguments[field] for field in _PATH_FIELDS if field in arguments), "")
    if not isinstance(value, str) or not value:
        return None
    cwd = payload.get("cwd")
    base = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    return base / value


def findings(path: Path, *, root: Path = _ROOT) -> str:
    """Run the fast gates for one file inside ``root`` and return their findings.

    Args:
        path (Path): Edited file; files outside ``root`` or not Python yield nothing.
        root (Path): Repository whose gate scope and tools apply.

    Returns:
        str: Concatenated diagnostics, empty when the file is clean or out of scope.
    """
    root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(root):
        return ""
    python = resolved.suffix == _PYTHON_SUFFIX
    if not python and not resolved.name.endswith(_TEMPLATE_SUFFIX):
        return ""
    relative = PurePosixPath(resolved.relative_to(root).as_posix())
    commands: list[list[str]] = []
    if python:
        ruff = [sys.executable, "-m", "ruff"]
        commands.append([*ruff, "check", "--quiet", "--output-format=concise"])
        commands.append([*ruff, "format", "--check", "--quiet"])
    options = file_options(relative)
    if options is not None:
        commands.append([sys.executable, str(CHECKER), *options])
    reports = [_run([*command, str(resolved)], root=root) for command in commands]
    return "\n".join(report for report in reports if report)


def _run(command: list[str], *, root: Path) -> str:
    """Run one fixed gate command and return its output when it fails."""
    result = subprocess.run(  # noqa: S603 - fixed gate commands, no shell
        command, capture_output=True, check=False, cwd=root, text=True
    )
    return "" if result.returncode == 0 else (result.stdout + result.stderr).strip()


def response(report: str, *, host: Host) -> dict[str, object]:
    """Wrap a findings report in the native post-tool response for ``host``."""
    if len(report) > _MAX_FEEDBACK_CHARS:
        report = report[:_MAX_FEEDBACK_CHARS] + _TRUNCATED
    context = f"Fix these findings in the file you just edited:\n{report}"
    if host is Host.CLAUDE:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": context,
            }
        }
    return {"additionalContext": context}


def main(argv: list[str] | None = None) -> int:
    """Read a post-tool hook payload and print findings; ``1`` on unusable input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", choices=list(Host))
    host = Host(parser.parse_args(argv).host)
    try:
        raw = sys.stdin.read(_MAX_INPUT_CHARS + 1)
        if len(raw) > _MAX_INPUT_CHARS:
            sys.stderr.write("edit feedback input is too large\n")
            return 1
        payload: object = json.loads(raw)
    except (RecursionError, OSError, ValueError) as error:
        sys.stderr.write(f"edit feedback could not read the hook input: {error}\n")
        return 1
    path = edited_file(payload)
    report = findings(path) if path is not None else ""
    if report:
        sys.stdout.write(f"{json.dumps(response(report, host=host))}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
