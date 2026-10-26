"""Generate Python and TypeScript identifier modules from a naming registry.

The registry is a JSON document (see ``naming_registry.json.template``) with a
semantic ``version`` and ``groups`` of named entries. Every group becomes a
Python ``StrEnum`` and a TypeScript ``as const`` object with a matching union
type. Output is deterministic: the same registry always produces the same
bytes, and files are rewritten only when their content changes.

Each generated file starts with a header recording the registry version, the
SHA-256 of the canonical registry JSON, and the SHA-256 of the generated body.
``check_registry.py`` uses those digests to detect stale or hand-edited files
without importing this module.

Run ``check_registry.py`` first; this generator only enforces the minimum
needed to emit safe code (identifier and text patterns) and stops on the first
problem.

Exit status: 0 when outputs are written or unchanged, 2 for usage errors,
unreadable input, or a registry that cannot be rendered safely.
``--self-test`` renders a synthetic registry, checks determinism and safety,
and exits.

Example:
    python generate_registry.py registry/naming_registry.json \
        --python backend/src/app/registry.py --typescript frontend/src/registry.ts
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys

EXIT_OK = 0
EXIT_USAGE = 2
GENERATOR_NAME = "generate_registry.py"
_GROUP_NAME = re.compile(r"[A-Z][A-Za-z0-9]*")
_ENTRY_NAME = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*")
_VALUE = re.compile(r"\S(?:.*\S)?")
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_UNSAFE_TEXT = re.compile(r'"""|"$|\\|\*/|[\x00-\x1f\x7f]')
# Names the generated modules already bind, plus PascalCase Python keywords.
RESERVED_GROUP_NAMES = frozenset({"StrEnum", "Final", "True", "False", "None"})


class RegistryError(ValueError):
    """The registry cannot be rendered safely."""


@dataclass(frozen=True, kw_only=True, slots=True)
class Entry:
    """One identifier inside a group.

    Attributes:
        name: Constant name in ``UPPER_SNAKE_CASE``.
        value: Wire value shared by backend and frontend.
        description: Optional one-line explanation.
        deprecation: Deprecation note such as ``since 1.1.0. Use PAID.``, or
            empty when the entry is active.
    """

    name: str
    value: str
    description: str
    deprecation: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Group:
    """A named set of identifiers of one kind.

    Attributes:
        name: Type name in ``PascalCase``.
        kind: Identifier kind such as ``enum`` or ``route``.
        description: One-line explanation used in docstrings.
        entries: Entries in registry order.
    """

    name: str
    kind: str
    description: str
    entries: tuple[Entry, ...]


@dataclass(frozen=True, kw_only=True, slots=True)
class Registry:
    """Parsed registry ready for rendering.

    Attributes:
        version: Semantic version of the registry.
        digest: SHA-256 of the canonical registry JSON.
        groups: Groups in registry order.
    """

    version: str
    digest: str
    groups: tuple[Group, ...]


def canonical_digest(document: object) -> str:
    """Return the SHA-256 of a JSON value with sorted keys and compact separators.

    Args:
        document: Parsed JSON value.

    Returns:
        Lower-case hexadecimal digest.
    """
    text = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(
    item: dict[str, object],
    key: str,
    *,
    where: str,
    pattern: re.Pattern[str] | None = None,
) -> str:
    """Read a string field, enforcing a full-match pattern or safe text.

    Raises:
        RegistryError: The value is not safe text matching ``pattern``.
    """
    value = item.get(key, "")
    if not isinstance(value, str):
        message = f"{where}.{key} must be a string"
        raise RegistryError(message)
    if pattern is not None and not pattern.fullmatch(value):
        message = f"{where}.{key} {value!r} does not match {pattern.pattern}"
        raise RegistryError(message)
    if _UNSAFE_TEXT.search(value):
        message = f"{where}.{key} contains characters that cannot be rendered safely"
        raise RegistryError(message)
    return value


def _objects(value: object, *, where: str) -> list[dict[str, object]]:
    """Return a list of JSON objects or raise ``RegistryError``.

    Raises:
        RegistryError: The value is not a list of objects.
    """
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        message = f"{where} must be a list of objects"
        raise RegistryError(message)
    return [{str(key): field for key, field in item.items()} for item in value]


def _deprecation(entry: dict[str, object], *, where: str) -> str:
    """Render the deprecation note for an entry, or return an empty string.

    Raises:
        RegistryError: The deprecation is not an object.
    """
    raw = entry.get("deprecated")
    if raw is None:
        return ""
    if not isinstance(raw, dict):
        message = f"{where}.deprecated must be an object"
        raise RegistryError(message)
    details = {str(key): value for key, value in raw.items()}
    since = _text(details, "since", where=f"{where}.deprecated", pattern=_VERSION)
    note = f"since {since}."
    replacement = _text(details, "replacement", where=f"{where}.deprecated")
    if replacement:
        note += f" Use {replacement}."
    reason = _text(details, "reason", where=f"{where}.deprecated")
    return f"{note} {reason}".strip()


def _entry(item: dict[str, object], *, where: str) -> Entry:
    """Parse one entry."""
    return Entry(
        name=_text(item, "name", where=where, pattern=_ENTRY_NAME),
        value=_text(item, "value", where=where, pattern=_VALUE),
        description=_text(item, "description", where=where),
        deprecation=_deprecation(item, where=where),
    )


def _group(item: dict[str, object], *, where: str) -> Group:
    """Parse one group, rejecting names and shapes that would break the output.

    Raises:
        RegistryError: The name is reserved or the group has no entries.
    """
    name = _text(item, "name", where=where, pattern=_GROUP_NAME)
    if name in RESERVED_GROUP_NAMES:
        message = f"{where}.name {name!r} is reserved in the generated modules"
        raise RegistryError(message)
    entries = _objects(item.get("entries"), where=f"{where}.entries")
    if not entries:
        message = f"{where}.entries must not be empty"
        raise RegistryError(message)
    return Group(
        name=name,
        kind=_text(item, "kind", where=where),
        description=_text(item, "description", where=where),
        entries=tuple(
            _entry(entry, where=f"{where}.entries[{position}]")
            for position, entry in enumerate(entries)
        ),
    )


def parse_registry(document: object) -> Registry:
    """Convert a parsed registry document into render-ready records.

    Args:
        document: JSON value loaded from the registry file.

    Returns:
        The parsed registry.

    Raises:
        RegistryError: If a field needed for safe rendering is missing or invalid.
    """
    if not isinstance(document, dict):
        message = "registry must be a JSON object"
        raise RegistryError(message)
    root = {str(key): value for key, value in document.items()}
    groups = tuple(
        _group(item, where=f"groups[{index}]")
        for index, item in enumerate(_objects(root.get("groups"), where="groups"))
    )
    return Registry(
        version=_text(root, "version", where="registry", pattern=_VERSION),
        digest=canonical_digest(document),
        groups=groups,
    )


def _header(registry: Registry, body: str, *, comment: str) -> str:
    """Return the provenance header that ``check_registry.py`` verifies."""
    content = hashlib.sha256(body.encode("utf-8")).hexdigest()
    lines = (
        f"Generated by {GENERATOR_NAME} from the naming registry. Do not edit.",
        f"registry-version: {registry.version}",
        f"registry-sha256: {registry.digest}",
        f"content-sha256: {content}",
    )
    return "".join(f"{comment} {line}\n" for line in lines)


def _python_group(group: Group) -> list[str]:
    """Render one group as a ``StrEnum`` class."""
    lines = ["", "", f"class {group.name}(StrEnum):"]
    lines.append(f'    """{group.description or group.name}"""')
    lines.append("")
    for entry in group.entries:
        if entry.description:
            lines.append(f"    # {entry.description}")
        if entry.deprecation:
            lines.append(f"    # Deprecated {entry.deprecation}")
        lines.append(f"    {entry.name} = {json.dumps(entry.value)}")
    return lines


def render_python(registry: Registry) -> str:
    """Render the Python module.

    Args:
        registry: Parsed registry.

    Returns:
        Module text with a provenance header.
    """
    lines = [
        '"""Shared identifiers generated from the naming registry."""',
        "",
        "from enum import StrEnum",
        "from typing import Final",
        "",
        f"REGISTRY_VERSION: Final = {json.dumps(registry.version)}",
    ]
    for group in registry.groups:
        lines.extend(_python_group(group))
    body = "\n".join(lines) + "\n"
    return _header(registry, body, comment="#") + body


def _typescript_group(group: Group) -> list[str]:
    """Render one group as a constant object and a union type."""
    lines = ["", f"/** {group.description or group.name} */"]
    lines.append(f"export const {group.name} = {{")
    for entry in group.entries:
        notes = [entry.description] if entry.description else []
        if entry.deprecation:
            notes.append(f"@deprecated {entry.deprecation}")
        if notes:
            lines.append(f"  /** {' '.join(notes)} */")
        lines.append(f"  {entry.name}: {json.dumps(entry.value)},")
    lines.append("} as const;")
    lines.append(
        f"export type {group.name} = (typeof {group.name})[keyof typeof {group.name}];"
    )
    return lines


def render_typescript(registry: Registry) -> str:
    """Render the TypeScript module.

    Args:
        registry: Parsed registry.

    Returns:
        Module text with a provenance header.
    """
    lines = [f"export const REGISTRY_VERSION = {json.dumps(registry.version)};"]
    for group in registry.groups:
        lines.extend(_typescript_group(group))
    body = "\n".join(lines) + "\n"
    return _header(registry, body, comment="//") + body


def load_registry(path: Path) -> Registry:
    """Read and parse a registry file.

    Args:
        path: Registry JSON file.

    Returns:
        The parsed registry.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the JSON is invalid or the registry cannot be rendered.
    """
    return parse_registry(json.loads(path.read_text(encoding="utf-8")))


def write_if_changed(path: Path, text: str) -> bool:
    """Write text with LF line endings when it differs from the current file.

    Args:
        path: Output file; parent directories are created.
        text: Complete file content.

    Returns:
        True when the file was written, False when it was already current.
    """
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


class SelfTestError(AssertionError):
    """Generated output did not meet a documented guarantee."""


_SELF_TEST_REGISTRY: dict[str, object] = {
    "version": "1.0.0",
    "groups": [
        {
            "name": "Status",
            "kind": "enum",
            "description": "Example status.",
            "entries": [
                {"name": "ACTIVE", "value": "active"},
                {
                    "name": "RETIRED",
                    "value": "retired",
                    "deprecated": {
                        "since": "1.0.0",
                        "replacement": "ACTIVE",
                        "reason": "Unused.",
                    },
                },
            ],
        }
    ],
}


def self_test() -> None:
    """Render a synthetic registry and check determinism and safety.

    Raises:
        SelfTestError: If output differs between runs, does not compile, lacks
            the deprecation note, or unsafe text is accepted.
    """
    copy = json.loads(json.dumps(_SELF_TEST_REGISTRY))
    python = render_python(parse_registry(_SELF_TEST_REGISTRY))
    typescript = render_typescript(parse_registry(_SELF_TEST_REGISTRY))
    if python != render_python(parse_registry(copy)):
        message = "Python output is not deterministic"
        raise SelfTestError(message)
    compile(python, "<generated registry>", "exec")
    if "@deprecated since 1.0.0. Use ACTIVE." not in typescript:
        message = "TypeScript output lacks the deprecation note"
        raise SelfTestError(message)
    copy["groups"][0]["description"] = 'Ends with a quote"'
    try:
        parse_registry(copy)
    except RegistryError:
        return
    message = "unsafe description was accepted"
    raise SelfTestError(message)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the requested outputs.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 on success, 2 for unreadable input or text that cannot be rendered (argparse exits
        with 2 on invalid arguments).
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("registry", nargs="?", type=Path, help="registry JSON file")
    parser.add_argument("--python", type=Path, help="output path for the Python module")
    parser.add_argument(
        "--typescript", type=Path, help="output path for the TypeScript module"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="check the generator and exit"
    )
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Registry generator self-test passed.")
        return EXIT_OK
    if args.registry is None or (args.python is None and args.typescript is None):
        parser.error("give REGISTRY and --python, --typescript, or both")
    try:
        registry = load_registry(args.registry)
    except (OSError, ValueError) as error:
        print(f"Cannot generate from {args.registry}: {error}", file=sys.stderr)
        return EXIT_USAGE
    outputs = ((args.python, render_python), (args.typescript, render_typescript))
    for path, render in outputs:
        if path is not None:
            changed = write_if_changed(path, render(registry))
            print(f"{'wrote' if changed else 'unchanged'} {path.as_posix()}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
