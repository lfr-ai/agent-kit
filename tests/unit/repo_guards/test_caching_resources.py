"""The caching skill, its templates, checker, and instruction behave as documented."""

import ast
from pathlib import Path
import re
import runpy

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _ROOT / "packages/backend/.apm"
_SKILL = _BACKEND / "skills/kit-caching"
_ASSETS = _SKILL / "assets"
_INSTRUCTION = _BACKEND / "instructions/kit-cache-usage.instructions.md"
_CHECKER = runpy.run_path(str(_ASSETS / "check_cache_usage.py"))
_LINK = re.compile(r"\]\(([^)\s#]+)")
_VERIFIED = "Verified as of 2026-10-27"
_MAX_DESCRIPTION = 110


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    metadata = yaml.safe_load(header)
    assert isinstance(metadata, dict)
    return {str(key): str(value) for key, value in metadata.items()}, body


def _reachable(skill: Path) -> set[Path]:
    pending = [skill / "SKILL.md"]
    seen: set[Path] = set()
    while pending:
        path = pending.pop().resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8")
            pending.extend(
                path.parent / target
                for target in _LINK.findall(text)
                if "://" not in target
            )
    return seen


def _run(paths: list[str], *extra: str) -> int:
    main = _CHECKER["main"]
    assert callable(main)
    result = main([*paths, *extra])
    assert isinstance(result, int)
    return result


def _write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


# Skill structure


def test_skill_metadata_and_procedure_shape() -> None:
    metadata, body = _frontmatter(_SKILL / "SKILL.md")

    assert set(metadata) == {"name", "description", "license"}
    assert metadata["name"] == "kit-caching"
    assert metadata["license"] == "MIT"
    assert metadata["description"].startswith("Use when")
    assert "\n" not in metadata["description"]
    assert len(metadata["description"]) <= _MAX_DESCRIPTION
    assert len(body.splitlines()) < 300
    assert "## Procedure" in body
    assert "## Acceptance gates" in body
    assert re.search(r"^1\. ", body, re.MULTILINE)


def test_every_resource_is_linked_and_stays_inside_the_skill() -> None:
    resources = {
        path.resolve()
        for folder in ("references", "assets")
        for path in (_SKILL / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    reachable = _reachable(_SKILL)

    assert resources
    assert resources <= reachable
    assert all(path.is_relative_to(_SKILL.resolve()) for path in reachable)


@pytest.mark.parametrize(
    "reference", sorted((_SKILL / "references").glob("*.md")), ids=lambda p: p.name
)
def test_references_cite_dated_official_sources(reference: Path) -> None:
    text = reference.read_text(encoding="utf-8")

    assert _VERIFIED in text
    assert "## Sources" in text
    assert "https://" in text.split("## Sources", 1)[1]


def test_cross_skill_references_are_by_name_only() -> None:
    for document in [_SKILL / "SKILL.md", *(_SKILL / "references").glob("*.md")]:
        for target in _LINK.findall(document.read_text(encoding="utf-8")):
            if "://" not in target:
                assert (
                    (document.parent / target)
                    .resolve()
                    .is_relative_to(_SKILL.resolve())
                ), (document.name, target)


# Templates


@pytest.mark.parametrize(
    "path", sorted(_ASSETS.glob("*.py.template")), ids=lambda path: path.name
)
def test_python_templates_parse_and_name_a_destination(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstring = ast.get_docstring(tree)

    assert docstring
    assert re.search(r"Copy into ``[^`]+\.py``", docstring)
    assert not any(
        isinstance(node, ast.Name) and node.id == "Any" for node in ast.walk(tree)
    )


def test_python_templates_never_unpickle() -> None:
    for path in _ASSETS.glob("*.py.template"):
        assert "pickle.load" not in path.read_text(encoding="utf-8"), path.name


def test_compose_template_parses_with_pinned_image_and_health_check() -> None:
    document = yaml.safe_load(
        (_ASSETS / "compose.cache.yaml.template").read_text(encoding="utf-8")
    )
    service = document["services"]["cache"]

    assert service["image"].startswith("${CACHE_IMAGE:?")
    assert "healthcheck" in service
    assert all(port.startswith("127.0.0.1:") for port in service["ports"])
    command = service["command"]
    assert command[command.index("--save") + 1] == ""
    assert command[command.index("--appendonly") + 1] == "no"
    assert "allkeys-lru" in command
    assert "${CACHE_PASSWORD:?" in command[-1]


def test_cache_aside_template_documents_every_reported_event() -> None:
    text = (_ASSETS / "cache_aside.py.template").read_text(encoding="utf-8")
    emitted = set(re.findall(r'_on_event\(self\._namespace, "([a-z_]+)"\)', text))

    assert emitted == {
        "hit",
        "negative_hit",
        "miss",
        "load",
        "unavailable",
        "corrupt",
        "store_failed",
        "lock_wait",
        "lock_fallback",
    }
    for event in emitted:
        assert event in text.split("type CacheEventSink", 1)[1].split('"""', 2)[1]


# Instruction


def test_instruction_is_short_scoped_and_names_the_skill() -> None:
    text = _INSTRUCTION.read_text(encoding="utf-8")
    metadata, body = _frontmatter(_INSTRUCTION)
    bullets = [line for line in body.splitlines() if line.startswith("- ")]

    assert len(text.splitlines()) <= 20
    assert set(metadata) == {"description", "applyTo"}
    assert metadata["applyTo"] not in {"**", "**/*"}
    assert all(scope.startswith("**/") for scope in metadata["applyTo"].split(","))
    assert "`kit-caching`" in bullets[-1]
    assert _INSTRUCTION.name.removesuffix(".instructions.md") != _SKILL.name


# Checker


def test_checker_self_test_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run([], "--self-test") == 0
    assert "self-test passed" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        (
            (
                "import functools\nclass Repo:\n    @functools.lru_cache(maxsize=8)\n"
                "    def find(self, key):\n        return key\n"
            ),
            "method-cache",
        ),
        (
            (
                "from functools import cache as memo\nclass Repo:\n    @memo\n"
                "    def all(self):\n        return []\n"
            ),
            "method-cache",
        ),
        (
            "import functools\n@functools.cache\nasync def load(key):\n    return key\n",
            "async-cache",
        ),
        (
            (
                "from functools import lru_cache\n@lru_cache(maxsize=None)\n"
                "def price(sku):\n    return sku\n"
            ),
            "unbounded-cache",
        ),
        (
            (
                "import pickle as pk\nfrom valkey import Valkey\n"
                "def read(raw):\n    return pk.Unpickler(raw)\n"
            ),
            "pickle-redis",
        ),
    ],
    ids=["method", "aliased-method", "async", "unbounded", "pickle"],
)
def test_checker_reports_each_rule_with_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], source: str, rule: str
) -> None:
    path = _write(tmp_path, "shop/cache/module.py", source)

    assert _run([str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert re.search(
        rf"^{re.escape(path.as_posix())}:\d+: \[{rule}\] ", output, re.MULTILINE
    )


def test_checker_passes_clean_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        tmp_path,
        "shop/cache/clean.py",
        "import functools\nimport json\nimport redis\n"
        "@functools.lru_cache(maxsize=256)\ndef parse(text):\n    return text\n"
        "@functools.cache\ndef get_settings():\n    return {}\n"
        "class Units:\n    @staticmethod\n    @functools.lru_cache(maxsize=4)\n"
        "    def code(text):\n        return text\n"
        "def decode(raw):\n    return json.loads(raw)\n",
    )

    assert _run([str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_checker_honors_allow_unbounded_exclude_rule_and_suppression(
    tmp_path: Path,
) -> None:
    unbounded = (
        "from functools import cache\n@cache\ndef load(name):\n    return name\n"
    )
    _write(tmp_path, "shop/settings.py", unbounded)
    _write(tmp_path, "migrations/old.py", unbounded)
    _write(
        tmp_path,
        "shop/reviewed.py",
        "from functools import cache\n@cache  # cache-usage: reviewed\n"
        "def rate(code):\n    return code\n",
    )

    assert _run([str(tmp_path)]) == 1
    assert (
        _run(
            [str(tmp_path)],
            "--allow-unbounded",
            "*/settings.py",
            "--exclude",
            "migrations",
        )
        == 0
    )
    assert _run([str(tmp_path)], "--rule", "pickle-redis") == 0


def test_checker_ignores_unrelated_names(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "shop/helpers.py",
        "from shop.memo import cache\nimport pickle\n"
        "@cache\ndef price(sku):\n    return sku\n"
        "def restore(raw):\n    return pickle.loads(raw)\n",
    )

    assert _run([str(tmp_path)]) == 0


def test_checker_input_errors_exit_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "broken.py", "def broken(:\n")

    assert _run([str(tmp_path)]) == 2
    assert _run([str(tmp_path / "missing")]) == 2
    assert "input error" in capsys.readouterr().err
