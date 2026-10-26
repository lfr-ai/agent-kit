"""Backend persistence and Python idiom resources behave as documented."""

import ast
from pathlib import Path
import re
import runpy

import pytest
import yaml

_BACKEND = Path(__file__).resolve().parents[3] / "packages/backend/.apm"
_SQL_SKILL = _BACKEND / "skills/kit-sql-persistence"
_GRAPH_SKILL = _BACKEND / "skills/kit-graph-database"
_SERVICE_SKILL = _BACKEND / "skills/kit-python-service"
_SQL = runpy.run_path(str(_SQL_SKILL / "assets/check_sql_safety.py"))
_CYPHER = runpy.run_path(str(_GRAPH_SKILL / "assets/check_cypher_queries.py"))
_PYTHON = runpy.run_path(str(_SERVICE_SKILL / "assets/check_python.py"))
_LINK = re.compile(r"\]\(([^)#]+)")
_MAX_BODY_LINES = 300
_MAX_DESCRIPTION = 350


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sql(source: str) -> list[str]:
    return _SQL["check_source"](source, "m.py")


def _cypher(source: str) -> list[tuple[int, str]]:
    return [(item.line, item.rule) for item in _CYPHER["check_python"](source, "m.py")]


# check_sql_safety.py


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("session.execute(text(f\"SELECT * FROM t WHERE a = '{a}'\"))\n", "f-string"),
        ("q = 'SELECT * FROM t WHERE a = ' + a\nsession.execute(q)\n", "name 'q'"),
        ("cursor.execute('SELECT %s' % a)\n", "%-formatting"),
        ("session.execute(text('SELECT {}'.format(a)))\n", "str.format()"),
        ("sql = 'SELECT 1'\nsql += clause\nconnection.exec_driver_sql(sql)\n", "'sql'"),
        ("session.scalars(statement=f'SELECT {a}')\n", "f-string"),
        (
            "def f(a):\n    s = f'SELECT {a}'\n    t = s\n    return db.execute(t)\n",
            "'t'",
        ),
    ],
)
def test_sql_checker_flags_formatted_sql(source: str, kind: str) -> None:
    findings = _sql(source)
    assert len(findings) == 1
    assert "formatted-sql" in findings[0]
    assert kind in findings[0]


@pytest.mark.parametrize(
    "source",
    [
        "session.execute(text('SELECT * FROM t WHERE a = :a'), {'a': a})\n",
        "session.execute(text('SELECT 1'), {'pattern': f'%{term}%'})\n",
        "COLUMNS = 'a, b'\nsession.execute(text(f'SELECT {COLUMNS} FROM t'))\n",
        "session.execute(text('SELECT ' + _COLUMNS + ' FROM t'))\n",
        "session.execute(select(Row).where(Row.id == a))\n",
        "session.execute(text(f'SELECT {a}'))  # sql-safety: reviewed\n",
        "subprocess.check_call(f'echo {a}')\n",
    ],
)
def test_sql_checker_accepts_bound_constant_or_waived_sql(source: str) -> None:
    assert _sql(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "s = Session(engine)\n",
        "s = AsyncSession(engine)\n",
        "factory = sessionmaker(engine)\ns = factory()\n",
        "def f(self):\n    return self._session_factory()\n",
        "s = SessionLocal()\n",
    ],
)
def test_sql_checker_flags_sessions_outside_context_managers(source: str) -> None:
    findings = _sql(source)
    assert [finding.split(": ")[1] for finding in findings] == ["unmanaged-session"]


@pytest.mark.parametrize(
    "source",
    [
        "with Session(engine) as s, s.begin():\n    pass\n",
        "async def f():\n    async with factory() as s:\n        pass\n",
        "stack.enter_context(Session(engine))\n",
        "factory = async_sessionmaker(engine, expire_on_commit=False)\n",
        (
            "class Uow:\n    async def __aenter__(self):\n"
            "        self._session = self._session_factory()\n"
        ),
    ],
)
def test_sql_checker_accepts_managed_session_lifecycles(source: str) -> None:
    assert _sql(source) == []


def test_sql_checker_main_reports_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = _write(tmp_path, "clean/repo.py", "session.execute(text('SELECT 1'))\n")
    bad = _write(tmp_path, "bad/repo.py", "session.execute(text(f'SELECT {a}'))\n")
    _write(tmp_path, "bad/.venv/skip.py", "session.execute(f'SELECT {a}')\n")
    broken = _write(tmp_path, "broken/repo.py", "def (:\n")
    assert _SQL["main"]([str(clean)]) == 0
    assert _SQL["main"]([str(bad.parent)]) == 1
    assert capsys.readouterr().out.splitlines() == [
        (
            f"{bad.as_posix()}:1: formatted-sql: an f-string reaches text(); "
            "bind values as parameters and allow-list identifiers"
        )
    ]
    assert _SQL["main"]([str(broken)]) == 2
    assert _SQL["main"]([str(tmp_path / "missing")]) == 2
    assert "path does not exist" in capsys.readouterr().err


def test_sql_checker_scans_templates_only_on_request(tmp_path: Path) -> None:
    _write(tmp_path, "repo.py.template", "s = Session(engine)\n")
    assert _SQL["main"]([str(tmp_path)]) == 0
    assert _SQL["main"]([str(tmp_path), "--templates"]) == 1


def test_sql_assets_pass_their_own_checker() -> None:
    assert _SQL["main"]([str(_SQL_SKILL / "assets"), "--templates"]) == 0


@pytest.mark.parametrize("name", ["sql", "cypher"])
def test_checkers_self_test_and_require_paths_otherwise(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    module = {"sql": _SQL, "cypher": _CYPHER}[name]
    assert module["self_test"]() == []
    assert module["main"](["--self-test"]) == 0
    assert "self-test passed" in capsys.readouterr().out
    with pytest.raises(SystemExit) as raised:
        module["main"]([])
    assert raised.value.code == 2


# check_cypher_queries.py


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("tx.run(f'MATCH (n:{label}) RETURN n LIMIT 1')\n", [(1, "formatted-cypher")]),
        (
            "q = 'MATCH (n) WHERE n.a = ' + a + ' RETURN n LIMIT 1'\ntx.run(q)\n",
            [(2, "formatted-cypher")],
        ),
        (
            "driver.execute_query('MATCH (n:%s) RETURN n LIMIT 1' % label)\n",
            [(1, "formatted-cypher")],
        ),
        ("Query(text='CREATE (n:{})'.format(label))\n", [(1, "formatted-cypher")]),
        ("ALL = 'MATCH (c:Customer) RETURN c'\n", [(1, "unbounded-read")]),
        (
            "OWN = 'MATCH (c:C {id: $id})-[:P]->(o) RETURN o'\n",
            [(1, "unbounded-read")],
        ),
        ("tx.run('MATCH (a)-[:K*]->(b) RETURN b LIMIT 5')\n", [(1, "unbounded-read")]),
        (
            "tx.run('MATCH (a)-[:K*2..]->(b) RETURN b LIMIT 5')\n",
            [(1, "unbounded-read")],
        ),
    ],
)
def test_cypher_checker_flags_formatting_and_unbounded_reads(
    source: str, expected: list[tuple[int, str]]
) -> None:
    assert _cypher(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "tx.run('MATCH (n:A) WHERE n.id = $id RETURN n')\n",
        "FIND = 'MATCH (c:Customer {customerId: $id}) RETURN c'\n",
        "COUNT = 'MATCH (c:Customer) RETURN count(c) AS total'\n",
        "PAGE = 'MATCH (c:C)-[:P]->(o) RETURN o ORDER BY o.id LIMIT $limit'\n",
        "PATH = 'MATCH (a)-[:K*1..3]->(b) RETURN b LIMIT 5'\n",
        "WRITE = 'MATCH (n:A) SET n.seen = true RETURN n'\n",
        "subprocess.run(f'echo {name}')\n",
        "LABEL = 'Customer'\ntx.run(f'MATCH (n:{LABEL}) RETURN n LIMIT 1')\n",
        "TAGS = 'MATCH (t:Tag) RETURN t // cypher-safety: reviewed'\n",
        "tx.run(f'MATCH (n:{label}) RETURN n LIMIT 1')  # cypher-safety: reviewed\n",
    ],
)
def test_cypher_checker_accepts_parameterized_bounded_or_waived_queries(
    source: str,
) -> None:
    assert _cypher(source) == []


def test_cypher_checker_reads_statements_in_cypher_files() -> None:
    text = (
        "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:A) REQUIRE n.id IS UNIQUE;\n"
        "\n"
        "// all nodes\n"
        "MATCH (n:A)\n"
        "RETURN n;\n"
        "MATCH (n:A) RETURN n.name // cypher-safety: reviewed\n"
    )
    findings = _CYPHER["check_cypher"](text)
    assert [(item.line, item.rule) for item in findings] == [(3, "unbounded-read")]


def test_cypher_checker_main_reports_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = _write(tmp_path, "graph/ok.cypher", "MATCH (n:A) RETURN count(n);\n")
    bad = _write(tmp_path, "graph/bad.cypher", "MATCH (n:A) RETURN n;\n")
    broken = _write(tmp_path, "broken.py", "def (:\n")
    assert _CYPHER["main"]([str(clean)]) == 0
    assert _CYPHER["main"]([str(tmp_path / "graph")]) == 1
    assert capsys.readouterr().out.splitlines() == [
        (
            f"{bad.as_posix()}:1: unbounded-read: read query without LIMIT; "
            "bound it, aggregate, or seek a unique key"
        )
    ]
    assert _CYPHER["main"]([str(broken)]) == 2
    assert _CYPHER["main"]([str(tmp_path / "missing")]) == 2


def test_graph_assets_pass_their_own_checker() -> None:
    assert _CYPHER["main"]([str(_GRAPH_SKILL / "assets"), "--templates"]) == 0


# check_python.py redundant-default rule

_REDUNDANT = frozenset({"redundant-default"})
_DEFAULTS_SOURCE = (
    "from dataclasses import dataclass, field\n"
    "_LIMIT = 50\n"
    "def export(report, *, limit=_LIMIT, mode=Mode.FULL, strict=False):\n"
    "    return report\n"
    "@dataclass(frozen=True, kw_only=True, slots=True)\n"
    "class Settings:\n"
    "    timeout: float = 30.0\n"
    "    retries: int = field(default=3)\n"
    "class Client:\n"
    "    def __init__(self, *, verbose=False) -> None: ...\n"
    "def twice(*, flag=False): ...\n"
    "def twice(*, flag=True): ...\n"
)


@pytest.mark.parametrize(
    ("call", "argument"),
    [
        ("export(r, limit=_LIMIT)", "limit=_LIMIT"),
        ("export(r, mode=Mode.FULL)", "mode=Mode.FULL"),
        ("export(r, strict=False)", "strict=False"),
        ("Settings(timeout=30.0)", "timeout=30.0"),
        ("Settings(retries=3)", "retries=3"),
        ("Client(verbose=False)", "verbose=False"),
    ],
)
def test_python_checker_flags_repeated_defaults(call: str, argument: str) -> None:
    source = f"{_DEFAULTS_SOURCE}{call}\n"
    callee = call.partition("(")[0]
    findings = _PYTHON["violations"](source, "m.py", rules=_REDUNDANT)
    assert findings == [
        f"m.py:13: argument {argument} repeats the default of '{callee}'; omit it"
    ]


@pytest.mark.parametrize(
    "call",
    [
        "export(r, strict=True)",
        "export(r, limit=other_limit)",
        "Settings(timeout=5.0)",
        "twice(flag=False)",
        "imported(limit=_LIMIT)",
        "service.export(r, strict=False)",
    ],
)
def test_python_checker_keeps_deliberate_or_unknown_callee_arguments(call: str) -> None:
    source = f"{_DEFAULTS_SOURCE}{call}\n"
    assert _PYTHON["violations"](source, "m.py", rules=_REDUNDANT) == []


@pytest.mark.parametrize(
    ("definition", "call", "expected"),
    [
        ("def f(a, b=1, /): ...\n", "f(0, 1)\n", []),
        (
            "def f(a=1, /, b=2): ...\n",
            "f(1, b=2)\n",
            ["m.py:2: argument b=2 repeats the default of 'f'; omit it"],
        ),
        ("def f(a=1, /, b=2): ...\n", "f(a=1, b=3)\n", []),
    ],
)
def test_redundant_default_handles_positional_only_defaults(
    definition: str, call: str, expected: list[str]
) -> None:
    source = f"{definition}{call}"
    assert _PYTHON["violations"](source, "m.py", rules=_REDUNDANT) == expected


def test_redundant_default_rule_is_opt_in(tmp_path: Path) -> None:
    path = _write(tmp_path, "m.py", f"{_DEFAULTS_SOURCE}export(r, strict=False)\n")
    assert "redundant-default" in _PYTHON["ALL_RULES"]
    assert _PYTHON["main"]([str(path)]) == 0
    assert _PYTHON["main"]([str(path), "--redundant-defaults"]) == 1
    assert _PYTHON["main"]([str(path), "--only", "redundant-default"]) == 1


# Templates and capability structure


def _templates(skill: Path) -> list[Path]:
    return sorted((skill / "assets").glob("*.py.template"))


@pytest.mark.parametrize(
    "template", [*_templates(_SQL_SKILL), *_templates(_GRAPH_SKILL)], ids=str
)
def test_python_templates_parse_and_follow_conventions(template: Path) -> None:
    text = template.read_text(encoding="utf-8")
    ast.parse(text, filename=str(template))
    rules = _PYTHON["ALL_RULES"] - {"bool-trap"}
    if template.name.startswith(("test_", "conftest")):
        rules -= {"magic-number"}
    assert _PYTHON["violations"](text, template.name, rules=rules) == []


def test_sql_templates_keep_transaction_and_mapping_contracts() -> None:
    assets = _SQL_SKILL / "assets"
    repository = (assets / "repository.py.template").read_text(encoding="utf-8")
    unit = (assets / "unit_of_work.py.template").read_text(encoding="utf-8")
    factory = (assets / "session_factory.py.template").read_text(encoding="utf-8")
    models = (assets / "models_base.py.template").read_text(encoding="utf-8")
    assert ".commit(" not in repository
    assert "selectinload" in repository
    assert "tuple_(" in repository
    assert "await session.rollback()" in unit
    assert "await session.close()" in unit
    assert "expire_on_commit=False" in factory
    assert "pool_pre_ping=True" in factory
    assert "statement_timeout" in factory
    assert "PRAGMA foreign_keys = ON" in factory
    assert 'lazy="raise"' in models
    assert "version_id_col" in models
    assert "naming_convention" in models


def test_graph_templates_keep_parameter_and_schema_contracts() -> None:
    assets = _GRAPH_SKILL / "assets"
    catalog = ast.parse((assets / "query_catalog.py.template").read_text("utf-8"))
    queries = [
        node
        for node in catalog.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    assert queries
    for node in queries:
        assert "LiteralString" in ast.unparse(node.annotation)
        assert isinstance(node.value, ast.Constant)
        assert isinstance(node.value.value, str)
        assert "$" in node.value.value
    adapter = (assets / "graph_repository.py.template").read_text(encoding="utf-8")
    assert "execute_write" in adapter
    assert "execute_read" in adapter
    assert "RoutingControl.READ" in adapter
    schema = (assets / "schema.cypher.template").read_text(encoding="utf-8")
    creates = [line for line in schema.splitlines() if line.startswith("CREATE ")]
    assert creates
    assert all("IF NOT EXISTS" in line for line in creates)


@pytest.mark.parametrize("skill", [_SQL_SKILL, _GRAPH_SKILL, _SERVICE_SKILL], ids=str)
def test_skills_have_valid_metadata_and_link_every_resource(skill: Path) -> None:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    metadata = yaml.safe_load(frontmatter)
    assert set(metadata) == {"name", "description", "license"}
    assert metadata["name"] == skill.name
    assert metadata["license"] == "MIT"
    assert metadata["description"].startswith("Use when")
    assert len(metadata["description"]) <= _MAX_DESCRIPTION
    assert len(body.splitlines()) < _MAX_BODY_LINES
    linked = {(skill / target).resolve() for target in _LINK.findall(body)}
    resources = [
        path
        for folder in ("references", "assets")
        for path in (skill / folder).iterdir()
        if path.is_file() and path.name != "agents.json"
    ]
    assert [path.name for path in resources if path.resolve() not in linked] == []


def test_new_references_cite_primary_sources_with_review_date() -> None:
    references = [
        *(_SQL_SKILL / "references").glob("*.md"),
        *(_GRAPH_SKILL / "references").glob("*.md"),
        _SERVICE_SKILL / "references/python-idioms.md",
    ]
    for reference in references:
        text = reference.read_text(encoding="utf-8")
        assert "2026-10-23" in text, reference.name
        assert "## Primary sources" in text, reference.name
        assert "https://" in text, reference.name
    idioms = (_SERVICE_SKILL / "references/python-idioms.md").read_text("utf-8")
    for pep in (8, 257, 484, 544, 585, 604, 612, 646, 655, 681, 692, 695, 698, 749):
        assert f"pep-{pep:04d}" in idioms


@pytest.mark.parametrize(
    ("name", "skill"),
    [
        ("kit-sql.instructions.md", "kit-sql-persistence"),
        ("kit-cypher.instructions.md", "kit-graph-database"),
        ("kit-python-conventions.instructions.md", "kit-python-service"),
    ],
)
def test_instructions_are_scoped_and_point_to_their_skill(
    name: str, skill: str
) -> None:
    text = (_BACKEND / "instructions" / name).read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    metadata = yaml.safe_load(frontmatter)
    assert set(metadata) == {"description", "applyTo"}
    bullets = [line for line in body.splitlines() if line.startswith("- ")]
    assert bullets
    assert f"`{skill}`" in bullets[-1]
