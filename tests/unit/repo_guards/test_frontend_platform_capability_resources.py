"""Frontend platform and naming-registry assets behave as documented."""

from collections.abc import Callable
import json
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND = _ROOT / "packages/frontend/.apm"
_COORDINATION = _ROOT / "packages/coordination/.apm"
_DESIGN = _FRONTEND / "skills/kit-design-system"
_BUILD = _FRONTEND / "skills/kit-frontend-build"
_AUTH = _FRONTEND / "skills/kit-client-auth"
_REGISTRY = _COORDINATION / "skills/kit-naming-registry"
_SKILLS = (_DESIGN, _BUILD, _AUTH, _REGISTRY)
_INSTRUCTIONS = (
    _FRONTEND / "instructions/kit-design-tokens.instructions.md",
    _COORDINATION / "instructions/kit-naming-registry.instructions.md",
)
_TOKENS = runpy.run_path(str(_DESIGN / "assets/check_design_tokens.py"))
_ENV = runpy.run_path(str(_BUILD / "assets/check_frontend_env.py"))
_GENERATE = runpy.run_path(str(_REGISTRY / "assets/generate_registry.py"))
_CHECK = runpy.run_path(str(_REGISTRY / "assets/check_registry.py"))
_LINK = re.compile(r"\]\(([^)#\s]+)\)")


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    return yaml.safe_load(header), body


# Skill and instruction structure


@pytest.mark.parametrize("skill", _SKILLS, ids=lambda path: path.name)
def test_skill_metadata_and_body_follow_the_contract(skill: Path) -> None:
    metadata, body = _frontmatter(skill / "SKILL.md")
    assert set(metadata) == {"name", "description", "license"}
    assert metadata["name"] == skill.name
    assert metadata["license"] == "MIT"
    assert metadata["description"].startswith("Use when")
    assert len(metadata["description"]) <= 350
    assert len(body.splitlines()) < 100
    assert "## Acceptance gates" in body
    assert re.search(r"^1\. ", body, re.MULTILINE)


@pytest.mark.parametrize("skill", _SKILLS, ids=lambda path: path.name)
def test_every_resource_is_linked_from_the_skill(skill: Path) -> None:
    linked = set(_LINK.findall((skill / "SKILL.md").read_text(encoding="utf-8")))
    resources = {
        path.relative_to(skill).as_posix()
        for folder in ("references", "assets")
        for path in (skill / folder).iterdir()
        if path.is_file()
    }
    assert resources <= linked, sorted(resources - linked)


@pytest.mark.parametrize("skill", _SKILLS, ids=lambda path: path.name)
def test_references_are_dated_and_cite_primary_sources(skill: Path) -> None:
    guide = (skill / "references/guide.md").read_text(encoding="utf-8")
    assert "2026-10-23" in guide
    for reference in (skill / "references").glob("*.md"):
        text = reference.read_text(encoding="utf-8")
        assert "https://" in text, reference.name
        assert "| --- |" in text, reference.name


@pytest.mark.parametrize("path", _INSTRUCTIONS, ids=lambda path: path.name)
def test_instructions_are_narrow_and_short(path: Path) -> None:
    metadata, body = _frontmatter(path)
    assert set(metadata) == {"description", "applyTo"}
    assert "**/*" not in metadata["applyTo"].split(",")
    bullets = [line for line in body.splitlines() if line.startswith("- ")]
    assert 4 <= len(bullets) <= 10


@pytest.mark.parametrize(
    "template",
    sorted(
        path for skill in _SKILLS for path in (skill / "assets").glob("*.json.template")
    ),
    ids=lambda path: path.name,
)
def test_json_templates_parse(template: Path) -> None:
    assert isinstance(json.loads(template.read_text(encoding="utf-8")), dict)


# Template contracts


def test_theme_is_css_first_with_semantic_layers() -> None:
    theme = (_DESIGN / "assets/theme.css.template").read_text(encoding="utf-8")
    assert '@import "tailwindcss";' in theme
    assert "@theme inline {" in theme
    assert "@custom-variant dark" in theme
    assert "--color-*: initial;" in theme
    assert "prefers-reduced-motion" in theme
    assert "forced-colors" in theme
    assert "tailwind.config" not in theme
    assert "@config" not in theme


def test_storybook_templates_use_csf3_interactions_and_axe() -> None:
    story = (_DESIGN / "assets/button.stories.tsx.template").read_text(encoding="utf-8")
    assert "satisfies Meta<typeof Button>" in story
    assert "play: async" in story
    assert 'a11y: { test: "error" }' in story
    main = (_DESIGN / "assets/storybook-main.ts.template").read_text(encoding="utf-8")
    assert "@storybook/addon-a11y" in main
    assert "disableTelemetry: true" in main


def test_strict_compiler_options_are_on() -> None:
    app = json.loads(
        (_BUILD / "assets/tsconfig.app.json.template").read_text(encoding="utf-8")
    )
    options = app["compilerOptions"]
    for flag in (
        "strict",
        "noUncheckedIndexedAccess",
        "exactOptionalPropertyTypes",
        "verbatimModuleSyntax",
    ):
        assert options[flag] is True, flag
    assert options["moduleResolution"] == "bundler"
    solution = json.loads(
        (_BUILD / "assets/tsconfig.solution.json.template").read_text(encoding="utf-8")
    )
    assert solution["files"] == []
    assert len(solution["references"]) == 2


def test_vite_template_limits_public_env_and_source_maps() -> None:
    config = (_BUILD / "assets/vite.config.ts.template").read_text(encoding="utf-8")
    assert 'envPrefix: ["VITE_"]' in config
    assert 'sourcemap: "hidden"' in config
    assert "rolldownOptions" in config
    vitest = (_BUILD / "assets/vitest.config.ts.template").read_text(encoding="utf-8")
    assert 'provider: "v8"' in vitest
    assert 'environment: "jsdom"' in vitest


def test_auth_templates_keep_tokens_out_of_web_storage() -> None:
    sources = [
        (_AUTH / "assets" / name).read_text(encoding="utf-8")
        for name in (
            "auth-provider.tsx.template",
            "auth-fetch.ts.template",
            "route-guard.tsx.template",
        )
    ]
    combined = "\n".join(sources)
    assert "localStorage" not in combined
    assert "sessionStorage" not in combined
    assert 'credentials: trusted ? "include" : "omit"' in combined
    assert "safeReturnTo" in combined
    guide = (_AUTH / "references/guide.md").read_text(encoding="utf-8")
    for citation in ("RFC 10017", "RFC 9700", "RFC 7636", "OWASP", "S256"):
        assert citation in guide


# check_design_tokens.py


def test_design_token_scan_reports_each_rule_with_position(tmp_path: Path) -> None:
    line = 'export const Card = () => <div className="bg-[#1d4ed8] w-[37px]" />;'
    tsx = _write(tmp_path, "src/card.tsx", f"{line}\n").as_posix()
    css = _write(
        tmp_path, "src/card.css", ".card {\n  color: rgb(0 0 0);\n  margin: 13px;\n}\n"
    ).as_posix()
    findings = _TOKENS["scan_paths"]([tmp_path])
    hex_column = line.index("#1d4ed8") + 1
    px_column = line.index("37px") + 1
    color = "is a raw color; use a semantic color token"
    scale = "bypasses the scale; use a spacing or size token"
    assert [item.render() for item in findings] == [
        f"{css}:2:10: [literal-color] rgb(0...) {color}",
        f"{css}:3:11: [arbitrary-px] 13px {scale}",
        f"{tsx}:1:{hex_column}: [hex-color] #1d4ed8 {color}",
        f"{tsx}:1:{px_column}: [arbitrary-px] 37px {scale}",
    ]


def test_design_token_scan_ignores_tokens_comments_and_allowed_values(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "styles/theme.css", ":root { --brand: #1d4ed8; }\n")
    _write(tmp_path, "node_modules/lib/x.css", "a { color: #fff; }\n")
    _write(
        tmp_path,
        "src/a.css",
        "/* #ffffff and 13px\n   in a block comment */\n"
        "a { border: 1px solid var(--border); margin: 0px; }\n"
        "b { inset: 3px; } /* design-tokens: allow hairline offset */\n",
    )
    _write(
        tmp_path,
        "src/b.tsx",
        "// legacy #123456 and 9px\n"
        'export const B = () => <a href="#main" className="p-4">&#123;</a>;\n',
    )
    assert _TOKENS["scan_paths"]([tmp_path]) == []
    custom = _TOKENS["scan_paths"]([tmp_path], token_files=("other.css",))
    assert [item.rule for item in custom] == ["hex-color"]


def test_design_token_scan_skips_only_directories_inside_the_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "build" / "src"
    bad = _write(root, "a.css", "a { margin: 13px; }\n")
    _write(root, "build/skipped.css", "a { margin: 13px; }\n")
    findings = _TOKENS["scan_paths"]([root])
    assert [(item.path, item.rule) for item in findings] == [
        (bad.as_posix(), "arbitrary-px")
    ]
    assert _TOKENS["main"]([str(root)]) == 1
    named = _write(tmp_path, "node_modules/theme.css", "a { margin: 13px; }\n")
    assert [item.rule for item in _TOKENS["scan_paths"]([named])] == ["arbitrary-px"]


def test_design_token_scan_accepts_its_own_templates(tmp_path: Path) -> None:
    for template in (_DESIGN / "assets").glob("*.t*.template"):
        name = template.name.removesuffix(".template")
        shutil.copy(template, tmp_path / name)
    shutil.copy(_DESIGN / "assets/theme.css.template", tmp_path / "theme.css")
    assert _TOKENS["scan_paths"]([tmp_path]) == []


def test_design_token_main_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = _write(tmp_path, "a.css", "a { color: var(--foreground); }\n")
    assert _TOKENS["main"]([str(clean)]) == 0
    bad = _write(tmp_path, "b.css", "a { width: 13px; }\n")
    assert _TOKENS["main"]([str(bad)]) == 1
    assert _TOKENS["main"]([str(bad), "--allow-px", "13"]) == 0
    assert _TOKENS["main"]([str(tmp_path / "missing")]) == 2
    assert "Cannot scan" in capsys.readouterr().err
    with pytest.raises(SystemExit) as error:
        _TOKENS["main"]([])
    assert error.value.code == 2
    assert _TOKENS["main"](["--self-test"]) == 0


# check_frontend_env.py


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("VITE_API_KEY", True),
        ("VITE_APIKEY", True),
        ("VITE_CLIENT_SECRET", True),
        ("VITE_AUTH_TOKENS", True),
        ("VITE_DB_PASSWORD", True),
        ("VITE_PRIVATE_URL", True),
        ("VITE_APP_NAME", False),
        ("VITE_KEYBOARD_LAYOUT", False),
        ("VITE_OIDC_CLIENT_ID", False),
        ("SERVER_SECRET", False),
    ],
)
def test_env_names_are_classified(name: str, expected: bool) -> None:
    assert _ENV["is_secret_like"](name, prefixes=("VITE_",)) is expected


def test_env_scan_reads_dotenv_files_and_sources(tmp_path: Path) -> None:
    _write(tmp_path, ".env.local", "VITE_APP_NAME=x\nexport VITE_API_KEY=\n")
    _write(tmp_path, ".env.example", "SERVER_SECRET=\nVITE_CLIENT_SECRET=\n")
    _write(tmp_path, "src/a.ts", "const t = import.meta.env.VITE_AUTH_TOKEN;\n")
    _write(
        tmp_path,
        "src/b.ts",
        "const s = import.meta.env.VITE_SECRET; // frontend-env: allow\n",
    )
    _write(tmp_path, "node_modules/x/.env", "VITE_API_KEY=\n")
    _write(tmp_path, "README.md", "VITE_API_KEY\n")
    findings = _ENV["scan_paths"]([tmp_path])
    assert [(Path(item.path).name, item.line, item.name) for item in findings] == [
        (".env.example", 2, "VITE_CLIENT_SECRET"),
        (".env.local", 2, "VITE_API_KEY"),
        ("a.ts", 1, "VITE_AUTH_TOKEN"),
    ]
    allowed = _ENV["scan_paths"]([tmp_path], allow=("VITE_API_KEY",))
    assert "VITE_API_KEY" not in {item.name for item in allowed}
    custom = _ENV["scan_paths"]([tmp_path], prefixes=("PUBLIC_",))
    assert custom == []


def test_env_example_template_is_clean(tmp_path: Path) -> None:
    shutil.copy(_BUILD / "assets/env.example.template", tmp_path / ".env.example")
    assert _ENV["scan_paths"]([tmp_path]) == []


def test_env_main_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = _write(tmp_path, "clean/.env", "VITE_APP_NAME=x\n")
    bad = _write(tmp_path, "bad/.env", "VITE_API_TOKEN=\n")
    assert _ENV["main"]([str(clean)]) == 0
    assert _ENV["main"]([str(bad)]) == 1
    assert "[secret-like-public-name] VITE_API_TOKEN" in capsys.readouterr().out
    assert _ENV["main"]([str(bad), "--allow", "VITE_API_TOKEN"]) == 0
    assert _ENV["main"]([str(bad), "--prefix", ""]) == 2
    assert _ENV["main"]([str(tmp_path / "missing")]) == 2
    with pytest.raises(SystemExit) as error:
        _ENV["main"]([])
    assert error.value.code == 2
    assert _ENV["main"](["--self-test"]) == 0


# generate_registry.py and check_registry.py


@pytest.fixture
def registry(tmp_path: Path) -> Path:
    assets = _REGISTRY / "assets"
    shutil.copy(
        assets / "naming_registry.schema.json.template",
        tmp_path / "naming_registry.schema.json",
    )
    target = tmp_path / "naming_registry.json"
    shutil.copy(assets / "naming_registry.json.template", target)
    return target


def _generate(registry: Path) -> tuple[Path, Path]:
    python = registry.parent / "out/registry.py"
    typescript = registry.parent / "out/registry.ts"
    arguments = [str(registry), "--python", str(python)]
    assert _GENERATE["main"]([*arguments, "--typescript", str(typescript)]) == 0
    return python, typescript


def _check(registry: Path, *extra: str) -> list[str]:
    python = registry.parent / "out/registry.py"
    typescript = registry.parent / "out/registry.ts"
    outputs = (python, typescript) if python.exists() else ()
    findings = _CHECK["check"](
        registry,
        outputs=outputs,
        baseline=Path(extra[0]) if extra else None,
    )
    return [item.render() for item in findings]


def _edit(registry: Path, change: Callable[..., object]) -> None:
    document = json.loads(registry.read_text(encoding="utf-8"))
    change(document)
    registry.write_text(json.dumps(document, indent=2), encoding="utf-8")


def test_generator_output_is_deterministic_and_importable(registry: Path) -> None:
    python, typescript = _generate(registry)
    first = (python.read_bytes(), typescript.read_bytes())
    _generate(registry)
    assert (python.read_bytes(), typescript.read_bytes()) == first
    module = runpy.run_path(str(python))
    assert module["REGISTRY_VERSION"] == "1.1.0"
    assert module["OrderStatus"].VOIDED == "voided"
    assert module["Route"]("/api/v1/orders/{order_id}").name == "ORDER_DETAIL"
    text = typescript.read_text(encoding="utf-8")
    assert "export const OrderStatus = {" in text
    assert "} as const;" in text
    assert "@deprecated since 1.1.0. Use CANCELLED." in text
    assert text.startswith("// Generated by generate_registry.py")


def test_checker_accepts_template_and_generated_files(registry: Path) -> None:
    _generate(registry)
    assert _check(registry, str(registry)) == []


def test_scripts_run_as_standalone_commands(registry: Path) -> None:
    out = registry.parent / "cli"
    commands = (
        [
            _REGISTRY / "assets/generate_registry.py",
            registry,
            "--python",
            out / "registry.py",
            "--typescript",
            out / "registry.ts",
        ],
        [
            _REGISTRY / "assets/check_registry.py",
            registry,
            "--python",
            out / "registry.py",
            "--typescript",
            out / "registry.ts",
        ],
    )
    for command in commands:
        result = subprocess.run(  # noqa: S603 - first-party scripts, synthetic inputs
            [sys.executable, *map(str, command)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_drift_detects_stale_edited_missing_and_unmarked_files(
    registry: Path,
) -> None:
    python, typescript = _generate(registry)
    python.write_text(
        python.read_text(encoding="utf-8") + "EXTRA = 1\n", encoding="utf-8"
    )
    typescript.unlink()
    findings = _check(registry)
    assert any("edited by hand" in item for item in findings)
    assert any("generated file is missing" in item for item in findings)
    _generate(registry)
    _edit(
        registry,
        lambda document: document["groups"][3]["entries"].append(
            {"name": "REFUNDED", "value": "refunded"}
        ),
    )
    assert sum("stale" in item for item in _check(registry)) == 2
    python.write_text('"""No header."""\n', encoding="utf-8")
    assert any("provenance header missing" in item for item in _check(registry))


@pytest.mark.parametrize(
    ("change", "rule"),
    [
        (
            lambda d: d["groups"][3]["entries"].append({"name": "X", "value": "paid"}),
            "[duplicate-value]",
        ),
        (
            lambda d: d["groups"][3]["entries"].append({"name": "PAID", "value": "x"}),
            "[duplicate-name]",
        ),
        (
            lambda d: d["groups"][0]["entries"].append(
                {"name": "BAD", "value": "/Orders_List"}
            ),
            "[value-pattern]",
        ),
        (
            lambda d: d["groups"][2]["entries"].append(
                {"name": "SHORT", "value": "created"}
            ),
            "[value-pattern]",
        ),
        (
            lambda d: d["groups"].append(
                {
                    "name": "MoreErrors",
                    "kind": "error_code",
                    "description": "Second group.",
                    "entries": [{"name": "AGAIN", "value": "order_not_found"}],
                }
            ),
            "[duplicate-value]",
        ),
        (lambda d: d["groups"][3].update(name="None"), "[reserved-name]"),
        (
            lambda d: d["groups"][3]["entries"][3]["deprecated"].update(
                replacement="MISSING"
            ),
            "[deprecation]",
        ),
        (
            lambda d: d["groups"][3]["entries"][3]["deprecated"].update(since="9.0.0"),
            "[deprecation]",
        ),
        (lambda d: d.update(version="2.0.0"), "[deprecation]"),
        (lambda d: d.update(extra=True), "[schema]"),
        (lambda d: d.pop("version"), "[schema]"),
        (lambda d: d["groups"][0].update(kind="url"), "[schema]"),
    ],
    ids=[
        "duplicate-value",
        "duplicate-name",
        "route-pattern",
        "event-pattern",
        "global-error-code",
        "reserved-name",
        "missing-replacement",
        "future-since",
        "past-remove-after",
        "extra-property",
        "missing-version",
        "unknown-kind",
    ],
)
def test_checker_reports_semantic_and_schema_problems(
    registry: Path, change: Callable[..., object], rule: str
) -> None:
    _edit(registry, change)
    assert any(rule in item for item in _check(registry))


def test_checker_reports_duplicate_json_keys(registry: Path) -> None:
    text = registry.read_text(encoding="utf-8")
    registry.write_text(
        text.replace('"version": "1.1.0",', '"version": "1.1.0", "version": "1.1.0",'),
        encoding="utf-8",
    )
    assert any("[duplicate-key]" in item for item in _check(registry))


def test_baseline_guards_removal_values_and_version(registry: Path) -> None:
    baseline = registry.parent / "released.json"
    shutil.copy(registry, baseline)
    _edit(registry, lambda d: d["groups"][3]["entries"].pop(0))
    findings = _check(registry, str(baseline))
    assert any("[removed]" in item for item in findings)
    assert any("[version]" in item for item in findings)
    shutil.copy(baseline, registry)
    _edit(
        registry,
        lambda d: (
            d["groups"][3]["entries"][1].update(value="settled"),
            d.update(version="1.2.0"),
        ),
    )
    assert [item for item in _check(registry, str(baseline)) if "[value" in item]


def test_baseline_allows_removing_expired_deprecations(registry: Path) -> None:
    baseline = registry.parent / "released.json"
    shutil.copy(registry, baseline)
    _edit(
        registry,
        lambda d: (d["groups"][3]["entries"].pop(3), d.update(version="2.0.0")),
    )
    assert _check(registry, str(baseline)) == []


def test_checker_and_generator_input_errors(
    registry: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _CHECK["main"]([str(registry.parent / "missing.json")]) == 2
    registry.write_text("{not json", encoding="utf-8")
    assert _CHECK["main"]([str(registry)]) == 2
    assert _GENERATE["main"]([str(registry), "--python", "x.py"]) == 2
    plain = _write(registry.parent, "plain.json", '{"version": "1.0.0"}')
    assert _CHECK["main"]([str(plain)]) == 2
    unsupported = _write(registry.parent, "s.json", '{"oneOf": []}')
    assert _CHECK["main"]([str(plain), "--schema", str(unsupported)]) == 2
    assert "unsupported schema keywords" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        _GENERATE["main"]([str(registry)])
    assert _CHECK["main"](["--self-test"]) == 0
    assert _GENERATE["main"](["--self-test"]) == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("description", 'Breaks """ docstrings'),
        ("description", "Closes */ comments"),
        ("name", "StrEnum"),
        ("name", "lowercase"),
    ],
)
def test_generator_rejects_unsafe_registry_text(field: str, value: str) -> None:
    group: dict[str, object] = {
        "name": "Status",
        "kind": "enum",
        "description": "Example.",
        "entries": [{"name": "ACTIVE", "value": "active"}],
    }
    group[field] = value
    document = {"version": "1.0.0", "groups": [group]}
    with pytest.raises(_GENERATE["RegistryError"]):
        _GENERATE["parse_registry"](document)
