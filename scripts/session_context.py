"""Emit bounded, advisory workspace context for native session-start hooks."""

import json
import sys

from agent_kit.core.errors import InputTypeError
from agent_kit.infrastructure.session_context import session_context

_MAX_CONTEXT_CHARS = 1_000_000
_HOOK_EVENT = "SessionStart"


def main() -> int:
    """Read hook JSON and return the native host's context response."""
    try:
        raw = sys.stdin.read(_MAX_CONTEXT_CHARS + 1)
        if len(raw) > _MAX_CONTEXT_CHARS:
            sys.stderr.write("session context input is too large\n")
            return 1
        payload: object = json.loads(raw)
        context = session_context(payload)
    except (RecursionError, OSError, ValueError, InputTypeError) as error:
        sys.stderr.write(f"session context could not be checked: {error}\n")
        return 1
    text = (
        f"Active workspace: {context.workspace}\n"
        "Agent entry points: AGENTS.md, PROJECT.md, llms.txt."
    )
    if context.missing:
        text += f"\nMissing agent context files: {', '.join(context.missing)}."
    response = {
        "hookSpecificOutput": {
            "hookEventName": _HOOK_EVENT,
            "additionalContext": text,
        },
    }
    sys.stdout.write(f"{json.dumps(response, ensure_ascii=True)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
