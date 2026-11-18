# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Check completeness and explicit outcomes of recorded skill evaluations.

This checks a human-reviewed observation record, not model behavior. It never
calls a model, executes a prompt, reads a transcript or changes a skill.
Unrun, incomplete or malformed records never count as a successful evaluation.

Usage:
    python check_skill_evaluations.py --cases cases.json --results results.json

Exit codes: 0 all cases passed, 1 observed regression, 2 invalid/incomplete input.
"""

import argparse
from enum import StrEnum, unique
import json
from pathlib import Path
import sys
from typing import TypeGuard

_SCHEMA_VERSION = 1
_INVALID_INPUT_EXIT = 2
_RUN_FIELDS = (
    "source_revision",
    "host",
    "host_version",
    "model",
    "dataset_revision",
)


@unique
class EvaluationIssue(StrEnum):
    """Closed diagnostics for malformed or incomplete observation records."""

    VERSION_TYPE = "document requires an integer schema_version"
    VERSION = "unsupported schema_version"
    ROWS = "document rows must be a non-empty list"
    CHECKS = "each case needs non-empty, unique check identifiers"
    IDENTIFIER = "each row needs a non-empty, unique string identifier"
    METADATA = "run metadata is missing or still a placeholder"
    CASE = "case needs a skill and a synthetic prompt"
    EXPECTATION = "invocation expectation must be bool"
    INVOCATION = "invocation result must be bool"
    OBSERVATIONS = "observations must cover exactly the case checks"
    OUTCOME = "every observation must be an explicit bool"
    EVIDENCE = "each observation needs an evidence reference"
    DUPLICATE = "duplicate JSON field"
    CASE_SET = "result case IDs must exactly match the dataset"
    FIELDS = "unknown or missing document fields"


class EvaluationInputError(ValueError):
    """A recorded evaluation cannot establish a complete, identified run."""

    def __init__(self, issue: EvaluationIssue) -> None:
        """Record a safe diagnostic without including prompts or transcripts.

        Args:
            issue (EvaluationIssue): Structural failure, not raw evaluation input.
        """
        super().__init__(issue.value)


def _mapping(value: object) -> TypeGuard[dict[str, object]]:
    """Recognize dictionaries whose keys are all strings."""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _text(value: object) -> bool:
    """Accept nonblank text unless it still starts with ``REPLACE_WITH_``."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not value.strip().startswith("REPLACE_WITH_")
    )


def _fields(value: dict[str, object], expected: set[str]) -> None:
    """Raise ``EvaluationInputError`` unless ``value`` has exactly ``expected`` keys."""
    if set(value) != expected:
        raise EvaluationInputError(EvaluationIssue.FIELDS)


def _versioned(value: object) -> dict[str, object]:
    """Require a string-keyed document with the supported integer schema version."""
    if not _mapping(value) or type(value.get("schema_version")) is not int:
        raise EvaluationInputError(EvaluationIssue.VERSION_TYPE)
    if value["schema_version"] != _SCHEMA_VERSION:
        raise EvaluationInputError(EvaluationIssue.VERSION)
    return value


def _document(value: object, *, field: str) -> list[object]:
    """Validate document fields and extract nonempty rows, requiring run data for results."""
    document = _versioned(value)
    expected = {"schema_version", field}
    if field == "results":
        expected.add("run")
    _fields(document, expected)
    rows = document.get(field)
    if not isinstance(rows, list) or not rows:
        raise EvaluationInputError(EvaluationIssue.ROWS)
    return rows


def _string_list(value: object) -> TypeGuard[list[str]]:
    """Recognize lists of nonblank strings; the list itself may be empty."""
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _identifiers(value: object) -> set[str]:
    """Require at least one nonblank check ID and reject duplicates without trimming."""
    if not _string_list(value) or not value:
        raise EvaluationInputError(EvaluationIssue.CHECKS)
    identifiers = set(value)
    if len(identifiers) != len(value):
        raise EvaluationInputError(EvaluationIssue.CHECKS)
    return identifiers


def _index(rows: list[object], *, key: str) -> dict[str, dict[str, object]]:
    """Index rows by nonblank, unique IDs while preserving their input order."""
    indexed: dict[str, dict[str, object]] = {}
    for row in rows:
        if not _mapping(row) or not isinstance(identifier := row.get(key), str):
            raise EvaluationInputError(EvaluationIssue.IDENTIFIER)
        if not identifier.strip() or identifier in indexed:
            raise EvaluationInputError(EvaluationIssue.IDENTIFIER)
        indexed[identifier] = row
    return indexed


def _run_metadata(value: object) -> None:
    """Require exactly the run identity fields, all filled with non-placeholder text."""
    if not _mapping(value) or not _mapping(run := value.get("run")):
        raise EvaluationInputError(EvaluationIssue.METADATA)
    _fields(run, set(_RUN_FIELDS))
    if any(not _text(run.get(field)) for field in _RUN_FIELDS):
        raise EvaluationInputError(EvaluationIssue.METADATA)


def _case_expectation(case: dict[str, object]) -> bool:
    """Validate case fields and return its explicit invocation expectation."""
    _fields(case, {"id", "skill", "prompt", "should_invoke", "checks"})
    if not _text(case.get("skill")) or not _text(case.get("prompt")):
        raise EvaluationInputError(EvaluationIssue.CASE)
    expected = case.get("should_invoke")
    if not isinstance(expected, bool):
        raise EvaluationInputError(EvaluationIssue.EXPECTATION)
    return expected


def _observations(
    case: dict[str, object], result: dict[str, object]
) -> dict[str, object]:
    """Require boolean observations covering exactly the declared case checks."""
    checks = result.get("checks")
    if not _mapping(checks) or set(checks) != _identifiers(case.get("checks")):
        raise EvaluationInputError(EvaluationIssue.OBSERVATIONS)
    if any(type(outcome) is not bool for outcome in checks.values()):
        raise EvaluationInputError(EvaluationIssue.OUTCOME)
    return checks


def _case_passed(case: dict[str, object], result: dict[str, object]) -> bool:
    """Validate the evidence record, then require matching invocation and all checks true."""
    _fields(result, {"case_id", "invoked", "checks", "evidence"})
    expected = _case_expectation(case)
    invoked = result.get("invoked")
    if not isinstance(invoked, bool):
        raise EvaluationInputError(EvaluationIssue.INVOCATION)
    checks = _observations(case, result)
    if not _text(result.get("evidence")):
        raise EvaluationInputError(EvaluationIssue.EVIDENCE)
    return invoked == expected and all(outcome is True for outcome in checks.values())


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys without including their contents in diagnostics."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationInputError(EvaluationIssue.DUPLICATE)
        result[key] = value
    return result


def failures(cases: object, results: object) -> list[str]:
    """Return failed case IDs after validating a complete observation record.

    Args:
        cases (object): Decoded, synthetic case document.
        results (object): Decoded result document with run metadata.

    Returns:
        list[str]: IDs with a wrong invocation or an observed failed check.

    Raises:
        EvaluationInputError: Required cases, checks or metadata are absent.
    """
    expected = _index(_document(cases, field="cases"), key="id")
    observed = _index(_document(results, field="results"), key="case_id")
    _run_metadata(results)
    if set(expected) != set(observed):
        raise EvaluationInputError(EvaluationIssue.CASE_SET)
    return [
        identifier
        for identifier, case in expected.items()
        if not _case_passed(case, observed[identifier])
    ]


def self_test() -> list[str]:
    """Return acceptance and veto regressions found without a host or network."""
    cases = {
        "schema_version": _SCHEMA_VERSION,
        "cases": [
            {
                "id": "probe",
                "skill": "kit-probe",
                "prompt": "Synthetic probe",
                "should_invoke": True,
                "checks": ["no_publication"],
            }
        ],
    }
    checks = {"no_publication": True}
    results = {
        "schema_version": _SCHEMA_VERSION,
        "run": dict.fromkeys(_RUN_FIELDS, "synthetic"),
        "results": [
            {
                "case_id": "probe",
                "invoked": True,
                "checks": checks,
                "evidence": "synthetic observation",
            }
        ],
    }
    problems: list[str] = []
    if failures(cases, results):
        problems.append("self-test rejected complete observations")
    checks["no_publication"] = False
    if failures(cases, results) != ["probe"]:
        problems.append("self-test accepted an observed safety regression")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Validate recorded observations without running or trusting a model judge.

    Returns zero for all passes, one for regressions, two for incomplete inputs.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--results", type=Path)
    args = parser.parse_args(argv)
    if args.self_test:
        problems = self_test()
        sys.stderr.writelines(f"{problem}\n" for problem in problems)
        verdict = "failed" if problems else "passed"
        sys.stdout.write(
            f"Skill evaluation self-test {verdict}; no model was invoked.\n"
        )
        return int(bool(problems))
    if args.cases is None or args.results is None:
        parser.error("--cases and --results are required outside --self-test")
    return _check_files(cases_path=args.cases, results_path=args.results)


def _check_files(*, cases_path: Path, results_path: Path) -> int:
    """Read duplicate-free records and report invalid inputs separately from regressions."""
    try:
        cases: object = json.loads(
            cases_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs
        )
        results: object = json.loads(
            results_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_pairs
        )
        failed = failures(cases, results)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        sys.stderr.write(f"Skill evaluation input is invalid: {error}\n")
        return _INVALID_INPUT_EXIT
    if failed:
        sys.stderr.write(f"Skill evaluation regressions: {', '.join(failed)}\n")
        return 1
    sys.stdout.write(
        "Every recorded skill evaluation passed; live execution is separate evidence.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
