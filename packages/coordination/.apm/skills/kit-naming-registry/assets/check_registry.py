"""Validate a naming registry and detect drift in its generated modules.

Checks, in order:

1. Structure against the registry JSON Schema (``--schema``, or the registry's
   relative ``$schema``). A stdlib subset validator supports ``type``,
   ``required``, ``properties``, ``additionalProperties``, ``items``,
   ``minItems``, ``minLength``, ``maxLength``, ``pattern``, ``enum`` and local
   ``$ref``; any other keyword is an input error so schema changes never pass
   silently.
2. Semantics: duplicate JSON keys, unique group names, unique entry names and
   values per group, unique values across groups for routes, query keys,
   events and error codes, kind-specific value patterns, reserved names, and
   consistent deprecations.
3. Compatibility with ``--baseline`` (the released registry): removed entries
   must have been deprecated and past ``remove_after``; values never change;
   any change increments ``version``.
4. Drift of ``--python`` and ``--typescript`` outputs: each file's header must
   name the current registry digest and match its own body digest, as written
   by ``generate_registry.py``.

Output is ``location: [rule] message`` per finding, in a stable order.
Exit status: 0 clean, 1 findings, 2 usage error or unreadable input.
``--self-test`` exercises the checks on synthetic input and exits.

Example:
    python check_registry.py registry/naming_registry.json \
        --python backend/src/app/registry.py --typescript frontend/src/registry.ts \
        --baseline build/released_registry.json
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import json
import keyword
from pathlib import Path
import re
import sys

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2
_SEGMENT = r"[a-z][a-z0-9_]*"
_SNAKE = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"
_PATH_PART = r"(?:[a-z0-9]+(?:-[a-z0-9]+)*|\{[a-z][a-z0-9_]*\})"
KIND_PATTERNS: dict[str, re.Pattern[str]] = {
    "route": re.compile(rf"/(?:{_PATH_PART}(?:/{_PATH_PART})*)?"),
    "query_key": re.compile(rf"{_SEGMENT}(?:\.{_SEGMENT})*"),
    "event": re.compile(rf"{_SEGMENT}(?:\.{_SEGMENT})+"),
    "enum": re.compile(_SNAKE),
    "error_code": re.compile(_SNAKE),
    "field": re.compile(_SNAKE),
}
# Kinds whose values share one namespace across all groups.
GLOBAL_KINDS = frozenset({"route", "query_key", "event", "error_code"})
RESERVED_GROUP_NAMES = frozenset({"StrEnum", "Final", "True", "False", "None"})
_SUPPORTED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$defs",
        "$ref",
        "title",
        "description",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "minItems",
        "minLength",
        "maxLength",
        "pattern",
        "enum",
    }
)
_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "boolean": (bool,),
    "null": (type(None),),
}
_HEADER_FIELD = re.compile(r"(?:#|//) (registry-sha256|content-sha256): ([0-9a-f]{64})")
_HEADER_LINES = 4

type Schema = dict[str, object]


class RegistryInputError(ValueError):
    """The registry, schema, or baseline cannot be used as input."""


@dataclass(frozen=True, kw_only=True, slots=True)
class Finding:
    """One registry problem.

    Attributes:
        location: File path or JSON location such as ``groups[2].entries[0]``.
        rule: Rule identifier.
        message: Explanation and repair.
    """

    location: str
    rule: str
    message: str

    def render(self) -> str:
        """Return ``location: [rule] message``."""
        return f"{self.location}: [{self.rule}] {self.message}"


@dataclass(frozen=True, kw_only=True, slots=True)
class Snapshot:
    """Compatibility-relevant state of one entry.

    Attributes:
        value: Wire value.
        deprecated: Whether the entry carries a deprecation.
        remove_after: Version after which removal is allowed, or empty.
    """

    value: str
    deprecated: bool
    remove_after: str


def load_json(path: Path, duplicates: list[str]) -> object:
    """Parse JSON, recording keys that appear twice in one object.

    Args:
        path: JSON file.
        duplicates: Receives each duplicated key name.

    Returns:
        The parsed value; for duplicated keys the last value wins.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the text is not valid JSON.
    """

    def collect(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                duplicates.append(key)
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=collect)


def canonical_digest(document: object) -> str:
    """Return the digest ``generate_registry.py`` records for a registry.

    Args:
        document: Parsed registry JSON.

    Returns:
        SHA-256 hex digest of the sorted, compact JSON serialization.
    """
    serialized = json.dumps(document, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _as_schema(value: object) -> Schema:
    """Return a schema object or raise ``RegistryInputError``.

    Raises:
        RegistryInputError: The value is not an object.
    """
    if not isinstance(value, dict):
        message = f"schema node must be an object, got {type(value).__name__}"
        raise RegistryInputError(message)
    return {str(key): item for key, item in value.items()}


def _resolve(schema: Schema, root: Schema) -> Schema:
    """Follow a local ``$ref`` such as ``#/$defs/entry``.

    Raises:
        RegistryInputError: The reference is not local.
    """
    reference = schema.get("$ref")
    if reference is None:
        return schema
    if not isinstance(reference, str) or not reference.startswith("#/"):
        message = f"unsupported $ref {reference!r}; only local references work"
        raise RegistryInputError(message)
    node: object = root
    for part in reference.removeprefix("#/").split("/"):
        node = _as_schema(node).get(part)
    return _as_schema(node)


def _string_findings(value: str, schema: Schema, where: str) -> list[Finding]:
    """Apply ``minLength``, ``maxLength`` and ``pattern``."""
    problems: list[str] = []
    minimum, maximum = schema.get("minLength"), schema.get("maxLength")
    if isinstance(minimum, int) and len(value) < minimum:
        problems.append(f"shorter than {minimum} characters")
    if isinstance(maximum, int) and len(value) > maximum:
        problems.append(f"longer than {maximum} characters")
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and not re.search(pattern, value):
        problems.append(f"does not match {pattern}")
    return [Finding(location=where, rule="schema", message=item) for item in problems]


def _array_findings(
    value: list[object], schema: Schema, *, where: str, root: Schema
) -> list[Finding]:
    """Apply ``minItems`` and ``items``."""
    findings: list[Finding] = []
    minimum = schema.get("minItems")
    if isinstance(minimum, int) and len(value) < minimum:
        message = f"needs at least {minimum} items"
        findings.append(Finding(location=where, rule="schema", message=message))
    items = schema.get("items")
    if items is not None:
        for index, item in enumerate(value):
            findings.extend(validate(item, items, where=f"{where}[{index}]", root=root))
    return findings


def _object_findings(
    value: dict[str, object], schema: Schema, *, where: str, root: Schema
) -> list[Finding]:
    """Apply ``required``, ``properties`` and ``additionalProperties: false``."""
    properties = _as_schema(schema.get("properties", {}))
    required = schema.get("required", [])
    names = required if isinstance(required, list) else []
    findings = [
        Finding(location=where, rule="schema", message=f"missing required {name!r}")
        for name in names
        if name not in value
    ]
    for key, item in value.items():
        if key in properties:
            findings.extend(
                validate(item, properties[key], where=f"{where}.{key}", root=root)
            )
        elif schema.get("additionalProperties") is False:
            message = f"unexpected property {key!r}"
            findings.append(Finding(location=where, rule="schema", message=message))
    return findings


def _scalar_problem(value: object, node: Schema) -> str:
    """Return a ``type`` or ``enum`` mismatch message, or an empty string."""
    expected = node.get("type")
    if isinstance(expected, str) and not isinstance(
        value, _JSON_TYPES.get(expected, ())
    ):
        return f"expected {expected}"
    allowed = node.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        return f"must be one of {allowed}"
    return ""


def validate(
    value: object, schema: object, *, where: str, root: Schema
) -> list[Finding]:
    """Validate a JSON value against a schema node from the supported subset.

    Args:
        value: Parsed JSON value.
        schema: Schema node, possibly a local ``$ref``.
        where: Location used in findings.
        root: Root schema for resolving references.

    Returns:
        Schema findings for this value and its children.

    Raises:
        RegistryInputError: If the schema uses an unsupported keyword or reference.
    """
    node = _resolve(_as_schema(schema), root)
    unsupported = sorted(set(node) - _SUPPORTED_KEYWORDS)
    if unsupported:
        message = f"unsupported schema keywords {unsupported}"
        raise RegistryInputError(message)
    problem = _scalar_problem(value, node)
    if problem:
        return [Finding(location=where, rule="schema", message=problem)]
    if isinstance(value, str):
        return _string_findings(value, node, where)
    if isinstance(value, list):
        return _array_findings(value, node, where=where, root=root)
    if isinstance(value, dict):
        fields = {str(key): item for key, item in value.items()}
        return _object_findings(fields, node, where=where, root=root)
    return []


def _text(item: dict[str, object], key: str) -> str:
    """Return a string field or an empty string when absent or mistyped."""
    value = item.get(key)
    return value if isinstance(value, str) else ""


def _objects(value: object) -> list[dict[str, object]]:
    """Return the JSON objects in a list, ignoring anything else."""
    if not isinstance(value, list):
        return []
    return [
        {str(key): field for key, field in item.items()}
        for item in value
        if isinstance(item, dict)
    ]


def _version(text: str) -> tuple[int, ...]:
    """Parse ``MAJOR.MINOR.PATCH``; malformed versions sort lowest."""
    parts = text.split(".")
    return tuple(int(part) for part in parts) if all(p.isdigit() for p in parts) else ()


def _deprecation_findings(
    entry: dict[str, object], *, where: str, version: str, active: frozenset[str]
) -> list[Finding]:
    """Check one entry's deprecation against the registry version and group."""
    raw = entry.get("deprecated")
    if not isinstance(raw, dict):
        return []
    details = {str(key): value for key, value in raw.items()}
    since, until = _text(details, "since"), _text(details, "remove_after")
    replacement = _text(details, "replacement")
    problems: list[str] = []
    if _version(since) > _version(version):
        problems.append(f"since {since} is newer than registry version {version}")
    if until and _version(until) <= _version(since):
        problems.append(f"remove_after {until} must be later than since {since}")
    if until and _version(version) >= _version(until):
        problems.append(f"past remove_after {until}; remove the entry")
    if replacement and replacement not in active:
        problems.append(f"replacement {replacement} is not an active entry")
    location = f"{where}.deprecated"
    return [Finding(location=location, rule="deprecation", message=p) for p in problems]


def _duplicates(
    items: Sequence[tuple[str, str]], *, rule: str, label: str
) -> list[Finding]:
    """Report repeated keys; ``items`` pairs a key with its location."""
    first: dict[str, str] = {}
    findings: list[Finding] = []
    for key, where in items:
        if key in first:
            message = f"{label} {key!r} already used at {first[key]}"
            findings.append(Finding(location=where, rule=rule, message=message))
        else:
            first[key] = where
    return findings


def _group_findings(
    group: dict[str, object], *, where: str, version: str
) -> list[Finding]:
    """Check names, values, patterns and deprecations inside one group."""
    name, kind = _text(group, "name"), _text(group, "kind")
    entries = _objects(group.get("entries"))
    places = [f"{where}.entries[{index}]" for index in range(len(entries))]
    findings: list[Finding] = []
    if name in RESERVED_GROUP_NAMES or keyword.iskeyword(name):
        message = f"group name {name!r} is reserved in generated code"
        findings.append(Finding(location=where, rule="reserved-name", message=message))
    pattern = KIND_PATTERNS.get(kind)
    active = frozenset(
        _text(entry, "name") for entry in entries if "deprecated" not in entry
    )
    for entry, place in zip(entries, places, strict=True):
        value = _text(entry, "value")
        if pattern is not None and value and not pattern.fullmatch(value):
            message = f"{kind} value {value!r} does not match {pattern.pattern}"
            findings.append(
                Finding(location=place, rule="value-pattern", message=message)
            )
        findings.extend(
            _deprecation_findings(entry, where=place, version=version, active=active)
        )
    names = [
        (_text(entry, "name"), place)
        for entry, place in zip(entries, places, strict=True)
    ]
    values = [
        (_text(entry, "value"), place)
        for entry, place in zip(entries, places, strict=True)
    ]
    findings.extend(_duplicates(names, rule="duplicate-name", label="entry name"))
    findings.extend(_duplicates(values, rule="duplicate-value", label="value"))
    return findings


def semantic_findings(document: object) -> list[Finding]:
    """Check registry rules that a JSON Schema cannot express.

    Args:
        document: Parsed registry JSON.

    Returns:
        Findings for names, values, patterns and deprecations.
    """
    if not isinstance(document, dict):
        return []
    root = {str(key): value for key, value in document.items()}
    version = _text(root, "version")
    groups = _objects(root.get("groups"))
    places = [f"groups[{index}]" for index in range(len(groups))]
    findings = _duplicates(
        [
            (_text(group, "name"), place)
            for group, place in zip(groups, places, strict=True)
        ],
        rule="duplicate-name",
        label="group name",
    )
    shared: list[tuple[str, str]] = []
    for group, place in zip(groups, places, strict=True):
        findings.extend(_group_findings(group, where=place, version=version))
        kind = _text(group, "kind")
        if kind in GLOBAL_KINDS:
            entries = _objects(group.get("entries"))
            # Deduplicate inside the group first; those repeats are reported above.
            unique = dict.fromkeys(_text(entry, "value") for entry in entries)
            shared.extend((f"{kind}:{value}", place) for value in unique)
    findings.extend(
        _duplicates(shared, rule="duplicate-value", label="value across groups")
    )
    return findings


def _index(document: object) -> dict[tuple[str, str], Snapshot]:
    """Map ``(group, entry)`` names to their compatibility snapshot."""
    root = document if isinstance(document, dict) else {}
    index: dict[tuple[str, str], Snapshot] = {}
    for group in _objects(root.get("groups")):
        for entry in _objects(group.get("entries")):
            raw = entry.get("deprecated")
            details = (
                {str(key): value for key, value in raw.items()}
                if isinstance(raw, dict)
                else {}
            )
            index[_text(group, "name"), _text(entry, "name")] = Snapshot(
                value=_text(entry, "value"),
                deprecated=isinstance(raw, dict),
                remove_after=_text(details, "remove_after"),
            )
    return index


def baseline_findings(current: object, baseline: object) -> list[Finding]:
    """Compare a candidate registry with the released one.

    Args:
        current: Candidate registry JSON.
        baseline: Released registry JSON.

    Returns:
        Findings for unsafe removals, changed values, and a missing version bump.
    """
    now, before = _index(current), _index(baseline)
    version = _text(current, "version") if isinstance(current, dict) else ""
    released = _text(baseline, "version") if isinstance(baseline, dict) else ""
    findings: list[Finding] = []
    for (group, name), old in sorted(before.items()):
        where = f"{group}.{name}"
        new = now.get((group, name))
        if new is None and not old.deprecated:
            message = "removed without a prior deprecation release"
            findings.append(Finding(location=where, rule="removed", message=message))
        elif (
            new is None
            and old.remove_after
            and _version(version) < _version(old.remove_after)
        ):
            message = f"removed before remove_after {old.remove_after}"
            findings.append(Finding(location=where, rule="removed", message=message))
        elif new is not None and new.value != old.value:
            message = f"value changed {old.value!r} -> {new.value!r}; add a new entry"
            findings.append(
                Finding(location=where, rule="value-changed", message=message)
            )
    changed = canonical_digest(current) != canonical_digest(baseline)
    if changed and _version(version) <= _version(released):
        message = f"registry changed but version {version} is not above {released}"
        findings.append(Finding(location="version", rule="version", message=message))
    return findings


def drift_text_findings(
    text: str, *, where: str, registry_digest: str
) -> list[Finding]:
    """Check generated module text against the registry digest and its own body.

    Args:
        text: Content of a module written by the generator.
        where: Location used in findings.
        registry_digest: Canonical digest of the current registry.

    Returns:
        Findings for a missing header, a stale module, or a hand-edited body.
    """
    lines = text.splitlines(keepends=True)
    fields = {
        name: digest
        for line in lines[:_HEADER_LINES]
        if (match := _HEADER_FIELD.fullmatch(line.strip()))
        for name, digest in [match.groups()]
    }
    body = "".join(lines[_HEADER_LINES:]).replace("\r\n", "\n")
    if set(fields) != {"registry-sha256", "content-sha256"}:
        message = "provenance header missing; regenerate the file"
        return [Finding(location=where, rule="drift", message=message)]
    findings: list[Finding] = []
    if fields["registry-sha256"] != registry_digest:
        message = "stale: registry changed since generation; run generate_registry.py"
        findings.append(Finding(location=where, rule="drift", message=message))
    if fields["content-sha256"] != hashlib.sha256(body.encode("utf-8")).hexdigest():
        message = "edited by hand; change the registry and regenerate instead"
        findings.append(Finding(location=where, rule="drift", message=message))
    return findings


def drift_findings(generated: Path, *, registry_digest: str) -> list[Finding]:
    """Check that a generated module exists, matches the registry, and was not edited.

    Args:
        generated: Python or TypeScript module written by the generator.
        registry_digest: Canonical digest of the current registry.

    Returns:
        Findings for a missing, stale, or hand-edited module.

    Raises:
        OSError: If an existing file cannot be read.
    """
    where = generated.as_posix()
    if not generated.is_file():
        message = "generated file is missing; run generate_registry.py"
        return [Finding(location=where, rule="drift", message=message)]
    return drift_text_findings(
        generated.read_text(encoding="utf-8"),
        where=where,
        registry_digest=registry_digest,
    )


def _schema_path(registry: Path, document: object, explicit: Path | None) -> Path:
    """Choose the schema file from ``--schema`` or the registry's ``$schema``.

    Raises:
        RegistryInputError: No relative ``$schema`` path is available.
    """
    if explicit is not None:
        return explicit
    declared = _text(document, "$schema") if isinstance(document, dict) else ""
    if not declared or "://" in declared:
        message = "pass --schema; the registry has no relative $schema path"
        raise RegistryInputError(message)
    return registry.parent / declared


def check(
    registry: Path,
    *,
    schema: Path | None = None,
    outputs: Sequence[Path] = (),
    baseline: Path | None = None,
) -> list[Finding]:
    """Run every check and return findings.

    Args:
        registry: Registry JSON file.
        schema: Schema file; defaults to the registry's relative ``$schema``.
        outputs: Generated modules to check for drift.
        baseline: Released registry to compare against.

    Returns:
        Findings in a stable order.

    Raises:
        OSError: If an input file cannot be read.
        ValueError: If JSON is invalid or the schema is unsupported.
    """
    duplicates: list[str] = []
    document = load_json(registry, duplicates)
    schema_document = _as_schema(
        load_json(_schema_path(registry, document, schema), [])
    )
    findings = [
        Finding(
            location=registry.as_posix(),
            rule="duplicate-key",
            message=f"key {key!r} repeated",
        )
        for key in duplicates
    ]
    findings.extend(
        validate(document, schema_document, where="registry", root=schema_document)
    )
    findings.extend(semantic_findings(document))
    if baseline is not None:
        findings.extend(baseline_findings(document, load_json(baseline, [])))
    digest = canonical_digest(document)
    for output in outputs:
        findings.extend(drift_findings(output, registry_digest=digest))
    return findings


class SelfTestError(AssertionError):
    """A documented check did not behave as expected on synthetic input."""


_SELF_TEST_SCHEMA: Schema = {
    "type": "object",
    "required": ["version"],
    "additionalProperties": False,
    "properties": {"version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"}},
}
_SELF_TEST_REGISTRY: dict[str, object] = {
    "version": "1.0.0",
    "groups": [
        {
            "name": "Status",
            "kind": "enum",
            "entries": [
                {"name": "ACTIVE", "value": "active"},
                {"name": "ENABLED", "value": "active"},
            ],
        },
        {
            "name": "EventName",
            "kind": "event",
            "entries": [{"name": "CREATED", "value": "created"}],
        },
    ],
}


def _expect(message: str, *, ok: bool) -> None:
    """Raise ``SelfTestError`` with ``message`` unless ``ok`` is true.

    Raises:
        SelfTestError: ``ok`` is false.
    """
    if not ok:
        raise SelfTestError(message)


def self_test() -> None:
    """Exercise schema, semantic, and drift checks on synthetic input.

    Raises:
        SelfTestError: If a check misses a planted problem or flags clean input.
    """
    root = _SELF_TEST_SCHEMA
    clean_schema = validate({"version": "1.0.0"}, root, where="r", root=root)
    _expect(f"clean schema input flagged {clean_schema}", ok=not clean_schema)
    invalid = validate({"version": "one", "extra": 1}, root, where="r", root=root)
    expected = [r"does not match ^\d+\.\d+\.\d+$", "unexpected property 'extra'"]
    _expect(f"schema findings {invalid}", ok=[f.message for f in invalid] == expected)
    rules = sorted(item.rule for item in semantic_findings(_SELF_TEST_REGISTRY))
    _expect(f"semantic {rules}", ok=rules == ["duplicate-value", "value-pattern"])
    body = "x = 1\n"
    digest = canonical_digest(_SELF_TEST_REGISTRY)
    header = (
        "# Generated by generate_registry.py. Do not edit.\n"
        "# registry-version: 1.0.0\n"
        f"# registry-sha256: {digest}\n"
        f"# content-sha256: {hashlib.sha256(body.encode()).hexdigest()}\n"
    )
    clean = drift_text_findings(header + body, where="m", registry_digest=digest)
    _expect(f"drift on clean module {clean}", ok=not clean)
    edited = drift_text_findings(header + "x = 2\n", where="m", registry_digest=digest)
    _expect(f"hand edit not detected {edited}", ok=len(edited) == 1)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checks and print findings.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        0 when clean, 1 with findings, 2 for unreadable or unsupported input
        (argparse exits with 2 on invalid arguments).
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("registry", nargs="?", type=Path, help="registry JSON file")
    parser.add_argument("--schema", type=Path, help="registry JSON Schema file")
    parser.add_argument("--python", type=Path, help="generated Python module")
    parser.add_argument("--typescript", type=Path, help="generated TypeScript module")
    parser.add_argument("--baseline", type=Path, help="released registry JSON")
    parser.add_argument("--self-test", action="store_true", help="check the checker")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("Registry checker self-test passed.")
        return EXIT_CLEAN
    if args.registry is None:
        parser.error("give the registry JSON file")
    outputs = tuple(path for path in (args.python, args.typescript) if path is not None)
    try:
        findings = check(
            args.registry, schema=args.schema, outputs=outputs, baseline=args.baseline
        )
    except (OSError, ValueError) as error:
        print(f"Cannot check {args.registry}: {error}", file=sys.stderr)
        return EXIT_USAGE
    for finding in findings:
        print(finding.render())
    if findings:
        return EXIT_FINDINGS
    print(f"Registry {args.registry.as_posix()} is valid and outputs are current.")
    return EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
