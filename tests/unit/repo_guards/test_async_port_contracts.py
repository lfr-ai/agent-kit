"""Portable port checkers distinguish coroutine and generator call contracts."""

from pathlib import Path
import runpy
from textwrap import indent

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_SHARED = (
    _ROOT
    / "packages/shared/.apm/skills/kit-hexagonal-architecture/assets/check_ports_adapters.py"
)
_BACKEND = (
    _ROOT
    / "packages/backend/.apm/skills/kit-domain-model/assets/check_port_adapter_binding.py"
)
_ASYNC_ITERATOR_PORT = "def events(self) -> AsyncIterator[int]: ..."
_COROUTINE_PORT = "async def events(self) -> int: ..."
_ASYNC_GENERATOR = "async def events(self):\n    yield 1"
_NESTED_YIELDS = (
    "def helper():\n    yield 1",
    "async def helper():\n    yield 1",
    "class Helper:\n    def items(self):\n        yield 1",
    "helper = lambda: (yield 1)",
)


@pytest.fixture(params=(_SHARED, _BACKEND), ids=("shared", "backend"))
def checker(request: pytest.FixtureRequest) -> Path:
    path: object = request.param
    assert isinstance(path, Path)
    return path


def _run(
    checker: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    port: str,
    adapter: str,
) -> tuple[object, str]:
    ports = tmp_path / "ports.py"
    adapters = tmp_path / "adapters.py"
    ports.write_text(
        "from typing import Protocol\nclass EventPort(Protocol):\n"
        + indent(port, "    ")
        + "\n",
        encoding="utf-8",
    )
    adapters.write_text(
        "class EventAdapter:\n" + indent(adapter, "    ") + "\n",
        encoding="utf-8",
    )
    namespace: dict[str, object] = runpy.run_path(str(checker))
    main = namespace["main"]
    assert callable(main)
    arguments = (
        [str(adapters), "--ports", str(ports)]
        if checker == _SHARED
        else ["--core", str(ports), "--adapters", str(adapters)]
    )
    result = main(arguments)
    return result, capsys.readouterr().out


@pytest.mark.parametrize(
    "annotation",
    [
        "AsyncIterator[int]",
        "collections.abc.AsyncIterator[int]",
        "typing.AsyncIterator[int]",
        "AsyncIterator",
    ],
)
def test_sync_async_iterator_port_accepts_async_generator(
    checker: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    annotation: str,
) -> None:
    result, output = _run(
        checker,
        tmp_path,
        capsys,
        port=f"def events(self) -> {annotation}: ...",
        adapter=_ASYNC_GENERATOR,
    )
    assert result == 0, output


@pytest.mark.parametrize(
    ("port", "adapter", "expected"),
    [
        (_COROUTINE_PORT, "async def events(self): return 1", 0),
        (_COROUTINE_PORT, "def events(self): return 1", 1),
        (_COROUTINE_PORT, _ASYNC_GENERATOR, 1),
        (_ASYNC_GENERATOR, _ASYNC_GENERATOR, 0),
        (_ASYNC_GENERATOR, "async def events(self): return 1", 1),
        (_ASYNC_GENERATOR, "def events(self): return 1", 1),
        ("def events(self) -> int: ...", "async def events(self): return 1", 1),
        ("def events(self) -> int: ...", _ASYNC_GENERATOR, 1),
        (_ASYNC_ITERATOR_PORT, "async def events(self): return None", 1),
        (
            _ASYNC_ITERATOR_PORT,
            "async def events(self) -> AsyncIterator[int]: return None",
            1,
        ),
        (
            "async def events(self) -> AsyncIterator[int]: ...",
            "async def events(self) -> AsyncIterator[int]: return None",
            0,
        ),
        (_ASYNC_ITERATOR_PORT, "def events(self): return iter(())", 0),
        ("def events(self) -> Iterator[int]: ...", "def events(self): yield 1", 0),
        (
            "def events(self): yield from ()",
            "def events(self): yield from ()",
            0,
        ),
        ("def events(self): yield from ()", _ASYNC_GENERATOR, 1),
        ("def events(self) -> AsyncIterator[int]: yield 1", _ASYNC_GENERATOR, 1),
        ("def events(self) -> StreamAlias: ...", _ASYNC_GENERATOR, 1),
        ('def events(self) -> "AsyncIterator[int]": ...', _ASYNC_GENERATOR, 1),
    ],
)
def test_callable_contract_compatibility(
    checker: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    port: str,
    adapter: str,
    expected: int,
) -> None:
    result, output = _run(checker, tmp_path, capsys, port=port, adapter=adapter)
    assert result == expected, output
    if expected:
        assert "EventPort" in output
        assert "events" in output


@pytest.mark.parametrize("nested", _NESTED_YIELDS)
@pytest.mark.parametrize(
    ("port", "expected"), [(_COROUTINE_PORT, 0), (_ASYNC_ITERATOR_PORT, 1)]
)
def test_nested_yields_do_not_turn_a_coroutine_into_an_async_generator(
    checker: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    nested: str,
    port: str,
    expected: int,
) -> None:
    adapter = "async def events(self):\n" + indent(nested + "\nreturn 1", "    ")
    result, output = _run(checker, tmp_path, capsys, port=port, adapter=adapter)
    assert result == expected, output


@pytest.mark.parametrize("nested", _NESTED_YIELDS)
def test_nested_yields_do_not_turn_a_normal_port_into_a_generator(
    checker: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    nested: str,
) -> None:
    port = "def events(self) -> AsyncIterator[int]:\n" + indent(nested, "    ")
    result, output = _run(
        checker, tmp_path, capsys, port=port, adapter=_ASYNC_GENERATOR
    )
    assert result == 0, output


@pytest.mark.parametrize(
    "body", ["if False:\n    yield 1", "for item in ():\n    yield item"]
)
def test_yields_in_control_flow_belong_to_the_enclosing_callable(
    checker: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    body: str,
) -> None:
    result, output = _run(
        checker,
        tmp_path,
        capsys,
        port=_ASYNC_ITERATOR_PORT,
        adapter='async def events(self):\n    """Stream events."""\n'
        + indent(body, "    "),
    )
    assert result == 0, output


@pytest.mark.parametrize("decorator", ["staticmethod", "classmethod"])
@pytest.mark.parametrize("asynchronous_generator", [True, False])
def test_decorated_methods_keep_their_callable_contract(
    checker: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    decorator: str,
    asynchronous_generator: bool,
) -> None:
    receiver = "" if decorator == "staticmethod" else "cls"
    result, output = _run(
        checker,
        tmp_path,
        capsys,
        port=_ASYNC_ITERATOR_PORT,
        adapter=f"@{decorator}\nasync def events({receiver}):\n    "
        + ("yield 1" if asynchronous_generator else "return None"),
    )
    assert result == (0 if asynchronous_generator else 1), output


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ("*, count: int = 1", "does not match"),
        ("*, limit: int", "needs a default"),
        ("*, limit: int = 0", "defaults to 0"),
    ],
)
def test_async_generator_bridge_preserves_shared_signature_checks(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    parameters: str,
    message: str,
) -> None:
    result, output = _run(
        _SHARED,
        tmp_path,
        capsys,
        port="def events(self, *, limit: int = 1) -> AsyncIterator[int]: ...",
        adapter=f"async def events(self, {parameters}):\n    yield 1",
    )
    assert result == 1
    assert message in output
