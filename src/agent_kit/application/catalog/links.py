"""Own Markdown resource link checks and hidden-Unicode detection.

Links must stay inside their owning source root; external links are limited to
web addresses and, outside bundles, plain project contacts.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from posixpath import pardir
import re
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from agent_kit.application.catalog.schema import is_absolute
from agent_kit.application.findings import add_finding
from agent_kit.core.text import markdown_link_targets, visible_text

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Set as AbstractSet
    from urllib.parse import SplitResult

    from agent_kit.core.models import Finding, SourceDocument

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _unvisited_members(current: object, visited: set[int]) -> tuple[object, ...]:
    """Flatten an unseen dict or list into members, marking it visited; else ``()``."""
    if not isinstance(current, dict | list) or id(current) in visited:
        return ()
    visited.add(id(current))
    if isinstance(current, dict):
        return tuple(part for pair in current.items() for part in pair)
    return tuple(current)


def contains_hidden_unicode(value: object) -> bool:
    """Find unsupported format and control characters in decoded content."""
    pending: list[object] = [value]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, str) and not visible_text(current):
            return True
        pending.extend(_unvisited_members(current, visited))
    return False


def check_hidden_unicode(value: object, path: str, findings: list[Finding]) -> None:
    """Record a safe diagnostic without including the offending text."""
    if contains_hidden_unicode(value):
        add_finding(
            findings,
            "unicode.hidden",
            "source content contains unsupported hidden Unicode controls",
            path,
        )


def _is_project_contact(parsed: SplitResult) -> bool:
    """Accept a plain ``mailto:`` address without query, fragment, or escapes."""
    address = unquote(parsed.path)
    return (
        parsed.scheme.lower() == "mailto"
        and not parsed.netloc
        and not parsed.query
        and not parsed.fragment
        and parsed.path == address
        and _EMAIL.fullmatch(address) is not None
    )


def _external_link_allowed(parsed: SplitResult, *, base_is_bundle: bool) -> bool:
    """Allow web links everywhere and project contacts outside bundles."""
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return True
    return not base_is_bundle and _is_project_contact(parsed)


def _resolved_link(raw_path: str, document_path: str) -> str | None:
    """Resolve a link beside its document; ``None`` if it escapes the source root."""
    stack = list(PurePosixPath(document_path).parent.parts)
    # PurePosixPath already drops empty and current-directory segments.
    for part in PurePosixPath(raw_path).parts:
        if part != pardir:
            stack.append(part)
        elif stack:
            stack.pop()
        else:
            return None
    return "/".join(stack)


def link_index(available_paths: Iterable[str]) -> frozenset[str]:
    """Index every source path and ancestor directory once for link lookups."""
    index: set[str] = set()
    for path in available_paths:
        index.add(path)
        parent, separator, _ = path.rpartition("/")
        while separator and parent and parent not in index:
            index.add(parent)
            parent, separator, _ = parent.rpartition("/")
    return frozenset(index)


def _local_link_issue(
    raw_path: str, document_path: str, index: AbstractSet[str]
) -> tuple[str, str] | None:
    """Return ``(code, message)`` for an invalid link (case-sensitive) or ``None``."""
    if "\\" in raw_path:
        return "links.path", "resource link is not a portable path"
    target = None if is_absolute(raw_path) else _resolved_link(raw_path, document_path)
    if target is None:
        return "links.escape", "resource link escapes its source root"
    if target in index:
        return None
    return "links.missing", f"resource link target does not exist: {raw_path}"


def link_target(
    link: str,
    document_path: str,
    index: AbstractSet[str],
    findings: list[Finding],
    *,
    base_is_bundle: bool,
) -> None:
    """Verify a Markdown resource target stays in its owning source root."""
    parsed = urlsplit(link)
    if parsed.scheme or parsed.netloc:
        if not _external_link_allowed(parsed, base_is_bundle=base_is_bundle):
            add_finding(
                findings,
                "links.scheme",
                "unsupported external link or invalid project contact",
                document_path,
            )
        return
    raw_path = unquote(parsed.path)
    if not raw_path:
        return
    issue = _local_link_issue(raw_path, document_path, index)
    if issue is not None:
        code, message = issue
        add_finding(findings, code, message, document_path)


def check_links(
    document: SourceDocument,
    index: AbstractSet[str],
    findings: list[Finding],
    *,
    base_is_bundle: bool,
) -> None:
    """Check Markdown document links; skip templates and non-text documents."""
    text = document.text
    name = PurePosixPath(document.relative_path).name.casefold()
    markdown = PurePosixPath(name).suffix in {".md", ".markdown"} or name == "llms.txt"
    if text is None or not markdown or ".template." in name:
        return
    for link in markdown_link_targets(text):
        link_target(
            link,
            document.relative_path,
            index,
            findings,
            base_is_bundle=base_is_bundle,
        )


def is_markdown_source(relative_path: str) -> bool:
    """Select Markdown sources whose links are validated, excluding templates."""
    path = PurePosixPath(relative_path)
    return (
        path.suffix.lower() in {".md", ".markdown"}
        and ".template." not in path.name.casefold()
    )
