"""Name authored source primitives and the native runtimes that discover them."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, auto, unique
from typing import Final

FRONTMATTER_DELIMITER: Final[str] = "---"
JSON_INDENT: Final[int] = 2  # every generated JSON ledger, manifest and report
INSTRUCTION_SUFFIX: Final[str] = ".instructions.md"
PROMPT_SUFFIX: Final[str] = ".prompt.md"
SKILL_FILE: Final[str] = "SKILL.md"
KIT_NAME_PATTERN: Final[str] = r"kit-[a-z0-9]+(?:-[a-z0-9]+)*"
PACKAGE_REQUIRED_FILES: Final[frozenset[str]] = frozenset(
    {"apm.yml", "apm-policy.yml", "LICENSE"}
)


@unique
class NativeRuntime(StrEnum):
    """Supported native agent adapters."""

    COPILOT = auto()
    CLAUDE = auto()

    @property
    def agent_directory(self) -> str:
        """Repository-relative directory the runtime scans for agent files."""
        return _LAYOUTS[self].agent_directory

    @property
    def agent_suffix(self) -> str:
        """File name suffix that marks one native agent file."""
        return _LAYOUTS[self].agent_suffix

    @property
    def prompt_directory(self) -> str:
        """Repository-relative directory the runtime scans for prompt files."""
        return _LAYOUTS[self].prompt_directory

    @property
    def prompt_suffix(self) -> str:
        """File name suffix that marks one native prompt file."""
        return _LAYOUTS[self].prompt_suffix


@dataclass(frozen=True, kw_only=True, slots=True)
class _Layout:
    """Discovery locations of one native runtime.

    Attributes:
        agent_directory (str): Directory scanned for agent files.
        agent_suffix (str): Suffix marking one agent file.
        prompt_directory (str): Directory scanned for prompt files.
        prompt_suffix (str): Suffix marking one prompt file.
    """

    agent_directory: str
    agent_suffix: str
    prompt_directory: str
    prompt_suffix: str


_LAYOUTS = {
    NativeRuntime.COPILOT: _Layout(
        agent_directory=".github/agents",
        agent_suffix=".agent.md",
        prompt_directory=".github/prompts",
        prompt_suffix=PROMPT_SUFFIX,
    ),
    NativeRuntime.CLAUDE: _Layout(
        agent_directory=".claude/agents",
        agent_suffix=".md",
        prompt_directory=".claude/commands",
        prompt_suffix=".md",
    ),
}
