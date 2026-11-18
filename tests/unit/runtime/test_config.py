from dataclasses import FrozenInstanceError, fields
import inspect

import pytest

from platform_kit_runtime import RuntimeConfig

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("timeout", [0.001, 1, 2.0, 60.0])
def test_config_accepts_bounded_timeout(timeout: float) -> None:
    config = RuntimeConfig(readiness_timeout_seconds=timeout)

    assert config.readiness_timeout_seconds == timeout


@pytest.mark.parametrize(
    "timeout", [0, -1, 60.001, float("inf"), float("nan"), True, "private-value", None]
)
def test_config_rejects_invalid_timeout_without_echoing_value(timeout: float) -> None:
    with pytest.raises(ValueError, match="readiness_timeout_seconds") as caught:
        RuntimeConfig(readiness_timeout_seconds=timeout)

    assert "private-value" not in str(caught.value)


def test_config_error_states_the_allowed_range() -> None:
    with pytest.raises(ValueError, match="readiness_timeout_seconds") as caught:
        RuntimeConfig(readiness_timeout_seconds=0)

    assert str(caught.value) == (
        "readiness_timeout_seconds must be finite and in (0, 60]."
    )


@pytest.mark.parametrize("field", [field.name for field in fields(RuntimeConfig)])
def test_config_is_immutable_and_slotted(field: str) -> None:
    config = RuntimeConfig()

    with pytest.raises(FrozenInstanceError):
        setattr(config, field, 1.0)
    assert not hasattr(config, "__dict__")


def test_config_requires_keyword_arguments() -> None:
    with pytest.raises(TypeError):
        inspect.signature(RuntimeConfig).bind(1.0)


def test_config_does_not_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("READINESS_TIMEOUT_SECONDS", "private-value")

    assert RuntimeConfig().readiness_timeout_seconds == 2.0
