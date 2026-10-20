"""Report likely breaking changes between two OpenAPI descriptions in JSON.

Compares a released description ('old') with a candidate ('new') using only the
standard library. Convert YAML to JSON first with the project's tooling (for
example by exporting 'app.openapi()' from FastAPI). Local '$ref' pointers
('#/...') are resolved; remote references are reported and not followed.

Checked:
- removed paths, operations, response status codes, and media types;
- new required parameters, headers, request bodies, and request properties;
- parameters or request properties that became required;
- schema type changes (narrowed for requests, widened for responses);
- removed request enum values and added response enum values (warning);
- removed response properties and response properties no longer required;
- tightened request constraints (length, range, item counts, pattern);
- security added to an operation that had none.

The result is evidence for a compatibility review, not a certification: it does
not understand composition keywords ('allOf', 'oneOf', 'anyOf') beyond flagging
that they changed, and it cannot know how real clients behave.

Output lines look like 'new.json: GET /orders: breaking: message'. The exit code
is 1 when any breaking change is found (or any warning with '--strict').
"""

import argparse
import json
import re
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
_MAX_DEPTH = 64
_TIGHTER_WHEN_LARGER = (
    "minLength",
    "minimum",
    "exclusiveMinimum",
    "minItems",
    "minProperties",
)
_TIGHTER_WHEN_SMALLER = (
    "maxLength",
    "maximum",
    "exclusiveMaximum",
    "maxItems",
    "maxProperties",
)
_COMPOSITION = ("allOf", "oneOf", "anyOf", "not")

type Json = object
type Document = Mapping[str, Json]


@dataclass(frozen=True, kw_only=True, slots=True)
class Change:
    """One difference relevant to clients.

    Attributes:
        severity: 'breaking' or 'warning'.
        location: Operation and position, such as 'GET /orders response 200'.
        message: What changed.
    """

    severity: str
    location: str
    message: str


def compare(old: Document, new: Document) -> list[Change]:
    """Return client-relevant changes from 'old' to 'new', sorted for stable output.

    Args:
        old: Released OpenAPI description.
        new: Candidate OpenAPI description.

    Returns:
        Changes sorted by location, severity, and message.
    """
    changes: list[Change] = []
    old_paths = _mapping(old.get("paths"))
    new_paths = _mapping(new.get("paths"))
    for path in sorted(old_paths):
        if path not in new_paths:
            changes.append(
                Change(severity="breaking", location=path, message="path removed")
            )
            continue
        old_item = _resolve(old, old_paths[path])
        new_item = _resolve(new, new_paths[path])
        for method in _METHODS:
            if method not in old_item:
                continue
            location = f"{method.upper()} {path}"
            if method not in new_item:
                changes.append(
                    Change(
                        severity="breaking",
                        location=location,
                        message="operation removed",
                    )
                )
                continue
            changes.extend(
                _Operation(old=old, new=new, location=location).compare(
                    old_item, new_item, method
                )
            )
    return sorted(
        changes, key=lambda change: (change.location, change.severity, change.message)
    )


@dataclass(frozen=True, kw_only=True, slots=True)
class _Operation:
    """Compare one operation present in both documents."""

    old: Document
    new: Document
    location: str

    def compare(
        self, old_item: Document, new_item: Document, method: str
    ) -> Iterator[Change]:
        """Yield parameter, body, response, and security changes."""
        old_operation = _resolve(self.old, old_item[method])
        new_operation = _resolve(self.new, new_item[method])
        yield from self._parameters(old_item, old_operation, new_item, new_operation)
        yield from self._request_body(old_operation, new_operation)
        yield from self._responses(old_operation, new_operation)
        yield from self._security(old_operation, new_operation)

    def _parameters(
        self,
        old_item: Document,
        old_operation: Document,
        new_item: Document,
        new_operation: Document,
    ) -> Iterator[Change]:
        old_parameters = _parameters(self.old, old_item, old_operation)
        new_parameters = _parameters(self.new, new_item, new_operation)
        for key, parameter in sorted(new_parameters.items()):
            label = f"{key[0]} parameter '{key[1]}'"
            previous = old_parameters.get(key)
            required = parameter.get("required") is True
            if previous is None:
                if required:
                    yield self._breaking(f"new required {label}")
                continue
            if required and previous.get("required") is not True:
                yield self._breaking(f"{label} became required")
            yield from _Schema(
                old=self.old,
                new=self.new,
                location=f"{self.location} {label}",
                request=True,
            ).compare(previous.get("schema"), parameter.get("schema"), "", 0)
        for key in sorted(old_parameters.keys() - new_parameters.keys()):
            yield self._warning(f"{key[0]} parameter '{key[1]}' removed")

    def _request_body(
        self, old_operation: Document, new_operation: Document
    ) -> Iterator[Change]:
        old_body = _resolve(self.old, old_operation.get("requestBody"))
        new_body = _resolve(self.new, new_operation.get("requestBody"))
        if not new_body:
            return
        if new_body.get("required") is True and old_body.get("required") is not True:
            yield self._breaking("request body became required")
        old_content = _mapping(old_body.get("content"))
        new_content = _mapping(new_body.get("content"))
        for media_type in sorted(old_content.keys() - new_content.keys()):
            yield self._breaking(
                f"request media type '{media_type}' no longer accepted"
            )
        for media_type in sorted(old_content.keys() & new_content.keys()):
            yield from _Schema(
                old=self.old,
                new=self.new,
                location=f"{self.location} request {media_type}",
                request=True,
            ).compare(
                _mapping(old_content[media_type]).get("schema"),
                _mapping(new_content[media_type]).get("schema"),
                "",
                0,
            )

    def _responses(
        self, old_operation: Document, new_operation: Document
    ) -> Iterator[Change]:
        old_responses = _mapping(old_operation.get("responses"))
        new_responses = _mapping(new_operation.get("responses"))
        for status in sorted(old_responses):
            if status not in new_responses:
                yield self._breaking(f"response {status} removed")
                continue
            old_content = _mapping(
                _resolve(self.old, old_responses[status]).get("content")
            )
            new_content = _mapping(
                _resolve(self.new, new_responses[status]).get("content")
            )
            for media_type in sorted(old_content):
                where = f"{self.location} response {status} {media_type}"
                if media_type not in new_content:
                    yield Change(
                        severity="breaking",
                        location=where,
                        message="media type removed",
                    )
                    continue
                yield from _Schema(
                    old=self.old, new=self.new, location=where, request=False
                ).compare(
                    _mapping(old_content[media_type]).get("schema"),
                    _mapping(new_content[media_type]).get("schema"),
                    "",
                    0,
                )

    def _security(
        self, old_operation: Document, new_operation: Document
    ) -> Iterator[Change]:
        old_security = old_operation.get("security", self.old.get("security"))
        new_security = new_operation.get("security", self.new.get("security"))
        if not old_security and new_security:
            yield self._breaking("security requirement added")
        elif old_security != new_security:
            yield self._warning("security requirements changed")

    def _breaking(self, message: str) -> Change:
        return Change(severity="breaking", location=self.location, message=message)

    def _warning(self, message: str) -> Change:
        return Change(severity="warning", location=self.location, message=message)


@dataclass(frozen=True, kw_only=True, slots=True)
class _Schema:
    """Compare two schemas in request or response direction."""

    old: Document
    new: Document
    location: str
    request: bool

    def compare(
        self, old_raw: Json, new_raw: Json, pointer: str, depth: int
    ) -> Iterator[Change]:
        """Yield changes between two schemas at a JSON pointer below the root."""
        if depth > _MAX_DEPTH:
            return
        for raw in (old_raw, new_raw):
            reference = _mapping(raw).get("$ref")
            if isinstance(reference, str) and not reference.startswith("#/"):
                yield self._change(
                    "warning", pointer, f"remote reference '{reference}' not followed"
                )
                return
        old_schema = _resolve(self.old, old_raw)
        new_schema = _resolve(self.new, new_raw)
        if not old_schema or not new_schema:
            return
        yield from self._types(old_schema, new_schema, pointer)
        yield from self._enums(old_schema, new_schema, pointer)
        if self.request:
            yield from self._constraints(old_schema, new_schema, pointer)
        yield from self._properties(old_schema, new_schema, pointer, depth)
        for keyword in ("items", "additionalProperties"):
            if isinstance(old_schema.get(keyword), dict) and isinstance(
                new_schema.get(keyword), dict
            ):
                yield from self.compare(
                    old_schema[keyword],
                    new_schema[keyword],
                    f"{pointer}/{keyword}",
                    depth + 1,
                )
        for keyword in _COMPOSITION:
            if json.dumps(old_schema.get(keyword), sort_keys=True) != json.dumps(
                new_schema.get(keyword), sort_keys=True
            ):
                yield self._change(
                    "warning", pointer, f"'{keyword}' changed; review manually"
                )

    def _types(
        self, old_schema: Document, new_schema: Document, pointer: str
    ) -> Iterator[Change]:
        old_types = _types(old_schema)
        new_types = _types(new_schema)
        if not old_types or not new_types or old_types == new_types:
            return
        narrowed = self.request and not new_types >= old_types
        widened = not self.request and not new_types <= old_types
        if narrowed or widened:
            yield self._change(
                "breaking",
                pointer,
                f"type changed from {sorted(old_types)} to {sorted(new_types)}",
            )

    def _enums(
        self, old_schema: Document, new_schema: Document, pointer: str
    ) -> Iterator[Change]:
        old_enum = old_schema.get("enum")
        new_enum = new_schema.get("enum")
        if not isinstance(old_enum, list) or not isinstance(new_enum, list):
            return
        old_values = {json.dumps(value) for value in old_enum}
        new_values = {json.dumps(value) for value in new_enum}
        if self.request and old_values - new_values:
            removed = ", ".join(sorted(old_values - new_values))
            yield self._change(
                "breaking", pointer, f"enum values no longer accepted: {removed}"
            )
        if not self.request and new_values - old_values:
            added = ", ".join(sorted(new_values - old_values))
            yield self._change(
                "warning", pointer, f"enum values added to response: {added}"
            )

    def _constraints(
        self, old_schema: Document, new_schema: Document, pointer: str
    ) -> Iterator[Change]:
        for keyword in (*_TIGHTER_WHEN_LARGER, *_TIGHTER_WHEN_SMALLER):
            old_value = old_schema.get(keyword)
            new_value = new_schema.get(keyword)
            if not isinstance(new_value, int | float) or isinstance(new_value, bool):
                continue
            if not isinstance(old_value, int | float) or isinstance(old_value, bool):
                yield self._change(
                    "breaking", pointer, f"new constraint {keyword}={new_value}"
                )
                continue
            tighter = (
                new_value > old_value
                if keyword in _TIGHTER_WHEN_LARGER
                else new_value < old_value
            )
            if tighter:
                yield self._change(
                    "breaking",
                    pointer,
                    f"{keyword} tightened from {old_value} to {new_value}",
                )
        if new_schema.get("pattern") is not None and new_schema.get(
            "pattern"
        ) != old_schema.get("pattern"):
            yield self._change("breaking", pointer, "pattern added or changed")

    def _properties(
        self, old_schema: Document, new_schema: Document, pointer: str, depth: int
    ) -> Iterator[Change]:
        old_properties = _mapping(old_schema.get("properties"))
        new_properties = _mapping(new_schema.get("properties"))
        old_required = set(_strings(old_schema.get("required")))
        new_required = set(_strings(new_schema.get("required")))
        if self.request:
            for name in sorted(new_required - old_required):
                yield self._change(
                    "breaking", f"{pointer}/{name}", "property became required"
                )
            for name in sorted(old_properties.keys() - new_properties.keys()):
                yield self._change(
                    "warning", f"{pointer}/{name}", "request property removed"
                )
        else:
            for name in sorted(old_properties.keys() - new_properties.keys()):
                yield self._change(
                    "breaking", f"{pointer}/{name}", "response property removed"
                )
            for name in sorted(old_required - new_required):
                yield self._change(
                    "breaking",
                    f"{pointer}/{name}",
                    "response property no longer required",
                )
        for name in sorted(old_properties.keys() & new_properties.keys()):
            yield from self.compare(
                old_properties[name],
                new_properties[name],
                f"{pointer}/{name}",
                depth + 1,
            )

    def _change(self, severity: str, pointer: str, message: str) -> Change:
        where = f"{self.location} {pointer}" if pointer else self.location
        return Change(severity=severity, location=where, message=message)


def _parameters(
    document: Document, item: Document, operation: Document
) -> dict[tuple[str, str], Document]:
    merged: dict[tuple[str, str], Document] = {}
    for raw in [
        *_sequence(item.get("parameters")),
        *_sequence(operation.get("parameters")),
    ]:
        parameter = _resolve(document, raw)
        name = parameter.get("name")
        place = parameter.get("in")
        if isinstance(name, str) and isinstance(place, str):
            merged[(place, name.lower() if place == "header" else name)] = parameter
    return merged


def _types(schema: Document) -> frozenset[str]:
    raw = schema.get("type")
    types = {raw} if isinstance(raw, str) else set(_strings(raw))
    if types and schema.get("nullable") is True:
        types.add("null")
    if "number" in types:
        types.add("integer")
    return frozenset(types)


def _resolve(document: Document, value: Json) -> Document:
    """Follow local '$ref' chains; return an empty mapping when unresolvable."""
    current = _mapping(value)
    seen: set[str] = set()
    while isinstance(current.get("$ref"), str):
        reference = str(current["$ref"])
        if not reference.startswith("#/") or reference in seen:
            return {}
        seen.add(reference)
        target: Json = document
        for part in reference[2:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            target = _mapping(target).get(key)
        current = _mapping(target)
    return current


def _mapping(value: Json) -> Document:
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return value
    return {}


def _sequence(value: Json) -> list[Json]:
    return value if isinstance(value, list) else []


def _strings(value: Json) -> list[str]:
    return [item for item in _sequence(value) if isinstance(item, str)]


def main(argv: list[str] | None = None) -> int:
    """Compare two JSON OpenAPI files and print changes.

    Args:
        argv: Command-line arguments; defaults to 'sys.argv[1:]'.

    Returns:
        One when breaking changes exist (or warnings with '--strict'), two on
        unreadable input, otherwise zero.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("old", type=Path, help="released description (JSON)")
    parser.add_argument("new", type=Path, help="candidate description (JSON)")
    parser.add_argument("--strict", action="store_true", help="also fail on warnings")
    parser.add_argument(
        "--ignore-path",
        action="append",
        default=[],
        help="regular expression of locations to skip (repeatable)",
    )
    args = parser.parse_args(argv)
    try:
        old = _load(args.old)
        new = _load(args.new)
        ignore = [re.compile(pattern) for pattern in args.ignore_path]
    except (
        OSError,
        UnicodeError,
        ValueError,
        OpenApiInputTypeError,
        re.error,
    ) as error:
        print(f"cannot compare: {error}", file=sys.stderr)
        return 2
    changes = [
        change
        for change in compare(old, new)
        if not any(pattern.search(change.location) for pattern in ignore)
    ]
    for change in changes:
        print(
            f"{args.new.as_posix()}: {change.location}: {change.severity}: {change.message}"
        )
    failing = {"breaking", "warning"} if args.strict else {"breaking"}
    return 1 if any(change.severity in failing for change in changes) else 0


class OpenApiInputIssue(StrEnum):
    """Supported OpenAPI input validation failures and their stable messages."""

    DOCUMENT_SHAPE = "{path} is not an OpenAPI JSON object with 'paths'"


class OpenApiInputError(ValueError):
    """An input violates the OpenAPI input contract."""

    def __init__(self, issue: OpenApiInputIssue, *, path: Path | None = None) -> None:
        """Describe a supported input failure.

        Args:
            issue: The violated input invariant.
            path: Diagnostic path for the invalid input.
        """
        super().__init__(issue.value.format(path=path))


class OpenApiInputTypeError(TypeError):
    """An input has the wrong Python type for the OpenAPI input contract."""

    def __init__(self, issue: OpenApiInputIssue, *, path: Path | None = None) -> None:
        """Describe a wrong input type.

        Args:
            issue: The violated input invariant.
            path: Diagnostic path for the invalid input.
        """
        super().__init__(issue.value.format(path=path))


def _load(path: Path) -> Document:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise OpenApiInputTypeError(OpenApiInputIssue.DOCUMENT_SHAPE, path=path)
    document = _mapping(loaded)
    if "paths" not in document:
        raise OpenApiInputError(OpenApiInputIssue.DOCUMENT_SHAPE, path=path)
    if not isinstance(document["paths"], dict):
        raise OpenApiInputTypeError(OpenApiInputIssue.DOCUMENT_SHAPE, path=path)
    return document


if __name__ == "__main__":
    raise SystemExit(main())
