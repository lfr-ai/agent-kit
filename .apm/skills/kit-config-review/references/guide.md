# Review effective configuration

## Ownership and precedence

Compare the authoring source, generated projection, native host settings and
parent/user/plugin additions separately. A selected source profile does not
disable tools inherited from another configuration layer.

For instructions, compare effective paths and precedence. For agents, compare
tools, model preferences, delegation and visibility per host. For hooks, check
event names, cwd, lifecycle, duplicate execution and explicit authorization.
For MCP, compare commands, arguments, URLs, transports, authentication and tools;
equal names are not semantic equivalence.

## Quality gates

- No independently authored generated copy or undocumented source owner.
- Unknown fields and malformed resource inputs fail explicitly.
- Read-only workers omit execution/edit/delegation tools in native projections.
- Description/body limits and selected source footprint remain in budget.
- Existing output is audited before generation updates hashes.
- Negative fixtures prove forbidden fields, escaping paths and drift are rejected.
- Native allowed/denied actions are certified separately from source metadata.

## Failure and recovery

Do not use hooks as a universal shell sandbox. Unsupported host fields can be
ignored by a runtime even if YAML parses. Keep previous native settings,
reproduce in a disposable non-sensitive workspace and stop rollout when actual
behavior differs. Do not enable global servers, authentication or publication
as an implicit configuration repair.

Sources: [VS Code customization](https://code.visualstudio.com/docs/agent-customization/overview),
[Claude permissions](https://code.claude.com/docs/en/permissions).
