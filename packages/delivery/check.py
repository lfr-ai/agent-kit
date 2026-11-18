"""Validate the delivery package from any working directory, without installs or network."""

import argparse
from pathlib import Path
import sys

import yaml

from delivery_tools.catalog import ROOT, render
from delivery_tools.validate import validate


def main() -> int:
    """Check source contracts or explicitly regenerate the catalog."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflow-root",
        type=Path,
        required=True,
        help="Directory containing the five canonical delivery-*.yml workflows.",
    )
    parser.add_argument("--write-catalog", action="store_true")
    args = parser.parse_args()
    try:
        if args.write_catalog:
            (ROOT / "catalog.json").write_text(
                render(workflow_root=args.workflow_root),
                encoding="utf-8",
                newline="\n",
            )
        validate(workflow_root=args.workflow_root)
    except KeyError as exc:
        sys.stderr.write(f"delivery: missing required field: {exc.args[0]}\n")
        return 1
    except (OSError, ValueError, yaml.YAMLError) as exc:
        sys.stderr.write(f"delivery: {exc}\n")
        return 1
    sys.stdout.write("delivery: source contracts and catalog passed (offline)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
