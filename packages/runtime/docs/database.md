# PostgreSQL database foundation

An opt-in async PostgreSQL foundation: settings, a pooled SQLAlchemy engine on
asyncpg, request-scoped sessions, a transaction helper, a declarative `Base`
for Alembic, and a readiness probe. It contains no models, repositories,
migrations or business rules; those belong to the consuming application.

## Install and import boundary

Install `platform-kit-runtime[database]` (SQLAlchemy asyncio, asyncpg,
azure-identity and `aiohttp`, the async HTTP transport that the credentials in
`azure.identity.aio` need for Microsoft Entra authentication).

Importing `platform_kit_runtime` never loads the extra. Importing
`platform_kit_runtime.database` loads SQLAlchemy and asyncpg but never an Azure
SDK: the application creates, injects and closes its own credential.

## Settings

`DatabaseSettings` is explicit; `PG*` environment variables and password files
are never consulted because every connection passes all parameters.

| Setting | Default | Rule |
| --- | --- | --- |
| `host`, `database`, `user` | required | Nonblank; `user` is omitted from `repr` |
| `password` | `None` | Required for password authentication, forbidden with Entra; omitted from `repr` |
| `port` | `5432` | 1 to 65535 |
| `entra_authentication` | `False` | Requires TLS and no password |
| `require_tls` | `True` | Verifies the certificate chain and host name against the system trust store |
| `pool_size`, `max_overflow` | `5`, `5` | 1 to 100 and 0 to 100; size them against the server's `max_connections` across all replicas |

Invalid values raise `DatabaseConfigurationError` (also a `ValueError`) naming
the setting, never its value. A connection URL is deliberately not accepted, so
credentials cannot leak through URLs or logs. Container images need the
operating system CA bundle (for example `ca-certificates`) for TLS.

## Azure Database for PostgreSQL with Microsoft Entra ID

```python
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from azure.identity.aio import ManagedIdentityCredential
from fastapi import FastAPI
from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.database import DatabaseSettings, create_database

credential = ManagedIdentityCredential(client_id="<user-assigned-client-id>")
database = create_database(
    settings=DatabaseSettings(
        host="<server>.postgres.database.azure.com",
        database="app",
        user="<app-identity>",
        entra_authentication=True,
    ),
    credential=credential,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with credential, database.lifespan(app):
        yield


app = create_app(config=RuntimeConfig(), probes=(database.probe,), lifespan=lifespan)
```

Use `ManagedIdentityCredential` in production, as above. For local development
use `DefaultAzureCredential` from `azure.identity.aio` with
`AZURE_TOKEN_CREDENTIALS=dev`, which limits the chain to developer sign-in such
as the Azure CLI. Reuse one credential per process so azure-identity can cache
tokens.

Each new pooled connection requests a token for
`https://ossrdbms-aad.database.windows.net/.default` and uses it as the
password. A token authenticates only when a connection opens; user tokens are
valid for up to an hour, so connections are recycled after 30 minutes and
re-authenticate with a current token. `pool_pre_ping` discards connections the
server or network dropped. Credential failures raise
`DatabaseAuthenticationError`, chained to the azure-identity error, when the
pool opens a connection. Only the public-cloud scope is supported.

### Grant the application identity a database role

Connected to the `postgres` database as a Microsoft Entra administrator, create
a role whose name matches the Entra principal (the managed identity's or
service principal's display name):

```sql
SELECT * FROM pg_catalog.pgaadauth_create_principal('<app-identity>', false, false);
-- Or bind by object ID; objectType is 'user', 'group' or 'service'.
SELECT * FROM pg_catalog.pgaadauth_create_principal_with_oid(
    '<app-identity>', '<object-id>', 'service', false, false
);
```

Then, connected to the application database as the role that owns the schema
(typically the migration role), grant only data access:

```sql
GRANT CONNECT ON DATABASE app TO "<app-identity>";
GRANT USAGE ON SCHEMA public TO "<app-identity>";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "<app-identity>";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "<app-identity>";
ALTER DEFAULT PRIVILEGES FOR ROLE "<migration-role>" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "<app-identity>";
ALTER DEFAULT PRIVILEGES FOR ROLE "<migration-role>" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO "<app-identity>";
-- Optional server-side bound for runaway queries.
ALTER ROLE "<app-identity>" SET statement_timeout = '30s';
```

## Local development with password authentication

```yaml
# compose.yaml
services:
  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set a local password}
    ports:
      - "127.0.0.1:5432:5432"
```

```python
import os

from platform_kit_runtime.database import DatabaseSettings, create_database

database = create_database(
    settings=DatabaseSettings(
        host="localhost",
        database="app",
        user="app",
        password=os.environ["POSTGRES_PASSWORD"],
        require_tls=False,
    )
)
```

No Azure package is used. Pass `database.lifespan` and `database.probe` to
`create_app` as above.

## Sessions and transactions

```python
from typing import Annotated

from fastapi import Depends
from platform_kit_runtime.database import transaction
from sqlalchemy.ext.asyncio import AsyncSession

Session = Annotated[AsyncSession, Depends(database.session)]


@app.post("/items")
async def create_item(session: Session) -> None:
    async with transaction(session=session):
        session.add(...)
```

`database.session` opens one `AsyncSession` per request and closes it after
the response is sent (FastAPI's default dependency scope); use
`Depends(database.session, scope="function")` to release the connection before
the response. Sessions never commit implicitly. `transaction` commits when its
block completes and otherwise rolls back once and re-raises the original error,
including commit failures and cancellation. Sessions use
`expire_on_commit=False`, so loaded attributes stay readable after commit. Use
`database.sessions()` for work outside requests.

## Readiness and shutdown

`database.probe` runs `SELECT 1` on a pooled connection with a 1.5-second
deadline, below the runtime's default readiness deadline. Refused connections,
driver and authentication errors and deadline expiry raise
`ProbeUnavailableError`, so `/health/ready` returns a sanitized 503; caller
cancellation propagates. Build `DatabaseReadinessProbe(engine=database.engine,
timeout_seconds=...)` for another deadline of at most 60 seconds.
`database.lifespan` disposes the pool on shutdown; nothing connects before the
first session or readiness check.

## Alembic in the consuming application

Models subclass `Base`, whose metadata names indexes and constraints
(`ix_`, `uq_`, `ck_`, `fk_`, `pk_`) so autogenerate produces stable,
reviewable names. Migrations, the Alembic configuration and the role that runs
DDL belong to the application. A minimal async `env.py` for online migrations:

```python
import asyncio

from alembic import context
from platform_kit_runtime.database import Base, DatabaseSettings, create_database
from sqlalchemy.engine import Connection

import app.models  # noqa: F401 - registers tables on Base.metadata

target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    database = create_database(settings=DatabaseSettings(...), credential=...)
    try:
        async with database.engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await database.engine.dispose()


asyncio.run(run_async_migrations())
```

Pass a migration role with DDL rights through the same settings; with Entra
authentication, open the credential as an async context manager around
`run_async_migrations`: `ManagedIdentityCredential` in deployed environments,
or `DefaultAzureCredential` with `AZURE_TOKEN_CREDENTIALS=dev` locally.

## Errors

| Error | Raised when |
| --- | --- |
| `DatabaseConfigurationError` | Settings, credential pairing or probe deadline are invalid |
| `DatabaseAuthenticationError` | The credential fails or returns an empty token while connecting |
| `ProbeUnavailableError` | A readiness check cannot reach the database in time |

SQLAlchemy and asyncpg errors from application queries propagate unchanged.
Messages from this package never contain passwords, tokens or user names.

## Verification and sources

Tests use in-process fakes for the driver connect call, the credential and
sessions, plus real SQLAlchemy and asyncpg code with the event loop's socket
connect replaced. They do not certify a live PostgreSQL server, Azure
credentials, Entra role mapping or network TLS.

Inspected on 2026-11-11:

- [Microsoft Entra authentication concepts](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/security-entra-concepts):
  the token is the password, user tokens last up to one hour.
- [Connect with Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-configure-sign-in-azure-ad-authentication):
  token scope and acquisition before connecting.
- [Manage Microsoft Entra roles](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-manage-azure-ad-users):
  `pgaadauth_create_principal` and `pgaadauth_create_principal_with_oid`.
- [Azure Identity for Python](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme):
  async credentials need an async transport and should be closed.
- [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html),
  [engines](https://docs.sqlalchemy.org/en/21/core/engines.html) and
  [pooling](https://docs.sqlalchemy.org/en/21/core/pooling.html):
  `async_creator`, `async_sessionmaker`, `expire_on_commit`, `pool_pre_ping`
  and `pool_recycle`.
- [asyncpg API](https://magicstack.github.io/asyncpg/current/api/index.html):
  explicit connection parameters and `SSLContext` verification.
- [Alembic naming conventions](https://alembic.sqlalchemy.org/en/latest/naming.html)
  and [asyncio cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html).
- [FastAPI dependencies with yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/):
  dependency exit scope.
