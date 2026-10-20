"""Installed console entrypoint."""

from agent_kit.composition.root import build_actions
from agent_kit.presentation.cli import main as run_cli


def main() -> int:
    """Run the CLI with the declared local collaborators."""
    return run_cli(build_actions())
