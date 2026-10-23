"""Frontend skill resources: runnable checkers, parseable templates, and roles."""

import json
from pathlib import Path
import re
import runpy

import pytest

_SKILLS = Path(__file__).resolve().parents[3] / "packages/frontend/.apm/skills"
_IMPORTS = runpy.run_path(
    str(_SKILLS / "kit-react-feature/assets/check_feature_imports.py")
)
_BUNDLE = runpy.run_path(
    str(_SKILLS / "kit-runtime-config/assets/scan_public_bundle.py")
)
_HAR = runpy.run_path(str(_SKILLS / "kit-browser-debugging/assets/check_har.py"))
_TOOL_WORDS = ("powershell", "grep", "glob", "bash", "view tool", "edit tool")


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# Feature import boundary checker


def test_feature_imports_accept_public_entries_and_packages(tmp_path: Path) -> None:
    _write(tmp_path, "src/features/orders/index.ts", "export const a = 1;\n")
    _write(
        tmp_path,
        "src/features/invoices/ui/list.tsx",
        'import { a } from "../../orders";\n'
        'import { b } from "@/features/orders/index";\n'
        'import { c } from "./local";\n'
        'import React from "react";\n',
    )
    _write(tmp_path, "src/shared/util.ts", 'import { z } from "zod";\n')
    assert _IMPORTS["check"](tmp_path, aliases=("@/=src/",)) == []


def test_feature_imports_report_deep_and_inverted_imports(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/features/invoices/ui/list.tsx",
        'import { x } from "@/features/orders/api/orders.api";\n'
        'const lazy = () => import("../../orders/ui/view");\n',
    )
    _write(tmp_path, "src/shared/util.ts", 'export * from "../features/orders";\n')
    findings = _IMPORTS["check"](tmp_path, aliases=("@/=src/",))
    deep = "deep import into feature 'orders'"
    hint = "import its public index instead"
    source = "src/features/invoices/ui/list.tsx"
    assert findings == [
        f"{source}:1: {deep} (@/features/orders/api/orders.api); {hint}",
        f"{source}:2: {deep} (../../orders/ui/view); {hint}",
        "src/shared/util.ts:1: shared code imports feature 'orders' (../features/orders)",
    ]


def test_feature_imports_honor_custom_directories_and_skip_generated(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "app/modules/a/x.ts", 'import "../b/internal/y";\n')
    _write(tmp_path, "app/common/z.ts", 'import "../modules/a";\n')
    _write(tmp_path, "node_modules/pkg/index.ts", 'import "../../app/modules/a/x";\n')
    findings = _IMPORTS["check"](
        tmp_path, features_dir="app/modules", shared_dirs=("app/common",)
    )
    assert [finding.split(":", 1)[0] for finding in findings] == [
        "app/common/z.ts",
        "app/modules/a/x.ts",
    ]


def test_feature_imports_reject_malformed_alias(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="PREFIX=DIRECTORY"):
        _IMPORTS["check"](tmp_path, aliases=("@/src/",))


def test_feature_imports_main_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "src/features/a/x.ts", 'import "../b/deep";\n')
    assert _IMPORTS["main"](["--root", str(tmp_path)]) == 1
    assert "deep import into feature 'b'" in capsys.readouterr().out
    _write(tmp_path, "src/features/a/x.ts", 'import "../b";\n')
    assert _IMPORTS["main"](["--root", str(tmp_path)]) == 0
    assert _IMPORTS["main"](["--root", str(tmp_path), "--alias", "bad"]) == 1
    assert _IMPORTS["main"](["--self-test"]) == 0


# Public bundle scanner


def test_bundle_scan_passes_clean_output(tmp_path: Path) -> None:
    _write(tmp_path, "assets/index.js", 'const base="https://api.example.test/";\n')
    _write(tmp_path, "index.html", "<!doctype html><title>App</title>\n")
    assert _BUNDLE["scan"](tmp_path) == []


def test_bundle_scan_reports_redacted_secrets_and_options(tmp_path: Path) -> None:
    secret = "client_" + 'secret: "' + "s" * 20 + '"'  # pragma: allowlist secret
    token = "gh" + "p_" + "a" * 36
    _write(tmp_path, "assets/app.js", f"const cfg={{{secret}}};\nconst t='{token}';\n")
    _write(tmp_path, "assets/app.js.map", "{}\n")
    _write(tmp_path, "config.json", '{"api": "https://db.internal.test"}\n')
    findings = _BUNDLE["scan"](
        tmp_path, deny=(r"\.internal\.test",), forbid_source_maps=True
    )
    rules = [item.split("[", 1)[1].split("]", 1)[0] for item in findings]
    assert rules == ["source-map", "client-secret", "vcs-token", "denied-pattern"]
    assert all("a" * 36 not in item and "s" * 20 not in item for item in findings)
    assert _BUNDLE["scan"](tmp_path, allow=(r"client_secret.*", r"gh._a+")) == []


def test_bundle_scan_flags_oversized_files_and_rejects_missing_root(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "big.js", "x" * 100)
    assert _BUNDLE["scan"](tmp_path, max_bytes=10) == [
        "big.js:1: [too-large] not scanned (> 10)"
    ]
    with pytest.raises(ValueError, match="not a directory"):
        _BUNDLE["scan"](tmp_path / "missing")


def test_bundle_scan_main_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "a.js", "const ok = 1;\n")
    assert _BUNDLE["main"]([str(tmp_path)]) == 0
    _write(tmp_path, "b.js", "const k='AKIA" + "Q" * 16 + "';\n")
    assert _BUNDLE["main"]([str(tmp_path)]) == 1
    assert "[cloud-access-key-id]" in capsys.readouterr().out
    assert _BUNDLE["main"]([str(tmp_path / "nope")]) == 1
    assert _BUNDLE["main"](["--self-test"]) == 0


# HAR checker


def _har(entries: list[dict[str, object]]) -> str:
    return json.dumps({"log": {"version": "1.2", "entries": entries}})


def test_har_check_accepts_sanitized_archive(tmp_path: Path) -> None:
    entry: dict[str, object] = {
        "request": {
            "headers": [{"name": "Authorization", "value": ""}],
            "queryString": [{"name": "page", "value": "1"}],
        },
        "response": {"headers": [{"name": "Content-Type", "value": "x"}]},
    }
    path = _write(tmp_path, "ok.har", _har([entry]))
    assert _HAR["check"](path) == []


def test_har_check_reports_without_echoing_values(tmp_path: Path) -> None:
    entry: dict[str, object] = {
        "request": {
            "headers": [{"name": "Cookie", "value": "sid=topsecretvalue"}],
            "queryString": [
                {"name": "access_token", "value": "topsecretvalue"},
                {"name": "q", "value": "someone@example.test"},
            ],
            "postData": {
                "text": '{"client_secret": "topsecretvalue"}'  # pragma: allowlist secret
            },  # pragma: allowlist secret
        },
        "response": {"content": {"text": '{"refresh_token": "topsecretvalue"}'}},
    }
    path = _write(tmp_path, "leak.har", _har([entry]))
    findings = _HAR["check"](path)
    assert findings == [
        "leak.har:0: request header 'Cookie' has a value",
        "leak.har:0: query parameter 'access_token' has a value",
        "leak.har:0: query parameter 'q' contains an email",
        "leak.har:0: request body contains a sensitive field",
        "leak.har:0: response body contains a sensitive field",
    ]
    assert all("topsecretvalue" not in item for item in findings)


def test_har_check_bodies_and_invalid_input(tmp_path: Path) -> None:
    entry: dict[str, object] = {
        "request": {},
        "response": {"content": {"text": "<html></html>"}},
    }
    path = _write(tmp_path, "body.har", _har([entry]))
    assert _HAR["check"](path) == [
        "body.har:0: response body retained (export without content)"
    ]
    assert _HAR["check"](path, allow_bodies=True) == []
    bad = _write(tmp_path, "bad.har", '{"log": {}}')
    with pytest.raises(ValueError, match="not a HAR file"):
        _HAR["check"](bad)


def test_har_main_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = _write(tmp_path, "clean.har", _har([]))
    assert _HAR["main"]([str(clean)]) == 0
    broken = _write(tmp_path, "broken.har", "not json")
    assert _HAR["main"]([str(broken)]) == 1
    assert "Cannot check HAR input" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        _HAR["main"]([])
    assert _HAR["main"](["--self-test"]) == 0


# Templates, roles, and file hygiene


def _skill_files() -> list[Path]:
    return sorted(
        path
        for path in _SKILLS.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


@pytest.mark.parametrize(
    "template",
    sorted(_SKILLS.rglob("*.json.template")),
    ids=lambda path: path.name,
)
def test_json_templates_parse(template: Path) -> None:
    assert isinstance(json.loads(template.read_text(encoding="utf-8")), dict)


def test_every_skill_ships_code_templates_with_matching_tests() -> None:
    for skill in sorted(path for path in _SKILLS.iterdir() if path.is_dir()):
        templates = [path.name for path in (skill / "assets").glob("*.template")]
        assert any(
            name.endswith((".ts.template", ".tsx.template")) for name in templates
        )
        assert any(".test." in name or ".spec." in name for name in templates), skill


def test_frontend_files_are_utf8_lf_with_final_newline() -> None:
    for path in _skill_files():
        data = path.read_bytes()
        assert not data.startswith(b"\xef\xbb\xbf"), path
        assert b"\r" not in data, path
        assert data.endswith(b"\n"), path
        data.decode("utf-8")


def test_frontend_roles_have_structured_bodies_without_tool_names() -> None:
    asset = json.loads(
        (_SKILLS / "kit-react-feature/assets/agents.json").read_text(encoding="utf-8")
    )
    roles = {role["id"]: role for role in asset["roles"]}
    assert set(roles) == {"kit-frontend", "kit-frontend-implementer"}
    assert roles["kit-frontend"]["kind"] == "primary"
    assert roles["kit-frontend-implementer"]["kind"] == "worker"
    for role in roles.values():
        body = role["body"]
        assert 15 <= len(body.splitlines()) <= 60
        for heading in ("Mission", "Inputs", "Method", "Quality gates", "Report"):
            assert heading in body
        assert "Stop conditions" in body
        assert not any(
            re.search(rf"\b{re.escape(word)}\b", body, re.IGNORECASE)
            for word in _TOOL_WORDS
        )
        assert role["workers"] == []
