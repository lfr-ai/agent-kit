"""Check a LiteLLM proxy config or a resolved compose file exported as JSON.

Input: one JSON document from a file path or ``-`` for standard input.

- LiteLLM config (top-level ``model_list``): convert the YAML first, for
  example with PyYAML or yq. Findings: credential fields whose value is not an
  ``os.environ/`` reference, string values that look like provider keys,
  deployments without a positive timeout when no global timeout is set,
  ``:latest`` models, untagged Ollama models, fallback targets that are not
  defined aliases, and production aliases (``--production``, repeatable)
  without a fallback.
- Compose file (top-level ``services``): pipe the JSON output of
  ``docker compose config --format json`` into ``-`` so resolved secrets are
  never stored. Findings: images without a ``sha256`` digest that use no tag,
  a floating tag, or an unresolved variable. Environment values are not
  inspected in this mode.

Findings print as ``<location>: <message>`` and never include values.
``--self-test`` runs built-in synthetic cases without any input file.
Exit codes: 0 clean, 1 findings, 2 unreadable input or bad arguments.
Limitations: static checks only; it does not contact the proxy, a registry or
a provider, and cannot prove that a referenced variable holds a secret.
"""

import argparse
from collections.abc import Iterator, Mapping, Sequence
import json
from pathlib import Path
import re
import sys

EXIT_CLEAN: int = 0
EXIT_FINDINGS: int = 1
EXIT_INVALID: int = 2
ENV_REFERENCE: str = "os.environ/"
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "master_key",
        "salt_key",
        "database_url",
        "password",
        "redis_password",
        "aws_access_key_id",
        "aws_secret_access_key",
        "azure_ad_token",
        "client_secret",
        "vertex_credentials",
        "langfuse_public_key",
        "langfuse_secret_key",
    }
)
SENSITIVE_SUFFIXES: tuple[str, ...] = ("_api_key", "_secret", "_password", "_token")
FLOATING_TAGS: frozenset[str] = frozenset(
    {"latest", "main-latest", "main-stable", "stable", "main", "nightly", "dev", "edge"}
)
LOCAL_PREFIXES: tuple[str, ...] = ("ollama/", "ollama_chat/")
_KEY_LIKE = re.compile(r"^(sk-|sk_|pk-lf-|sk-lf-)[A-Za-z0-9_-]{8,}")
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
_SHA256_HEX_CHARS = 64
_SELF_TEST_TIMEOUT = 10
_FALLBACK_KEYS = ("fallbacks", "context_window_fallbacks", "content_policy_fallbacks")


def _walk(value: object, location: str) -> Iterator[tuple[str, str, object]]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{location}.{key}" if location else str(key)
            yield path, str(key), item
            yield from _walk(item, path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{location}[{index}]"
            yield path, "", item
            yield from _walk(item, path)


def _sensitive(key: str) -> bool:
    lowered = key.lower()
    return lowered in SENSITIVE_KEYS or lowered.endswith(SENSITIVE_SUFFIXES)


def secret_findings(document: Mapping[str, object]) -> list[str]:
    """Report literal credentials and key-like strings.

    Args:
        document (Mapping[str, object]): Decoded LiteLLM configuration.

    Returns:
        list[str]: Findings with locations only.
    """
    findings: list[str] = []
    for path, key, value in _walk(document, ""):
        if not isinstance(value, str):
            continue
        if key and _sensitive(key) and not value.startswith(ENV_REFERENCE):
            findings.append(f"{path}: credential must be an {ENV_REFERENCE} reference")
        elif _KEY_LIKE.match(value):
            findings.append(f"{path}: value looks like a literal provider key")
    return findings


def _positive_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def _section(document: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = document.get(name)
    return value if isinstance(value, Mapping) else {}


def _deployments(
    document: Mapping[str, object],
) -> Iterator[tuple[str, str, Mapping[str, object]]]:
    entries = document.get("model_list")
    for index, entry in enumerate(entries if isinstance(entries, list) else []):
        location = f"model_list[{index}]"
        if not isinstance(entry, Mapping):
            continue
        alias = entry.get("model_name")
        params = entry.get("litellm_params")
        yield (
            location,
            alias if isinstance(alias, str) else "",
            params if isinstance(params, Mapping) else {},
        )


def _timeout_problem(timeout: object, *, has_global_timeout: bool) -> str | None:
    if timeout is not None and not _positive_number(timeout):
        return "timeout: must be positive"
    if timeout is None and not has_global_timeout:
        return "timeout: no timeout configured"
    return None


def _model_problem(model: object) -> str | None:
    if not isinstance(model, str) or not model:
        return "model: model is required"
    if model.endswith(":latest"):
        return "model: floating latest tag"
    if model.startswith(LOCAL_PREFIXES) and ":" not in model.split("/", 1)[1]:
        return "model: local model needs a tag"
    return None


def deployment_findings(document: Mapping[str, object]) -> list[str]:
    """Report missing aliases, missing timeouts and unpinned models.

    Args:
        document (Mapping[str, object]): Decoded LiteLLM configuration.

    Returns:
        list[str]: Findings with locations only.
    """
    has_global_timeout = _positive_number(
        _section(document, "router_settings").get("timeout")
    ) or _positive_number(_section(document, "litellm_settings").get("request_timeout"))
    findings: list[str] = []
    for location, alias, params in _deployments(document):
        if not alias:
            findings.append(f"{location}.model_name: alias is required")
        problems = (
            _timeout_problem(
                params.get("timeout"), has_global_timeout=has_global_timeout
            ),
            _model_problem(params.get("model")),
        )
        findings.extend(
            f"{location}.litellm_params.{problem}" for problem in problems if problem
        )
    return findings


def _fallback_rules(
    document: Mapping[str, object],
) -> Iterator[tuple[str, str, str, list[object]]]:
    for section in ("router_settings", "litellm_settings"):
        settings = _section(document, section)
        for key in _FALLBACK_KEYS:
            rules = settings.get(key)
            for index, rule in enumerate(rules if isinstance(rules, list) else []):
                if not isinstance(rule, Mapping):
                    continue
                for source, targets in rule.items():
                    location = f"{section}.{key}[{index}].{source}"
                    yield (
                        location,
                        key,
                        str(source),
                        (targets if isinstance(targets, list) else []),
                    )


def _rule_findings(
    document: Mapping[str, object], aliases: set[str]
) -> tuple[list[str], set[str]]:
    findings: list[str] = []
    covered: set[str] = set()
    for location, key, source, targets in _fallback_rules(document):
        if not targets:
            findings.append(f"{location}: fallback list is empty")
        findings.extend(
            f"{location}: target is undefined or the source alias"
            for target in targets
            if target not in aliases or target == source
        )
        if key == "fallbacks" and targets:
            covered.add(source)
    return findings, covered


def fallback_findings(
    document: Mapping[str, object], *, production: Sequence[str]
) -> list[str]:
    """Report undefined fallback targets and production aliases without fallbacks.

    Args:
        document (Mapping[str, object]): Decoded LiteLLM configuration.
        production (Sequence[str]): Aliases that must have a general fallback.

    Returns:
        list[str]: Findings with locations only.
    """
    aliases = {alias for _, alias, _ in _deployments(document) if alias}
    findings, covered = _rule_findings(document, aliases)
    defaults = _section(document, "router_settings").get("default_fallbacks")
    has_default = isinstance(defaults, list) and bool(defaults)
    for alias in production:
        if alias not in aliases:
            findings.append(f"--production {alias}: alias is not defined")
        elif alias not in covered and not has_default:
            findings.append(f"--production {alias}: production alias has no fallback")
    return findings


def _image_problem(image: str) -> str | None:
    if "${" in image:
        return "unresolved variable; check resolved config"
    if _DIGEST.search(image):
        return None
    last = image.rsplit("/", 1)[-1]
    tag = last.split(":", 1)[1] if ":" in last else ""
    if not tag:
        return "image has no tag or digest"
    if tag in FLOATING_TAGS or tag.endswith("-latest"):
        return "floating tag; pin a release and digest"
    return "tag without digest; add @sha256 digest"


def image_findings(document: Mapping[str, object]) -> list[str]:
    """Report compose images that are not pinned by digest or a fixed tag.

    Args:
        document (Mapping[str, object]): Decoded, resolved compose document.

    Returns:
        list[str]: Findings with locations only.
    """
    findings: list[str] = []
    for name, service in sorted(_section(document, "services").items()):
        image = service.get("image") if isinstance(service, Mapping) else None
        problem = _image_problem(image) if isinstance(image, str) and image else None
        if problem:
            findings.append(f"services.{name}.image: {problem}")
    return findings


def check(document: Mapping[str, object], *, production: Sequence[str]) -> list[str]:
    """Dispatch on document kind and return sorted findings.

    Args:
        document (Mapping[str, object]): Decoded JSON document.
        production (Sequence[str]): Production aliases for LiteLLM configs.

    Returns:
        list[str]: Sorted findings.

    Raises:
        ValueError: The document is neither a LiteLLM config nor a compose file.
    """
    if "model_list" in document:
        findings = [
            *secret_findings(document),
            *deployment_findings(document),
            *fallback_findings(document, production=production),
        ]
    elif "services" in document:
        findings = image_findings(document)
    else:
        message = "expected a LiteLLM config (model_list) or compose file (services)"
        raise ValueError(message)
    return sorted(findings)


def _load(source: str) -> Mapping[str, object]:
    text = sys.stdin.read() if source == "-" else Path(source).read_text("utf-8")
    document: object = json.loads(text)
    if not isinstance(document, dict):
        message = "expected a JSON object"
        raise TypeError(message)
    return {str(key): value for key, value in document.items()}


def _self_test_cases() -> list[tuple[str, Mapping[str, object], str | None]]:
    # pragma: allowlist nextline secret: synthetic rejection fixture
    secret = "sk-" + "synthetic-selftest-value"
    env_key = ENV_REFERENCE + "PROVIDER_KEY"

    def config(**params: object) -> dict[str, object]:
        deployment = {"model": "openai/model-snapshot", "api_key": env_key, **params}
        return {"model_list": [{"model_name": "chat", "litellm_params": deployment}]}

    covered = {
        **config(timeout=_SELF_TEST_TIMEOUT),
        "router_settings": {"default_fallbacks": ["chat"]},
    }
    pinned = "registry.example/gateway:1.0.0@sha256:" + "0" * _SHA256_HEX_CHARS
    return [
        ("clean config", covered, None),
        (
            "literal key",
            config(api_key=secret, timeout=_SELF_TEST_TIMEOUT),
            "credential must be",
        ),
        ("missing timeout", config(), "no timeout configured"),
        (
            "latest model",
            config(model="ollama/m:latest", timeout=_SELF_TEST_TIMEOUT),
            "latest",
        ),
        (
            "untagged local model",
            config(model="ollama/m", timeout=_SELF_TEST_TIMEOUT),
            "needs a tag",
        ),
        ("no fallback", config(timeout=_SELF_TEST_TIMEOUT), "has no fallback"),
        ("pinned image", {"services": {"s": {"image": pinned}}}, None),
        ("floating image", {"services": {"s": {"image": "x/y:latest"}}}, "floating"),
    ]


def self_test() -> list[str]:
    """Run built-in synthetic cases and return unmet expectations.

    Returns:
        list[str]: One message per case whose findings did not match.
    """
    failures: list[str] = []
    for label, document, expected in _self_test_cases():
        findings = check(
            document, production=["chat"] if "model_list" in document else []
        )
        if expected is None and findings:
            failures.append(f"{label}: expected no findings")
        elif expected is not None and not any(expected in item for item in findings):
            failures.append(f"{label}: expected a finding containing {expected!r}")
    return failures


def _run_self_test() -> int:
    failures = self_test()
    for failure in failures:
        sys.stderr.write(failure + "\n")
    if failures:
        return EXIT_FINDINGS
    sys.stdout.write("check_gateway_config self-test passed.\n")
    return EXIT_CLEAN


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv (Sequence[str] | None): Arguments; defaults to ``sys.argv``.

    Returns:
        int: 0 clean, 1 findings, 2 invalid input or arguments.
    """
    parser = argparse.ArgumentParser(description="Check model gateway configuration.")
    parser.add_argument(
        "source", nargs="?", help="JSON file path, or - for standard input"
    )
    parser.add_argument("--production", action="append", default=[])
    parser.add_argument(
        "--self-test", action="store_true", help="run built-in checks and exit"
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return EXIT_CLEAN if error.code == EXIT_CLEAN else EXIT_INVALID
    if args.self_test:
        return _run_self_test()
    if args.source is None:
        sys.stderr.write("invalid input: a source path or - is required\n")
        return EXIT_INVALID
    try:
        findings = check(_load(args.source), production=args.production)
    except (OSError, TypeError, ValueError) as error:
        sys.stderr.write(f"invalid input: {error}\n")
        return EXIT_INVALID
    for finding in findings:
        sys.stdout.write(finding + "\n")
    return EXIT_FINDINGS if findings else EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
