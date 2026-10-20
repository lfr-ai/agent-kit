"""Flag risky GitHub Actions workflow patterns with a line-based scan.

Reports a missing top-level 'permissions' key in workflow files, 'write-all'
grants, 'uses:' references that are not pinned to a full commit SHA (or an image
digest), and '${{' expressions inside 'run:' scripts. The scan reads files only;
it never contacts GitHub, resolves tags, or executes workflow content.

Exit codes: 0 clean, 1 findings, 2 unreadable input or bad arguments.
"""

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_FINDINGS = 1
_INVALID = 2
_SHA = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_TOP_ON = re.compile(r"""^["']?on["']?\s*:""")
_TOP_PERMISSIONS = re.compile(r"^permissions\s*:")
_WRITE_ALL = re.compile(r"""^\s*permissions\s*:\s*["']?write-all["']?\s*(?:#.*)?$""")
_USES = re.compile(r"""^\s*(?:-\s+)?uses\s*:\s*(?P<ref>["'][^"']*["']|[^\s#]+)""")
_RUN = re.compile(r"^(?P<indent>\s*(?:-\s+)?)run\s*:(?P<rest>.*)$")
_EXPRESSION = re.compile(r"\$\{\{\s*(?P<body>.*?)\s*\}\}")
_COMMENT = re.compile(r"(?:^|\s+)#.*$")
_MAPPING_KEY = re.compile(r"^\s+[A-Za-z_][\w-]*\s*:(?:\s|$)")
_WORKFLOW_SUFFIXES = (".yml", ".yaml")


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One reportable workflow problem.

    Attributes:
        path: File that contains the problem.
        line: One-based line number.
        message: Human-readable explanation.
    """

    path: Path
    line: int
    message: str

    def render(self) -> str:
        """Return the deterministic 'path:line: message' form."""
        return f"{self.path.as_posix()}:{self.line}: {self.message}"


@dataclass(frozen=True, kw_only=True, slots=True)
class Options:
    """Scan configuration supplied on the command line.

    Attributes:
        trusted_owners: Action owners exempt from SHA pinning (for example 'my-org').
        allowed_expressions: Expression prefixes tolerated inside 'run:' scripts.
        require_permissions: Whether workflow files must declare top-level permissions.
    """

    trusted_owners: frozenset[str]
    allowed_expressions: tuple[str, ...]
    require_permissions: bool


def check_reference(reference: str, options: Options) -> str | None:
    """Explain why a 'uses:' reference is unpinned, or return None when acceptable.

    Args:
        reference: Raw value of a 'uses:' key without quotes.
        options: Scan configuration.

    Returns:
        A finding message, or None for local, digest-pinned, SHA-pinned or trusted refs.
    """
    message: str | None = None
    target, separator, ref = reference.partition("@")
    if reference.startswith("docker://"):
        if not _DIGEST.search(reference):
            message = f"container action '{reference}' is not pinned to a digest"
    elif reference.startswith("./") or target.split("/", 1)[0] in (
        options.trusted_owners
    ):
        message = None
    elif not separator or not ref:
        message = f"action '{reference}' has no ref; pin a full 40-character SHA"
    elif _SHA.fullmatch(ref) is None:
        message = f"action '{reference}' uses mutable ref '{ref}'; pin a full SHA"
    return message


def _run_block_end(lines: Sequence[str], start: int, key_column: int) -> int:
    """Return the index after the last continuation line of a 'run:' value."""
    index = start + 1
    while index < len(lines):
        text = lines[index]
        if text.strip() and len(text) - len(text.lstrip(" ")) <= key_column:
            break
        index += 1
    return index


def _is_mapping(rest: str, following: Sequence[str]) -> bool:
    """Tell a 'defaults: run:' settings mapping apart from a 'run:' script.

    Args:
        rest: Text after 'run:' on the key line.
        following: Lines after the key line.

    Returns:
        True when the key has no inline value and its first child is a key.
    """
    if _COMMENT.sub("", rest).strip():
        return False
    child = next((text for text in following if text.strip()), "")
    return _MAPPING_KEY.match(child) is not None


def _expression_findings(
    path: Path, number: int, text: str, options: Options
) -> list[Finding]:
    """Report every disallowed '${{' expression in one line of a 'run:' script."""
    findings: list[Finding] = []
    for match in _EXPRESSION.finditer(text):
        body = match.group("body")
        if any(body.startswith(prefix) for prefix in options.allowed_expressions):
            continue
        findings.append(
            Finding(
                path=path,
                line=number,
                message=(
                    f"expression '${{{{ {body} }}}}' is interpolated into a run "
                    "script; pass it through 'env:' and quote the variable"
                ),
            )
        )
    if "${{" in text and not _EXPRESSION.search(text):
        findings.append(
            Finding(
                path=path,
                line=number,
                message="unterminated '${{' inside a run script",
            )
        )
    return findings


def scan_text(path: Path, text: str, options: Options) -> list[Finding]:
    """Scan one workflow or action file and return its findings in line order.

    Args:
        path: Path reported in findings.
        text: File content.
        options: Scan configuration.

    Returns:
        Findings sorted by line number.
    """
    lines = text.splitlines()
    findings: list[Finding] = []
    is_workflow = any(_TOP_ON.match(line) for line in lines)
    has_permissions = any(_TOP_PERMISSIONS.match(line) for line in lines)
    if options.require_permissions and is_workflow and not has_permissions:
        findings.append(
            Finding(
                path=path,
                line=1,
                message=(
                    "workflow has no top-level 'permissions'; declare least "
                    "privilege (for example 'contents: read')"
                ),
            )
        )
    index = 0
    while index < len(lines):
        line = lines[index]
        number = index + 1
        if line.lstrip().startswith("#"):
            index += 1
            continue
        run = _RUN.match(line)
        if run is not None and not _is_mapping(run.group("rest"), lines[index + 1 :]):
            end = _run_block_end(lines, index, len(run.group("indent")))
            findings.extend(
                _expression_findings(path, number, run.group("rest"), options)
            )
            for offset, body in enumerate(lines[index + 1 : end], start=index + 2):
                findings.extend(_expression_findings(path, offset, body, options))
            index = end
            continue
        if _WRITE_ALL.match(line):
            findings.append(
                Finding(
                    path=path,
                    line=number,
                    message="'permissions: write-all' grants every scope; list scopes",
                )
            )
        uses = _USES.match(line)
        if uses is not None:
            reference = uses.group("ref").strip("\"'")
            message = check_reference(reference, options)
            if message is not None:
                findings.append(Finding(path=path, line=number, message=message))
        index += 1
    return sorted(findings, key=lambda finding: finding.line)


class WorkflowInputError(ValueError):
    """An input violates the workflowinput contract."""

    def __init__(self, *, path: Path) -> None:
        """Describe the violated invariant.

        Args:
            path: Diagnostic path for the failing input.
        """
        super().__init__(f"path does not exist: {path}")


def collect_files(paths: Iterable[Path]) -> list[Path]:
    """Expand directories into sorted YAML files; keep explicit files as given.

    Args:
        paths: Files or directories supplied by the operator.

    Returns:
        Sorted, de-duplicated file list.

    Raises:
        ValueError: If a path does not exist.
    """
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix in _WORKFLOW_SUFFIXES
            )
        elif path.is_file():
            files.add(path)
        else:
            raise WorkflowInputError(path=path)
    return sorted(files)


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    CLEAN_WORKFLOW_REJECTED = "clean workflow produced findings"
    RISKY_WORKFLOW_FINDINGS = "risky workflow findings regressed: {lines}"
    COMPOSITE_PERMISSIONS = "composite action must not require permissions"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(self, issue: SelfTestIssue, *, lines: list[int] | None = None) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            lines: Observed lines for the failing case.
        """
        super().__init__(issue.value.format(lines=lines))


def self_test() -> None:
    """Exercise passing and failing synthetic workflows without touching disk."""
    options = Options(
        trusted_owners=frozenset({"trusted-org"}),
        allowed_expressions=("runner.",),
        require_permissions=True,
    )
    sha = "0123456789abcdef0123456789abcdef01234567"  # pragma: allowlist secret
    clean = (
        "name: ci\non:\n  push:\npermissions:\n  contents: read\n"
        "defaults:\n  run:  # job settings, not a script\n    shell: bash\n"
        "    working-directory: ${{ inputs.directory }}\njobs:\n"
        "  test:\n    runs-on: ubuntu-latest\n    steps:\n"
        f"      - uses: actions/checkout@{sha} # v4\n"
        "      - uses: ./.github/actions/setup\n"
        "      - uses: trusted-org/tool@main\n"
        "      - env:\n          TITLE: ${{ github.event.pull_request.title }}\n"
        '        run: |\n          echo "$TITLE"\n'
        "          echo ${{ runner.temp }}\n"
    )
    if scan_text(Path("clean.yml"), clean, options):
        raise SelfTestError(SelfTestIssue.CLEAN_WORKFLOW_REJECTED)
    risky = (
        "on: pull_request_target\njobs:\n  build:\n    permissions: write-all\n"
        "    steps:\n      - uses: actions/checkout@v4\n      - uses: owner/action\n"
        "      - uses: docker://alpine:3\n"
        "      - run: echo ${{ github.event.pull_request.title }}\n"
        "      - run: |\n          echo ok\n          echo ${{ github.head_ref }}\n"
    )
    lines = [finding.line for finding in scan_text(Path("risky.yml"), risky, options)]
    if lines != [1, 4, 6, 7, 8, 9, 12]:
        raise SelfTestError(SelfTestIssue.RISKY_WORKFLOW_FINDINGS, lines=lines)
    action = "runs:\n  using: composite\n  steps:\n    - run: echo hi\n"
    if scan_text(Path("action.yml"), action, options):
        raise SelfTestError(SelfTestIssue.COMPOSITE_PERMISSIONS)


def main(argv: list[str] | None = None) -> int:
    """Scan workflow files and print one 'path:line: message' line per finding.

    Args:
        argv: Command-line arguments; defaults to 'sys.argv'.

    Returns:
        0 when clean, 1 with findings, 2 for unreadable input.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".github/workflows")],
        help="workflow files or directories (default: .github/workflows)",
    )
    parser.add_argument(
        "--trusted-owner",
        action="append",
        default=[],
        help="action owner exempt from SHA pinning; repeatable",
    )
    parser.add_argument(
        "--allow-expression",
        action="append",
        default=[],
        help="expression prefix tolerated inside run scripts, e.g. 'runner.'",
    )
    parser.add_argument(
        "--no-require-permissions",
        action="store_true",
        help="do not require a top-level permissions key",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Workflow permission checker self-test passed.")
        return 0
    options = Options(
        trusted_owners=frozenset(args.trusted_owner),
        allowed_expressions=tuple(args.allow_expression),
        require_permissions=not args.no_require_permissions,
    )
    try:
        files = collect_files(args.paths)
        findings = [
            finding
            for path in files
            for finding in scan_text(path, path.read_text(encoding="utf-8"), options)
        ]
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Cannot scan workflows: {error}", file=sys.stderr)
        return _INVALID
    for finding in findings:
        print(finding.render())
    if findings:
        print(
            f"{len(findings)} finding(s) in {len(files)} file(s)",
            file=sys.stderr,
        )
        return _FINDINGS
    print(f"No findings in {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
