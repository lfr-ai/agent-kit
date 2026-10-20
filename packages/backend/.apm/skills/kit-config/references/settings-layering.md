# Layered settings with pydantic-settings

`BaseSettings` lives in the separately installed `pydantic-settings`
distribution. It extends a Pydantic model with sources that populate fields from
the environment, dotenv files, secret directories, and optional providers.

## Default source order

Without customization the first source that provides a value wins, in this
order:

1. Keyword arguments passed to the settings constructor.
2. Command-line arguments, only when CLI parsing is enabled.
3. Environment variables.
4. Variables loaded from the configured dotenv file(s).
5. Files in the configured secrets directory.
6. Field defaults.

Pin the `pydantic-settings` version in the consumer lockfile and re-read the
release notes when upgrading; source behavior and defaults have evolved between
minor versions.

## Model configuration

Declare behavior once with `SettingsConfigDict`:

- `env_prefix="ORDERS_"` scopes every lookup. The prefix applies to dotenv and
  secret sources too.
- `env_nested_delimiter="__"` lets `ORDERS_DATABASE__POOL_SIZE` populate a
  nested `database.pool_size` field. Without it, nested models must be provided
  as JSON.
- `env_file=".env"` enables dotenv loading for local development. Missing files
  are ignored; do not point production at a dotenv file unless the platform
  mounts one.
- `secrets_dir="/run/secrets"` reads one file per field, named after the field
  (plus prefix). This matches container-orchestrator secret mounts.
- `extra`: the settings class rejects unexpected keys from dotenv input by
  default in current releases; keep that strictness so typos fail loudly.
- `case_sensitive=False` is the default; keep it unless the platform needs
  case-sensitive names.
- `frozen=True` prevents accidental mutation after startup.

## Nested settings as facets

Group related values into nested `BaseModel` classes (not nested
`BaseSettings`) and expose them as fields of one root settings object:

```python
class DatabaseSettings(BaseModel):
    url: PostgresDsn
    pool_size: int = Field(default=5, ge=1, le=100)


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORDERS_", env_nested_delimiter="__")

    database: DatabaseSettings
```

The composition root passes `settings.database` to the repository factory and
nothing else. Collaborators depend on the facet type, which keeps their
signatures narrow and their tests independent of unrelated settings.

## Customizing sources

Override the `settings_customise_sources` classmethod to change precedence or add
a provider. It receives the settings class and the default sources (init,
environment, dotenv, file secrets) and returns a tuple in priority order:

```python
@classmethod
def settings_customise_sources(
    cls,
    settings_cls: type[BaseSettings],
    init_settings: PydanticBaseSettingsSource,
    env_settings: PydanticBaseSettingsSource,
    dotenv_settings: PydanticBaseSettingsSource,
    file_secret_settings: PydanticBaseSettingsSource,
) -> tuple[PydanticBaseSettingsSource, ...]:
    return (init_settings, env_settings, file_secret_settings)
```

Dropping `dotenv_settings` from the tuple is a simple way to forbid dotenv files
outside development. Adding a TOML, YAML, or provider source is done by
inserting it in the returned tuple; see [secrets providers](secrets-providers.md).

## Aliases

- `Field(validation_alias="LEGACY_NAME")` reads a different variable name for
  one field. Use `AliasChoices("NEW_NAME", "OLD_NAME")` to accept a renamed
  variable during a migration window, then remove the old name.
- An alias on a nested model narrows the prefix used for its sub-fields in every
  source. Test renamed nested settings in each source you rely on.

## Testing the layering

- Construct settings with explicit keyword arguments in unit tests; do not
  depend on the developer's shell.
- Use `monkeypatch.setenv` and `monkeypatch.delenv` for environment cases, and
  pass `_env_file=tmp_path / ".env"` for dotenv cases.
- Assert precedence directly: set the same field in two sources and verify the
  documented winner. The [test template](../assets/test_settings.py.template)
  shows this pattern.

## Sources

- <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>
- <https://docs.pydantic.dev/latest/api/pydantic_settings/>
- <https://docs.pydantic.dev/latest/concepts/alias/>
