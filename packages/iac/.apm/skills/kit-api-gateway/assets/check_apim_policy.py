# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Flag risky Azure API Management policy XML before it is published.

Each file is checked on its own and every finding is printed as
``path:line: [rule] message``. Rules:

- ``missing-base``: an ``inbound``, ``backend``, ``outbound``, or ``on-error``
  section below global scope has no direct ``<base />`` child, so policies of
  the enclosing scope silently stop applying.
- ``cors-wildcard``: a ``cors`` policy allows the origin ``*``.
- ``missing-rate-limit``: an API-scope policy has no ``rate-limit``,
  ``rate-limit-by-key``, ``llm-token-limit``, or ``azure-openai-token-limit``
  (on by default; disable with ``--no-require-rate-limit``).
- ``missing-quota``: an API-scope policy has no ``quota``, ``quota-by-key``, or
  token quota (only with ``--require-quota``).
- ``missing-auth``: an API-scope policy has no ``validate-jwt``,
  ``validate-azure-ad-token``, or ``validate-client-certificate`` (only with
  ``--require-auth``).
- ``weak-jwt``: ``validate-jwt`` turns off signature or expiry checks, or has
  no ``audiences``.
- ``inline-secret``: a literal that looks like a credential (bearer token, JWT,
  32-hex subscription key, connection-string key, sensitive header value, or
  basic-auth password) instead of a ``{{named-value}}`` or an expression.
- ``on-error-status``: an ``on-error`` section with its own policies but no
  ``set-status`` (directly or inside ``return-response``), a
  ``return-response`` without ``set-status``, or a global policy without an
  ``on-error`` section.

``include-fragment`` references are not resolved; name fragments that provide
limits or authentication with ``--limit-fragment`` and ``--auth-fragment``.
The scope comes from ``--scope`` or, with ``auto``, from the file name
(``global``, ``workspace``, ``product``, ``operation``; otherwise ``api``).

Only parse local, trusted files. The stdlib ``expat`` parser is used directly so
any ``DOCTYPE`` (and therefore entity expansion) is rejected, but it is not a
hardened parser such as ``defusedxml``.

Exit codes: 0 clean, 1 findings or a failed self-test, 2 unreadable or
unparsable input.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING
from xml.parsers import expat

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

_FINDINGS = 1
_INVALID = 2
_LAST_CHUNK = True
_SECTIONS = ("inbound", "backend", "outbound", "on-error")
_ROOTS = frozenset({"policies", "fragment"})
_SCOPES = ("global", "workspace", "product", "api", "operation")
_RATE_POLICIES = frozenset(
    {"rate-limit", "rate-limit-by-key", "llm-token-limit", "azure-openai-token-limit"}
)
_TOKEN_POLICIES = frozenset({"llm-token-limit", "azure-openai-token-limit"})
_QUOTA_POLICIES = frozenset({"quota", "quota-by-key"})
_AUTH_POLICIES = frozenset(
    {"validate-jwt", "validate-azure-ad-token", "validate-client-certificate"}
)
_HEADER_POLICIES = frozenset({"set-header", "set-query-parameter"})
_PASSWORD_POLICIES = frozenset({"authentication-basic", "authentication-certificate"})
_SENSITIVE_NAMES = frozenset(
    {
        "authorization",
        "api-key",
        "x-api-key",
        "ocp-apim-subscription-key",
        "subscription-key",
        "x-functions-key",
        "code",
        "sig",
        "client_secret",
        "password",
    }
)
_SECRET_PATTERNS = (
    (
        re.compile(r"(?i)\bbearer\s+(?!\{\{)[A-Za-z0-9._~+/-]{16,}"),
        "literal bearer token",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\."),
        "literal JWT",
    ),
    (
        re.compile(r"(?<![0-9A-Fa-f])[0-9a-f]{32}(?![0-9A-Fa-f])"),
        "32-hex literal that looks like a subscription key",
    ),
    (
        re.compile(
            r"(?i)\b(?:AccountKey|SharedAccessKey|sig|client_secret|password)"
            r"=(?!\{\{)[^&;\s\"']{8,}"
        ),
        "literal key, signature, or password in a connection string or URL",
    ),
)
_POLICY_SUFFIXES = (".xml", ".xml.template")
RULES = (
    "missing-base",
    "cors-wildcard",
    "missing-rate-limit",
    "missing-quota",
    "missing-auth",
    "weak-jwt",
    "inline-secret",
    "on-error-status",
)


class PolicyXmlError(ValueError):
    """The file is not a well-formed, DOCTYPE-free policy document."""

    def __init__(self, *, line: int, problem: str) -> None:
        """Describe the parse problem.

        Args:
            line: One-based line where parsing failed.
            problem: Short description of the problem.
        """
        super().__init__(f"line {line}: {problem}")


class InvalidPolicyFileError(ValueError):
    """A named file could not be parsed as a policy document."""

    def __init__(self, *, path: Path, error: PolicyXmlError) -> None:
        """Name the file and the parse problem.

        Args:
            path: The file that failed to parse.
            error: The underlying parse error.
        """
        super().__init__(f"{path.as_posix()}: {error}")


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
    """One parsed XML element.

    Attributes:
        tag: Element name.
        attrs: Attribute names mapped to values.
        line: One-based line of the start tag.
        text: Character data directly inside the element.
        children: Child elements in source order.
    """

    tag: str
    attrs: dict[str, str]
    line: int
    text: str
    children: tuple[Node, ...]

    def walk(self) -> Iterator[Node]:
        """Yield this element and every descendant in document order."""
        yield self
        for child in self.children:
            yield from child.walk()

    def first(self, tag: str) -> Node | None:
        """Return the first direct child called ``tag``, if any.

        Args:
            tag: Element name to match.
        """
        return next((child for child in self.children if child.tag == tag), None)


@dataclass(frozen=True, kw_only=True, slots=True)
class Options:
    """Policy expectations for one run.

    Attributes:
        scope: ``auto`` or one of the policy scopes.
        require_auth: Require an authentication policy at API scope.
        require_rate_limit: Require a rate limit at API scope.
        require_quota: Require a quota at API scope.
        limit_fragments: Fragment ids that provide rate limits and quotas.
        auth_fragments: Fragment ids that provide authentication.
        disabled: Rule names to skip.
    """

    scope: str = "auto"
    require_auth: bool = False
    require_rate_limit: bool = True
    require_quota: bool = False
    limit_fragments: frozenset[str] = frozenset()
    auth_fragments: frozenset[str] = frozenset()
    disabled: frozenset[str] = frozenset()


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One reportable policy problem.

    Attributes:
        path: File that contains the problem.
        line: One-based line number.
        rule: Rule name from ``RULES``.
        message: Human-readable explanation.
    """

    path: Path
    line: int
    rule: str
    message: str

    def render(self) -> str:
        """Return the deterministic ``path:line: [rule] message`` form."""
        return f"{self.path.as_posix()}:{self.line}: [{self.rule}] {self.message}"


@dataclass(kw_only=True, slots=True)
class _Open:
    """An element whose end tag has not been read yet."""

    tag: str
    attrs: dict[str, str]
    line: int
    text: list[str] = field(default_factory=list)
    children: list[Node] = field(default_factory=list)


class _TreeBuilder:
    """Collect expat callbacks into ``Node`` trees with line numbers."""

    def __init__(self, parser: expat.XMLParserType) -> None:
        """Bind the builder to the parser that reports line numbers.

        Args:
            parser: The expat parser whose callbacks feed this builder.
        """
        self._parser = parser
        self._stack: list[_Open] = []
        self._root: Node | None = None

    def start(self, tag: str, attrs: dict[str, str]) -> None:
        """Open an element at the parser's current line."""
        line = self._parser.CurrentLineNumber
        self._stack.append(_Open(tag=tag, attrs=dict(attrs), line=line))

    def end(self, _tag: str) -> None:
        """Close the innermost element and attach it to its parent."""
        current = self._stack.pop()
        node = Node(
            tag=current.tag,
            attrs=current.attrs,
            line=current.line,
            text="".join(current.text),
            children=tuple(current.children),
        )
        if self._stack:
            self._stack[-1].children.append(node)
        else:
            self._root = node

    def data(self, text: str) -> None:
        """Append character data to the innermost open element."""
        if self._stack:
            self._stack[-1].text.append(text)

    def root(self) -> Node:
        """Return the document element.

        Raises:
            PolicyXmlError: If no element was parsed.
        """
        if self._root is None:
            raise PolicyXmlError(line=1, problem="no root element")
        return self._root


def _reject_doctype(
    name: str, _system_id: str | None, _public_id: str | None, _internal: int
) -> None:
    """Refuse documents that declare a DOCTYPE and could define entities.

    Raises:
        PolicyXmlError: Always.
    """
    raise PolicyXmlError(line=1, problem=f"DOCTYPE '{name}' is not allowed")


def parse(text: str) -> Node:
    """Parse policy XML into a ``Node`` tree.

    Args:
        text: Complete policy document.

    Returns:
        The ``policies`` or ``fragment`` root element.

    Raises:
        PolicyXmlError: If the XML is malformed, declares a DOCTYPE, or has
            another root element.
    """
    parser = expat.ParserCreate()
    parser.buffer_text = True
    builder = _TreeBuilder(parser)
    parser.StartElementHandler = builder.start
    parser.EndElementHandler = builder.end
    parser.CharacterDataHandler = builder.data
    parser.StartDoctypeDeclHandler = _reject_doctype
    try:
        parser.Parse(text, _LAST_CHUNK)
    except expat.ExpatError as error:
        raise PolicyXmlError(
            line=error.lineno, problem=expat.ErrorString(error.code)
        ) from error
    root = builder.root()
    if root.tag not in _ROOTS:
        raise PolicyXmlError(
            line=root.line,
            problem=f"root element is <{root.tag}>, expected <policies> or <fragment>",
        )
    return root


def scope_for(path: Path, configured: str) -> str:
    """Return the policy scope for ``path``.

    Args:
        path: Policy file.
        configured: ``auto`` or an explicit scope.

    Returns:
        The explicit scope, or the first scope named in the file name, else
        ``api``.
    """
    if configured != "auto":
        return configured
    name = path.name.lower()
    return next((scope for scope in _SCOPES if scope in name), "api")


def _finding(path: Path, line: int, rule: str, message: str) -> Finding:
    """Build a finding; keeps call sites short."""
    return Finding(path=path, line=line, rule=rule, message=message)


def _base_findings(path: Path, root: Node) -> list[Finding]:
    """Report sections that drop policies inherited from the enclosing scope."""
    return [
        _finding(
            path,
            section.line,
            "missing-base",
            f"<{section.tag}> has no <base />; enclosing-scope policies will not run",
        )
        for section in root.children
        if section.tag in _SECTIONS and section.first("base") is None
    ]


def _cors_findings(path: Path, root: Node) -> list[Finding]:
    """Report CORS policies that allow every origin."""
    return [
        _finding(
            path,
            origin.line,
            "cors-wildcard",
            "cors allows origin '*'; list explicit origins",
        )
        for cors in root.walk()
        if cors.tag == "cors"
        for origin in cors.walk()
        if origin.tag == "origin" and origin.text.strip() == "*"
    ]


def _fragments(root: Node) -> set[str]:
    """Return the ids of included policy fragments."""
    return {
        node.attrs.get("fragment-id", "")
        for node in root.walk()
        if node.tag == "include-fragment"
    }


def _has_quota(root: Node) -> bool:
    """Tell whether a call or token quota is configured."""
    return any(
        node.tag in _QUOTA_POLICIES
        or (node.tag in _TOKEN_POLICIES and "token-quota" in node.attrs)
        for node in root.walk()
    )


def _anchor(root: Node) -> int:
    """Return the line where a missing inbound policy should be reported."""
    inbound = root.first("inbound")
    return inbound.line if inbound is not None else root.line


def _api_findings(path: Path, root: Node, options: Options) -> list[Finding]:
    """Report missing limits and authentication on an API-scope policy."""
    tags = {node.tag for node in root.walk()}
    fragments = _fragments(root)
    limited = bool(fragments & options.limit_fragments)
    line = _anchor(root)
    findings: list[Finding] = []
    if options.require_rate_limit and not (tags & _RATE_POLICIES or limited):
        findings.append(
            _finding(
                path,
                line,
                "missing-rate-limit",
                "API policy has no rate-limit, rate-limit-by-key, or token limit",
            )
        )
    if options.require_quota and not (_has_quota(root) or limited):
        findings.append(
            _finding(
                path, line, "missing-quota", "API policy has no quota or token quota"
            )
        )
    authenticated = tags & _AUTH_POLICIES or fragments & options.auth_fragments
    if options.require_auth and not authenticated:
        findings.append(
            _finding(
                path,
                line,
                "missing-auth",
                "API policy has no validate-jwt, validate-azure-ad-token, "
                "or validate-client-certificate",
            )
        )
    return findings


def _jwt_findings(path: Path, root: Node) -> list[Finding]:
    """Report ``validate-jwt`` policies that weaken token validation."""
    findings: list[Finding] = []
    for node in root.walk():
        if node.tag != "validate-jwt":
            continue
        findings.extend(
            _finding(path, node.line, "weak-jwt", f"validate-jwt sets {name}=false")
            for name in ("require-signed-tokens", "require-expiration-time")
            if node.attrs.get(name, "true").strip().lower() == "false"
        )
        if node.first("audiences") is None:
            findings.append(
                _finding(path, node.line, "weak-jwt", "validate-jwt has no <audiences>")
            )
    return findings


def _is_reference(value: str) -> bool:
    """Tell whether a value is empty, an expression, or uses a named value."""
    stripped = value.strip()
    return not stripped or stripped.startswith("@") or "{{" in stripped


def _pattern_findings(path: Path, node: Node) -> list[Finding]:
    """Report secret-shaped literals in one element's attributes and text."""
    values = [*node.attrs.values(), node.text]
    return [
        _finding(path, node.line, "inline-secret", f"{label}; use a named value")
        for pattern, label in _SECRET_PATTERNS
        if any(pattern.search(value) for value in values)
    ]


def _structural_secret(path: Path, node: Node) -> Finding | None:
    """Report literal credentials in sensitive headers or password attributes."""
    if node.tag in _PASSWORD_POLICIES and not _is_reference(
        node.attrs.get("password", "")
    ):
        return _finding(
            path,
            node.line,
            "inline-secret",
            f"{node.tag} has a literal password; use a named value",
        )
    name = node.attrs.get("name", "").strip().lower()
    if node.tag not in _HEADER_POLICIES or name not in _SENSITIVE_NAMES:
        return None
    literal = [
        value
        for value in node.children
        if value.tag == "value" and not _is_reference(value.text)
    ]
    if not literal:
        return None
    return _finding(
        path,
        literal[0].line,
        "inline-secret",
        f"{node.tag} '{name}' has a literal value; use a named value",
    )


def _secret_findings(path: Path, root: Node) -> list[Finding]:
    """Report credentials written into the policy instead of named values."""
    findings: list[Finding] = []
    for node in root.walk():
        structural = _structural_secret(path, node)
        if structural is not None:
            findings.append(structural)
        findings.extend(_pattern_findings(path, node))
    return findings


def _missing_on_error(path: Path, root: Node, scope: str) -> list[Finding]:
    """Report a global policy that leaves error responses to the defaults."""
    if scope != "global":
        return []
    return [
        _finding(
            path,
            root.line,
            "on-error-status",
            "global policy has no <on-error>; callers get default error bodies",
        )
    ]


def _on_error_findings(path: Path, root: Node, scope: str) -> list[Finding]:
    """Report error handlers that cannot produce a deliberate status code."""
    on_error = root.first("on-error")
    if on_error is None:
        return _missing_on_error(path, root, scope)
    findings = [
        _finding(
            path,
            node.line,
            "on-error-status",
            "return-response has no set-status and would answer 200",
        )
        for node in on_error.walk()
        if node.tag == "return-response" and node.first("set-status") is None
    ]
    own = [child for child in on_error.children if child.tag != "base"]
    sets_status = any(node.tag == "set-status" for node in on_error.walk())
    if (own or scope == "global") and not sets_status:
        findings.append(
            _finding(
                path,
                on_error.line,
                "on-error-status",
                "on-error has no set-status",
            )
        )
    return findings


def scan_text(path: Path, text: str, options: Options) -> list[Finding]:
    """Check one policy document and return its findings in line order.

    Args:
        path: Path reported in findings and used for scope detection.
        text: Policy XML.
        options: Expectations for this run.

    Returns:
        Findings sorted by line, rule, and message, without disabled rules.

    Raises:
        PolicyXmlError: If the XML is malformed or not a policy document.
    """
    root = parse(text)
    scope = scope_for(path, options.scope)
    findings = _cors_findings(path, root)
    findings.extend(_jwt_findings(path, root))
    findings.extend(_secret_findings(path, root))
    if root.tag == "policies":
        if scope != "global":
            findings.extend(_base_findings(path, root))
        if scope == "api":
            findings.extend(_api_findings(path, root, options))
        findings.extend(_on_error_findings(path, root, scope))
    kept = [item for item in findings if item.rule not in options.disabled]
    return sorted(kept, key=lambda item: (item.line, item.rule, item.message))


def collect_files(paths: Iterable[Path]) -> list[Path]:
    """Expand directories into sorted policy files.

    Args:
        paths: Files or directories. Directories contribute files ending in
            ``.xml`` or ``.xml.template``.

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
                if candidate.is_file() and candidate.name.endswith(_POLICY_SUFFIXES)
            )
        elif path.is_file():
            files.add(path)
        else:
            raise MissingPathError(path=path)
    return sorted(files)


_CLEAN_API = """<policies>
  <inbound>
    <base />
    <cors>
      <allowed-origins><origin>https://shop.example.com</origin></allowed-origins>
    </cors>
    <validate-jwt header-name="Authorization">
      <openid-config url="{{jwt-openid-config-url}}" />
      <audiences><audience>{{orders-api-audience}}</audience></audiences>
    </validate-jwt>
    <rate-limit-by-key calls="60" renewal-period="60"
      counter-key="@(context.Subscription.Id)" />
    <set-header name="X-Api-Key" exists-action="override">
      <value>{{backend-key}}</value>
    </set-header>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
"""
_RISKY_API = """<policies>
  <inbound>
    <cors><allowed-origins><origin>*</origin></allowed-origins></cors>
    <validate-jwt header-name="Authorization" require-signed-tokens="false" />
    <set-header name="Authorization" exists-action="override">
      <value>Bearer abcdefghijklmnopqrstuvwxyz012345</value>
    </set-header>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error>
    <base />
    <set-header name="X-Error" exists-action="override"><value>failed</value></set-header>
  </on-error>
</policies>
"""
_SELF_EXPECTATIONS = {
    "missing base": "risky-api.xml:2: [missing-base] <inbound>",
    "missing rate limit": "risky-api.xml:2: [missing-rate-limit]",
    "wildcard origin": "risky-api.xml:3: [cors-wildcard]",
    "unsigned tokens": "risky-api.xml:4: [weak-jwt] validate-jwt sets require-signed",
    "no audiences": "risky-api.xml:4: [weak-jwt] validate-jwt has no <audiences>",
    "bearer literal": "risky-api.xml:6: [inline-secret] literal bearer token",
    "sensitive header": "risky-api.xml:6: [inline-secret] set-header 'authorization'",
    "error status": "risky-api.xml:11: [on-error-status] on-error has no set-status",
}


def self_test() -> list[str]:
    """Check every rule on in-memory documents and return unmet expectations.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    failures: list[str] = []
    strict = Options(require_auth=True)
    if scan_text(Path("clean-api.xml"), _CLEAN_API, strict):
        failures.append("clean API policy produced findings")
    risky = scan_text(Path("risky-api.xml"), _RISKY_API, strict)
    rendered = "\n".join(item.render() for item in risky)
    failures.extend(
        f"expected {label}: {needle!r}"
        for label, needle in _SELF_EXPECTATIONS.items()
        if needle not in rendered
    )
    if "[missing-auth]" in rendered:
        failures.append("validate-jwt did not satisfy --require-auth")
    global_doc = "<policies><inbound /><outbound /></policies>"
    if not scan_text(Path("global.xml"), global_doc, Options()):
        failures.append("global policy without on-error was accepted")
    for bad in ("<!DOCTYPE p [<!ENTITY a 'x'>]><policies />", "<policies>", "<p />"):
        try:
            parse(bad)
        except PolicyXmlError:
            continue
        failures.append(f"invalid document was accepted: {bad!r}")
    return failures


def _run_self_test() -> int:
    """Run the self-test, print its outcome, and return the exit status."""
    failures = self_test()
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return _FINDINGS
    sys.stdout.write("check_apim_policy self-test passed.\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, help="policy XML files or directories"
    )
    parser.add_argument(
        "--scope",
        choices=("auto", *_SCOPES),
        default="auto",
        help="policy scope of every file; 'auto' derives it from the file name",
    )
    parser.add_argument(
        "--require-auth", action="store_true", help="require auth at API scope"
    )
    parser.add_argument(
        "--no-require-rate-limit",
        dest="require_rate_limit",
        action="store_false",
        help="do not require a rate limit at API scope",
    )
    parser.add_argument(
        "--require-quota", action="store_true", help="require a quota at API scope"
    )
    parser.add_argument(
        "--limit-fragment",
        action="append",
        default=[],
        metavar="ID",
        help="fragment id that provides limits (repeatable)",
    )
    parser.add_argument(
        "--auth-fragment",
        action="append",
        default=[],
        metavar="ID",
        help="fragment id that provides authentication (repeatable)",
    )
    parser.add_argument(
        "--disable",
        action="append",
        default=[],
        choices=RULES,
        metavar="RULE",
        help=f"skip a rule (repeatable): {', '.join(RULES)}",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def _options(args: argparse.Namespace) -> Options:
    """Translate parsed arguments into ``Options``."""
    return Options(
        scope=args.scope,
        require_auth=args.require_auth,
        require_rate_limit=args.require_rate_limit,
        require_quota=args.require_quota,
        limit_fragments=frozenset(args.limit_fragment),
        auth_fragments=frozenset(args.auth_fragment),
        disabled=frozenset(args.disable),
    )


def _scan_files(files: Sequence[Path], options: Options) -> list[Finding]:
    """Check every file and collect findings.

    Raises:
        InvalidPolicyFileError: A file is not a well-formed policy document.
    """
    findings: list[Finding] = []
    for path in files:
        try:
            findings.extend(scan_text(path, path.read_text(encoding="utf-8"), options))
        except PolicyXmlError as error:
            raise InvalidPolicyFileError(path=path, error=error) from error
    return findings


def _scan(paths: Sequence[Path], options: Options) -> int:
    """Scan files, print findings, and return the exit status."""
    try:
        files = collect_files(paths)
        findings = _scan_files(files, options)
    except (OSError, UnicodeError, ValueError) as error:
        sys.stderr.write(f"Cannot check policies: {error}\n")
        return _INVALID
    for finding in findings:
        sys.stdout.write(f"{finding.render()}\n")
    if findings:
        sys.stderr.write(f"{len(findings)} finding(s) in {len(files)} file(s)\n")
        return _FINDINGS
    sys.stdout.write(f"No findings in {len(files)} file(s).\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Check API Management policy files and print one line per finding.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when clean, 1 with findings (or a failed self-test), 2 for missing
        paths or unreadable or unparsable input.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return _run_self_test()
    if not args.paths:
        parser.error("at least one path is required unless --self-test is given")
    return _scan(args.paths, _options(args))


if __name__ == "__main__":
    raise SystemExit(main())
