"""Pin authored enum values without executing portable modules or their imports."""

import ast
from enum import StrEnum
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_CONTRACTS = (
    (
        "scripts/checks/release.py",
        "_ArtifactKind",
        {"WHEEL": "wheel", "SDIST": "sdist", "SOURCE": "source"},
    ),
    (
        "packages/ai/.apm/skills/kit-agent-systems/assets/agent_tool_contract.py.template",
        "SideEffect",
        {"NONE": "none", "WRITE": "write", "EXTERNAL": "external"},
    ),
    (
        "packages/ai/.apm/skills/kit-agent-systems/assets/agent_tool_contract.py.template",
        "ToolErrorCode",
        {
            "UNKNOWN_TOOL": "unknown_tool",
            "INVALID_ARGUMENTS": "invalid_arguments",
            "APPROVAL_REQUIRED": "approval_required",
            "NOT_FOUND": "not_found",
            "UNAVAILABLE": "unavailable",
        },
    ),
    (
        "packages/ai/.apm/skills/kit-agent-systems/assets/supervisor_loop.py.template",
        "Outcome",
        {
            "COMPLETED": "completed",
            "STEP_BUDGET": "step_budget_exhausted",
            "COST_BUDGET": "cost_budget_exhausted",
            "DEADLINE": "deadline_exceeded",
            "REPEATED_ACTION": "repeated_action",
        },
    ),
    (
        "packages/ai/.apm/skills/kit-llm-client/assets/llm_port.py.template",
        "Role",
        {"SYSTEM": "system", "USER": "user", "ASSISTANT": "assistant"},
    ),
    (
        "packages/ai/.apm/skills/kit-retrieval/assets/retrieval_contracts.py.template",
        "EvidenceStatus",
        {
            "SUFFICIENT": "sufficient",
            "INSUFFICIENT": "insufficient",
            "NO_EVIDENCE": "no_evidence",
        },
    ),
    (
        "packages/ai/.apm/skills/kit-server-streaming/assets/stream_events.py.template",
        "EventName",
        {"START": "start", "DELTA": "delta", "PROGRESS": "progress", "END": "end"},
    ),
    (
        "packages/ai/.apm/skills/kit-server-streaming/assets/stream_events.py.template",
        "EndStatus",
        {
            "COMPLETED": "completed",
            "FAILED": "failed",
            "CANCELLED": "cancelled",
            "TIMEOUT": "timeout",
        },
    ),
    (
        "packages/ai/.apm/skills/kit-task-queue/assets/task_contracts.py.template",
        "ClaimState",
        {"ACQUIRED": "acquired", "IN_PROGRESS": "in_progress", "DONE": "done"},
    ),
    (
        "packages/ai/.apm/skills/kit-task-queue/assets/worker.py.template",
        "Outcome",
        {
            "ACKED": "acked",
            "DUPLICATE": "duplicate",
            "DEFERRED": "deferred",
            "RETRIED": "retried",
            "DEAD_LETTERED": "dead_lettered",
            "LEASE_LOST": "lease_lost",
        },
    ),
    (
        "packages/backend/.apm/skills/kit-auth/assets/policy.py.template",
        "Role",
        {"VIEWER": "viewer", "EDITOR": "editor", "ADMIN": "admin"},
    ),
    (
        "packages/backend/.apm/skills/kit-auth/assets/tokens.py.template",
        "RejectionReason",
        {
            "MALFORMED": "malformed",
            "UNSUPPORTED_ALGORITHM": "unsupported_algorithm",
            "WRONG_TYPE": "wrong_type",
            "UNKNOWN_KEY": "unknown_key",
            "BAD_SIGNATURE": "bad_signature",
            "EXPIRED": "expired",
            "NOT_YET_VALID": "not_yet_valid",
            "WRONG_ISSUER": "wrong_issuer",
            "WRONG_AUDIENCE": "wrong_audience",
            "MISSING_CLAIM": "missing_claim",
            "KEYS_UNAVAILABLE": "keys_unavailable",
        },
    ),
    (
        "packages/backend/.apm/skills/kit-cli-tool/assets/cli.py.template",
        "Source",
        {"DEFAULT": "default", "FILE": "file", "ENV": "env", "FLAG": "flag"},
    ),
    (
        "packages/backend/.apm/skills/kit-domain-model/assets/aggregate.py.template",
        "OrderStatus",
        {"DRAFT": "draft", "CONFIRMED": "confirmed", "CANCELLED": "cancelled"},
    ),
    (
        "packages/backend/.apm/skills/kit-domain-model/assets/check_port_adapter_binding.py",
        "_CallableKind",
        {
            "NORMAL": "normal",
            "GENERATOR": "generator",
            "COROUTINE": "coroutine",
            "ASYNC_GENERATOR": "async generator",
        },
    ),
    (
        "packages/backend/.apm/skills/kit-fastapi-service/assets/rate_limit.py.template",
        "FailureMode",
        {"OPEN": "open", "CLOSED": "closed"},
    ),
    (
        "packages/backend/.apm/skills/kit-fastapi-service/assets/rate_limit.py.template",
        "RateOutcome",
        {
            "ALLOWED": "allowed",
            "LIMITED": "limited",
            "FAILED_OPEN": "failed_open",
            "FAILED_CLOSED": "failed_closed",
        },
    ),
    (
        "packages/backend/.apm/skills/kit-python-service/assets/enum.py.template",
        "OrderStatus",
        {
            "DRAFT": "draft",
            "CONFIRMED": "confirmed",
            "SHIPPED": "shipped",
            "CANCELLED": "cancelled",
        },
    ),
    (
        "packages/backend/.apm/skills/kit-python-service/assets/resilience.py.template",
        "CircuitState",
        {"CLOSED": "closed", "OPEN": "open", "HALF_OPEN": "half_open"},
    ),
    (
        "packages/backend/.apm/skills/kit-python-service/assets/settings.py.template",
        "Environment",
        {"DEVELOPMENT": "development", "TEST": "test", "PRODUCTION": "production"},
    ),
    (
        "packages/backend/.apm/skills/kit-sql-persistence/assets/orders.py.template",
        "OrderStatus",
        {
            "DRAFT": "draft",
            "CONFIRMED": "confirmed",
            "SHIPPED": "shipped",
            "CANCELLED": "cancelled",
        },
    ),
    (
        "packages/delivery/delivery_tools/catalog.py",
        "_ValueType",
        {
            "STRING": "string",
            "BOOLEAN": "boolean",
            "NUMBER": "number",
            "OBJECT": "object",
            "STEP": "step",
            "STEP_LIST": "stepList",
            "JOB": "job",
            "JOB_LIST": "jobList",
            "DEPLOYMENT": "deployment",
            "DEPLOYMENT_LIST": "deploymentList",
            "STAGE": "stage",
            "STAGE_LIST": "stageList",
        },
    ),
    (
        "packages/runtime/src/platform_kit_runtime/application/readiness.py",
        "ReadinessFailure",
        {"PROBE_FAILED": "probe_failed", "TIMEOUT": "timeout"},
    ),
    (
        "packages/runtime/src/platform_kit_runtime/core/ai.py",
        "AIRole",
        {"SYSTEM": "system", "USER": "user", "ASSISTANT": "assistant"},
    ),
    (
        "packages/runtime/src/platform_kit_runtime/core/ai.py",
        "AIFinishReason",
        {"STOP": "stop", "LENGTH": "length"},
    ),
    (
        "packages/runtime/src/platform_kit_runtime/presentation/health.py",
        "HealthStatus",
        {"OK": "ok", "READY": "ready"},
    ),
    (
        "packages/runtime/src/platform_kit_runtime/presentation/identity/problems.py",
        "IdentityProblemCode",
        {
            "INVALID_CALLBACK": "invalid_callback",
            "AUTHENTICATION_REQUIRED": "authentication_required",
            "PERMISSION_DENIED": "permission_denied",
            "UNAVAILABLE": "identity_unavailable",
            "UPSTREAM_FAILURE": "identity_upstream_failure",
            "AVATAR_MISSING": "avatar_missing",
            "INTERNAL": "identity_internal_error",
        },
    ),
    (
        "packages/runtime/src/platform_kit_runtime/presentation/problems.py",
        "ProblemCode",
        {
            "NOT_READY": "not_ready",
            "INVALID_REQUEST": "invalid_request",
            "NOT_FOUND": "not_found",
            "METHOD_NOT_ALLOWED": "method_not_allowed",
            "HTTP_ERROR": "http_error",
            "INTERNAL_ERROR": "internal_error",
            "RATE_LIMITED": "rate_limited",
        },
    ),
    (
        "packages/shared/.apm/skills/kit-hexagonal-architecture/assets/check_ports_adapters.py",
        "_CallableKind",
        {
            "NORMAL": "normal",
            "GENERATOR": "generator",
            "COROUTINE": "coroutine",
            "ASYNC_GENERATOR": "async generator",
        },
    ),
    (
        "packages/shared/.apm/skills/kit-hexagonal-architecture/assets/invoice.py.template",
        "InvoiceStatus",
        {"OPEN": "open", "PAID": "paid", "VOID": "void"},
    ),
    (
        "packages/temporal/.apm/skills/kit-temporal/assets/effect_policy.py.template",
        "EffectDisposition",
        {"EXECUTE": "execute", "REUSE": "reuse"},
    ),
    (
        "packages/workflows/.apm/skills/kit-codebase-audit/assets/summarize_findings.py",
        "Level",
        {"NOTE": "note", "WARNING": "warning", "ERROR": "error"},
    ),
)
_IDS = [f"{path}:{name}" for path, name, _ in _CONTRACTS]


@pytest.mark.parametrize(("relative", "name", "expected"), _CONTRACTS, ids=_IDS)
def test_enum_member_value_contract(
    relative: str, name: str, expected: dict[str, str]
) -> None:
    enum_type = _load_enum(_ROOT / relative, name)
    assert {
        key: member.value for key, member in enum_type.__members__.items()
    } == expected
    assert [member.name for member in enum_type] == list(expected)
    for member_name, value in expected.items():
        assert enum_type(value) is enum_type[member_name]


@pytest.mark.parametrize(("relative", "name", "expected"), _CONTRACTS, ids=_IDS)
def test_enum_string_and_json_contract(
    relative: str, name: str, expected: dict[str, str]
) -> None:
    enum_type = _load_enum(_ROOT / relative, name)
    assert [str(member) for member in enum_type] == list(expected.values())
    assert json.dumps(list(enum_type)) == json.dumps(list(expected.values()))


def _load_enum(path: Path, name: str) -> type[StrEnum]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = [
        node
        for node in tree.body
        if (isinstance(node, ast.ImportFrom) and node.module in {"enum", "typing"})
        or (
            isinstance(node, ast.Import)
            and all(alias.name == "enum" for alias in node.names)
        )
    ]
    definition = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )
    module = ast.Module(body=[*imports, definition], type_ignores=[])
    namespace: dict[str, object] = {"__name__": "enum_value_contract"}
    # Only the named enum and stdlib enum/typing imports run, not the asset module.
    exec(  # noqa: S102 - executes only the extracted enum AST
        compile(module, str(path), "exec"), namespace
    )
    enum_type = namespace[name]
    assert isinstance(enum_type, type)
    assert issubclass(enum_type, StrEnum)
    return enum_type
