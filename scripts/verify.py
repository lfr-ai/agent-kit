"""Run repository-owned check commands without changing input files."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PYTHON = sys.executable
_CHECKS = {
    "format": (_PYTHON, "-m", "ruff", "format", "--check"),
    "lint": (_PYTHON, "-m", "ruff", "check"),
    "types": (_PYTHON, "-m", "ty", "check"),
    "architecture": ("lint-imports",),
    "source": ("agent-kit", "check", "--root", "."),
    "native": (_PYTHON, "scripts/check_native.py"),
    "roles": (_PYTHON, "-m", "scripts.render_native"),
    "coverage": (_PYTHON, "-m", "scripts.check_coverage"),
    "conventions": (_PYTHON, "scripts/check_conventions.py"),
    "governance": (_PYTHON, "scripts/check_governance.py"),
    "drift": ("apm", "audit", "--ci", "--policy", "./apm-policy.yml", "--no-fail-fast"),
    "docs": (_PYTHON, "scripts/check_docs.py"),
    "tests": (
        _PYTHON,
        "-m",
        "pytest",
        "--numprocesses=auto",
        "--cov",
        "--cov-report=term-missing:skip-covered",
    ),
}


def main() -> int:
    """Run one named gate or every gate and surface the first failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=["all", *_CHECKS], nargs="?", default="all")
    args = parser.parse_args()
    names = list(_CHECKS) if args.gate == "all" else [args.gate]
    env = dict(os.environ)
    env["APM_NO_SCRIPTS"] = "1"
    env["APM_NON_INTERACTIVE"] = "1"
    for name in names:
        command = _CHECKS[name]
        executable = shutil.which(command[0])
        if executable is None:
            print(
                f"{name}: required executable {command[0]} is missing", file=sys.stderr
            )
            return 1
        print(f"Gate: {name}", flush=True)
        result = subprocess.run(  # noqa: S603 - fixed repository commands, no shell
            [executable, *command[1:]], cwd=_ROOT, check=False, env=env
        )
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
