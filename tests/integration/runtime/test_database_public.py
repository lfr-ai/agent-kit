"""Public database facade wiring through SQLAlchemy and asyncpg without a server."""

import asyncio
from collections.abc import Callable
import subprocess
import sys

from azure.core.credentials import AccessToken
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime import database as public
from platform_kit_runtime.database import (
    Database,
    DatabaseReadinessProbe,
    DatabaseSettings,
    DatabaseTokenCredential,
    create_database,
    transaction,
)

pytestmark = pytest.mark.integration

_SENSITIVE_VALUE = "synthetic-database-secret"
_SENSITIVE_BEARER = "synthetic-entra-token"
_HOST = "server.postgres.database.example"


class RecordingCredential:
    def __init__(self) -> None:
        self.scopes: list[tuple[str, ...]] = []

    async def get_token(self, *scopes: str) -> AccessToken:
        self.scopes.append(scopes)
        return AccessToken(_SENSITIVE_BEARER, 0)


def entra_database(credential: RecordingCredential) -> Database:
    return create_database(
        settings=DatabaseSettings(
            host=_HOST, database="app", user="app-identity", entra_authentication=True
        ),
        credential=credential,
    )


def local_database() -> Database:
    return create_database(
        settings=DatabaseSettings(
            host="localhost",
            database="app",
            user="app",
            password=_SENSITIVE_VALUE,
            require_tls=False,
        )
    )


def test_public_surface_is_explicit() -> None:
    assert set(public.__all__) == {
        "NAMING_CONVENTION",
        "Base",
        "Database",
        "DatabaseAccessToken",
        "DatabaseAuthenticationError",
        "DatabaseConfigurationError",
        "DatabaseError",
        "DatabaseReadinessProbe",
        "DatabaseSettings",
        "DatabaseTokenCredential",
        "TransactionalSession",
        "create_database",
        "transaction",
    }
    assert all(hasattr(public, name) for name in public.__all__)


def test_azure_async_credentials_satisfy_the_token_port() -> None:
    credentials: tuple[type[DatabaseTokenCredential], ...] = (
        DefaultAzureCredential,
        ManagedIdentityCredential,
    )
    assert len(credentials) == 2


def test_readiness_uses_real_driver_and_fresh_token_without_a_server() -> None:
    credential = RecordingCredential()
    database = entra_database(credential)
    addresses: list[tuple[str, int]] = []

    async def refuse(_factory: Callable[[], object], host: str, port: int) -> object:
        addresses.append((host, port))
        message = "synthetic refusal"
        raise ConnectionRefusedError(message)

    async def ready() -> Response:
        loop = asyncio.get_running_loop()
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(loop, "create_connection", refuse)
            app = create_app(
                config=RuntimeConfig(),
                probes=(database.probe,),
                lifespan=database.lifespan,
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://runtime.test"
            ) as client:
                response = await client.get("/health/ready")
        await database.engine.dispose()
        return response

    response = asyncio.run(ready())

    assert response.status_code == 503
    assert _SENSITIVE_BEARER not in response.text
    assert _HOST not in response.text
    assert credential.scopes == [
        ("https://ossrdbms-aad.database.windows.net/.default",)
    ]
    assert addresses == [(_HOST, 5432)]


def test_session_dependency_transaction_and_lifespan() -> None:
    database = local_database()
    original_pool = database.engine.pool

    async def run() -> None:
        async with database.lifespan(FastAPI()):
            sessions = database.session()
            session = await anext(sessions)
            assert isinstance(session, AsyncSession)
            assert session.sync_session.expire_on_commit is False
            async with transaction(session=session) as active:
                assert active is session
            await sessions.aclose()

    asyncio.run(run())

    assert isinstance(database.probe, DatabaseReadinessProbe)
    assert database.engine.pool is not original_pool


def run_isolated(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed offline interpreter probe
        [sys.executable, "-I", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


_BLOCKER = """
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in BLOCKED:
            raise ModuleNotFoundError(f'blocked {fullname}', name=fullname)
sys.meta_path.insert(0, Block())
"""


def test_base_package_imports_without_the_database_extra() -> None:
    script = f"""
BLOCKED = {{'sqlalchemy', 'asyncpg', 'azure', 'greenlet'}}
{_BLOCKER}
from platform_kit_runtime import RuntimeConfig, create_app
assert create_app(config=RuntimeConfig(), probes=()) is not None
try:
    import platform_kit_runtime.database
except ModuleNotFoundError as error:
    assert error.name == 'sqlalchemy', error.name
else:
    raise AssertionError('database facade imported without its extra')
"""
    result = run_isolated(script)
    assert result.returncode == 0, result.stderr


def test_database_facade_never_loads_azure_sdks() -> None:
    script = f"""
BLOCKED = {{'azure'}}
{_BLOCKER}
from platform_kit_runtime.database import DatabaseSettings, create_database
database = create_database(
    settings=DatabaseSettings(
        host='localhost', database='app', user='app', password='p', require_tls=False
    )
)
assert database.engine.url.drivername == 'postgresql+asyncpg'
"""
    result = run_isolated(script)
    assert result.returncode == 0, result.stderr
