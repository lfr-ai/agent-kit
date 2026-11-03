# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Run the tool guard with the Git policy delivered beside this file.

Hosts start this file as a pre-tool hook. Fixing the policy path here keeps the hook
entry free of arguments that a package installer would have to rewrite.

A missing or unreadable engine exits 2, the status every supported runtime treats as a
block. Any other failing status would let Claude Code carry on, so the launcher never
lets an interpreter traceback (exit 1) stand in for a decision.
"""

from pathlib import Path
import runpy
import sys

_HERE = Path(__file__).resolve().parent
_BLOCK_EXIT = 2


def main() -> int:
    """Evaluate one hook payload from stdin against the delivered Git policy."""
    try:
        engine = runpy.run_path(str(_HERE / "tool_guard.py"))
        status: int = engine["main"](
            ["hook", "--policy", str(_HERE / "git-guard.policy")]
        )
    except (OSError, SyntaxError, KeyError, ValueError) as error:
        sys.stderr.write(
            f"git-guard: blocked because the guard could not run: {error}\n"
        )
        return _BLOCK_EXIT
    return status


if __name__ == "__main__":
    sys.exit(main())
