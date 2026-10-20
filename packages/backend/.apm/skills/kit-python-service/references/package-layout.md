# Backend package layout and composition root

The layout below is a default for a typed Python backend that follows
Hexagonal Architecture (ports and adapters) with a layered core. Adapt the
folder names to the project; keep the dependency direction.

## Default layout

```text
src/<package>/
  __init__.py
  core/                 # domain: entities, value objects, domain services, ports
    models.py
    errors.py
    ports.py            # Protocol interfaces the core needs
  application/          # use cases orchestrating the core through ports
    services.py
  infrastructure/       # adapters: database, HTTP clients, files, queues
    repositories.py
    clients.py
  presentation/         # transports: HTTP routers, CLI, message consumers
    api.py
    cli.py
  composition.py        # composition root: builds and wires everything
  settings.py           # typed configuration loaded once
  logging_setup.py      # handler and formatter configuration
tests/
  unit/                 # core and application with in-memory fakes
  integration/          # adapters against real or containerized services
  contract/             # transport contracts (HTTP schema, CLI output)
```

## Dependency rule

| Layer | May import | Must not import |
| --- | --- | --- |
| core | standard library, other core modules | application, infrastructure, presentation, frameworks |
| application | core | infrastructure, presentation |
| infrastructure | core (ports and models), drivers and SDKs | application services, presentation |
| presentation | application, core models for typing, transport framework | infrastructure |
| composition | everything | (nothing imports composition except entry points) |

Presentation receives fully built services from the composition root. It never
instantiates a repository or client itself; doing so couples the transport to a
storage choice and makes tests start real infrastructure.

[check_backend_wiring.py](../assets/check_backend_wiring.py) enforces these rules
statically:

```text
python check_backend_wiring.py src --package shop
python check_backend_wiring.py src --package shop \
    --forbid presentation:infrastructure --forbid core:application,infrastructure,presentation
```

Each `--forbid SOURCE:TARGET[,TARGET...]` names layers by their first segment
below the package. Relative imports are resolved before matching. With no
`--forbid`, the default rule is `presentation:infrastructure`.

## Ports

Declare ports as `typing.Protocol` classes in the core (or the application layer
when the port is a use-case concern). A port describes what the core needs in its
own vocabulary: `InvoiceRepository.get(invoice_id)`, not `execute_sql(...)`.

## Composition root

One module builds the object graph at process start:

1. Load settings once.
2. Configure logging once.
3. Construct adapters from settings (connection pools, HTTP clients).
4. Construct application services by injecting adapters through keyword-only
   constructors.
5. Hand the services to the transport (router dependencies, CLI commands).
6. Own shutdown: close pools and clients in reverse order.

Keep it explicit Python. A dependency-injection container is optional and only
pays off when the graph is large; explicit construction is easier to read, type
check, and debug.

```python
@dataclass(frozen=True, kw_only=True, slots=True)
class Container:
    invoices: InvoiceService


def build_container(settings: Settings) -> Container:
    repository = SqlInvoiceRepository(dsn=settings.database_dsn)
    return Container(
        invoices=InvoiceService(repository=repository, clock=SystemClock())
    )
```

Tests build the same graph with fakes:

```python
def build_test_container() -> Container:
    return Container(
        invoices=InvoiceService(
            repository=InMemoryInvoiceRepository(), clock=FixedClock()
        )
    )
```

## Framework integration

- FastAPI: build the container in the lifespan handler, store it on
  `app.state`, and expose services through small dependency functions. Override
  those dependency functions in tests instead of patching modules.
- CLI: build the container in `main()` after argument parsing; pass services to
  command functions as arguments.
- Workers and schedulers: build the container once per process, not per job.

## Settings

Load configuration from the environment into a frozen, typed record at startup,
validate it, and fail fast with a message naming the missing or invalid key. Do
not read `os.environ` anywhere else. See
[settings.py.template](../assets/settings.py.template).

## Anti-patterns

- Module-level singletons created at import time (`db = Database(...)`): import
  order becomes wiring order and tests cannot replace them.
- Service locators (`get_service("invoices")`) inside business code: hides
  dependencies from signatures.
- Framework request objects passed into application services.
- `utils`/`helpers`/`common` packages that every layer imports.

## Sources

- [Alistair Cockburn: Hexagonal architecture](https://alistair.cockburn.us/hexagonal-architecture/)
- [Robert C. Martin: The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Mark Seemann: Composition Root](https://blog.ploeh.dk/2011/07/28/CompositionRoot/)
- [PEP 544 - Protocols](https://peps.python.org/pep-0544/)
- [FastAPI: lifespan events](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI: testing dependencies with overrides](https://fastapi.tiangolo.com/advanced/testing-dependencies/)
- [Python Packaging User Guide: src layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
