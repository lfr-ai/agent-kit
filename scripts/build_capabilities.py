"""Build a selected, licensed APM source archive without plugin conversion."""

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory

_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = _ROOT / "build" / "capabilities"


class _ArchiveIssue(Enum):
    """Stable failures for the final licensed-archive contract."""

    MISSING_REQUIRED_ENTRIES = "archive is missing required source entries"
    NO_CAPABILITIES = "archive has no capabilities"


class _ArchiveContractError(ValueError):
    """Report one known source-archive completeness failure."""

    def __init__(self, issue: _ArchiveIssue) -> None:
        self.issue = issue
        super().__init__(issue.value)


def main() -> int:
    """Compose, verify, and archive first-party source with no existing overwrite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="fullstack")
    parser.add_argument("--feature", action="append", default=[])
    args = parser.parse_args()
    executable = shutil.which("agent-kit")
    if executable is None:
        print("Use the locked toolkit environment.", file=sys.stderr)
        return 1
    with TemporaryDirectory(prefix="agent-kit-source-") as temporary:
        package = Path(temporary) / "package"
        command = [
            executable,
            "compose",
            args.profile,
            "--root",
            str(_ROOT),
            "--output",
            str(package),
        ]
        for feature in args.feature:
            command.extend(["--feature", feature])
        result = subprocess.run(command, check=False)  # noqa: S603 - constrained CLI, no shell
        if result.returncode:
            return result.returncode
        result = subprocess.run(  # noqa: S603 - constrained CLI, no shell
            [executable, "provenance", "--root", str(package)], check=False
        )
        if result.returncode:
            return result.returncode
        provenance = json.loads(
            (package / "provenance.json").read_text(encoding="utf-8")
        )
        version = provenance["source"]["catalog_version"]
        suffix = "-".join([args.profile, *sorted(set(args.feature))])
        output = _OUTPUT / f"agent-kit-{suffix}-{version}.zip"
        _OUTPUT.mkdir(parents=True, exist_ok=True)
        created = False
        completed = False
        try:
            with zipfile.ZipFile(
                output, mode="x", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                created = True
                for relative in sorted([*provenance["files"], "provenance.json"]):
                    entry = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                    entry.create_system = 3
                    entry.external_attr = 0o100644 << 16
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, (package / relative).read_bytes())
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                if not {
                    "LICENSE",
                    "apm.yml",
                    "apm-policy.yml",
                    "provenance.json",
                }.issubset(names):
                    raise _ArchiveContractError(_ArchiveIssue.MISSING_REQUIRED_ENTRIES)
                if not any(name.endswith("/SKILL.md") for name in names):
                    raise _ArchiveContractError(_ArchiveIssue.NO_CAPABILITIES)
            completed = True
        finally:
            if created and not completed:
                output.unlink(missing_ok=True)
    print(f"Licensed APM source archive: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
