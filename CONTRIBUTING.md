# Contributing

1. Read [AGENTS.md](AGENTS.md) and [PROJECT.md](PROJECT.md).
2. Keep changes in the owning source; extend existing guidance before adding a skill.
3. Add a failing regression for changed behavior and invalid-input handling.
4. Run `uv sync --locked`, `task verify`, and `task apm:smoke`.
5. Report native runtimes actually tested; do not infer live behavior from metadata.

Review identity, provenance, context footprint, relocation, removal, and rollback.
External contributions must not include secrets or company-specific context.
Policy changes need explicit negative tests and reviewer approval.
Generated projections and lockfiles are changed through their owning tools.

## Pull requests

- Discuss contract-breaking or dependency changes before a large implementation.
- Keep source changes and related tests/documentation together.
- Write [Conventional Commits](https://www.conventionalcommits.org/); `task commit`
  prompts for one and the `commit-msg` hook runs `cz check`.
- After operator-owned `git init`, run
  `uv run --locked pre-commit install --install-hooks` once; `task precommit`
  checks every file. Install Node.js, Bun and Docker before running all hooks.
  Alternatively, open the repository in the [dev container](.devcontainer/devcontainer.json),
  which pins Python, uv, Task, Bun and Node to the CI versions and runs
  `uv sync --locked` on creation.
  See [developer tooling](docs/devtools.md) for checks and prerequisites.
- Place tests by tier as described in [tests/README.md](tests/README.md).
- Dependabot opens grouped weekly updates; review `apm-cli` updates with `task apm:smoke`.
- Run `task verify -- governance` after workflow, ownership, or community-file changes.
- CI uses the same check-only gate as local verification; do not regenerate
  checkout output before the drift audit.
- Use a clear change summary and list checks actually executed.
- Follow the [code of conduct](CODE_OF_CONDUCT.md) and [governance](GOVERNANCE.md).

## License and provenance

Original contributions are provided under the repository's MIT license.
Only submit work you have authority to contribute. Preserve upstream notices
and disclose copied/adapted material and its license; company approval may be required.
No CLA, paid support, or automatic publication is implied.

See the [release process](docs/releasing.md) for version and artifact changes.
