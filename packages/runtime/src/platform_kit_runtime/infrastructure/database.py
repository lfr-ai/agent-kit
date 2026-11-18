"""SQLAlchemy asyncio adapters for PostgreSQL over asyncpg."""

import asyncio
from collections.abc import Mapping
import ssl
from types import MappingProxyType
from typing import Final

import asyncpg
from sqlalchemy import URL, MetaData, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from platform_kit_runtime.core.database import (
    DatabaseAuthenticationError,
    DatabaseConfigurationError,
    DatabaseError,
    DatabaseSettings,
    DatabaseTokenCredential,
)
from platform_kit_runtime.core.readiness import (
    MAX_READINESS_TIMEOUT_SECONDS,
    ProbeUnavailableError,
)
from platform_kit_runtime.core.validation import is_bounded_seconds

ENTRA_DATABASE_SCOPE: Final[str] = "https://ossrdbms-aad.database.windows.net/.default"
NAMING_CONVENTION: Final[Mapping[str, str]] = MappingProxyType(
    {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)
_DRIVER = "postgresql+asyncpg"
# Entra user tokens last up to an hour and authenticate only when a connection
# opens; recycling at 30 minutes makes old connections re-authenticate.
_POOL_RECYCLE_SECONDS = 1800
# Below the runtime's default 2-second readiness deadline.
_DEFAULT_READINESS_TIMEOUT_SECONDS = 1.5
_UNAVAILABLE = "Database is unavailable."


class Base(DeclarativeBase):
    """Declarative base whose metadata names constraints for Alembic autogenerate."""

    metadata = MetaData(naming_convention=dict(NAMING_CONVENTION))


async def _access_token(*, credential: DatabaseTokenCredential) -> str:
    try:
        access = await credential.get_token(ENTRA_DATABASE_SCOPE)
        token = access.token
    except Exception as error:
        raise DatabaseAuthenticationError from error
    if not isinstance(token, str) or not token:
        raise DatabaseAuthenticationError
    return token


def create_database_engine(
    *, settings: DatabaseSettings, credential: DatabaseTokenCredential | None = None
) -> AsyncEngine:
    """Create a lazily connecting PostgreSQL engine; no I/O happens here.

    Every new pooled connection calls ``asyncpg.connect`` with explicit
    settings, so ``PG*`` environment variables and password files are never
    consulted. With Entra authentication, each new connection first requests
    a token from ``credential``; failures raise ``DatabaseAuthenticationError``
    when the pool connects.

    Args:
        settings (DatabaseSettings): Validated connection and pool settings.
        credential (DatabaseTokenCredential | None): Caller-owned token source,
            required with Entra authentication and rejected otherwise.

    Returns:
        AsyncEngine: Engine with pre-ping, 30-minute recycling and bounded pool.

    Raises:
        DatabaseConfigurationError: The credential does not match the
            authentication mode.
    """
    if settings.entra_authentication != (credential is not None):
        raise DatabaseConfigurationError(setting="credential")
    tls: ssl.SSLContext | bool = (
        ssl.create_default_context() if settings.require_tls else False
    )

    async def connect() -> asyncpg.Connection:
        password = (
            settings.password
            if credential is None
            else await _access_token(credential=credential)
        )
        return await asyncpg.connect(
            host=settings.host,
            port=settings.port,
            user=settings.user,
            database=settings.database,
            password=password,
            ssl=tls,
        )

    return create_async_engine(
        URL.create(_DRIVER),
        async_creator=connect,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_pre_ping=True,
        pool_recycle=_POOL_RECYCLE_SECONDS,
    )


def create_session_factory(*, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create sessions that keep loaded attributes usable after commit."""
    return async_sessionmaker(engine, expire_on_commit=False)


class DatabaseReadinessProbe:
    """Readiness probe running ``SELECT 1`` on a pooled connection."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        timeout_seconds: float = _DEFAULT_READINESS_TIMEOUT_SECONDS,
    ) -> None:
        """Bind the engine and a per-check deadline.

        Args:
            engine (AsyncEngine): Engine whose pool serves the check.
            timeout_seconds (float): Positive finite deadline, at most 60
                seconds, covering connection checkout and the query.

        Raises:
            DatabaseConfigurationError: The deadline is invalid.
        """
        if not is_bounded_seconds(
            timeout_seconds, maximum=MAX_READINESS_TIMEOUT_SECONDS
        ):
            raise DatabaseConfigurationError(setting="timeout_seconds")
        self._engine = engine
        self._timeout_seconds = timeout_seconds

    async def check(self) -> bool:
        """Return whether ``SELECT 1`` returns one within the deadline.

        Connection, authentication, query and deadline failures raise
        ``ProbeUnavailableError`` with the cause chained, never sent to clients.
        """
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._engine.connect() as connection:
                    result = await connection.scalar(text("SELECT 1"))
        except (OSError, SQLAlchemyError, DatabaseError) as error:
            raise ProbeUnavailableError(_UNAVAILABLE) from error
        return result == 1
