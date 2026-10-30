"""Run repository-owned check commands without changing input files."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

_ROOT = Path(__file__).resolve().parents[1]
_PYTHON = sys.executable
_CHECKS = {
    "lock": ("uv", "lock", "--check"),
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
    "licenses": (
        _PYTHON,
        "packages/shared/.apm/skills/kit-agent-runtime/assets/license_guard.py",
        "--allowlist",
        "license-allowlist.json",
    ),
    "pins": (
        _PYTHON,
        "packages/shared/.apm/skills/kit-verify-change/assets/check_pins.py",
        "--root",
        ".",
    ),
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
# Network gates are selected explicitly so the default gate stays deterministic.
_NETWORK_CHECKS = {
    "dependencies": (_PYTHON, "scripts/audit_dependencies.py"),
}


def main() -> int:
    """Run one named gate or every deterministic gate and surface the first failure."""
    checks = {**_CHECKS, **_NETWORK_CHECKS}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=["all", *checks], nargs="?", default="all")
    args = parser.parse_args()
    names = list(_CHECKS) if args.gate == "all" else [args.gate]
    env = dict(os.environ)
    env["APM_NO_SCRIPTS"] = "1"
    env["APM_NON_INTERACTIVE"] = "1"
    for name in names:
        command = checks[name]
        executable = shutil.which(command[0])
        if executable is None:
            sys.stderr.write(f"{name}: required executable {command[0]} is missing\n")
            return 1
        sys.stdout.write(f"Gate: {name}\n")
        sys.stdout.flush()
        result = subprocess.run(  # noqa: S603 - fixed repository commands, no shell
            [executable, *command[1:]], cwd=_ROOT, check=False, env=env
        )
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
