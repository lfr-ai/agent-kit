"""Invoke the toolkit's canonical gates from an explicit repository target."""

import argparse
from pathlib import Path
import subprocess
import sys


def main() -> int:
    """Run canonical configuration checks without duplicated implementations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    verifier = root / "scripts/verify.py"
    if not verifier.is_file():
        sys.stderr.write(
            "Target must be the toolkit checkout containing scripts/verify.py.\n"
        )
        return 1
    for gate in (
        "source",
        "native",
        "roles",
        "coverage",
        "conventions",
        "governance",
        "docs",
        "drift",
    ):
        result = subprocess.run(  # noqa: S603 - fixed gate commands, explicit target
            [sys.executable, str(verifier), gate], cwd=root, check=False
        )
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
