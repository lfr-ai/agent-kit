"""Public opt-in PostgreSQL facade and composition root for the ``database`` extra.

Importing this module loads SQLAlchemy and asyncpg but never an Azure SDK;
the caller injects and owns any token credential.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Final

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from platform_kit_runtime.application.database import transaction
from platform_kit_runtime.core.database import (
    DatabaseAccessToken,
    DatabaseAuthenticationError,
    DatabaseConfigurationError,
    DatabaseError,
    DatabaseSettings,
    DatabaseTokenCredential,
    TransactionalSession,
)
from platform_kit_runtime.infrastructure.database import (
    NAMING_CONVENTION,
    Base,
    DatabaseReadinessProbe,
    create_database_engine,
    create_session_factory,
)
from platform_kit_runtime.presentation.database import session_dependency

__all__: Final[list[str]] = [
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
]


@dataclass(frozen=True, kw_only=True, slots=True)
class Database:
    """One connection pool with its sessions, request dependency and probe.

    Attributes:
        engine (AsyncEngine): Lazily connecting engine; also usable by Alembic.
        sessions (async_sessionmaker[AsyncSession]): Session factory for work
            outside requests; sessions do not expire attributes on commit.
        session (Callable[[], AsyncGenerator[AsyncSession]]): FastAPI yield
            dependency providing one session per request, closed afterwards.
        probe (DatabaseReadinessProbe): Readiness probe for ``create_app``.
    """

    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    session: Callable[[], AsyncGenerator[AsyncSession]]
    probe: DatabaseReadinessProbe

    @asynccontextmanager
    async def lifespan(self, _app: object) -> AsyncGenerator[None]:
        """Dispose pooled connections when the application shuts down."""
        try:
            yield
        finally:
            await self.engine.dispose()


def create_database(
    *, settings: DatabaseSettings, credential: DatabaseTokenCredential | None = None
) -> Database:
    """Compose a PostgreSQL pool for one app; no connection is opened here.

    Raises ``DatabaseConfigurationError`` when ``credential`` is missing with
    Entra authentication or supplied without it.

    Args:
        settings (DatabaseSettings): Validated connection and pool settings.
        credential (DatabaseTokenCredential | None): Caller-owned async token
            source for Entra authentication, for example
            ``azure.identity.aio.ManagedIdentityCredential``; ``None`` for
            password authentication.

    Returns:
        Database: Engine, sessions, dependency and probe; pass ``lifespan`` to
            ``create_app`` so the pool is disposed on shutdown.
    """
    engine = create_database_engine(settings=settings, credential=credential)
    sessions = create_session_factory(engine=engine)
    return Database(
        engine=engine,
        sessions=sessions,
        session=session_dependency(sessions=sessions),
        probe=DatabaseReadinessProbe(engine=engine),
    )
