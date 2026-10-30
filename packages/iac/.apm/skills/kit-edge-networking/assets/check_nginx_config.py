# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Flag risky nginx reverse-proxy settings with a small block parser.

Each file is parsed on its own (``include`` is not followed) and every finding is
printed as ``path:line: message``:

- ``ssl_protocols`` enabling ``SSLv2``, ``SSLv3``, ``TLSv1``, or ``TLSv1.1``;
- ``server_tokens on`` or ``build``, and an ``http`` block that does not set
  ``server_tokens off`` directly (nginx defaults to ``on``);
- a ``location`` with ``proxy_pass`` whose effective ``proxy_set_header`` list
  lacks ``X-Forwarded-Proto`` or ``Forwarded``; nginx inherits
  ``proxy_set_header`` only when a level defines none of its own;
- a ``server`` block that proxies but has no ``client_max_body_size`` in itself
  or an enclosing block (the implicit default is 1 MiB);
- a streaming ``location`` whose effective ``proxy_buffering`` is not ``off``;
- an ``upstream`` without ``keepalive`` that a location reaches with
  ``proxy_http_version 1.1`` (or 2), so every request opens a new connection;
- a proxied ``location`` with an effective ``proxy_cache`` for requests that
  carry credentials (``proxy_set_header`` of ``Authorization``,
  ``Proxy-Authorization``, or ``Cookie``, an ``auth_basic``, ``auth_request``,
  or ``auth_jwt`` directive, or a ``# edge:authenticated`` comment) without both
  ``proxy_no_cache`` and ``proxy_cache_bypass``;
- a ``limit_req_zone`` or ``limit_conn_zone`` that no ``limit_req`` or
  ``limit_conn`` directive in the file uses. This rule is skipped when the file
  includes other files (except ``mime.types``), because the zone may be used
  there.

A location is streaming when its path has a segment named ``sse``, ``stream``,
``streams``, ``events``, or ``event-stream``, or when a comment ``# edge:stream``
appears directly inside its block. Blocks under ``stream`` and ``mail`` are
ignored. Embedded code blocks such as ``*_by_lua_block`` are not supported.

Exit codes: 0 clean, 1 findings, 2 unreadable or unparsable input.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_FINDINGS = 1
_INVALID = 2
_TOKEN = re.compile(
    r"""(?P<space>\s+)"""
    r"""|(?P<comment>\#[^\n]*)"""
    r"""|(?P<punct>[{};])"""
    r"""|(?P<word>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'"""
    r"""|(?:\$\{[^}\s]*\}|[^\s{};"'#])(?:\$\{[^}\s]*\}|[^\s{};])*)"""
)
_LEGACY_PROTOCOLS = frozenset({"SSLv2", "SSLv3", "TLSv1", "TLSv1.1"})
_LEAKY_TOKENS = frozenset({"on", "build"})
_PROTO_HEADERS = frozenset({"x-forwarded-proto", "forwarded"})
_IGNORED_CONTEXTS = frozenset({"stream", "mail"})
_STREAM_PATH = re.compile(
    r"(?i)(?:^|/)(?:sse|streams?|events|event-stream)(?=/|$|[^\w-])"
)
_STREAM_MARKER = re.compile(r"#\s*edge:\s*stream\b")
_AUTH_MARKER = re.compile(r"#\s*edge:\s*authenticated\b")
_CREDENTIAL_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie"})
_AUTH_DIRECTIVES = ("auth_basic", "auth_request", "auth_jwt")
_CACHE_SKIPS = ("proxy_no_cache", "proxy_cache_bypass")
_KEEPALIVE_VERSIONS = frozenset({"1.1", "2"})
_ZONE_USERS = {"limit_req_zone": "limit_req", "limit_conn_zone": "limit_conn"}
_CONFIG_SUFFIXES = (".conf", ".conf.template")


class NginxConfigError(ValueError):
    """The configuration text cannot be parsed into blocks and directives."""

    def __init__(self, *, line: int, problem: str) -> None:
        """Describe the syntax problem.

        Args:
            line: One-based line where parsing failed.
            problem: Short description of the problem.
        """
        super().__init__(f"line {line}: {problem}")


@dataclass(frozen=True, kw_only=True, slots=True)
class Token:
    """One lexical element of an nginx configuration.

    Attributes:
        kind: ``comment``, ``punct``, or ``word``.
        text: Raw token text.
        line: One-based line number.
    """

    kind: str
    text: str
    line: int


@dataclass(frozen=True, kw_only=True, slots=True)
class Directive:
    """A simple ``name args;`` directive.

    Attributes:
        name: Directive name.
        args: Arguments with surrounding quotes removed.
        line: One-based line number of the name.
    """

    name: str
    args: tuple[str, ...]
    line: int


@dataclass(frozen=True, kw_only=True, slots=True)
class Block:
    """A ``name args { ... }`` block, or the file's main context.

    Attributes:
        name: Block name; empty for the main context.
        args: Block arguments, such as a location path.
        line: One-based line number of the block name.
        directives: Simple directives directly inside the block.
        children: Nested blocks in source order.
        comments: Comments directly inside the block.
    """

    name: str
    args: tuple[str, ...]
    line: int
    directives: tuple[Directive, ...]
    children: tuple[Block, ...]
    comments: tuple[str, ...]

    def named(self, name: str) -> list[Directive]:
        """Return the directives called ``name`` directly inside this block.

        Args:
            name: Directive name to match.

        Returns:
            Matching directives in source order.
        """
        return [directive for directive in self.directives if directive.name == name]


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One reportable configuration problem.

    Attributes:
        path: File that contains the problem.
        line: One-based line number.
        message: Human-readable explanation.
    """

    path: Path
    line: int
    message: str

    def render(self) -> str:
        """Return the deterministic ``path:line: message`` form."""
        return f"{self.path.as_posix()}:{self.line}: {self.message}"


def tokenize(text: str) -> list[Token]:
    """Split configuration text into comments, punctuation, and words.

    Args:
        text: Complete configuration text.

    Returns:
        Tokens in source order without whitespace.

    Raises:
        NginxConfigError: If a quoted string is not terminated.
    """
    tokens: list[Token] = []
    position = 0
    line = 1
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None:
            raise NginxConfigError(line=line, problem="unterminated quoted string")
        kind = match.lastgroup or "space"
        if kind != "space":
            tokens.append(Token(kind=kind, text=match.group(), line=line))
        line += match.group().count("\n")
        position = match.end()
    return tokens


def _unquote(text: str) -> str:
    """Remove one pair of matching quotes around a word."""
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _directive(words: Sequence[Token], terminator: Token) -> Directive:
    """Build a directive from collected words or report a missing name.

    Raises:
        NginxConfigError: A terminator has no directive name.
    """
    if not words:
        raise NginxConfigError(
            line=terminator.line,
            problem=f"'{terminator.text}' without a directive name",
        )
    return Directive(
        name=words[0].text,
        args=tuple(_unquote(word.text) for word in words[1:]),
        line=words[0].line,
    )


def _require_terminated(words: Sequence[Token]) -> None:
    """Reject words left over before a closing brace or the end of input.

    Raises:
        NginxConfigError: A directive is missing ``;``.
    """
    if words:
        raise NginxConfigError(
            line=words[0].line, problem=f"directive '{words[0].text}' is missing ';'"
        )


def _parse_block(
    tokens: Sequence[Token], start: int, header: Directive | None
) -> tuple[Block, int]:
    """Parse tokens from ``start`` until the closing brace of ``header``.

    Args:
        tokens: All tokens of the file.
        start: Index of the first token inside the block.
        header: Name and arguments of the block; None for the main context.

    Returns:
        The parsed block and the index after its closing brace.

    Raises:
        NginxConfigError: If braces or semicolons are unbalanced.
    """
    directives: list[Directive] = []
    children: list[Block] = []
    comments: list[str] = []
    words: list[Token] = []
    index = start
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token.text == "}":
            return _close(header, token, words, (directives, children, comments)), index
        if token.text == "{":
            child, index = _parse_block(tokens, index, _directive(words, token))
            children.append(child)
            words.clear()
            continue
        _collect(token, words=words, directives=directives, comments=comments)
    if header is not None:
        raise NginxConfigError(
            line=header.line, problem=f"block '{header.name}' is not closed"
        )
    _require_terminated(words)
    main = Directive(name="", args=(), line=1)
    return _block(main, directives, children, comments), index


def _collect(
    token: Token,
    *,
    words: list[Token],
    directives: list[Directive],
    comments: list[str],
) -> None:
    """Add a comment, word, or completed directive to the open block."""
    if token.kind == "comment":
        comments.append(token.text)
    elif token.kind == "word":
        words.append(token)
    else:
        directives.append(_directive(words, token))
        words.clear()


def _close(
    header: Directive | None,
    token: Token,
    words: Sequence[Token],
    parts: tuple[list[Directive], list[Block], list[str]],
) -> Block:
    """Finish the open block at a closing brace.

    Raises:
        NginxConfigError: The brace closes no open block.
    """
    if header is None:
        raise NginxConfigError(line=token.line, problem="unexpected '}'")
    _require_terminated(words)
    directives, children, comments = parts
    return _block(header, directives, children, comments)


def _block(
    header: Directive,
    directives: Sequence[Directive],
    children: Sequence[Block],
    comments: Sequence[str],
) -> Block:
    """Freeze the parts collected for one block."""
    return Block(
        name=header.name,
        args=header.args,
        line=header.line,
        directives=tuple(directives),
        children=tuple(children),
        comments=tuple(comments),
    )


def parse(text: str) -> Block:
    """Parse configuration text into its main-context block.

    Args:
        text: Complete configuration text.

    Returns:
        The main context with nested blocks.

    Raises:
        NginxConfigError: If the text is not well-formed nginx syntax.
    """
    block, _ = _parse_block(tokenize(text), 0, None)
    return block


def _walk(
    block: Block, ancestors: tuple[Block, ...]
) -> Iterable[tuple[Block, tuple[Block, ...]]]:
    """Yield every block with its chain from the main context to itself."""
    chain = (*ancestors, block)
    yield block, chain
    for child in block.children:
        yield from _walk(child, chain)


def _effective(chain: Sequence[Block], name: str) -> list[Directive]:
    """Return the directives that apply at the end of ``chain`` by inheritance.

    nginx takes array and scalar directives from the nearest level that
    defines any of them; a level never merges with its parent.
    """
    for block in reversed(chain):
        found = block.named(name)
        if found:
            return found
    return []


def _header_names(directives: Iterable[Directive]) -> set[str]:
    """Return lower-cased header names set by ``proxy_set_header`` directives."""
    return {directive.args[0].lower() for directive in directives if directive.args}


def _directive_findings(path: Path, block: Block) -> list[Finding]:
    """Report legacy TLS protocols and version disclosure in one block."""
    findings: list[Finding] = []
    for directive in block.directives:
        if directive.name == "ssl_protocols":
            legacy = [arg for arg in directive.args if arg in _LEGACY_PROTOCOLS]
            if legacy:
                findings.append(
                    Finding(
                        path=path,
                        line=directive.line,
                        message=(
                            f"ssl_protocols enables {', '.join(legacy)}; "
                            "allow only TLSv1.2 and TLSv1.3"
                        ),
                    )
                )
        elif (
            directive.name == "server_tokens"
            and directive.args
            and directive.args[0].lower() in _LEAKY_TOKENS
        ):
            findings.append(
                Finding(
                    path=path,
                    line=directive.line,
                    message=(
                        f"server_tokens {directive.args[0]} discloses the nginx "
                        "version; set 'server_tokens off'"
                    ),
                )
            )
    return findings


def _http_findings(path: Path, block: Block) -> list[Finding]:
    """Report an ``http`` block that leaves ``server_tokens`` at its default."""
    if block.named("server_tokens"):
        return []
    return [
        Finding(
            path=path,
            line=block.line,
            message="http block does not set 'server_tokens off' (default is on)",
        )
    ]


def _server_findings(path: Path, chain: Sequence[Block]) -> list[Finding]:
    """Report a proxying ``server`` without an explicit request body limit."""
    server = chain[-1]
    proxies = any(block.named("proxy_pass") for block, _ in _walk(server, ()))
    if not proxies or _effective(chain, "client_max_body_size"):
        return []
    return [
        Finding(
            path=path,
            line=server.line,
            message=(
                "proxying server has no 'client_max_body_size'; set an explicit "
                "request body limit (nginx default is 1m)"
            ),
        )
    ]


def _is_streaming(location: Block, route: str) -> bool:
    """Tell whether a location serves a stream by path segment or marker."""
    marked = any(_STREAM_MARKER.match(comment) for comment in location.comments)
    return marked or _STREAM_PATH.search(route) is not None


def _forwarded_proto_finding(
    path: Path, chain: Sequence[Block], route: str
) -> Finding | None:
    """Report a proxied location that does not forward the original scheme."""
    location = chain[-1]
    if _header_names(_effective(chain, "proxy_set_header")) & _PROTO_HEADERS:
        return None
    message = f"location '{route}' proxies without 'proxy_set_header X-Forwarded-Proto'"
    inherited = _header_names(_effective(chain[:-1], "proxy_set_header"))
    if location.named("proxy_set_header") and inherited & _PROTO_HEADERS:
        message += "; its own proxy_set_header list replaces the inherited one"
    return Finding(path=path, line=location.line, message=message)


def _buffering_finding(
    path: Path, chain: Sequence[Block], route: str
) -> Finding | None:
    """Report a streaming location unless response buffering is off."""
    buffering = _effective(chain, "proxy_buffering")
    value = buffering[0].args[0].lower() if buffering and buffering[0].args else "on"
    if value == "off":
        return None
    return Finding(
        path=path,
        line=buffering[0].line if buffering else chain[-1].line,
        message=(
            f"streaming location '{route}' needs 'proxy_buffering off' "
            f"(effective value is '{value}')"
        ),
    )


def _credential_signals(chain: Sequence[Block]) -> list[str]:
    """Return the reasons a proxied location receives credential-bearing requests.

    Args:
        chain: Blocks from the main context to the location.

    Returns:
        Short descriptions such as ``proxy_set_header authorization``.
    """
    headers = _header_names(_effective(chain, "proxy_set_header"))
    signals = [
        f"proxy_set_header {name}" for name in sorted(headers & _CREDENTIAL_HEADERS)
    ]
    for name in _AUTH_DIRECTIVES:
        found = _effective(chain, name)
        if found and found[0].args and found[0].args[0].lower() != "off":
            signals.append(name)
    if any(_AUTH_MARKER.match(comment) for comment in chain[-1].comments):
        signals.append("# edge:authenticated")
    return signals


def _cache_finding(path: Path, chain: Sequence[Block], route: str) -> Finding | None:
    """Report a cached location that may store responses to authenticated requests.

    Args:
        path: File that contains the location.
        chain: Blocks from the main context to the location.
        route: Location path used in the message.

    Returns:
        A finding, or None when caching is off, no credentials are involved, or
        both ``proxy_no_cache`` and ``proxy_cache_bypass`` apply.
    """
    cache = _effective(chain, "proxy_cache")
    if not cache or not cache[0].args or cache[0].args[0].lower() == "off":
        return None
    signals = _credential_signals(chain)
    missing = [name for name in _CACHE_SKIPS if not _effective(chain, name)]
    if not signals or not missing:
        return None
    return Finding(
        path=path,
        line=chain[-1].line,
        message=(
            f"location '{route}' caches responses (proxy_cache {cache[0].args[0]}) "
            f"for requests with credentials ({', '.join(signals)}) without "
            f"{' and '.join(repr(name) for name in missing)}; skip the cache for "
            "credential-bearing requests"
        ),
    )


def _location_findings(path: Path, chain: Sequence[Block]) -> list[Finding]:
    """Report forwarded-header, buffering, and cache problems for a proxied location."""
    location = chain[-1]
    if not location.named("proxy_pass"):
        return []
    route = location.args[-1] if location.args else ""
    findings: list[Finding] = []
    proto = _forwarded_proto_finding(path, chain, route)
    if proto is not None:
        findings.append(proto)
    if _is_streaming(location, route):
        buffering = _buffering_finding(path, chain, route)
        if buffering is not None:
            findings.append(buffering)
    cache = _cache_finding(path, chain, route)
    if cache is not None:
        findings.append(cache)
    return findings


def _upstream_name(target: str) -> str:
    """Return the host part of a ``proxy_pass`` URL without scheme, port, or path.

    Args:
        target: First argument of ``proxy_pass``.

    Returns:
        The host or upstream group name; empty when the URL has no scheme.
    """
    _, _, rest = target.partition("://")
    return re.split(r"[/:]", rest, maxsplit=1)[0]


def _has_keepalive(upstream: Block) -> bool:
    """Tell whether an upstream block keeps idle connections open."""
    return any(
        directive.args and directive.args[0] != "0"
        for directive in upstream.named("keepalive")
    )


def _keepalive_findings(
    path: Path, blocks: Sequence[tuple[Block, tuple[Block, ...]]]
) -> list[Finding]:
    """Report upstream groups reached over HTTP/1.1 or 2 without ``keepalive``.

    Args:
        path: File that contains the blocks.
        blocks: Checked blocks with their chains.

    Returns:
        At most one finding per upstream group, at the group's line.
    """
    upstreams = {
        block.args[0]: block
        for block, _ in blocks
        if block.name == "upstream" and block.args
    }
    reported: dict[str, Finding] = {}
    for block, chain in blocks:
        for directive in block.named("proxy_pass"):
            name = _upstream_name(directive.args[0]) if directive.args else ""
            upstream = upstreams.get(name)
            if upstream is None or name in reported or _has_keepalive(upstream):
                continue
            version = _effective(chain, "proxy_http_version")
            if not version or not version[0].args:
                continue
            if version[0].args[0] not in _KEEPALIVE_VERSIONS:
                continue
            reported[name] = Finding(
                path=path,
                line=upstream.line,
                message=(
                    f"upstream '{name}' has no 'keepalive' although line "
                    f"{directive.line} proxies to it with proxy_http_version "
                    f"{version[0].args[0]}; add 'keepalive <connections>' so "
                    "upstream connections are reused (implicit only from nginx 1.29.7)"
                ),
            )
    return list(reported.values())


def _zone_name(args: Sequence[str]) -> str:
    """Return the zone name from a ``zone=name[:size]`` argument, or empty."""
    for arg in args:
        if arg.startswith("zone="):
            return arg.removeprefix("zone=").split(":", 1)[0]
    return ""


def _zone_findings(
    path: Path, blocks: Sequence[tuple[Block, tuple[Block, ...]]]
) -> list[Finding]:
    """Report rate and connection limit zones that nothing in the file applies.

    Args:
        path: File that contains the blocks.
        blocks: Checked blocks with their chains.

    Returns:
        One finding per unused zone; none when the file includes other files.
    """
    directives = [directive for block, _ in blocks for directive in block.directives]
    if any(
        directive.name == "include"
        and directive.args
        and not directive.args[0].endswith("mime.types")
        for directive in directives
    ):
        return []
    used = {
        ("limit_req", _zone_name(directive.args))
        for directive in directives
        if directive.name == "limit_req"
    } | {
        ("limit_conn", directive.args[0])
        for directive in directives
        if directive.name == "limit_conn" and directive.args
    }
    findings: list[Finding] = []
    for directive in directives:
        user = _ZONE_USERS.get(directive.name)
        name = _zone_name(directive.args)
        if user is None or not name or (user, name) in used:
            continue
        findings.append(
            Finding(
                path=path,
                line=directive.line,
                message=(
                    f"{directive.name} zone '{name}' is not used by any '{user}' "
                    "directive in this file; apply it or remove it"
                ),
            )
        )
    return findings


def scan_text(path: Path, text: str) -> list[Finding]:
    """Check one configuration file and return its findings in line order.

    Args:
        path: Path reported in findings.
        text: File content.

    Returns:
        Findings sorted by line number and message.

    Raises:
        NginxConfigError: If the text is not well-formed nginx syntax.
    """
    blocks = [
        (block, chain)
        for block, chain in _walk(parse(text), ())
        if not any(item.name in _IGNORED_CONTEXTS for item in chain)
    ]
    findings: list[Finding] = []
    for block, chain in blocks:
        findings.extend(_directive_findings(path, block))
        if block.name == "http":
            findings.extend(_http_findings(path, block))
        elif block.name == "server":
            findings.extend(_server_findings(path, chain))
        elif block.name == "location":
            findings.extend(_location_findings(path, chain))
    findings.extend(_keepalive_findings(path, blocks))
    findings.extend(_zone_findings(path, blocks))
    return sorted(findings, key=lambda finding: (finding.line, finding.message))


class MissingPathError(ValueError):
    """A path named on the command line does not exist."""

    def __init__(self, *, path: Path) -> None:
        """Describe the missing path.

        Args:
            path: The path that was not found.
        """
        super().__init__(f"path does not exist: {path}")


def collect_files(paths: Iterable[Path]) -> list[Path]:
    """Expand directories into sorted configuration files.

    Args:
        paths: Files or directories supplied by the operator. Directories
            contribute files ending in ``.conf`` or ``.conf.template``.

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
                if candidate.is_file() and candidate.name.endswith(_CONFIG_SUFFIXES)
            )
        elif path.is_file():
            files.add(path)
        else:
            raise MissingPathError(path=path)
    return sorted(files)


def self_test() -> list[str]:
    """Check the rules on in-memory configurations and return unmet expectations.

    Returns:
        Descriptions of failed expectations; empty when the checker works.
    """
    headers = "proxy_set_header X-Forwarded-Proto $scheme;\n"
    clean = (
        "http {\nserver_tokens off;\n"
        "limit_req_zone $binary_remote_addr zone=per_client:1m rate=5r/s;\n"
        "upstream app { server 127.0.0.1:8000; keepalive 8; }\n"
        "server {\nclient_max_body_size 10m;\n"
        f"{headers}ssl_protocols TLSv1.2 TLSv1.3;\n"
        "proxy_http_version 1.1;\nlimit_req zone=per_client;\n"
        "location / { proxy_pass http://app; }\n"
        "location /events/ { proxy_pass http://app; proxy_buffering off; }\n"
        "location /assets/ { proxy_pass http://app; proxy_cache edge; "
        'auth_basic "assets"; proxy_no_cache $http_authorization; '
        "proxy_cache_bypass $http_authorization; }\n"
        "}\n}\nstream {\nserver { proxy_pass db:5432; }\n}\n"
    )
    risky = (
        "http {\nserver {\nssl_protocols TLSv1 TLSv1.2;\nserver_tokens on;\n"
        "location / {\nproxy_pass http://app;\n}\n"
        "location /feed {\n# edge:stream\nproxy_pass http://app;\n"
        f"{headers}}}\n}}\n}}\n"
    )
    upstream = (
        "http {\nserver_tokens off;\n"
        "limit_req_zone $binary_remote_addr zone=unused:1m rate=1r/s;\n"
        "upstream app { server 127.0.0.1:8000; }\nserver {\n"
        "client_max_body_size 1m;\nproxy_http_version 1.1;\nlocation / {\n"
        "proxy_pass http://app;\nproxy_cache edge;\n"
        f"proxy_set_header Authorization $http_authorization;\n{headers}}}\n}}\n}}\n"
    )
    failures: list[str] = []
    if scan_text(Path("clean.conf"), clean):
        failures.append("clean configuration produced findings")
    rendered = "\n".join(
        item.render()
        for name, text in (("risky.conf", risky), ("upstream.conf", upstream))
        for item in scan_text(Path(name), text)
    )
    expectations = {
        "default server_tokens": "risky.conf:1: http block does not set",
        "legacy protocol": "risky.conf:3: ssl_protocols enables TLSv1;",
        "version disclosure": "risky.conf:4: server_tokens on",
        "missing body limit": "risky.conf:2: proxying server has no",
        "missing scheme header": "risky.conf:5: location '/' proxies without",
        "buffered stream": "risky.conf:8: streaming location '/feed'",
        "unused zone": "upstream.conf:3: limit_req_zone zone 'unused'",
        "upstream keepalive": "upstream.conf:4: upstream 'app' has no 'keepalive'",
        "authenticated cache": "upstream.conf:8: location '/' caches responses",
    }
    failures.extend(
        f"expected {label}: {needle!r}"
        for label, needle in expectations.items()
        if needle not in rendered
    )
    try:
        parse("http {\nserver {\n")
    except NginxConfigError:
        pass
    else:
        failures.append("unclosed block was accepted")
    return failures


def _run_self_test() -> int:
    """Run the self-test, print its outcome and return the exit status."""
    failures = self_test()
    for failure in failures:
        sys.stderr.write(f"{failure}\n")
    if failures:
        return _FINDINGS
    sys.stdout.write("check_nginx_config self-test passed.\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="nginx configuration files or directories to scan",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    return parser


def _scan(paths: Iterable[Path]) -> int:
    """Scan files, print findings, and return the exit status."""
    findings: list[Finding] = []
    try:
        files = collect_files(paths)
        for path in files:
            try:
                findings.extend(scan_text(path, path.read_text(encoding="utf-8")))
            except NginxConfigError as error:
                sys.stderr.write(f"Cannot check {path.as_posix()}: {error}\n")
                return _INVALID
    except (OSError, UnicodeError, ValueError) as error:
        sys.stderr.write(f"Cannot check nginx configuration: {error}\n")
        return _INVALID
    for finding in findings:
        sys.stdout.write(f"{finding.render()}\n")
    if findings:
        sys.stderr.write(f"{len(findings)} finding(s) in {len(files)} file(s)\n")
        return _FINDINGS
    sys.stdout.write(f"No findings in {len(files)} file(s).\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Check nginx files and print one ``path:line: message`` line per finding.

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
    return _scan(args.paths)


if __name__ == "__main__":
    raise SystemExit(main())
