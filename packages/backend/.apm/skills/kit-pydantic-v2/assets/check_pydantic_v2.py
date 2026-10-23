"""Flag Pydantic v1 APIs and compatibility shims in code that targets v2.

Python sources are parsed without importing them. Only files that import
``pydantic`` are inspected. Findings cover ``pydantic.v1`` imports,
``BaseSettings`` imported from ``pydantic``, v1 decorators (``validator``,
``root_validator``), inner ``class Config``, ``__root__`` fields, v1 ``Field`` and
config keywords, ``parse_obj_as`` style helpers, v1 class methods such as
``parse_obj``, and instance calls such as ``.dict(exclude_unset=True)``. A line
carrying ``# pydantic: reviewed`` is waived.
Exit 0 means no findings, 1 means findings or unreadable sources.
Run ``--self-test`` for built-in regressions.
"""

import argparse
import ast
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

_WAIVER = "# pydantic: reviewed"
_V1_DECORATORS = {
    "validator": "use field_validator",
    "root_validator": "use model_validator",
}
_V1_HELPERS = {
    "parse_obj_as": "use TypeAdapter(T).validate_python",
    "parse_raw_as": "use TypeAdapter(T).validate_json",
    "parse_file_as": "read the file, then TypeAdapter(T).validate_json",
    "schema_of": "use TypeAdapter(T).json_schema",
}
_V1_CLASS_METHODS = {
    "parse_obj": "use model_validate",
    "parse_raw": "use model_validate_json",
    "parse_file": "read the file, then model_validate_json",
    "from_orm": "use model_validate with from_attributes=True",
    "update_forward_refs": "use model_rebuild",
    "schema_json": "use json.dumps(Model.model_json_schema())",
}
_V1_DUMP_METHODS = {
    "dict": "use model_dump",
    "json": "use model_dump_json",
    "copy": "use model_copy",
}
_DUMP_KEYWORDS = frozenset(
    {"by_alias", "exclude_unset", "exclude_defaults", "exclude_none", "include"}
)
_V1_FIELD_KEYWORDS = {
    "regex": "use pattern",
    "min_items": "use min_length",
    "max_items": "use max_length",
    "allow_mutation": "use frozen",
    "const": "use a Literal type",
    "unique_items": "use a set type",
}
_V1_CONFIG_KEYS = {
    "orm_mode": "use from_attributes",
    "allow_population_by_field_name": "use populate_by_name or validate_by_name",
    "anystr_strip_whitespace": "use str_strip_whitespace",
    "anystr_lower": "use str_to_lower",
    "min_anystr_length": "use str_min_length",
    "max_anystr_length": "use str_max_length",
    "validate_all": "use validate_default",
    "schema_extra": "use json_schema_extra",
    "allow_mutation": "use frozen",
    "underscore_attrs_are_private": "private attributes are the v2 default",
    "smart_union": "smart union is the v2 default",
    "copy_on_model_validation": "use revalidate_instances",
}

_KEYWORD_TABLES = {"Field": _V1_FIELD_KEYWORDS, "ConfigDict": _V1_CONFIG_KEYS}


class _Scanner(ast.NodeVisitor):
    """Collect v1 API usage in one module."""

    def __init__(self) -> None:
        """Create an empty scanner."""
        self.hits: list[tuple[int, str]] = []
        self.pydantic_names: dict[str, str] = {}

    def _hit(self, node: ast.AST, message: str) -> None:
        """Record a finding.

        Args:
            node: Node providing the line number.
            message: Finding text.
        """
        self.hits.append((getattr(node, "lineno", 1), message))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Track names imported from pydantic and flag v1 shims.

        Args:
            node: Import statement.
        """
        module = node.module or ""
        if module == "pydantic.v1" or module.startswith("pydantic.v1."):
            self._hit(node, "pydantic.v1 compatibility import; migrate to v2 APIs")
        if module == "pydantic":
            for alias in node.names:
                self.pydantic_names[alias.asname or alias.name] = alias.name
                if alias.name == "BaseSettings":
                    self._hit(
                        node, "BaseSettings moved to the pydantic-settings package"
                    )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Flag ``import pydantic.v1``.

        Args:
            node: Import statement.
        """
        if any(alias.name.startswith("pydantic.v1") for alias in node.names):
            self._hit(node, "pydantic.v1 compatibility import; migrate to v2 APIs")
        self.generic_visit(node)

    def _resolve(self, node: ast.expr) -> str | None:
        """Resolve a name or ``pydantic.attr`` to its original pydantic name.

        Args:
            node: Expression to resolve.

        Returns:
            Original pydantic name, or None.
        """
        if isinstance(node, ast.Call):
            node = node.func
        if isinstance(node, ast.Name):
            return self.pydantic_names.get(node.id)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "pydantic"
        ):
            return node.attr
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Flag v1 validator decorators.

        Args:
            node: Function definition.
        """
        for decorator in node.decorator_list:
            name = self._resolve(decorator)
            if name in _V1_DECORATORS:
                self._hit(decorator, f"@{name} is v1; {_V1_DECORATORS[name]}")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Flag inner Config classes, v1 config keys, and ``__root__`` fields.

        Args:
            node: Class definition.
        """
        for statement in node.body:
            if isinstance(statement, ast.ClassDef) and statement.name == "Config":
                self._config_class(statement)
            if (
                isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and statement.target.id == "__root__"
            ):
                self._hit(statement, "__root__ field is v1; use RootModel[T]")
        self.generic_visit(node)

    def _config_class(self, node: ast.ClassDef) -> None:
        """Flag an inner Config class and the v1 keys it assigns.

        Args:
            node: The inner ``Config`` class.
        """
        self._hit(node, "inner class Config is v1; use model_config")
        for item in node.body:
            if not isinstance(item, ast.Assign):
                continue
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id in _V1_CONFIG_KEYS:
                    self._hit(
                        item,
                        f"config '{target.id}' is v1; {_V1_CONFIG_KEYS[target.id]}",
                    )

    def visit_Call(self, node: ast.Call) -> None:
        """Flag v1 helpers, class methods, dump calls, and keywords.

        Args:
            node: Call expression.
        """
        name = self._resolve(node)
        if name in _V1_HELPERS:
            self._hit(node, f"{name} is v1; {_V1_HELPERS[name]}")
        if name is not None:
            self._v1_keywords(node, name)
        self._v1_method(node)
        self.generic_visit(node)

    def _v1_keywords(self, node: ast.Call, name: str) -> None:
        """Flag v1 keywords passed to ``Field`` or ``ConfigDict``.

        Args:
            node: Call expression.
            name: Original pydantic name of the callee.
        """
        table = _KEYWORD_TABLES.get(name, {})
        for keyword in node.keywords:
            if keyword.arg in table:
                self._hit(
                    node,
                    f"{name}({keyword.arg}=...) is v1; {table[keyword.arg]}",
                )

    def _v1_method(self, node: ast.Call) -> None:
        """Flag v1 class methods and v1 dump calls with v1 keywords.

        Args:
            node: Call expression.
        """
        func = node.func
        if not isinstance(func, ast.Attribute):
            return
        if func.attr in _V1_CLASS_METHODS:
            self._hit(node, f".{func.attr}() is v1; {_V1_CLASS_METHODS[func.attr]}")
        elif func.attr in _V1_DUMP_METHODS and any(
            keyword.arg in _DUMP_KEYWORDS for keyword in node.keywords
        ):
            self._hit(node, f".{func.attr}(...) is v1; {_V1_DUMP_METHODS[func.attr]}")


def check_source(text: str, path: str) -> list[str]:
    """Report v1 API usage in one source file.

    Args:
        text: Python source.
        path: Display path.

    Returns:
        Findings formatted as ``path:line: message``.

    Raises:
        SyntaxError: The source cannot be parsed.
    """
    tree = ast.parse(text, filename=path)
    imports_pydantic = any(
        (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("pydantic")
        )
        or (
            isinstance(node, ast.Import)
            and any(alias.name.startswith("pydantic") for alias in node.names)
        )
        for node in ast.walk(tree)
    )
    if not imports_pydantic:
        return []
    scanner = _Scanner()
    scanner.visit(tree)
    lines = text.splitlines()
    unique = sorted(set(scanner.hits))
    return [
        f"{path}:{line}: {message}"
        for line, message in unique
        if _WAIVER not in lines[line - 1]
    ]


def _python_files(targets: Sequence[Path]) -> tuple[list[Path], list[str]]:
    """Expand targets into Python files.

    Args:
        targets: Files or directories.

    Returns:
        Sorted files and findings for missing targets.
    """
    files: set[Path] = set()
    problems: list[str] = []
    for target in targets:
        if not target.exists() or target.is_symlink():
            problems.append(f"{target.as_posix()}:1: missing or linked target")
            continue
        candidates = [target] if target.is_file() else target.rglob("*.py")
        files.update(
            path
            for path in candidates
            if path.suffix == ".py"
            and not path.is_symlink()
            and not {"__pycache__", ".venv", "node_modules"}.intersection(path.parts)
        )
    return sorted(files), problems


class SelfTestIssue(StrEnum):
    """Bounded regressions exercised by the standalone self-test."""

    MISSED_V1_USAGE = "missed v1 usage: {source!r} {found}"
    FALSE_POSITIVE = "false positive: {source!r}"


class SelfTestError(AssertionError):
    """A documented self-test invariant failed."""

    def __init__(
        self,
        issue: SelfTestIssue,
        *,
        source: str | None = None,
        found: list[str] | None = None,
    ) -> None:
        """Describe a self-test regression.

        Args:
            issue: The invariant that failed.
            source: Observed source for the failing case.
            found: Observed found for the failing case.
        """
        super().__init__(issue.value.format(source=source, found=found))


def self_test() -> None:
    """Exercise each v1 pattern, waivers, and clean v2 code.

    Raises:
        AssertionError: A regression was detected.
    """
    risky = {
        "from pydantic.v1 import BaseModel\n": "pydantic.v1",
        "from pydantic import BaseSettings\n": "pydantic-settings",
        "from pydantic import validator\n@validator('a')\ndef f(cls, v): ...\n": "field_validator",
        "from pydantic import BaseModel\nclass A(BaseModel):\n    class Config:\n        orm_mode = True\n": "from_attributes",
        "from pydantic import BaseModel\nclass A(BaseModel):\n    __root__: list[int]\n": "RootModel",
        "from pydantic import Field\nx = Field(regex='a')\n": "pattern",
        "from pydantic import ConfigDict\nc = ConfigDict(allow_mutation=False)\n": "frozen",
        "from pydantic import parse_obj_as\nparse_obj_as(int, '1')\n": "TypeAdapter",
        "import pydantic\nOrder.parse_obj({})\n": "model_validate",
        "import pydantic\norder.dict(exclude_unset=True)\n": "model_dump",
    }
    for source, fragment in risky.items():
        found = check_source(source, "app/models.py")
        if not any(fragment in item for item in found):
            raise SelfTestError(
                SelfTestIssue.MISSED_V1_USAGE, source=source, found=found
            )
    clean = (
        (
            "from pydantic import BaseModel, ConfigDict, field_validator\n"
            "class A(BaseModel):\n    model_config = ConfigDict(from_attributes=True)\n"
            "a = A.model_validate({}).model_dump(exclude_unset=True)\n"
        ),
        "data = {}.copy()\nresponse.json()\n",
        "import pydantic\nOrder.parse_obj({})  # pydantic: reviewed\n",
        "class Config:\n    orm_mode = True\n",
    )
    for source in clean:
        if check_source(source, "app/models.py"):
            raise SelfTestError(SelfTestIssue.FALSE_POSITIVE, source=source)


def main(argv: list[str] | None = None) -> int:
    """Run the checker.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        0 when clean, 1 when findings were reported.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="files or directories")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        print("check_pydantic_v2 self-test passed.")
        return 0
    if not args.paths:
        parser.error("at least one path is required unless --self-test is used")
    files, findings = _python_files(args.paths)
    for path in files:
        display = path.as_posix()
        try:
            findings.extend(check_source(path.read_text(encoding="utf-8"), display))
        except (OSError, UnicodeError, SyntaxError):
            findings.append(f"{display}:1: source cannot be read or parsed")
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
