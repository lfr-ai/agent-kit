import ast
import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
import inspect
import sys
from types import ModuleType
from typing import Annotated

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient, Response
import pytest

from platform_kit_runtime import database as facade
from platform_kit_runtime.application import database as application
from platform_kit_runtime.application.database import transaction
from platform_kit_runtime.core import database as core
from platform_kit_runtime.core.database import (
    DatabaseAuthenticationError,
    DatabaseConfigurationError,
    DatabaseError,
    DatabaseSettings,
)
from platform_kit_runtime.infrastructure import database as infrastructure
from platform_kit_runtime.presentation import database as presentation
from platform_kit_runtime.presentation.database import session_dependency

pytestmark = pytest.mark.unit

_SENSITIVE_VALUE = "synthetic-database-secret"
_PRIVATE_USER = "synthetic-person@example.invalid"


def local_settings() -> DatabaseSettings:
    return DatabaseSettings(
        host="localhost",
        database="app",
        user=_PRIVATE_USER,
        password=_SENSITIVE_VALUE,
        require_tls=False,
    )


def entra_settings() -> DatabaseSettings:
    return DatabaseSettings(
        host="server.postgres.database.example",
        database="app",
        user=_PRIVATE_USER,
        entra_authentication=True,
    )


def test_defaults_are_secure_and_bounded() -> None:
    settings = DatabaseSettings(
        host="db.internal", database="app", user="app", password=_SENSITIVE_VALUE
    )
    assert settings.port == 5432
    assert settings.require_tls is True
    assert settings.entra_authentication is False
    assert (settings.pool_size, settings.max_overflow) == (5, 5)


@pytest.mark.parametrize("settings", [local_settings(), entra_settings()])
def test_repr_omits_credentials_and_personal_data(settings: DatabaseSettings) -> None:
    text = repr(settings)
    assert _SENSITIVE_VALUE not in text
    assert _PRIVATE_USER not in text
    assert "password" not in text
    assert "user" not in text


@pytest.mark.parametrize(
    ("changes", "setting"),
    [
        ({"host": ""}, "host"),
        ({"host": "db host"}, "host"),
        ({"host": "db\nhost"}, "host"),
        ({"host": None}, "host"),
        ({"database": " "}, "database"),
        ({"user": "\t"}, "user"),
        ({"port": 0}, "port"),
        ({"port": 65536}, "port"),
        ({"port": True}, "port"),
        ({"port": "5432"}, "port"),
        ({"entra_authentication": 1}, "entra_authentication"),
        ({"require_tls": "yes"}, "require_tls"),
        ({"pool_size": 0}, "pool_size"),
        ({"pool_size": 101}, "pool_size"),
        ({"pool_size": 2.0}, "pool_size"),
        ({"max_overflow": -1}, "max_overflow"),
        ({"max_overflow": 101}, "max_overflow"),
        ({"max_overflow": False}, "max_overflow"),
        ({"password": None}, "password"),
        ({"password": ""}, "password"),
    ],
)
def test_invalid_settings_name_the_setting_without_its_value(
    changes: dict[str, object], setting: str
) -> None:
    with pytest.raises(DatabaseConfigurationError) as caught:
        replace(local_settings(), **changes)
    assert caught.value.setting == setting
    assert str(caught.value) == f"Database setting {setting!r} is invalid."
    assert _SENSITIVE_VALUE not in str(caught.value)
    assert _PRIVATE_USER not in str(caught.value)
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value, DatabaseError)


@pytest.mark.parametrize(
    ("changes", "setting"),
    [
        ({"password": _SENSITIVE_VALUE}, "password"),
        ({"require_tls": False}, "require_tls"),
    ],
)
def test_entra_authentication_requires_tls_and_no_password(
    changes: dict[str, object], setting: str
) -> None:
    with pytest.raises(DatabaseConfigurationError) as caught:
        replace(entra_settings(), **changes)
    assert caught.value.setting == setting
    assert _SENSITIVE_VALUE not in str(caught.value)


def test_bounds_are_inclusive() -> None:
    settings = replace(local_settings(), port=65535, pool_size=100, max_overflow=0)
    assert (settings.port, settings.pool_size, settings.max_overflow) == (65535, 100, 0)


def test_authentication_error_message_is_fixed() -> None:
    error = DatabaseAuthenticationError()
    assert str(error) == "Database access token could not be acquired."
    assert isinstance(error, DatabaseError)
    assert not isinstance(error, ValueError)


@dataclass(kw_only=True, slots=True)
class FakeSession:
    events: list[str] = field(default_factory=list)
    commit_error: Exception | None = None

    async def commit(self) -> None:
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.events.append("rollback")


def test_transaction_commits_on_success() -> None:
    session = FakeSession()

    async def run() -> None:
        async with transaction(session=session) as active:
            assert active is session
            assert session.events == []

    asyncio.run(run())
    assert session.events == ["commit"]


def test_transaction_rolls_back_and_reraises_block_errors() -> None:
    session = FakeSession()
    failure = LookupError("domain failure")

    async def run() -> None:
        async with transaction(session=session):
            raise failure

    with pytest.raises(LookupError) as caught:
        asyncio.run(run())
    assert caught.value is failure
    assert session.events == ["rollback"]


def test_transaction_rolls_back_when_commit_fails() -> None:
    failure = RuntimeError("commit failed")
    session = FakeSession(commit_error=failure)

    async def run() -> None:
        async with transaction(session=session):
            pass

    with pytest.raises(RuntimeError) as caught:
        asyncio.run(run())
    assert caught.value is failure
    assert session.events == ["commit", "rollback"]


def test_transaction_rolls_back_on_cancellation() -> None:
    session = FakeSession()

    async def run() -> None:
        entered = asyncio.Event()

        async def work() -> None:
            async with transaction(session=session):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(work())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert session.events == ["rollback"]


def request_paths(*, app: FastAPI, paths: tuple[str, ...]) -> list[Response]:
    async def send() -> list[Response]:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://runtime.test",
        ) as client:
            return [await client.get(path) for path in paths]

    return asyncio.run(send())


def test_dependency_opens_and_closes_one_session_per_request() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def sessions() -> AsyncGenerator[str]:
        name = f"session-{len(events) // 2 + 1}"
        events.append(f"open {name}")
        try:
            yield name
        finally:
            events.append(f"close {name}")

    provide = session_dependency(sessions=sessions)
    app = FastAPI()

    @app.get("/session")
    async def read(session: Annotated[str, Depends(provide)]) -> dict[str, str]:
        return {"session": session}

    @app.get("/failure")
    async def fail(session: Annotated[str, Depends(provide)]) -> dict[str, str]:
        message = f"handler failed with {session}"
        raise RuntimeError(message)

    responses = request_paths(app=app, paths=("/session", "/session", "/failure"))
    assert [response.status_code for response in responses] == [200, 200, 500]
    assert [response.json() for response in responses[:2]] == [
        {"session": "session-1"},
        {"session": "session-2"},
    ]
    assert events == [
        "open session-1",
        "close session-1",
        "open session-2",
        "close session-2",
        "open session-3",
        "close session-3",
    ]


def imports(module: ModuleType) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module is not None
            result.add(node.module)
    return result


def stdlib(name: str) -> bool:
    return name.split(".", maxsplit=1)[0] in sys.stdlib_module_names


def test_database_core_imports_only_stdlib() -> None:
    assert all(
        stdlib(name) or name.startswith("platform_kit_runtime.core.")
        for name in imports(core)
    )


@pytest.mark.parametrize("module", [application, presentation])
def test_database_inner_adapters_depend_only_on_core_and_stdlib(
    module: ModuleType,
) -> None:
    assert all(
        name.startswith("platform_kit_runtime.core.") or stdlib(name)
        for name in imports(module)
    )


def test_database_infrastructure_avoids_inner_adapters_and_azure() -> None:
    allowed = ("platform_kit_runtime.core.", "sqlalchemy", "asyncpg")
    assert all(
        name.startswith(allowed) or stdlib(name) for name in imports(infrastructure)
    )


def test_database_facade_never_imports_azure() -> None:
    assert not any(name.startswith("azure") for name in imports(facade))
