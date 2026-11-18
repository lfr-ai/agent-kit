import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
import math
import ssl
import traceback

import asyncpg
from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError
import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy.schema import CreateIndex, CreateTable

from platform_kit_runtime.core.database import (
    DatabaseAuthenticationError,
    DatabaseConfigurationError,
    DatabaseSettings,
)
from platform_kit_runtime.core.readiness import ProbeUnavailableError
from platform_kit_runtime.infrastructure.database import (
    ENTRA_DATABASE_SCOPE,
    NAMING_CONVENTION,
    Base,
    DatabaseReadinessProbe,
    create_database_engine,
    create_session_factory,
)

pytestmark = pytest.mark.unit

_SENSITIVE_VALUE = "synthetic-database-secret"
_SENSITIVE_BEARER = "synthetic-entra-token"
_HOST = "server.postgres.database.example"


def local_settings(*, require_tls: bool = False) -> DatabaseSettings:
    return DatabaseSettings(
        host="localhost",
        port=55432,
        database="app",
        user="app_user",
        password=_SENSITIVE_VALUE,
        require_tls=require_tls,
        pool_size=2,
        max_overflow=3,
    )


def entra_settings() -> DatabaseSettings:
    return DatabaseSettings(
        host=_HOST, database="app", user="app-identity", entra_authentication=True
    )


@dataclass(kw_only=True, slots=True)
class FakeCredential:
    tokens: list[str]
    error: Exception | None = None
    scopes: list[tuple[str, ...]] = field(default_factory=list)

    async def get_token(self, *scopes: str) -> AccessToken:
        self.scopes.append(scopes)
        if self.error is not None:
            raise self.error
        return AccessToken(self.tokens.pop(0), 0)


@dataclass(kw_only=True, slots=True)
class FakeConnect:
    error: Exception
    calls: list[dict[str, object]] = field(default_factory=list)

    async def __call__(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        raise self.error


@pytest.fixture
def refused(monkeypatch: pytest.MonkeyPatch) -> FakeConnect:
    connect = FakeConnect(error=ConnectionRefusedError("synthetic refusal"))
    monkeypatch.setattr(asyncpg, "connect", connect)
    return connect


async def open_connection(engine: AsyncEngine) -> None:
    async with engine.connect():
        pass


def connect_failures(engine: AsyncEngine, *, attempts: int) -> list[BaseException]:
    async def run() -> list[BaseException]:
        failures: list[BaseException] = []
        for _ in range(attempts):
            try:
                await open_connection(engine)
            except Exception as error:  # noqa: BLE001 - the test inspects each failure
                failures.append(error)
        await engine.dispose()
        return failures

    return asyncio.run(run())


def test_each_new_connection_requests_a_fresh_entra_token(
    refused: FakeConnect,
) -> None:
    credential = FakeCredential(tokens=["token-1", "token-2"])
    engine = create_database_engine(settings=entra_settings(), credential=credential)

    failures = connect_failures(engine, attempts=2)

    assert all(isinstance(error, ConnectionRefusedError) for error in failures)
    assert credential.scopes == [(ENTRA_DATABASE_SCOPE,), (ENTRA_DATABASE_SCOPE,)]
    assert [call["password"] for call in refused.calls] == ["token-1", "token-2"]
    first = refused.calls[0]
    assert {key: first[key] for key in ("host", "port", "user", "database")} == {
        "host": _HOST,
        "port": 5432,
        "user": "app-identity",
        "database": "app",
    }
    tls = first["ssl"]
    assert isinstance(tls, ssl.SSLContext)
    assert tls.verify_mode is ssl.CERT_REQUIRED
    assert tls.check_hostname is True
    assert refused.calls[1]["ssl"] is tls


def test_entra_scope_targets_azure_database_for_postgresql() -> None:
    assert ENTRA_DATABASE_SCOPE == "https://ossrdbms-aad.database.windows.net/.default"


def test_password_authentication_needs_no_credential(refused: FakeConnect) -> None:
    engine = create_database_engine(settings=local_settings())

    connect_failures(engine, attempts=1)

    assert refused.calls == [
        {
            "host": "localhost",
            "port": 55432,
            "user": "app_user",
            "database": "app",
            "password": _SENSITIVE_VALUE,
            "ssl": False,
        }
    ]


def test_password_authentication_verifies_tls_by_default(refused: FakeConnect) -> None:
    engine = create_database_engine(settings=local_settings(require_tls=True))

    connect_failures(engine, attempts=1)

    tls = refused.calls[0]["ssl"]
    assert isinstance(tls, ssl.SSLContext)
    assert tls.verify_mode is ssl.CERT_REQUIRED
    assert tls.check_hostname is True


def test_credential_failure_is_translated_without_connecting(
    refused: FakeConnect,
) -> None:
    vendor = ClientAuthenticationError(message="synthetic identity failure")
    credential = FakeCredential(tokens=[], error=vendor)
    engine = create_database_engine(settings=entra_settings(), credential=credential)

    (failure,) = connect_failures(engine, attempts=1)

    assert isinstance(failure, DatabaseAuthenticationError)
    assert failure.__cause__ is vendor
    assert str(failure) == "Database access token could not be acquired."
    assert refused.calls == []


def test_empty_token_is_rejected_without_connecting(refused: FakeConnect) -> None:
    credential = FakeCredential(tokens=[""])
    engine = create_database_engine(settings=entra_settings(), credential=credential)

    (failure,) = connect_failures(engine, attempts=1)

    assert isinstance(failure, DatabaseAuthenticationError)
    assert failure.__cause__ is None
    assert refused.calls == []


def test_tokens_and_passwords_never_appear_in_failures(refused: FakeConnect) -> None:
    entra = create_database_engine(
        settings=entra_settings(), credential=FakeCredential(tokens=[_SENSITIVE_BEARER])
    )
    local = create_database_engine(settings=local_settings())

    failures = connect_failures(entra, attempts=1) + connect_failures(local, attempts=1)

    rendered = "".join("".join(traceback.format_exception(error)) for error in failures)
    assert _SENSITIVE_BEARER not in rendered
    assert _SENSITIVE_VALUE not in rendered
    assert _SENSITIVE_VALUE not in repr(local) + repr(local.url)
    assert local.url.render_as_string(hide_password=False) == "postgresql+asyncpg://"


@pytest.mark.parametrize(
    ("settings", "credential"),
    [
        (entra_settings(), None),
        (local_settings(), FakeCredential(tokens=[_SENSITIVE_BEARER])),
    ],
)
def test_credential_must_match_authentication_mode(
    settings: DatabaseSettings, credential: FakeCredential | None
) -> None:
    with pytest.raises(DatabaseConfigurationError) as caught:
        create_database_engine(settings=settings, credential=credential)
    assert caught.value.setting == "credential"


def test_pool_is_bounded_pre_pinged_and_recycled_before_token_expiry() -> None:
    engine = create_database_engine(settings=local_settings())
    pool = engine.pool

    assert isinstance(pool, AsyncAdaptedQueuePool)
    assert pool.size() == 2
    assert pool._max_overflow == 3
    assert pool._pre_ping is True
    assert 0 < pool._recycle < 3600


def test_session_factory_keeps_attributes_after_commit() -> None:
    engine = create_database_engine(settings=local_settings())
    factory = create_session_factory(engine=engine)
    session = factory()

    assert isinstance(session, AsyncSession)
    assert session.bind is engine
    assert session.sync_session.expire_on_commit is False
    asyncio.run(session.close())


def test_base_metadata_uses_the_constraint_naming_convention() -> None:
    assert Base.metadata.naming_convention == dict(NAMING_CONVENTION)
    assert Base.metadata.tables == {}
    metadata = MetaData(naming_convention=dict(NAMING_CONVENTION))
    Table("parent", metadata, Column("id", Integer, primary_key=True))
    child = Table(
        "child",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("code", String(8), unique=True),
        Column("parent_id", ForeignKey("parent.id"), index=True),
    )
    dialect = postgresql.dialect()

    ddl = str(CreateTable(child).compile(dialect=dialect))
    (index,) = child.indexes

    assert "CONSTRAINT pk_child PRIMARY KEY" in ddl
    assert "CONSTRAINT uq_child_code UNIQUE" in ddl
    assert "CONSTRAINT fk_child_parent_id_parent FOREIGN KEY" in ddl
    assert "ix_child_parent_id" in str(CreateIndex(index).compile(dialect=dialect))


@dataclass(kw_only=True, slots=True)
class FakeConnection:
    value: object
    statements: list[str]

    async def scalar(self, statement: object) -> object:
        self.statements.append(str(statement))
        return self.value


def fake_engine_connect(
    *, value: object, statements: list[str]
) -> Callable[[AsyncEngine], AbstractAsyncContextManager[FakeConnection]]:
    @asynccontextmanager
    async def connect(_engine: AsyncEngine) -> AsyncGenerator[FakeConnection]:
        yield FakeConnection(value=value, statements=statements)

    return connect


@pytest.mark.parametrize(("value", "ready"), [(1, True), (0, False), (None, False)])
def test_readiness_runs_select_one(
    monkeypatch: pytest.MonkeyPatch, value: object, ready: bool
) -> None:
    statements: list[str] = []
    monkeypatch.setattr(
        AsyncEngine,
        "connect",
        fake_engine_connect(value=value, statements=statements),
    )
    probe = DatabaseReadinessProbe(
        engine=create_database_engine(settings=local_settings())
    )

    assert asyncio.run(probe.check()) is ready
    assert statements == ["SELECT 1"]


def probe_failure(probe: DatabaseReadinessProbe) -> ProbeUnavailableError:
    with pytest.raises(ProbeUnavailableError) as caught:
        asyncio.run(probe.check())
    assert str(caught.value) == "Database is unavailable."
    return caught.value


def test_readiness_reports_refused_connections_as_unavailable(
    refused: FakeConnect,
) -> None:
    probe = DatabaseReadinessProbe(
        engine=create_database_engine(settings=local_settings())
    )

    failure = probe_failure(probe)

    assert isinstance(failure.__cause__, ConnectionRefusedError)
    assert len(refused.calls) == 1


def test_readiness_reports_driver_errors_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejected = asyncpg.exceptions.InvalidPasswordError("synthetic rejection")
    monkeypatch.setattr(asyncpg, "connect", FakeConnect(error=rejected))
    probe = DatabaseReadinessProbe(
        engine=create_database_engine(settings=local_settings())
    )

    failure = probe_failure(probe)

    assert isinstance(failure.__cause__, DBAPIError)
    assert _SENSITIVE_VALUE not in "".join(traceback.format_exception(failure))


def test_readiness_reports_token_failures_as_unavailable(refused: FakeConnect) -> None:
    credential = FakeCredential(tokens=[], error=ClientAuthenticationError())
    engine = create_database_engine(settings=entra_settings(), credential=credential)

    failure = probe_failure(DatabaseReadinessProbe(engine=engine))

    assert isinstance(failure.__cause__, DatabaseAuthenticationError)
    assert refused.calls == []


def test_readiness_deadline_cancels_a_hanging_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled: list[bool] = []

    async def hang(**kwargs: object) -> object:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return kwargs

    monkeypatch.setattr(asyncpg, "connect", hang)
    engine = create_database_engine(settings=local_settings())
    probe = DatabaseReadinessProbe(engine=engine, timeout_seconds=0.05)

    failure = probe_failure(probe)

    assert isinstance(failure.__cause__, TimeoutError)
    assert cancelled == [True]


def test_readiness_propagates_caller_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    async def hang(**kwargs: object) -> object:
        started.set()
        await asyncio.Event().wait()
        return kwargs

    monkeypatch.setattr(asyncpg, "connect", hang)
    probe = DatabaseReadinessProbe(
        engine=create_database_engine(settings=local_settings())
    )

    async def run() -> None:
        task = asyncio.create_task(probe.check())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())


@pytest.mark.parametrize("timeout", [0, -1.0, 60.5, math.inf, math.nan, True])
def test_readiness_timeout_is_validated(timeout: float) -> None:
    engine = create_database_engine(settings=local_settings())
    with pytest.raises(DatabaseConfigurationError) as caught:
        DatabaseReadinessProbe(engine=engine, timeout_seconds=timeout)
    assert caught.value.setting == "timeout_seconds"


def test_readiness_accepts_the_maximum_timeout() -> None:
    engine = create_database_engine(settings=local_settings())
    assert isinstance(
        DatabaseReadinessProbe(engine=engine, timeout_seconds=60),
        DatabaseReadinessProbe,
    )
