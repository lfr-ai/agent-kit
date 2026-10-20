"""Check installed Python distribution licenses against a local allowlist.

The checker reads only installed metadata through 'importlib.metadata'. It never
downloads anything and does not read license files. License evidence is taken in
this order: the PEP 639 'License-Expression' field, then 'License ::' trove
classifiers, then a short 'License' field that parses as an SPDX expression.

SPDX expressions are evaluated conservatively: 'A OR B' passes when either side is
allowed; 'A AND B' passes only when both are. 'A WITH E' must be allowed as the
full 'A WITH E' string. Several classifiers on one distribution are combined with
AND because a classifier list does not say whether it offers a choice.

Findings are written as 'path:line: message', where the path is the distribution's
metadata location. Exit codes: 0 clean, 1 findings, 2 unusable configuration.
"""

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from importlib import metadata
from pathlib import Path
from typing import TextIO

_SCHEMA_VERSION = 1
_CONFIG_EXIT = 2
_MAX_CONFIG_BYTES = 1024 * 1024
_MAX_LICENSE_FIELD = 120
_CONFIG_FIELDS = frozenset(
    {"schema_version", "description", "allowed", "denied", "exceptions"}
)
_EXCEPTION_FIELDS = frozenset({"license", "reason", "expires"})
_NAME_RUN = re.compile(r"[-_.]+")
_TOKEN = re.compile(r"\(|\)|[^\s()]+")
_OPERATORS = frozenset({"and", "or", "with"})
_CLASSIFIERS = {
    "license :: osi approved :: mit license": "MIT",
    "license :: osi approved :: mit no attribution license (mit-0)": "MIT-0",
    "license :: osi approved :: apache software license": "Apache-2.0",
    "license :: osi approved :: isc license (iscl)": "ISC",
    "license :: osi approved :: bsd license": "LicenseRef-BSD-unspecified",
    "license :: osi approved :: python software foundation license": "PSF-2.0",
    "license :: osi approved :: mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "license :: osi approved :: the unlicense (unlicense)": "Unlicense",
    "license :: osi approved :: zlib/libpng license": "Zlib",
    "license :: osi approved :: boost software license 1.0 (bsl-1.0)": "BSL-1.0",
    "license :: osi approved :: eclipse public license 2.0 (epl-2.0)": "EPL-2.0",
    "license :: osi approved :: zope public license": "ZPL-2.1",
    "license :: osi approved :: gnu general public license v2 (gplv2)": "GPL-2.0-only",
    "license :: osi approved :: gnu general public license v2 or later (gplv2+)": (
        "GPL-2.0-or-later"
    ),
    "license :: osi approved :: gnu general public license v3 (gplv3)": "GPL-3.0-only",
    "license :: osi approved :: gnu general public license v3 or later (gplv3+)": (
        "GPL-3.0-or-later"
    ),
    "license :: osi approved :: gnu lesser general public license v2 (lgplv2)": (
        "LGPL-2.0-only"
    ),
    "license :: osi approved :: gnu lesser general public license v2 or later (lgplv2+)": (
        "LGPL-2.0-or-later"
    ),
    "license :: osi approved :: gnu lesser general public license v3 (lgplv3)": (
        "LGPL-3.0-only"
    ),
    "license :: osi approved :: gnu lesser general public license v3 or later (lgplv3+)": (
        "LGPL-3.0-or-later"
    ),
    "license :: osi approved :: gnu affero general public license v3": "AGPL-3.0-only",
    "license :: osi approved :: gnu affero general public license v3 or later (agplv3+)": (
        "AGPL-3.0-or-later"
    ),
    "license :: public domain": "LicenseRef-Public-Domain",
    "license :: other/proprietary license": "LicenseRef-Proprietary",
}


@dataclass(frozen=True, kw_only=True, slots=True)
class Waiver:
    """A reviewed, optionally expiring exception for one distribution."""

    license: str
    reason: str
    expires: date | None


@dataclass(frozen=True, kw_only=True, slots=True)
class Allowlist:
    """Allowed and denied SPDX identifiers plus per-distribution exceptions."""

    allowed: frozenset[str]
    denied: frozenset[str]
    exceptions: dict[str, Waiver]


@dataclass(frozen=True, kw_only=True, slots=True)
class Record:
    """License evidence for one installed distribution."""

    name: str
    version: str
    expression: str | None
    source: str
    location: str


@dataclass(frozen=True, kw_only=True, slots=True)
class Result:
    """Evaluation status for one distribution."""

    record: Record
    status: str
    detail: str


def canonical_name(name: str) -> str:
    """Normalize a distribution name as package indexes do."""
    return _NAME_RUN.sub("-", name).casefold()


def _key(identifier: str) -> str:
    """Compare SPDX identifiers case-insensitively."""
    return identifier.casefold()


class LicenseInputIssue(StrEnum):
    """Supported license input validation failures and their stable messages."""

    IDENTIFIER_LIST = "{label} must be a list of non-empty strings"
    EXCEPTION_FIELDS = f"exceptions.{{name}} must use only {sorted(_EXCEPTION_FIELDS)}"
    EXCEPTION_LICENSE = "exceptions.{name}.license must name the observed license"
    EXCEPTION_REASON = "exceptions.{name}.reason must record the review decision"
    EXCEPTION_EXPIRY = "exceptions.{name}.expires must be an ISO date"
    ALLOWLIST_OBJECT = "allowlist must be a JSON object"
    UNKNOWN_FIELD = "unknown allowlist field '{field}'"
    SCHEMA_VERSION = f"schema_version must be {_SCHEMA_VERSION}"
    CONFLICTING_IDENTIFIER = "'{identifier}' is both allowed and denied"
    EXCEPTIONS_OBJECT = "exceptions must be an object keyed by distribution name"
    ALLOWLIST_SIZE = f"allowlist exceeds {_MAX_CONFIG_BYTES} bytes"
    EXPRESSION_END = "license expression ends unexpectedly"
    UNCLOSED_PARENTHESIS = "license expression has an unclosed parenthesis"
    UNEXPECTED_TERM = "license expression has unexpected '{token}'"
    INCOMPLETE_WITH = "license expression has an incomplete WITH clause"
    EMPTY_EXPRESSION = "license expression is empty"


class LicenseInputError(ValueError):
    """An input violates the license input contract."""

    def __init__(
        self,
        issue: LicenseInputIssue,
        *,
        label: str | None = None,
        name: str | None = None,
        field: str | None = None,
        identifier: str | None = None,
        token: str | None = None,
    ) -> None:
        """Describe a supported input failure.

        Args:
            issue: The violated input invariant.
            label: Diagnostic label for the invalid input.
            name: Diagnostic name for the invalid input.
            field: Diagnostic field for the invalid input.
            identifier: Diagnostic identifier for the invalid input.
            token: Diagnostic token for the invalid input.
        """
        super().__init__(
            issue.value.format(
                label=label, name=name, field=field, identifier=identifier, token=token
            )
        )


class LicenseInputTypeError(TypeError):
    """An input has the wrong Python type for the license input contract."""

    def __init__(
        self,
        issue: LicenseInputIssue,
        *,
        label: str | None = None,
        name: str | None = None,
    ) -> None:
        """Describe a wrong input type.

        Args:
            issue: The violated input invariant.
            label: Diagnostic label for the invalid input.
            name: Diagnostic name for the invalid input.
        """
        super().__init__(issue.value.format(label=label, name=name))


def _identifiers(value: object, label: str) -> frozenset[str]:
    """Validate a list of non-empty identifier strings."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LicenseInputTypeError(LicenseInputIssue.IDENTIFIER_LIST, label=label)
    if not all(item.strip() for item in value):
        raise LicenseInputError(LicenseInputIssue.IDENTIFIER_LIST, label=label)
    return frozenset(_key(item.strip()) for item in value)


def _exception(name: str, value: object) -> Waiver:
    """Validate one exception entry."""
    if not isinstance(value, dict):
        raise LicenseInputTypeError(LicenseInputIssue.EXCEPTION_FIELDS, name=name)
    if value.keys() - _EXCEPTION_FIELDS:
        raise LicenseInputError(LicenseInputIssue.EXCEPTION_FIELDS, name=name)
    license_value = value.get("license")
    reason = value.get("reason")
    if "license" not in value:
        raise LicenseInputError(LicenseInputIssue.EXCEPTION_LICENSE, name=name)
    if not isinstance(license_value, str):
        raise LicenseInputTypeError(LicenseInputIssue.EXCEPTION_LICENSE, name=name)
    if not license_value.strip():
        raise LicenseInputError(LicenseInputIssue.EXCEPTION_LICENSE, name=name)
    if "reason" not in value:
        raise LicenseInputError(LicenseInputIssue.EXCEPTION_REASON, name=name)
    if not isinstance(reason, str):
        raise LicenseInputTypeError(LicenseInputIssue.EXCEPTION_REASON, name=name)
    if not reason.strip():
        raise LicenseInputError(LicenseInputIssue.EXCEPTION_REASON, name=name)
    expires = value.get("expires")
    if expires is not None and not isinstance(expires, str):
        raise LicenseInputTypeError(LicenseInputIssue.EXCEPTION_EXPIRY, name=name)
    return Waiver(
        license=license_value.strip(),
        reason=reason.strip(),
        expires=date.fromisoformat(expires) if expires else None,
    )


def parse_allowlist(text: str) -> Allowlist:
    """Validate allowlist JSON against its closed schema.

    Raises:
        ValueError: A required field is missing or an allowlist value is invalid.
        TypeError: The document or a present field has the wrong Python type.
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        raise LicenseInputTypeError(LicenseInputIssue.ALLOWLIST_OBJECT)
    unknown = sorted(data.keys() - _CONFIG_FIELDS)
    if unknown:
        raise LicenseInputError(LicenseInputIssue.UNKNOWN_FIELD, field=unknown[0])
    version = data.get("schema_version")
    if "schema_version" not in data:
        raise LicenseInputError(LicenseInputIssue.SCHEMA_VERSION)
    if type(version) is not int:
        raise LicenseInputTypeError(LicenseInputIssue.SCHEMA_VERSION)
    if version != _SCHEMA_VERSION:
        raise LicenseInputError(LicenseInputIssue.SCHEMA_VERSION)
    if "allowed" not in data:
        raise LicenseInputError(LicenseInputIssue.IDENTIFIER_LIST, label="allowed")
    allowed = _identifiers(data.get("allowed"), "allowed")
    denied = _identifiers(data.get("denied", []), "denied")
    overlap = sorted(allowed & denied)
    if overlap:
        raise LicenseInputError(
            LicenseInputIssue.CONFLICTING_IDENTIFIER, identifier=overlap[0]
        )
    raw_exceptions = data.get("exceptions", {})
    if not isinstance(raw_exceptions, dict):
        raise LicenseInputTypeError(LicenseInputIssue.EXCEPTIONS_OBJECT)
    exceptions = {
        canonical_name(name): _exception(name, value)
        for name, value in raw_exceptions.items()
    }
    return Allowlist(allowed=allowed, denied=denied, exceptions=exceptions)


def load_allowlist(path: Path) -> Allowlist:
    """Read a bounded allowlist file and validate it."""
    with path.open("rb") as handle:
        data = handle.read(_MAX_CONFIG_BYTES + 1)
    if len(data) > _MAX_CONFIG_BYTES:
        raise LicenseInputError(LicenseInputIssue.ALLOWLIST_SIZE)
    return parse_allowlist(data.decode("utf-8-sig"))


class _ExpressionParser:
    """Recursive-descent evaluator for one tokenized SPDX license expression."""

    def __init__(self, tokens: list[str], allowlist: Allowlist) -> None:
        """Prepare to evaluate one expression.

        Args:
            tokens: Expression tokens, with parentheses as separate tokens.
            allowlist: Allowed and denied identifiers that decide each leaf.
        """
        self._tokens = tokens
        self._allowlist = allowlist
        self.position = 0

    def _peek(self) -> str | None:
        """Return the current token in lowercase, or None at the end."""
        if self.position >= len(self._tokens):
            return None
        return self._tokens[self.position].casefold()

    def expression(self) -> str:
        """Parse 'conjunction (OR conjunction)*'; OR passes if any side passes."""
        statuses = [self._conjunction()]
        while self._peek() == "or":
            self.position += 1
            statuses.append(self._conjunction())
        if "allowed" in statuses:
            return "allowed"
        return "unknown" if "unknown" in statuses else "denied"

    def _conjunction(self) -> str:
        """Parse 'factor (AND factor)*'; AND passes only if every side passes."""
        statuses = [self._factor()]
        while self._peek() == "and":
            self.position += 1
            statuses.append(self._factor())
        if "denied" in statuses:
            return "denied"
        return "unknown" if "unknown" in statuses else "allowed"

    def _factor(self) -> str:
        """Parse a parenthesized expression or one license with optional WITH."""
        current = self._peek()
        if current is None:
            raise LicenseInputError(LicenseInputIssue.EXPRESSION_END)
        if current == "(":
            self.position += 1
            status = self.expression()
            if self._peek() != ")":
                raise LicenseInputError(LicenseInputIssue.UNCLOSED_PARENTHESIS)
            self.position += 1
            return status
        if current == ")" or current in _OPERATORS:
            raise LicenseInputError(LicenseInputIssue.UNEXPECTED_TERM, token=current)
        base = self._tokens[self.position]
        self.position += 1
        leaf = base
        if self._peek() == "with":
            self.position += 1
            addition = self._peek()
            if addition is None or addition in {"(", ")"} or addition in _OPERATORS:
                raise LicenseInputError(LicenseInputIssue.INCOMPLETE_WITH)
            leaf = f"{base} WITH {self._tokens[self.position]}"
            self.position += 1
        if _key(leaf) in self._allowlist.allowed:
            return "allowed"
        if _key(leaf) in self._allowlist.denied or _key(base) in self._allowlist.denied:
            return "denied"
        return "unknown"


def classify(expression: str, allowlist: Allowlist) -> str:
    """Return 'allowed', 'denied', or 'unknown' for an SPDX expression."""
    tokens = _TOKEN.findall(expression)
    if not tokens:
        raise LicenseInputError(LicenseInputIssue.EMPTY_EXPRESSION)
    parser = _ExpressionParser(tokens, allowlist)
    status = parser.expression()
    if parser.position != len(tokens):
        raise LicenseInputError(
            LicenseInputIssue.UNEXPECTED_TERM, token=tokens[parser.position]
        )
    return status


def license_evidence(
    expression: str | None, classifiers: Iterable[str], license_field: str | None
) -> tuple[str | None, str]:
    """Choose the strongest available license statement and name its source."""
    if expression and expression.strip():
        return expression.strip(), "License-Expression"
    mapped: list[str] = []
    for classifier in classifiers:
        text = " ".join(classifier.split()).casefold()
        if not text.startswith("license ::"):
            continue
        mapped.append(_CLASSIFIERS.get(text, f"LicenseRef-Unmapped-Classifier({text})"))
    if mapped:
        unique = list(dict.fromkeys(mapped))
        if any(item.startswith("LicenseRef-Unmapped") for item in unique):
            return None, "Classifier (unmapped: " + "; ".join(unique) + ")"
        joined = " AND ".join(unique)
        return (joined if len(unique) == 1 else f"({joined})"), "Classifier"
    if license_field:
        text = license_field.strip()
        if text and len(text) <= _MAX_LICENSE_FIELD and "\n" not in text:
            return text, "License"
    return None, "none"


def evaluate(record: Record, allowlist: Allowlist, today: date) -> Result:
    """Evaluate one distribution, honoring only unexpired, matching exceptions."""
    exception = allowlist.exceptions.get(canonical_name(record.name))
    observed = record.expression or "UNKNOWN"
    if exception is not None:
        if exception.expires is not None and exception.expires < today:
            return Result(
                record=record,
                status="expired-exception",
                detail=f"exception expired on {exception.expires.isoformat()}",
            )
        if _key(exception.license) == _key(observed):
            return Result(record=record, status="excepted", detail=exception.reason)
    if record.expression is None:
        return Result(
            record=record,
            status="unknown",
            detail=f"no usable license ({record.source})",
        )
    try:
        status = classify(record.expression, allowlist)
    except ValueError as error:
        return Result(record=record, status="unknown", detail=str(error))
    return Result(record=record, status=status, detail=record.expression)


def installed_records(paths: list[str] | None) -> list[Record]:
    """Collect license evidence for each installed distribution, first on path wins."""
    records: dict[str, Record] = {}
    found = metadata.distributions(path=paths) if paths else metadata.distributions()
    for distribution in found:
        meta = distribution.metadata
        name = meta.get("Name")
        if not name:
            continue
        key = canonical_name(name)
        if key in records:
            continue
        expression, source = license_evidence(
            meta.get("License-Expression"),
            meta.get_all("Classifier") or [],
            meta.get("License"),
        )
        location = distribution.locate_file("")
        for item in distribution.files or ():
            if item.name in {"METADATA", "PKG-INFO"}:
                location = distribution.locate_file(item)
                break
        records[key] = Record(
            name=name,
            version=meta.get("Version") or "unknown",
            expression=expression,
            source=source,
            location=str(location),
        )
    return [records[key] for key in sorted(records)]


def report(results: list[Result], stream: TextIO, output_format: str) -> int:
    """Write findings and return 1 when any distribution is not acceptable."""
    failing = [item for item in results if item.status not in {"allowed", "excepted"}]
    if output_format == "json":
        payload = [
            {
                "name": item.record.name,
                "version": item.record.version,
                "status": item.status,
                "source": item.record.source,
                "detail": item.detail,
            }
            for item in results
        ]
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        stream.writelines(
            f"{item.record.location}:1: {item.record.name} {item.record.version}: "
            f"{item.status} license ({item.record.source}): {item.detail}\n"
            for item in failing
        )
        stream.write(
            f"license-guard: {len(results)} distributions, {len(failing)} findings\n"
        )
    return 1 if failing else 0


def _self_test() -> int:
    """Run embedded regressions without reading installed metadata."""
    allowlist = parse_allowlist(
        json.dumps(
            {
                "schema_version": 1,
                "allowed": [
                    "MIT",
                    "Apache-2.0",
                    "GPL-2.0-only WITH Classpath-exception-2.0",
                ],
                "denied": ["AGPL-3.0-only", "GPL-2.0-only"],
                "exceptions": {
                    "Legacy_Tool": {"license": "LicenseRef-X", "reason": "reviewed"}
                },
            }
        )
    )
    cases = (
        ("MIT", "allowed"),
        ("mit OR AGPL-3.0-only", "allowed"),
        ("MIT AND AGPL-3.0-only", "denied"),
        ("(MIT AND Apache-2.0) OR BSD-3-Clause", "allowed"),
        ("GPL-2.0-only WITH Classpath-exception-2.0", "allowed"),
        ("GPL-2.0-only", "denied"),
        ("LicenseRef-Custom", "unknown"),
        ("MIT AND LicenseRef-Custom", "unknown"),
    )
    failures = [
        f"{text}: {classify(text, allowlist)} != {expected}"
        for text, expected in cases
        if classify(text, allowlist) != expected
    ]
    record = Record(
        name="legacy.tool",
        version="1",
        expression="LicenseRef-X",
        source="License",
        location="x",
    )
    if evaluate(record, allowlist, date(2026, 1, 1)).status != "excepted":
        failures.append("exception not applied")
    evidence = license_evidence(None, ["License :: OSI Approved :: MIT License"], None)
    if evidence != ("MIT", "Classifier"):
        failures.append(f"classifier mapping {evidence}")
    for failure in failures:
        print(f"self-test: {failure}")
    if failures:
        return 1
    print(f"self-test passed: {len(cases) + 2} cases")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Check installed distributions and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--allowlist", type=Path, help="allowlist JSON file")
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        help="site-packages directory to scan; repeatable (default: sys.path)",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--today", type=date.fromisoformat, help="ISO date for expiry")
    parser.add_argument("--self-test", action="store_true", help="run embedded checks")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.allowlist is None:
        parser.error("--allowlist is required")
    try:
        allowlist = load_allowlist(args.allowlist)
    except (OSError, UnicodeError, ValueError, LicenseInputTypeError) as error:
        print(f"{args.allowlist}:1: allowlist is unusable: {error}", file=sys.stderr)
        return _CONFIG_EXIT
    today = args.today or datetime.now(tz=UTC).date()
    results = [
        evaluate(record, allowlist, today) for record in installed_records(args.paths)
    ]
    return report(results, sys.stdout, args.format)


if __name__ == "__main__":
    raise SystemExit(main())
