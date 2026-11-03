"""Pure checks for the hook and MCP declarations a source bundle may ship.

Both are executable capabilities. The schemas are closed: anything not named here
is rejected, so a bundle cannot gain a new launcher, option or credential path
without a reviewed change to this module.
"""

from collections.abc import Iterable
import json
from pathlib import PurePosixPath
import re
from typing import TypeGuard
from urllib.parse import urlsplit

from agent_kit.core.guards import JsonObject, is_int, is_json_object, is_str_list

_MCP_FIELDS = frozenset(
    {"name", "registry", "transport", "url", "command", "args", "headers"}
)
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})
_HEADER_NAME = re.compile(r"X-MCP-[A-Za-z0-9-]+\Z")
_HEADER_VALUE = re.compile(r"[A-Za-z0-9_,.-]{1,128}\Z")
_PLAIN_ARGUMENT = re.compile(r"[A-Za-z0-9_@./:=,+-]{1,200}\Z")
_PACKAGE = re.compile(r"(?:@[a-z0-9][a-z0-9-]*/)?[a-z0-9][a-z0-9._-]*@\d+\.\d+\.\d+\Z")
_IMAGE = re.compile(r"[a-z0-9][a-z0-9./_-]*:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}\Z")
_DOCKER_PREFIX = ["run", "-i", "--rm"]
_DOCKER_IMAGE_INDEX = len(_DOCKER_PREFIX)
_BUNX_PREFIX_LENGTH = 2  # --bun, then package@version
_HOOK_EVENTS = frozenset({"preToolUse"})
_HOOK_FIELDS = frozenset({"type", "bash", "powershell", "timeoutSec"})
_BASH_COMMAND = re.compile(r"python3 \./scripts/([a-z][a-z0-9_]*\.py)\Z")
_POWERSHELL_COMMAND = re.compile(r"python \./scripts/([a-z][a-z0-9_]*\.py)\Z")
_MAX_HOOK_TIMEOUT_SECONDS = 30
_SCRIPT_SUFFIXES = frozenset({".py", ".policy"})


def mcp_issues(entries: object, *, allowed: Iterable[str]) -> list[str]:
    """Report every defect in a bundle's ``dependencies.mcp`` list.

    Args:
        entries (object): Decoded ``dependencies.mcp`` value.
        allowed (Iterable[str]): Policy-approved server names.

    Returns:
        list[str]: Safe validation messages in declaration order, followed by any
        duplicate-name finding. Empty when valid; declared values are never echoed.
    """
    if not isinstance(entries, list) or not entries:
        return ["mcp must be a non-empty list of server declarations"]
    permitted = frozenset(allowed)
    issues = [
        issue
        for index, entry in enumerate(entries)
        for issue in _entry_issues(entry, f"mcp[{index}]", permitted)
    ]
    names = [
        entry["name"]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    ]
    if len(names) != len(set(names)):
        issues.append("mcp server names must be unique")
    return issues


def _entry_issues(entry: object, label: str, permitted: frozenset[str]) -> list[str]:
    """Validate one MCP declaration against the closed schema.

    Args:
        entry (object): Decoded declaration.
        label (str): Safe location prefix for messages.
        permitted (frozenset[str]): Policy-approved server names.

    Returns:
        list[str]: Safe messages; empty when the declaration is valid.
    """
    if not isinstance(entry, dict):
        return [f"{label} must be an object"]
    issues = [
        f"{label} has an unknown field"
        for key in sorted(entry.keys() - _MCP_FIELDS, key=str)
    ]
    name = entry.get("name")
    if not isinstance(name, str) or name not in permitted:
        issues.append(f"{label}.name is not a policy-approved server")
    if entry.get("registry") is not False:
        issues.append(f"{label}.registry must be false; servers are declared in place")
    transport = entry.get("transport")
    if transport == "http":
        issues.extend(_http_issues(entry, label))
    elif transport == "stdio":
        issues.extend(_stdio_issues(entry, label))
    else:
        issues.append(f"{label}.transport must be http or stdio")
    return issues


def _http_issues(entry: dict[object, object], label: str) -> list[str]:
    """Validate a remote or loopback HTTP server declaration.

    Args:
        entry (dict[object, object]): Declaration whose transport is ``http``.
        label (str): Safe location prefix for messages.

    Returns:
        list[str]: Safe messages; empty when the declaration is valid.
    """
    issues = [
        f"{label}.{key} is not allowed for an http server"
        for key in ("command", "args")
        if key in entry
    ]
    issues.extend(_url_issues(entry.get("url"), label))
    issues.extend(_header_issues(entry.get("headers", {}), label))
    return issues


def _url_issues(url: object, label: str) -> list[str]:
    """Require https, or loopback http, without credentials or query data.

    Args:
        url (object): Decoded ``url`` value.
        label (str): Safe location prefix for messages.

    Returns:
        list[str]: Safe messages; empty when the URL is acceptable.
    """
    if not isinstance(url, str):
        return [f"{label}.url must be text"]
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        return [f"{label}.url is not a valid URL"]
    issues: list[str] = []
    loopback = parts.scheme == "http" and hostname in _LOOPBACK_HOSTS
    if parts.scheme != "https" and not loopback:
        issues.append(f"{label}.url must use https, or http only for localhost")
    if not hostname or any(character.isspace() for character in url) or port == 0:
        issues.append(f"{label}.url must name a valid host and port")
    if parts.username or parts.password or parts.query or parts.fragment:
        issues.append(f"{label}.url must not carry credentials, a query or a fragment")
    return issues


def _header_issues(headers: object, label: str) -> list[str]:
    """Allow only ``X-MCP-*`` options; credentials are never declared in source.

    Args:
        headers (object): Decoded ``headers`` value.
        label (str): Safe location prefix for messages.

    Returns:
        list[str]: Safe messages; empty when every header is acceptable.
    """
    if not isinstance(headers, dict):
        return [f"{label}.headers must be an object"]
    issues: list[str] = []
    for name, value in headers.items():
        if not isinstance(name, str) or _HEADER_NAME.fullmatch(name) is None:
            issues.append(f"{label}.headers may only set X-MCP-* options")
        if not isinstance(value, str) or _HEADER_VALUE.fullmatch(value) is None:
            issues.append(f"{label}.headers values must be short plain text")
    return issues


def _stdio_issues(entry: dict[object, object], label: str) -> list[str]:
    """Validate a locally launched server: a pinned package or a digested image.

    Args:
        entry (dict[object, object]): Declaration whose transport is ``stdio``.
        label (str): Safe location prefix for messages.

    Returns:
        list[str]: Safe messages; empty when the declaration is valid.
    """
    issues = [
        f"{label}.{key} is not allowed for a stdio server"
        for key in ("url", "headers")
        if key in entry
    ]
    command = entry.get("command")
    args = entry.get("args")
    if not isinstance(command, str) or command not in {"bunx", "docker"}:
        issues.append(f"{label}.command must be bunx or docker")
    if not _plain_arguments(args):
        issues.append(f"{label}.args must be plain arguments and never use latest")
        return issues
    if command == "bunx":
        issues.extend(_bunx_issues(args, label))
    elif command == "docker":
        issues.extend(_docker_issues(args, label))
    return issues


def _plain_arguments(args: object) -> TypeGuard[list[str]]:
    """Check for a non-empty list of shell-inert arguments without ``latest``."""
    return (
        is_str_list(args)
        and bool(args)
        and all(
            _PLAIN_ARGUMENT.fullmatch(item) is not None and "latest" not in item
            for item in args
        )
    )


def _bunx_issues(args: list[str], label: str) -> list[str]:
    """Require ``--bun`` and one exact package version before any server option.

    Args:
        args (list[str]): Validated plain arguments of a ``bunx`` server.
        label (str): Safe location prefix for messages.

    Returns:
        list[str]: One message when the prefix is wrong; empty otherwise.
    """
    if (
        len(args) < _BUNX_PREFIX_LENGTH
        or args[0] != "--bun"
        or _PACKAGE.fullmatch(args[1]) is None
    ):
        return [f"{label}.args must start with --bun and an exact package@version"]
    return []


def _docker_issues(args: list[str], label: str) -> list[str]:
    """Require ``run -i --rm`` and an image pinned by digest, with no other options.

    Args:
        args (list[str]): Validated plain arguments of a ``docker`` server.
        label (str): Safe location prefix for messages.

    Returns:
        list[str]: One message when the prefix or image is wrong; empty otherwise.
    """
    if (
        args[:_DOCKER_IMAGE_INDEX] != _DOCKER_PREFIX
        or len(args) <= _DOCKER_IMAGE_INDEX
        or _IMAGE.fullmatch(args[_DOCKER_IMAGE_INDEX]) is None
    ):
        return [f"{label}.args must be run -i --rm and an image pinned by sha256"]
    return []


def hook_issues(text: str, scripts: Iterable[str]) -> list[str]:
    """Report every defect in one hook registration file.

    Args:
        text (str): Raw JSON text of the hook registration file.
        scripts (Iterable[str]): Script names the bundle ships.

    Returns:
        list[str]: Safe messages in registration order, empty when valid. Script
        references must name files in ``scripts``; declared values are never echoed.
    """
    try:
        data = json.loads(text)
    except ValueError:
        return ["hook file is not valid JSON"]
    hooks = _registrations(data)
    if hooks is None:
        return ["hook file must hold version 1 and a hooks object"]
    available = frozenset(scripts)
    issues: list[str] = []
    for event, entries in hooks.items():
        if event not in _HOOK_EVENTS or not isinstance(entries, list) or not entries:
            issues.append("hook events must be preToolUse lists")
            continue
        for index, entry in enumerate(entries):
            issues.extend(_hook_entry_issues(entry, f"{event}[{index}]", available))
    return issues


def _registrations(data: object) -> JsonObject | None:
    """Return the non-empty hooks object of a version 1 document, else ``None``."""
    if not is_json_object(data) or set(data) != {"version", "hooks"}:
        return None
    hooks = data["hooks"]
    if data["version"] != 1 or not is_int(data["version"]):
        return None
    return hooks if is_json_object(hooks) and hooks else None


def _hook_entry_issues(
    entry: object, label: str, available: frozenset[str]
) -> list[str]:
    """Validate one command hook: shipped script, fixed interpreters, bounded time.

    Args:
        entry (object): Decoded hook entry.
        label (str): Safe location prefix for messages.
        available (frozenset[str]): Script names the bundle ships.

    Returns:
        list[str]: Safe messages; empty when the entry is valid.
    """
    if not isinstance(entry, dict):
        return [f"{label} must be an object"]
    issues = [
        f"{label} has an unknown field"
        for key in sorted(entry.keys() - _HOOK_FIELDS, key=str)
    ]
    if entry.get("type") != "command":
        issues.append(f"{label}.type must be command")
    for key, pattern in (("bash", _BASH_COMMAND), ("powershell", _POWERSHELL_COMMAND)):
        issues.extend(
            _command_issues(entry.get(key), f"{label}.{key}", pattern, available)
        )
    timeout = entry.get("timeoutSec")
    if not is_int(timeout) or not 1 <= timeout <= _MAX_HOOK_TIMEOUT_SECONDS:
        issues.append(f"{label}.timeoutSec must be 1 to {_MAX_HOOK_TIMEOUT_SECONDS}")
    return issues


def _command_issues(
    command: object, label: str, pattern: re.Pattern[str], available: frozenset[str]
) -> list[str]:
    """Require a fixed interpreter invoking a script that ships in the bundle.

    Args:
        command (object): Decoded command string.
        label (str): Safe location prefix for messages.
        pattern (re.Pattern[str]): Interpreter pattern capturing the script name.
        available (frozenset[str]): Script names the bundle ships.

    Returns:
        list[str]: One message when the command is rejected; empty otherwise.
    """
    match = pattern.fullmatch(command) if isinstance(command, str) else None
    if match is None:
        return [f"{label} must run a script from ./scripts with a fixed interpreter"]
    if match.group(1) not in available:
        return [f"{label} names a script that the bundle does not ship"]
    return []


def script_issue(name: str) -> str | None:
    """Return why a path beneath ``.apm/hooks/scripts`` is not allowed, if it is not.

    Copilot drops JSON assets nested in hook directories, so runtime configuration
    uses another suffix; only flat ``.py`` and ``.policy`` files are accepted. The
    ``name`` is the path relative to ``.apm/hooks/scripts``.
    """
    path = PurePosixPath(name)
    if len(path.parts) != 1 or path.suffix not in _SCRIPT_SUFFIXES:
        return "hook scripts must be flat .py or .policy files"
    return None
