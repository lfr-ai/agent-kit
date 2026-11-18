"""Shared offline harness for the delivery IaC composition tests.

Each test module binds its own timeout in a local ``_run`` and passes it here.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

type Run = Callable[..., subprocess.CompletedProcess[str]]
type Network = tuple[str, str]
type Case = tuple[str, str | None]
type VariableCase = tuple[Mapping[str, object], str | None]

MIRROR_SKIP_REASON: Final[str] = (
    "Full AzAPI validation needs reviewed Azure/azapi 2.13.0 in "
    "CONTAINER_APPS_AZAPI_MIRROR; no provider install attempted."
)
CACHED_MIRROR_SKIP_REASON: Final[str] = (
    "Full AzAPI validation needs cached Azure/azapi 2.13.0 in "
    "CONTAINER_APPS_AZAPI_MIRROR; no provider download attempted."
)
RESOURCE_TYPES: Final[re.Pattern[str]] = re.compile(
    r"""(?:resource \w+ '|type\s*=\s*")([\w./]+@[\w-]+)"""
)


def _executable(name: str) -> str:
    fallback = Path.home() / ".azure/bin/bicep.exe"
    found = shutil.which(name) or (
        str(fallback) if name == "bicep" and fallback.is_file() else None
    )
    if found is None:
        pytest.skip(f"{name} is not installed; nothing is downloaded or installed")
    return found


def _complete(
    command: list[str], workdir: Path, environment: Mapping[str, str], timeout: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - installed tools on synthetic offline inputs
        command,
        cwd=workdir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def run(
    name: str, workdir: Path, *arguments: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    """Run an installed tool offline with a Terraform data folder inside workdir.

    Args:
        name (str): Installed tool name; skips the test when it is missing.
        workdir (Path): Working directory that also holds the Terraform data.
        *arguments (str): Tool arguments.
        timeout (int): Seconds before the tool is stopped.

    Returns:
        subprocess.CompletedProcess[str]: The finished tool and its text output.
    """
    offline = {
        "ARM_ENABLE_PREFLIGHT": "false",
        "ARM_SKIP_PROVIDER_REGISTRATION": "true",
        "CHECKPOINT_DISABLE": "1",
        "TF_DATA_DIR": str(workdir / ".terraform"),
        "TF_IN_AUTOMATION": "1",
    }
    command = [_executable(name), *arguments]
    return _complete(command, workdir, os.environ | offline, timeout)


def run_isolated(
    name: str, folder: Path, *arguments: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    """Run an installed tool without inherited credentials, CLI config or account.

    Args:
        name (str): Installed tool name; skips the test when it is missing.
        folder (Path): Working directory that also holds every tool setting.
        *arguments (str): Tool arguments.
        timeout (int): Seconds before the tool is stopped.

    Returns:
        subprocess.CompletedProcess[str]: The finished tool and its text output.
    """
    # Do not inherit credentials, a user's Terraform CLI config or Azure CLI context.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("ARM_", "AZURE_", "TF_"))
    }
    cli_config = folder / "offline.tfrc"
    cli_config.write_text("disable_checkpoint = true\n", encoding="utf-8")
    environment.update(
        ARM_ENABLE_PREFLIGHT="false",
        ARM_SKIP_PROVIDER_REGISTRATION="true",
        ARM_USE_CLI="false",
        ARM_USE_MSI="false",
        ARM_USE_OIDC="false",
        AZURE_CONFIG_DIR=str(folder / ".azure"),
        CHECKPOINT_DISABLE="1",
        TF_CLI_CONFIG_FILE=str(cli_config),
        TF_DATA_DIR=str(folder / ".terraform"),
        TF_IN_AUTOMATION="1",
    )
    return _complete([_executable(name), *arguments], folder, environment, timeout)


def ok(result: subprocess.CompletedProcess[str]) -> str:
    """Assert that a tool succeeded and return its standard output."""
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    return result.stdout


def relocate(source: Path, target: Path) -> Path:
    """Copy a composition to target, assert the copy is byte-identical, return it.

    Args:
        source (Path): The composition folder in this repository.
        target (Path): A fresh folder outside the repository.

    Returns:
        Path: The target folder.
    """
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".terraform"))
    assert _digests(target) == _digests(source)
    return target


def _digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".terraform" not in path.parts
    }


def self_contained_sources(
    relocated: Path, messages: Mapping[str, str]
) -> tuple[str, str]:
    """Assert both sources stand alone and share every guard message.

    Args:
        relocated (Path): The relocated composition folder.
        messages (Mapping[str, str]): Guard messages both languages must state.

    Returns:
        tuple[str, str]: The main Bicep source and all Terraform files joined.
    """
    bicep = (relocated / "bicep/main.bicep").read_text(encoding="utf-8")
    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((relocated / "terraform").rglob("*.tf"))
    )
    assert not list(relocated.rglob("*.tfstate*"))
    assert "module " not in bicep
    assert 'module "' not in terraform
    assert 'version = "= 2.13.0"' in terraform
    for forbidden in ("azapi_resource_action", 'response_export_values = ["*"]'):
        assert forbidden not in terraform
    variables = (relocated / "terraform/variables.tf").read_text(encoding="utf-8")
    for message in messages.values():
        assert message in bicep, message
        assert message in variables, message
    return bicep, terraform


def shared_resource_types(bicep: str, terraform: str) -> set[str]:
    """Assert both sources declare the same resource types and return them."""
    declared = set(RESOURCE_TYPES.findall(bicep))
    assert declared == set(RESOURCE_TYPES.findall(terraform))
    return declared


def bicep_network(network: Network | None) -> str:
    """Return a Bicep private endpoint for a subnet and zone, or null."""
    if network is None:
        return "null"
    return f"{{ subnetId: '{network[0]}', privateDnsZoneId: '{network[1]}' }}"


def terraform_network(network: Network | None) -> dict[str, str] | None:
    """Return a Terraform private endpoint for a subnet and zone, or None."""
    if network is None:
        return None
    return {"subnet_id": network[0], "private_dns_zone_id": network[1]}


def assert_bicep_clean(folder: Path, run: Run) -> None:
    """Assert every Bicep source is formatted and main.bicep lints without output."""
    for source in sorted([*folder.rglob("*.bicep"), *folder.rglob("*.bicepparam")]):
        rendered = ok(run("bicep", folder, "format", str(source), "--stdout"))
        assert rendered == source.read_text(encoding="utf-8"), source.name
    lint = run("bicep", folder, "lint", "main.bicep", "--no-restore")
    assert ok(lint) == ""
    assert lint.stderr == ""


def build_bicep(folder: Path, run: Run) -> str:
    """Return the ARM JSON compiled from main.bicep without restoring modules."""
    return ok(run("bicep", folder, "build", "main.bicep", "--no-restore", "--stdout"))


def build_examples(folder: Path, run: Run) -> None:
    """Assert the development and production examples both compile."""
    for example in ("tests/dev.bicepparam", "tests/prod.bicepparam"):
        ok(run("bicep", folder, "build-params", example, "--no-restore", "--stdout"))


def guarded(variables: Mapping[str, object]) -> set[str]:
    """Return the template variables that keep a Bicep require guard."""
    return {
        name for name, value in variables.items() if "__bicep.require" in str(value)
    }


def rejected_example(
    example: Path, run: Run, pattern: str, replacement: str, *, flags: int = 0
) -> str:
    """Rewrite one match in an example, assert it fails to compile, return stderr.

    Args:
        example (Path): The example parameter file to copy.
        run (Run): The test module's tool runner.
        pattern (str): Regular expression that must match exactly once.
        replacement (str): Replacement for the first match.
        flags (int): Regular-expression flags.

    Returns:
        str: The compiler's standard error.
    """
    text = example.read_text(encoding="utf-8")
    unsafe_text, replaced = re.subn(pattern, replacement, text, count=1, flags=flags)
    assert replaced == 1
    unsafe = example.with_name("unsafe.bicepparam")
    unsafe.write_text(unsafe_text, encoding="utf-8")
    result = run(
        "bicep", unsafe.parent, "build-params", unsafe.name, "--no-restore", "--stdout"
    )
    assert result.returncode != 0
    return result.stderr


def assert_bicep_guards(
    folder: Path,
    run: Run,
    imports: Sequence[str],
    cases: Sequence[Case],
    messages: Mapping[str, str],
    *,
    extra: str = "",
) -> str:
    """Assert accepted guard cases compile and each rejected case fails by name.

    Args:
        folder (Path): The relocated Bicep folder that holds main.bicep.
        run (Run): The test module's tool runner.
        imports (Sequence[str]): Guard functions imported from main.bicep.
        cases (Sequence[Case]): Bicep expressions and their message key or None.
        messages (Mapping[str, str]): Guard messages by key.
        extra (str): Further parameter lines appended to the accepted cases.

    Returns:
        str: The compiled parameters of the accepted cases.
    """
    header = f"using none\nimport {{ {', '.join(imports)} }} from './main.bicep'\n"
    accepted = folder / "accepted.bicepparam"
    accepted.write_text(
        header
        + "".join(
            f"param case{index} = {expression}\n"
            for index, (expression, error) in enumerate(cases)
            if error is None
        )
        + extra,
        encoding="utf-8",
    )
    rendered = ok(
        run("bicep", folder, "build-params", accepted.name, "--no-restore", "--stdout")
    )
    rejected = [
        (index, expression, messages[error])
        for index, (expression, error) in enumerate(cases)
        if error is not None
    ]
    fixture = folder / "rejected.bicepparam"
    fixture.write_text(
        header
        + "".join(f"param case{i} = {expression}\n" for i, expression, _ in rejected),
        encoding="utf-8",
    )
    result = run(
        "bicep", folder, "build-params", fixture.name, "--no-restore", "--stdout"
    )
    assert result.returncode != 0
    assert result.stderr.count("Error BCP") == len(rejected), result.stderr
    for index, _, message in rejected:
        expected = f'Failed to evaluate parameter "case{index}": {message}'
        assert expected in result.stderr, expected
    return rendered


def assert_variable_contract(
    folder: Path,
    variables: Path,
    run: Run,
    baseline: Mapping[str, object],
    cases: Sequence[VariableCase],
) -> None:
    """Assert an unchanged variables.tf alone accepts and rejects every case.

    Args:
        folder (Path): An empty folder for the provider-free Terraform test.
        variables (Path): The composition's variables.tf.
        run (Run): The test module's tool runner.
        baseline (Mapping[str, object]): Valid inputs that each case overrides.
        cases (Sequence[VariableCase]): Overrides and the variable that must fail.
    """
    # The unchanged variables.tf alone proves input validation, not AzAPI schemas.
    shutil.copyfile(variables, folder / "variables.tf")
    (folder / "inputs.auto.tfvars.json").write_text(
        json.dumps(baseline), encoding="utf-8"
    )
    blocks = []
    for index, (overrides, failure) in enumerate(cases):
        # JSON scalars, lists, objects and null are valid HCL expressions.
        assignments = "".join(
            f"    {key} = {json.dumps(value)}\n" for key, value in overrides.items()
        )
        expected = f"  expect_failures = [var.{failure}]\n" if failure else ""
        blocks.append(
            f'run "case{index}" {{\n  command = plan\n'
            f"  variables {{\n{assignments}  }}\n{expected}}}\n"
        )
    (folder / "contract.tftest.hcl").write_text("".join(blocks), encoding="utf-8")
    ok(run("terraform", folder, "validate", "-json"))
    output = ok(run("terraform", folder, "test", "-no-color"))
    assert f"Success! {len(cases)} passed, 0 failed." in output, output
    assert not list(folder.glob("*.tfstate*"))


def init_from_mirror(
    folder: Path, run: Run, *options: str, reason: str = MIRROR_SKIP_REASON
) -> None:
    """Initialize Terraform from the provisioned AzAPI mirror, or skip without one.

    Args:
        folder (Path): The relocated Terraform folder.
        run (Run): The test module's tool runner.
        *options (str): Extra init options placed before the plugin folder.
        reason (str): Skip reason when no mirror is configured.
    """
    mirror = os.environ.get("CONTAINER_APPS_AZAPI_MIRROR")
    if not mirror:
        pytest.skip(reason)
    plugins = Path(mirror).resolve(strict=True)
    assert plugins.is_dir()
    # -plugin-dir limits init to the operator-provisioned local mirror.
    ok(
        run(
            "terraform",
            folder,
            "init",
            "-backend=false",
            "-input=false",
            *options,
            f"-plugin-dir={plugins}",
        )
    )


def mock_plans(folder: Path, run: Run) -> str:
    """Validate an initialized module, run its mocked plans, return the output."""
    ok(run("terraform", folder, "validate", "-json"))
    output = ok(run("terraform", folder, "test", "-no-color"))
    assert not list(folder.glob("*.tfstate*"))
    return output


def dependencies(graph: str, start: str) -> set[str]:
    """Return every node that a Terraform graph node reaches, itself included."""
    edges: dict[str, set[str]] = {}
    for dependent, prerequisite in re.findall(r'"([^"]+)" -> "([^"]+)"', graph):
        edges.setdefault(dependent, set()).add(prerequisite)
    found: set[str] = set()
    pending = [start]
    while pending:
        resource = pending.pop()
        if resource not in found:
            found.add(resource)
            pending.extend(edges.get(resource, ()))
    return found
