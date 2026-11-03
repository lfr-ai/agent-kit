"""Temporal policy behavior and the separately runnable SDK acceptance template."""

import ast
from datetime import timedelta
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest

_OWNER = Path(__file__).resolve().parents[3] / "packages/temporal/.apm"
_SKILL = _OWNER / "skills/kit-temporal"


@pytest.fixture
def policy() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(_SKILL / "assets/execution_policy.py")))


def test_policy_accepts_bounded_activity(policy: SimpleNamespace) -> None:
    result = policy.ActivityPolicy(
        start_to_close=timedelta(seconds=10),
        schedule_to_close=timedelta(minutes=1),
        heartbeat=timedelta(seconds=2),
        retry_initial=timedelta(seconds=1),
        retry_maximum=timedelta(seconds=5),
        maximum_attempts=3,
    )
    assert result.maximum_attempts == 3


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_to_close": timedelta(0)},
        {"schedule_to_close": timedelta(seconds=1)},
        {"heartbeat": timedelta(0)},
        {"heartbeat": timedelta(seconds=10)},
        {"retry_initial": timedelta(0)},
        {"retry_initial": timedelta(seconds=6)},
        {"retry_maximum": timedelta(0)},
        {"retry_maximum": timedelta(minutes=2)},
        {"maximum_attempts": 0},
    ],
)
def test_policy_rejects_unbounded_or_incoherent_timeouts(
    policy: SimpleNamespace, overrides: dict[str, object]
) -> None:
    values = {
        "start_to_close": timedelta(seconds=10),
        "schedule_to_close": timedelta(minutes=1),
        "heartbeat": timedelta(seconds=2),
        "retry_initial": timedelta(seconds=1),
        "retry_maximum": timedelta(seconds=5),
        "maximum_attempts": 3,
    }
    with pytest.raises(policy.InvalidPolicyError):
        policy.ActivityPolicy(**(values | overrides))


def test_sdk_template_contains_executable_behavior_tests() -> None:
    template = _SKILL / "assets/test_temporal_behavior.py.template"
    tree = ast.parse(template.read_text(encoding="utf-8"))
    tests = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)
    }
    assert {"test_retry_and_replay", "test_cancel_timer"} <= tests
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert {
        "start_time_skipping",
        "replay_workflow",
        "fetch_history",
        "cancel",
    } <= calls


def test_execution_policy_imports_only_stdlib() -> None:
    tree = ast.parse(
        (_SKILL / "assets/execution_policy.py").read_text(encoding="utf-8")
    )
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imports <= sys.stdlib_module_names


@pytest.fixture
def effects() -> SimpleNamespace:
    return SimpleNamespace(
        **runpy.run_path(str(_SKILL / "assets/effect_policy.py.template"))
    )


def test_activity_retry_reuses_committed_effect(effects: SimpleNamespace) -> None:
    """Model the response-lost window; retry returns the saved result reference."""
    first = effects.decide_effect(
        operation_key="order:synthetic:charge",
        payload=b'{"amount":100}',
        previous=None,
    )
    assert first.disposition == effects.EffectDisposition.EXECUTE
    committed = effects.EffectRecord(
        operation_key=first.operation_key,
        payload_digest=first.payload_digest,
        result_ref="receipt:synthetic",
    )
    retried = effects.decide_effect(
        operation_key="order:synthetic:charge",
        payload=b'{"amount":100}',
        previous=committed,
    )
    assert retried.disposition == effects.EffectDisposition.REUSE
    assert retried.result_ref == "receipt:synthetic"
    assert retried.payload_digest == first.payload_digest


@pytest.mark.parametrize(
    ("operation_key", "payload"),
    [
        ("order:synthetic:charge", b'{"amount":200}'),
        ("another-operation", b'{"amount":100}'),
    ],
)
def test_activity_deduplication_rejects_conflicting_receipt(
    effects: SimpleNamespace, operation_key: str, payload: bytes
) -> None:
    first = effects.decide_effect(
        operation_key="order:synthetic:charge",
        payload=b'{"amount":100}',
        previous=None,
    )
    committed = effects.EffectRecord(
        operation_key=first.operation_key,
        payload_digest=first.payload_digest,
        result_ref="receipt:synthetic",
    )
    with pytest.raises(effects.IdempotencyConflictError):
        effects.decide_effect(
            operation_key=operation_key, payload=payload, previous=committed
        )


def test_activity_rejects_empty_business_key(effects: SimpleNamespace) -> None:
    with pytest.raises(effects.InvalidEffectRequestError):
        effects.decide_effect(operation_key=" ", payload=b"synthetic", previous=None)


def test_temporal_resources_link_sources_and_runtime_limitations() -> None:
    skill = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    guide = (_SKILL / "references/guide.md").read_text(encoding="utf-8")
    assert "assets/execution_policy.py" in skill
    assert "assets/test_temporal_behavior.py.template" in skill
    assert "https://temporal.mcp.kapa.ai" in guide
    assert "tests/worker/test_workflow.py" in guide
    assert "unverified" in guide.lower()
