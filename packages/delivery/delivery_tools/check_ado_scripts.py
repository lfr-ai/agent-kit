"""Shellcheck imported Azure inline scripts; adapted from Delivery Kit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from delivery_tools.catalog import ROOT, nodes
from delivery_tools.documents import read_yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

_SCRIPT_KEYS = frozenset({"bash", "inlineScript"})
_TIMEOUT_SECONDS = 30
_ADO_MACRO = re.compile(r"\$\([A-Za-z_][\w.]*\)")


@dataclass(frozen=True, kw_only=True, slots=True)
class InlineScript:
    """An inline script and the template that owns it."""

    template: Path
    index: int
    body: str


def scripts_in(node: object) -> Iterator[str]:
    """Yield shell-script leaves without interpreting Azure expressions."""
    for item in nodes(node):
        for key in _SCRIPT_KEYS:
            value = item.get(key)
            if isinstance(value, str):
                yield value


def shell_source(script: str) -> str:
    """Neutralize Azure macros, which shellcheck would read as command substitutions."""
    return f"#!/usr/bin/env bash\n{_ADO_MACRO.sub('ado_macro', script)}"


def discover(root: Path) -> list[InlineScript]:
    """Find scripts in stable template order, relative to the package, not the cwd."""
    return [
        InlineScript(template=path, index=index, body=body)
        for path in sorted((root / "azure-devops").rglob("*.yml"))
        for index, body in enumerate(scripts_in(read_yaml(path)))
    ]


def main(*, root: Path = ROOT) -> int:
    """Run local shellcheck; missing tools or scripts fail rather than silently skip."""
    executable = shutil.which("shellcheck")
    scripts = discover(root)
    if not executable or not scripts:
        sys.stderr.write(
            "shellcheck executable and Azure template scripts are required\n"
        )
        return 1
    failures = 0
    with tempfile.TemporaryDirectory() as workspace:
        for script in scripts:
            target = Path(workspace) / f"{script.template.stem}-{script.index}.sh"
            target.write_text(shell_source(script.body), encoding="utf-8", newline="\n")
            result = subprocess.run(  # noqa: S603 - fixed local validator, no shell
                [executable, "--shell=bash", "--severity=warning", str(target)],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
            if result.returncode:
                failures += 1
                sys.stderr.write(
                    f"{script.template.relative_to(root).as_posix()}: "
                    f"{result.stdout}{result.stderr}"
                )
    sys.stdout.write(f"shellcheck: {len(scripts)} scripts, {failures} failing\n")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
