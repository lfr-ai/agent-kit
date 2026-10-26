# Secure patterns for Python sinks

Each section names the sink, the unsafe pattern, the safe pattern and the test
that proves it. Apply the control at the boundary where untrusted data first
enters, and keep the safe primitive in one helper so call sites cannot drift.
Review date: 2026-10-23.

## Input validation at boundaries

- Parse into typed values at the edge (Pydantic models, `argparse` types,
  dataclasses with validators) and pass only those inward.
- Prefer allow-lists (enumerations, regular expressions anchored with
  `fullmatch`) over deny-lists; bound lengths, sizes, counts and ranges.
- Reject invalid input with a specific error; do not "clean" it into
  something else. Normalize (Unicode NFC, case) before validating, not after.
- Limit request body size, upload size, archive member count and
  decompressed size before processing.

## Injection

| Sink | Unsafe | Safe |
| --- | --- | --- |
| SQL | f-strings or `%` into `execute` | driver placeholders (`execute(sql, params)`), SQLAlchemy Core/ORM expressions; identifiers from an allow-list |
| Shell | `os.system`, `subprocess.*(..., shell=True)` | `subprocess.run([exe, *args], shell=False, timeout=..., check=True)`; see the [subprocess helper](../assets/safe_subprocess.py.template) |
| Templates | `jinja2.Environment(autoescape=False)` for HTML; rendering user-supplied template source | `autoescape=select_autoescape()`, templates only from trusted files, `SandboxedEnvironment` if users author templates |
| LDAP | string-built filters | `ldap3.utils.conv.escape_filter_chars` on every value |
| Code | `eval`, `exec`, `compile` on input | `ast.literal_eval` for literals, a parser for a real grammar, or a lookup table of allowed operations |
| Headers and logs | raw newlines in values | reject `\r` and `\n`; structured logging |

Argument lists remove shell parsing but not option injection: put `--` before
user-supplied positional arguments and validate that values do not start
with `-` when the program would treat them as options.

## Subprocess

- Use an absolute or resolved executable (`shutil.which`) to avoid `PATH`
  hijacking; Ruff `S607` flags partial paths.
- Always pass `timeout=`; a hung child is a denial of service.
- Pass a minimal `env=` when the child does not need the parent's secrets.
- Capture output with a size limit when it is untrusted; never echo it into
  a shell again.

## Paths and files

- Resolve the joined path and require it to stay under the base directory:
  `candidate.resolve().is_relative_to(base.resolve())`. See the
  [path helper](../assets/safe_paths.py.template).
- Reject absolute paths, drive letters, `..` parts, NUL bytes and symlinks
  that leave the base when the input names a file.
- Extract archives member by member after validating names and sizes;
  for `tarfile` use `extractall(filter="data")`.
- Create files with explicit permissions (`os.open` with mode `0o600` for
  secrets) and open text with an explicit encoding.

## Server-side request forgery

- Allow-list schemes (`https`) and hosts; never fetch a URL the caller fully
  controls.
- Resolve the host and reject private, loopback, link-local and metadata
  addresses (`ipaddress.ip_address(...).is_private`, `is_loopback`,
  `is_link_local`, `is_reserved`) for every resolved address.
- Disable or re-validate redirects; set connect and read timeouts; cap the
  response size.

## Deserialization and parsers

| Data | Unsafe | Safe |
| --- | --- | --- |
| Python objects | `pickle.loads`, `marshal.loads`, `shelve`, `dill` on untrusted bytes | JSON plus schema validation; sign and verify (`hmac.compare_digest`) only between trusted parties |
| YAML | `yaml.load(data)`, `Loader=yaml.Loader`, `yaml.unsafe_load` | `yaml.safe_load` or `Loader=yaml.SafeLoader` |
| XML | `xml.etree`, `xml.dom.minidom`, `lxml` defaults on untrusted XML | `defusedxml.ElementTree.fromstring` and friends |
| Archives | blind `extractall` | per-member validation, size limits, `filter="data"` |

## Secrets

- Read secrets from the environment or a secret manager at startup into a
  type that hides its value (`pydantic.SecretStr` or a class whose `__repr__`
  redacts).
- Never log, return or put secrets in exception messages, URLs or command
  lines (process lists are visible to other users).
- Compare tokens with `hmac.compare_digest`.
- Keep test credentials obviously fake and scan commits with a secrets scanner.

## Cryptography and randomness

- Tokens, nonces, reset codes: `secrets.token_urlsafe(32)`, `secrets.token_bytes`,
  `secrets.choice`. The `random` module is for simulations only (Ruff `S311`).
- Passwords: never `hashlib.sha256(password)` or any fast hash, salted or not.
  Use Argon2id (`argon2-cffi`), scrypt (`hashlib.scrypt` with strong
  parameters) or bcrypt (`bcrypt`), and rehash on parameter upgrades.
- Encryption: use a high-level library (`cryptography` Fernet or AEAD
  primitives such as AES-GCM); never write a mode or padding yourself.
- Keep TLS verification on (`verify=True` is the default; Ruff `S501` flags
  `verify=False`).

## Temporary files

- `tempfile.mkstemp`, `NamedTemporaryFile` or `TemporaryDirectory`; never
  `tempfile.mktemp` (race) or a hard-coded `/tmp/name` (Ruff `S108`).

## Regular expressions

- Avoid nested quantifiers on overlapping input (`(a+)+`, `(.*a){n}`); they
  backtrack catastrophically.
- Bound input length before matching; prefer `fullmatch` with anchored,
  linear patterns; Python 3.11+ supports atomic groups and possessive
  quantifiers to cut backtracking.

## Logging hygiene

- Log security events (authentication failures, authorization denials,
  validation rejects) with a stable event name and non-sensitive context.
- Redact secrets and personal data before formatting; prefer an allow-list of
  logged fields over a deny-list.
- Use lazy `%` formatting and never log raw request bodies or headers.

## Error handling

- Fail closed: an exception in an authorization check denies access.
- Return generic messages to callers and log the detail once at the boundary.

## Internal tools versus exposed services

| Control | Internal tool | Exposed service |
| --- | --- | --- |
| Subprocess and path safety | required | required |
| Deserialization safety | required for files from other systems | required |
| Authentication and authorization | operating system or SSO account | full ASVS V6 to V10 |
| Rate limiting, request size limits | optional | required |
| Security headers, CORS | not applicable | required |
| Threat model | a short note | a worksheet per entry point |

## Primary sources

- Python, [subprocess security considerations](https://docs.python.org/3/library/subprocess.html#security-considerations)
- Python, [secrets](https://docs.python.org/3/library/secrets.html), [tempfile](https://docs.python.org/3/library/tempfile.html), [tarfile extraction filters](https://docs.python.org/3/library/tarfile.html#extraction-filters)
- Python, [XML vulnerabilities](https://docs.python.org/3/library/xml.html#xml-vulnerabilities) and [defusedxml](https://github.com/tiran/defusedxml)
- PyYAML, [yaml.load deprecation](https://github.com/yaml/pyyaml/wiki/PyYAML-yaml.load%28input%29-Deprecation)
- OWASP, [Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- OWASP, [Server-Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- OWASP, [Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html)
- OWASP, [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- OWASP, [Regular expression Denial of Service](https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS)
- [cryptography](https://cryptography.io/), [argon2-cffi](https://argon2-cffi.readthedocs.io/), [bcrypt](https://github.com/pyca/bcrypt)
