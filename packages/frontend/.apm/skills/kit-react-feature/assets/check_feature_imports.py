"""Report imports that bypass a feature's public entry or invert shared layering.

The checker reads TypeScript and JavaScript sources as text; it never runs a
compiler, bundler, or package manager. It reports two rule violations:

1. A file in feature ``a`` imports a non-entry module of feature ``b``.
2. A file in a shared directory imports any feature module.
"""

import argparse
from collections.abc import Sequence
from enum import StrEnum
import os
from pathlib import Path, PurePosixPath
import re
import sys
from tempfile import TemporaryDirectory

_SPECIFIER = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s+|\brequire\s*\(\s*)(['"])([^'"\n]+)\1"""
)
_DEFAULT_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs")
_SKIPPED_DIRECTORIES = frozenset({"node_modules", "dist", "build", "coverage", ".git"})
_SELF_TEST_EXPECTED_FINDINGS = 3


class FeatureAliasError(ValueError):
    """An input violates the feature alias contract."""

    def __init__(self, *, value: str) -> None:
        """Describe the violated invariant.

        Args:
            value: Diagnostic value for the failing input.
        """
        super().__init__(f"alias must look like PREFIX=DIRECTORY: {value}")


def _parse_aliases(values: Sequence[str]) -> list[tuple[str, PurePosixPath]]:
    """Parse ``PREFIX=DIRECTORY`` alias declarations into ordered pairs.

    Args:
        values: Alias declarations such as ``@/=src/``.

    Returns:
        Pairs of import prefix and root-relative directory, longest prefix first.

    Raises:
        ValueError: If a declaration has no ``=`` or an empty prefix.
    """
    aliases: list[tuple[str, PurePosixPath]] = []
    for value in values:
        prefix, separator, directory = value.partition("=")
        if not separator or not prefix:
            raise FeatureAliasError(value=value)
        aliases.append((prefix, PurePosixPath(directory or ".")))
    return sorted(aliases, key=lambda pair: len(pair[0]), reverse=True)


def _resolve(
    specifier: str,
    source: PurePosixPath,
    aliases: Sequence[tuple[str, PurePosixPath]],
) -> PurePosixPath | None:
    """Resolve a relative or aliased specifier to a root-relative path.

    Args:
        specifier: The import string from source text.
        source: Root-relative path of the importing file.
        aliases: Parsed alias pairs.

    Returns:
        A normalized root-relative path, or None for package imports.
    """
    if specifier.startswith("."):
        joined = os.path.normpath(str(source.parent / specifier)).replace("\\", "/")
        return PurePosixPath(joined)
    for prefix, directory in aliases:
        if specifier.startswith(prefix):
            remainder = specifier.removeprefix(prefix)
            joined = os.path.normpath(str(directory / remainder)).replace("\\", "/")
            return PurePosixPath(joined)
    return None


def _feature_of(
    path: PurePosixPath, features: PurePosixPath
) -> tuple[str, tuple[str, ...]] | None:
    """Split a path below the features directory into feature name and remainder.

    Args:
        path: Root-relative path to classify.
        features: Root-relative features directory.

    Returns:
        The feature name and the parts below it, or None outside features.
    """
    if not path.is_relative_to(features) or path == features:
        return None
    parts = path.relative_to(features).parts
    return parts[0], tuple(parts[1:])


def _is_entry(remainder: tuple[str, ...]) -> bool:
    """Return whether the remainder addresses a feature's public index."""
    return not remainder or (
        len(remainder) == 1 and remainder[0].split(".", 1)[0] == "index"
    )


def _source_files(root: Path, extensions: tuple[str, ...]) -> list[Path]:
    """List candidate source files below root, skipping generated directories."""
    found: list[Path] = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = sorted(
            name for name in subdirectories if name not in _SKIPPED_DIRECTORIES
        )
        found.extend(
            Path(directory) / name
            for name in sorted(files)
            if name.endswith(extensions) and not name.endswith(".d.ts")
        )
    return found


def check(
    root: Path,
    *,
    features_dir: str = "src/features",
    shared_dirs: Sequence[str] = ("src/shared",),
    aliases: Sequence[str] = (),
    extensions: tuple[str, ...] = _DEFAULT_EXTENSIONS,
) -> list[str]:
    """Collect boundary findings as sorted ``path:line: message`` strings.

    Args:
        root: Project directory that contains the source tree.
        features_dir: Root-relative directory holding one folder per feature.
        shared_dirs: Root-relative directories that must not import features.
        aliases: Import alias declarations such as ``@/=src/``.
        extensions: Source file suffixes to scan.

    Returns:
        Deterministically ordered findings; empty when boundaries hold.
    """
    features = PurePosixPath(features_dir)
    shared = [PurePosixPath(item) for item in shared_dirs]
    parsed_aliases = _parse_aliases(aliases)
    findings: list[str] = []
    for file in _source_files(root, extensions):
        relative = PurePosixPath(file.relative_to(root).as_posix())
        owner = _feature_of(relative, features)
        in_shared = any(relative.is_relative_to(item) for item in shared)
        if owner is None and not in_shared:
            continue
        text = file.read_text(encoding="utf-8")
        findings.extend(
            _file_findings(
                relative,
                text,
                owner=owner,
                in_shared=in_shared,
                features=features,
                aliases=parsed_aliases,
            )
        )
    return sorted(findings)


def _file_findings(
    relative: PurePosixPath,
    text: str,
    *,
    owner: tuple[str, tuple[str, ...]] | None,
    in_shared: bool,
    features: PurePosixPath,
    aliases: Sequence[tuple[str, PurePosixPath]],
) -> list[str]:
    """Return boundary findings for every import specifier in one file."""
    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for _, specifier in _SPECIFIER.findall(line):
            message = _boundary_violation(
                specifier,
                relative,
                owner=owner,
                in_shared=in_shared,
                features=features,
                aliases=aliases,
            )
            if message is not None:
                findings.append(f"{relative}:{number}: {message}")
    return findings


def _boundary_violation(
    specifier: str,
    relative: PurePosixPath,
    *,
    owner: tuple[str, tuple[str, ...]] | None,
    in_shared: bool,
    features: PurePosixPath,
    aliases: Sequence[tuple[str, PurePosixPath]],
) -> str | None:
    """Describe how one import crosses a feature boundary, if it does."""
    target = _resolve(specifier, relative, aliases)
    imported = None if target is None else _feature_of(target, features)
    if imported is None:
        return None
    name, remainder = imported
    if in_shared:
        return f"shared code imports feature '{name}' ({specifier})"
    if owner is not None and owner[0] != name and not _is_entry(remainder):
        return (
            f"deep import into feature '{name}'"
            f" ({specifier}); import its public index instead"
        )
    return None


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    PUBLIC_IMPORT_REJECTED = "public entry imports must pass"
    FINDING_COUNT = "expected {expected} findings, got {findings}"
    FINDING_LOCATION = "unexpected order or location: {findings}"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self,
        issue: SelfTestIssue,
        *,
        expected: int | None = None,
        findings: list[str] | None = None,
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            expected: Observed expected for the failing case.
            findings: Observed findings for the failing case.
        """
        super().__init__(issue.value.format(expected=expected, findings=findings))


def self_test() -> None:
    """Exercise passing, deep, aliased and shared-inversion imports in a temp tree.

    Raises:
        AssertionError: If any synthetic expectation does not hold.
    """
    with TemporaryDirectory(prefix="agent-kit-feature-imports-") as directory:
        root = Path(directory)
        orders = root / "src/features/orders"
        invoices = root / "src/features/invoices/ui"
        shared = root / "src/shared"
        for folder in (orders, invoices, shared):
            folder.mkdir(parents=True)
        (orders / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")
        (invoices / "list.tsx").write_text(
            'import { x } from "../../orders";\nimport "react";\n', encoding="utf-8"
        )
        (shared / "util.ts").write_text("export const y = 2;\n", encoding="utf-8")
        if check(root, aliases=("@/=src/",)):
            raise SelfTestError(SelfTestIssue.PUBLIC_IMPORT_REJECTED)
        (invoices / "list.tsx").write_text(
            'import { x } from "../../orders/api/orders.api";\n'
            'const lazy = import("@/features/orders/ui/view");\n',
            encoding="utf-8",
        )
        (shared / "util.ts").write_text(
            'export { x } from "@/features/orders";\n', encoding="utf-8"
        )
        findings = check(root, aliases=("@/=src/",))
        expected = _SELF_TEST_EXPECTED_FINDINGS
        if len(findings) != expected:
            raise SelfTestError(
                SelfTestIssue.FINDING_COUNT, expected=expected, findings=findings
            )
        if not findings[0].startswith("src/features/invoices/ui/list.tsx:1:"):
            raise SelfTestError(SelfTestIssue.FINDING_LOCATION, findings=findings)


def main(argv: list[str] | None = None) -> int:
    """Run the boundary check or its self-test and return a process exit code.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when no findings exist, 1 when findings or input errors exist.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--features-dir", default="src/features")
    parser.add_argument(
        "--shared-dir",
        action="append",
        default=[],
        help="root-relative directory that must not import features (repeatable)",
    )
    parser.add_argument(
        "--alias",
        action="append",
        default=[],
        help="import alias as PREFIX=DIRECTORY, for example '@/=src/'",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Feature import checker self-test passed.")
        return 0
    try:
        findings = check(
            args.root,
            features_dir=args.features_dir,
            shared_dirs=tuple(args.shared_dir) or ("src/shared",),
            aliases=tuple(args.alias),
        )
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Cannot check feature imports: {error}", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    if not findings:
        print("Feature import boundaries passed.")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
