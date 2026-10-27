"""Flag continuous-delivery hazards in GitHub Actions workflow files.

A deploy job is a job with an ``environment`` key, or a job that calls a
reusable workflow with an ``environment`` input. Environments that only scope
read-only credentials (for example ``prod-plan``) can be excluded with
``--skip-environment``. Findings are printed as ``path:line: [rule] message``:

- ``deploy-needs``: a deploy job has no ``needs``, so nothing proves the
  artifact was built, tested, or verified first.
- ``deploy-cancel``: a deploy job, or the workflow that contains one, sets
  ``cancel-in-progress: true``; a cancelled deploy can stop half applied.
- ``deploy-timeout``: a deploy job that runs steps has no ``timeout-minutes``.
- ``oidc-permission``: a deploy job runs a cloud login action
  (``azure/login``, ``aws-actions/configure-aws-credentials``, or
  ``google-github-actions/auth`` by default) without an effective
  ``id-token: write`` permission.
- ``mutable-image``: a deploy job references an image by tag (``:latest`` or
  ``registry/name:tag``) instead of an ``@sha256:`` digest.
- ``rebuild-in-deploy``: a deploy job builds (``docker build``, ``uv build``,
  ``npm run build``, ``docker/build-push-action``) instead of promoting the
  artifact that CI already built.

The analysis is heuristic: expressions are not evaluated, called reusable
workflows and composite actions are not opened, and only a literal ``true``
counts for ``cancel-in-progress``. PyYAML parses the files; when it is not
installed the checker exits 2.

Exit codes: 0 clean, 1 findings (or a failed self-test), 2 for usage errors,
missing or unparsable input, or missing PyYAML.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence
    from types import ModuleType

_FINDINGS = 1
_INVALID = 2
_MAP = "map"
_SEQ = "seq"
_SCALAR = "scalar"
_LITERAL = "|"
_FOLDED = ">"
_NEEDS = "deploy-needs"
_CANCEL = "deploy-cancel"
_TIMEOUT = "deploy-timeout"
_OIDC = "oidc-permission"
_IMAGE = "mutable-image"
_REBUILD = "rebuild-in-deploy"
RULES = (_NEEDS, _CANCEL, _TIMEOUT, _OIDC, _IMAGE, _REBUILD)
_DEFAULT_LOGIN_ACTIONS = (
    "azure/login",
    "aws-actions/configure-aws-credentials",
    "google-github-actions/auth",
)
_BUILD_ACTIONS = ("docker/build-push-action", "docker/bake-action")
_DEFAULT_BUILD_PATTERNS = (
    r"\bdocker\s+(?:buildx\s+)?build\b",
    r"\bdocker\s+(?:buildx\s+)?bake\b",
    r"\bdocker\s+compose\s+build\b",
    r"\b(?:podman|buildah)\s+(?:build|bud)\b",
    r"\baz\s+acr\s+build\b",
    r"\buv\s+build\b",
    r"\bpython3?\s+-m\s+build\b",
    r"\b(?:npm|pnpm|bun)\s+run\s+build\b",
    r"\b(?:pnpm|yarn)\s+build\b",
    r"\bdotnet\s+publish\b",
    r"\bmvn\b[^\n]*\bpackage\b",
    r"\bgradlew?\s+(?:build|assemble)\b",
)
_IMAGE_KEYS = ("steps", "env", "with")
_SKIPPED_KEYS = frozenset({"uses", "container", "services"})
_EXPRESSION = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)
_EXPRESSION_MARK = "\ue000"
_WORD = re.compile(r"[^\s\"'=,;()<>|&]+")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:/")
_DIGEST_MARK = "@"
_LATEST = ":latest"
_SUFFIXES = (".yml", ".yaml", ".yml.template", ".yaml.template")


class WorkflowError(ValueError):
    """A workflow file cannot be read as YAML."""

    def __init__(self, *, problem: str) -> None:
        """Describe the parse failure.

        Args:
            problem: Parser message, including the position when known.
        """
        super().__init__(problem)


class MissingPathError(ValueError):
    """A path named on the command line does not exist."""

    def __init__(self, *, path: Path) -> None:
        """Describe the missing path.

        Args:
            path: The path that was not found.
        """
        super().__init__(f"path does not exist: {path}")


@dataclass(frozen=True, kw_only=True, slots=True)
class Node:
    """A YAML node reduced to what the rules need.

    Attributes:
        kind: ``map``, ``seq``, or ``scalar``.
        line: One-based line where the node starts.
        text: Scalar value; empty for collections.
        style: Scalar style indicator such as ``|`` or ``>``; empty when plain.
        entries: Mapping entries as key, key line, and value.
        items: Sequence items.
    """

    kind: str
    line: int
    text: str = ""
    style: str = ""
    entries: tuple[tuple[str, int, Node], ...] = ()
    items: tuple[Node, ...] = ()

    def get(self, key: str) -> Node | None:
        """Return the value stored under ``key`` in a mapping.

        Args:
            key: Mapping key to look up.

        Returns:
            The value node, or None when the key is absent or this is not a map.
        """
        for name, _, value in self.entries:
            if name == key:
                return value
        return None


@dataclass(frozen=True, kw_only=True, slots=True)
class DeployJob:
    """A job that deploys to an environment.

    Attributes:
        name: Job identifier.
        line: One-based line of the job key.
        node: The job mapping.
        calls_workflow: True when the job calls a reusable workflow.
    """

    name: str
    line: int
    node: Node
    calls_workflow: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class Options:
    """Checker configuration.

    Attributes:
        ignored: Rule identifiers to skip.
        login_actions: Lower-case action names, without a ref, that exchange
            an OIDC token for cloud credentials.
        build_patterns: Patterns that identify build commands in ``run``.
        skip_environments: Patterns for environment names that only scope
            read-only credentials (for example ``-plan$``); such jobs are not
            treated as deploy jobs.
    """

    ignored: frozenset[str]
    login_actions: tuple[str, ...]
    build_patterns: tuple[re.Pattern[str], ...]
    skip_environments: tuple[re.Pattern[str], ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One reportable delivery hazard.

    Attributes:
        path: Workflow file that contains the problem.
        line: One-based line number.
        rule: Rule identifier.
        message: Human-readable explanation.
    """

    path: Path
    line: int
    rule: str
    message: str

    def render(self) -> str:
        """Return the deterministic ``path:line: [rule] message`` form."""
        return f"{self.path.as_posix()}:{self.line}: [{self.rule}] {self.message}"


def default_options() -> Options:
    """Return the options used when no flags are given."""
    return Options(
        ignored=frozenset(),
        login_actions=_DEFAULT_LOGIN_ACTIONS,
        build_patterns=tuple(re.compile(item) for item in _DEFAULT_BUILD_PATTERNS),
        skip_environments=(),
    )


def load_yaml() -> ModuleType | None:
    """Import PyYAML when it is installed.

    Returns:
        The ``yaml`` module, or None when it cannot be imported.
    """
    try:
        module = importlib.import_module("yaml")
    except ImportError:
        return None
    return module


def _convert(raw: object) -> Node:
    """Reduce a PyYAML composed node to a ``Node``."""
    fields = vars(raw)
    line = int(fields["start_mark"].line) + 1
    kind = type(raw).__name__
    value = fields["value"]
    if kind == "MappingNode":
        entries = tuple(_entry(key, item) for key, item in value)
        return Node(kind=_MAP, line=line, entries=entries)
    if kind == "SequenceNode":
        return Node(kind=_SEQ, line=line, items=tuple(_convert(i) for i in value))
    style = fields.get("style") or ""
    return Node(kind=_SCALAR, line=line, text=str(value), style=str(style))


def _entry(key: object, value: object) -> tuple[str, int, Node]:
    """Convert one mapping pair into a key, key line, and value node."""
    converted = _convert(key)
    return converted.text, converted.line, _convert(value)


def parse(text: str, yaml_module: ModuleType) -> Node | None:
    """Compose workflow text into nodes that keep line numbers.

    Args:
        text: Complete workflow file content.
        yaml_module: The imported PyYAML module.

    Returns:
        The root node, or None for an empty document.

    Raises:
        WorkflowError: If the text is not a single valid YAML document.
    """
    error_type = yaml_module.YAMLError
    try:
        raw = yaml_module.compose(text, Loader=yaml_module.SafeLoader)
    except error_type as error:
        raise WorkflowError(problem=str(error)) from error
    return None if raw is None else _convert(raw)


def _environment_name(job: Node) -> str | None:
    """Return the environment a job or reusable-workflow call targets."""
    target = job.get("environment")
    inputs = job.get("with")
    if target is None and job.get("uses") is not None and inputs is not None:
        target = inputs.get("environment")
    if target is None:
        return None
    named = target.get("name")
    return (named if named is not None else target).text


def _deploy_jobs(root: Node, options: Options) -> list[DeployJob]:
    """Return every job in the workflow that deploys to an environment."""
    jobs = root.get("jobs")
    if jobs is None:
        return []
    found: list[DeployJob] = []
    for name, line, job in jobs.entries:
        environment = _environment_name(job)
        if environment is None or any(
            pattern.search(environment) for pattern in options.skip_environments
        ):
            continue
        calls = job.get("uses") is not None
        found.append(DeployJob(name=name, line=line, node=job, calls_workflow=calls))
    return found


def _is_true(node: Node | None) -> bool:
    """Tell whether a node is the literal boolean ``true``."""
    return node is not None and node.text.strip().lower() == "true"


def _cancel_flag(owner: Node) -> Node | None:
    """Return a literal ``cancel-in-progress: true`` node under ``owner``."""
    concurrency = owner.get("concurrency")
    flag = None if concurrency is None else concurrency.get("cancel-in-progress")
    return flag if _is_true(flag) else None


def _workflow_cancel(
    path: Path, root: Node, jobs: Sequence[DeployJob]
) -> list[Finding]:
    """Report workflow-level cancellation that also cancels deploy jobs."""
    flag = _cancel_flag(root)
    if flag is None or not jobs:
        return []
    names = ", ".join(job.name for job in jobs)
    message = (
        "workflow concurrency cancels in-progress runs, including deploy jobs "
        f"({names}); scope cancellation to pull requests or set it false"
    )
    return [Finding(path=path, line=flag.line, rule=_CANCEL, message=message)]


def _needs_findings(path: Path, job: DeployJob) -> list[Finding]:
    """Report a deploy job that does not wait for build, test, or verify jobs."""
    needs = job.node.get("needs")
    if needs is not None and (needs.items or needs.text.strip()):
        return []
    message = (
        f"deploy job '{job.name}' has no 'needs'; run it only after the job "
        "that built, tested, or verified the artifact"
    )
    return [Finding(path=path, line=job.line, rule=_NEEDS, message=message)]


def _cancel_findings(path: Path, job: DeployJob) -> list[Finding]:
    """Report a deploy job whose own concurrency cancels in-progress runs."""
    flag = _cancel_flag(job.node)
    if flag is None:
        return []
    message = (
        f"deploy job '{job.name}' sets cancel-in-progress: true; a cancelled "
        "deploy can stop half applied, so queue deploys instead"
    )
    return [Finding(path=path, line=flag.line, rule=_CANCEL, message=message)]


def _timeout_findings(path: Path, job: DeployJob) -> list[Finding]:
    """Report a deploy job without an explicit timeout."""
    if job.node.get("timeout-minutes") is not None:
        return []
    message = (
        f"deploy job '{job.name}' has no timeout-minutes; the platform default "
        "is 360 minutes"
    )
    return [Finding(path=path, line=job.line, rule=_TIMEOUT, message=message)]


def _steps(job: Node) -> list[Node]:
    """Return the mapping steps of a job."""
    steps = job.get("steps")
    if steps is None:
        return []
    return [step for step in steps.items if step.kind == _MAP]


def _action(step: Node) -> Node | None:
    """Return the ``uses`` node of a step, if any."""
    uses = step.get("uses")
    return uses if uses is not None and uses.kind == _SCALAR else None


def _action_name(uses: Node) -> str:
    """Return the lower-case action name without its ref."""
    return uses.text.split(_DIGEST_MARK, 1)[0].strip().lower()


def _grants_id_token(permissions: Node | None) -> bool:
    """Tell whether a permissions node grants ``id-token: write``."""
    if permissions is None:
        return False
    if permissions.kind == _SCALAR:
        return permissions.text.strip() == "write-all"
    value = permissions.get("id-token")
    return value is not None and value.text.strip() == "write"


def _oidc_findings(
    path: Path, root: Node, job: DeployJob, options: Options
) -> list[Finding]:
    """Report a cloud login in a job that cannot request an OIDC token."""
    logins = [
        uses
        for step in _steps(job.node)
        if (uses := _action(step)) is not None
        and _action_name(uses) in options.login_actions
    ]
    own = job.node.get("permissions")
    effective = own if own is not None else root.get("permissions")
    if not logins or _grants_id_token(effective):
        return []
    message = (
        f"deploy job '{job.name}' runs {_action_name(logins[0])} without "
        "'id-token: write'; grant it on the job and keep long-lived cloud "
        "secrets out of the workflow"
    )
    return [Finding(path=path, line=logins[0].line, rule=_OIDC, message=message)]


def _line_at(node: Node, offset: int) -> int:
    """Map a character offset inside a scalar to a file line."""
    if node.style == _LITERAL:
        return node.line + 1 + node.text.count("\n", 0, offset)
    if node.style == _FOLDED:
        return node.line + 1
    return node.line + node.text.count("\n", 0, offset)


def _rebuild_in_step(step: Node, options: Options) -> tuple[int, str] | None:
    """Return the line and description of a build inside one step."""
    uses = _action(step)
    if uses is not None and _action_name(uses) in _BUILD_ACTIONS:
        return uses.line, _action_name(uses)
    run = step.get("run")
    if run is None:
        return None
    for pattern in options.build_patterns:
        match = pattern.search(run.text)
        if match is not None:
            return _line_at(run, match.start()), " ".join(match.group().split())
    return None


def _rebuild_findings(path: Path, job: DeployJob, options: Options) -> list[Finding]:
    """Report build commands that run inside a deploy job."""
    findings: list[Finding] = []
    for step in _steps(job.node):
        hit = _rebuild_in_step(step, options)
        if hit is None:
            continue
        line, command = hit
        message = (
            f"deploy job '{job.name}' builds ({command}); promote the artifact "
            "or digest that CI built and attested instead of rebuilding"
        )
        findings.append(Finding(path=path, line=line, rule=_REBUILD, message=message))
    return findings


def _scalars(node: Node) -> Iterator[Node]:
    """Yield every scalar below ``node`` except action and container keys."""
    if node.kind == _SCALAR:
        yield node
        return
    for item in node.items:
        yield from _scalars(item)
    for name, _, value in node.entries:
        if name not in _SKIPPED_KEYS:
            yield from _scalars(value)


def _looks_like_registry(segment: str) -> bool:
    """Tell whether the first path segment can name a registry host."""
    return (
        "." in segment
        or ":" in segment
        or segment == "localhost"
        or segment.startswith(("$", _EXPRESSION_MARK))
    )


def is_mutable_reference(word: str) -> bool:
    """Tell whether a word is an image reference pinned by tag, not digest.

    Args:
        word: One whitespace-free word, with expressions already masked.

    Returns:
        True for ``name:latest`` and for ``registry/name:tag`` without a digest.
    """
    if "://" in word or _WINDOWS_DRIVE.match(word):
        return False
    if word.lower().endswith(_LATEST):
        return True
    head, slash, tail = word.rpartition("/")
    if not slash or _DIGEST_MARK in tail or ":" not in tail:
        return False
    tag = tail.split(":", 1)[1]
    return bool(tag) and _looks_like_registry(head.split("/", 1)[0])


def _mask(text: str) -> str:
    """Replace each expression with marks of the same length and no spaces."""
    return _EXPRESSION.sub(lambda match: _EXPRESSION_MARK * len(match.group()), text)


def _scalar_image_findings(path: Path, job: DeployJob, scalar: Node) -> list[Finding]:
    """Report tag-pinned image references inside one scalar value."""
    findings: list[Finding] = []
    for match in _WORD.finditer(_mask(scalar.text)):
        if not is_mutable_reference(match.group()):
            continue
        reference = scalar.text[match.start() : match.end()]
        message = (
            f"deploy job '{job.name}' references image '{reference}' by tag; "
            "deploy the immutable '@sha256:' digest that CI produced"
        )
        line = _line_at(scalar, match.start())
        findings.append(Finding(path=path, line=line, rule=_IMAGE, message=message))
    return findings


def _image_findings(path: Path, job: DeployJob) -> list[Finding]:
    """Report image references by tag inside a deploy job."""
    findings: list[Finding] = []
    for key in _IMAGE_KEYS:
        value = job.node.get(key)
        if value is None:
            continue
        for scalar in _scalars(value):
            findings.extend(_scalar_image_findings(path, job, scalar))
    return findings


def _job_findings(
    path: Path, root: Node, job: DeployJob, options: Options
) -> list[Finding]:
    """Apply every per-job rule to one deploy job."""
    findings = [
        *_needs_findings(path, job),
        *_cancel_findings(path, job),
        *_image_findings(path, job),
    ]
    if not job.calls_workflow:
        findings.extend(_timeout_findings(path, job))
        findings.extend(_oidc_findings(path, root, job, options))
        findings.extend(_rebuild_findings(path, job, options))
    return findings


def scan_workflow(path: Path, root: Node | None, options: Options) -> list[Finding]:
    """Check one parsed workflow and return its findings in line order.

    Args:
        path: Path reported in findings.
        root: Parsed root node, or None for an empty file.
        options: Checker configuration.

    Returns:
        Findings sorted by line, rule, and message, without ignored rules.
    """
    if root is None or root.kind != _MAP:
        return []
    jobs = _deploy_jobs(root, options)
    findings = _workflow_cancel(path, root, jobs)
    for job in jobs:
        findings.extend(_job_findings(path, root, job, options))
    kept = [finding for finding in findings if finding.rule not in options.ignored]
    return sorted(kept, key=lambda item: (item.line, item.rule, item.message))


def scan_text(
    path: Path, text: str, yaml_module: ModuleType, options: Options
) -> list[Finding]:
    """Parse and check one workflow file.

    Args:
        path: Path reported in findings.
        text: Workflow file content.
        yaml_module: The imported PyYAML module.
        options: Checker configuration.

    Returns:
        Findings in line order.

    Raises:
        WorkflowError: If the text is not valid YAML.
    """
    return scan_workflow(path, parse(text, yaml_module), options)


def collect_files(paths: Iterable[Path]) -> list[Path]:
    """Expand directories into sorted workflow files.

    Args:
        paths: Files or directories. Directories contribute files ending in
            ``.yml``, ``.yaml``, ``.yml.template``, or ``.yaml.template``.

    Returns:
        Sorted, de-duplicated file list.

    Raises:
        MissingPathError: If a path does not exist.
    """
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.name.endswith(_SUFFIXES)
            )
        elif path.is_file():
            files.add(path)
        else:
            raise MissingPathError(path=path)
    return sorted(files)


_SELF_TEST_CLEAN = """\
on: push
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - run: docker build -t app .
  deploy:
    needs: build
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    environment: production
    concurrency:
      group: deploy-production
      cancel-in-progress: false
    permissions:
      id-token: write
    steps:
      - uses: azure/login@0000000000000000000000000000000000000000
      - run: |
          az containerapp update --image "${{ env.IMAGE }}@${{ env.DIGEST }}"
"""

_SELF_TEST_RISKY = """\
on: push
concurrency:
  group: everything
  cancel-in-progress: true
jobs:
  deploy:
    runs-on: ubuntu-24.04
    environment: production
    steps:
      - uses: azure/login@0000000000000000000000000000000000000000
      - run: |
          docker build -t ghcr.io/shop/orders:1.4.2 .
          az containerapp update --image ghcr.io/shop/orders:latest
"""


def self_test(yaml_module: ModuleType) -> list[str]:
    """Check the rules on in-memory workflows and return unmet expectations.

    Args:
        yaml_module: The imported PyYAML module.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    options = default_options()
    failures: list[str] = []
    if scan_text(Path("clean.yml"), _SELF_TEST_CLEAN, yaml_module, options):
        failures.append("clean workflow produced findings")
    risky = scan_text(Path("risky.yml"), _SELF_TEST_RISKY, yaml_module, options)
    rendered = "\n".join(item.render() for item in risky)
    expectations = {
        "workflow cancellation": "risky.yml:4: [deploy-cancel]",
        "missing needs": "risky.yml:6: [deploy-needs]",
        "missing timeout": "risky.yml:6: [deploy-timeout]",
        "missing id-token": "risky.yml:10: [oidc-permission]",
        "rebuild": "risky.yml:12: [rebuild-in-deploy]",
        "tagged image": "risky.yml:12: [mutable-image]",
        "latest image": "risky.yml:13: [mutable-image]",
    }
    failures.extend(
        f"expected {label}: {needle!r}"
        for label, needle in expectations.items()
        if needle not in rendered
    )
    try:
        parse("jobs: [unclosed\n", yaml_module)
    except WorkflowError:
        pass
    else:
        failures.append("invalid YAML was accepted")
    return failures


def _run_self_test(yaml_module: ModuleType) -> int:
    """Run the self-test, print its outcome, and return the exit status."""
    failures = self_test(yaml_module)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return _FINDINGS
    print("check_delivery_workflow self-test passed.")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths", nargs="*", type=Path, help="workflow files or directories to scan"
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        choices=RULES,
        help="skip a rule (repeatable)",
    )
    parser.add_argument(
        "--login-action",
        action="append",
        default=[],
        help="extra action name (owner/name) that exchanges an OIDC token",
    )
    parser.add_argument(
        "--build-pattern",
        action="append",
        default=[],
        help="extra regular expression that identifies a build command",
    )
    parser.add_argument(
        "--skip-environment",
        action="append",
        default=[],
        help="regular expression for read-only environment names to skip",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def _options(args: argparse.Namespace) -> Options:
    """Build options from parsed arguments.

    Raises:
        re.error: A ``--build-pattern`` or ``--skip-environment`` value is not
            a valid expression.
    """
    base = default_options()
    extra = tuple(re.compile(pattern) for pattern in args.build_pattern)
    skipped = tuple(re.compile(pattern) for pattern in args.skip_environment)
    logins = tuple(name.strip().lower() for name in args.login_action)
    return Options(
        ignored=frozenset(args.ignore),
        login_actions=base.login_actions + logins,
        build_patterns=base.build_patterns + extra,
        skip_environments=skipped,
    )


def _scan(paths: Iterable[Path], yaml_module: ModuleType, options: Options) -> int:
    """Scan files, print findings, and return the exit status."""
    findings: list[Finding] = []
    try:
        files = collect_files(paths)
        for path in files:
            text = path.read_text(encoding="utf-8")
            try:
                findings.extend(scan_text(path, text, yaml_module, options))
            except WorkflowError as error:
                print(f"Cannot parse {path.as_posix()}: {error}", file=sys.stderr)
                return _INVALID
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Cannot check workflows: {error}", file=sys.stderr)
        return _INVALID
    for finding in findings:
        print(finding.render())
    if findings:
        print(f"{len(findings)} finding(s) in {len(files)} file(s)", file=sys.stderr)
        return _FINDINGS
    print(f"No findings in {len(files)} file(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Check workflow files and print one finding per line.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when clean, 1 with findings or a failed self-test, 2 for usage
        errors, unreadable or invalid input, or missing PyYAML.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    yaml_module = load_yaml()
    if yaml_module is None:
        print(
            "PyYAML is required; run this checker in an environment that "
            "can import the yaml module.",
            file=sys.stderr,
        )
        return _INVALID
    if args.self_test:
        return _run_self_test(yaml_module)
    if not args.paths:
        parser.error("at least one path is required unless --self-test is given")
    try:
        options = _options(args)
    except re.error as error:
        print(f"Invalid regular expression option: {error}", file=sys.stderr)
        return _INVALID
    return _scan(args.paths, yaml_module, options)


if __name__ == "__main__":
    raise SystemExit(main())
