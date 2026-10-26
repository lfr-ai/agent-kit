# Adopting an MCP server

The Model Context Protocol (MCP) lets a host (VS Code, Claude Code and other
agents) call tools, read resources and use prompts that a server exposes.
Every server adds code, credentials and tool descriptions to the agent's
context, so adopt one only for a capability the project cannot get more
simply. Review date: 2026-10-23; the current specification revision at that
date is 2026-07-28.

The reviewed integration roster, inactive host templates and per-server
review notes live in the `kit-editor` skill (its integration catalog and MCP
reference). This page covers the decision and the controls that apply to any
server.

## MCP or something simpler

| Need | Prefer | Why |
| --- | --- | --- |
| Run one local command (tests, lint, build) | editor task or CLI the agent already runs | no extra process, no extra tool descriptions |
| Read local files or the repository | the host's built-in tools | already permissioned by the host |
| Query a remote service with authentication (issue tracker, docs, cloud read APIs) | MCP over Streamable HTTP | standard authorization, server-side tool limits |
| Many related operations with structured inputs and outputs | MCP | typed tool schemas and structured results |
| One-off script with secrets | a reviewed script run by a person | keeps credentials out of the agent loop |
| Operation that changes production | an operator workflow, not an agent tool | approval belongs to people |

## Transports

| Transport | Use for | Security notes |
| --- | --- | --- |
| stdio | a local process started by the host for one user | credentials come from the environment, not the authorization flow; the server runs with the user's rights; log to standard error only |
| Streamable HTTP | shared, remote or hosted servers | HTTPS only; authorization per the specification; validate the `Origin` header and bind local development servers to loopback |

Older SSE-only servers predate Streamable HTTP; prefer a version that
supports the current transport.

## Authorization

For HTTP transports the specification bases authorization on OAuth 2.1: the
server is a resource server, publishes protected resource metadata, and
accepts access tokens issued for it (audience-bound via resource indicators).
Consequences for adopters:

- Prefer servers that use the host's OAuth flow over static tokens.
- When a static token is unavoidable, scope it to read-only access for the
  minimum resources, give it an expiry, and supply it through a prompted
  input or environment variable.
- Never let a server pass the client's token through to another API
  ("token passthrough"); the server must obtain its own downstream token.

## Least privilege and consent

- Enable only the toolsets the task needs (many servers accept a toolset or
  read-only option); disable the rest in the host's tool picker.
- Use a dedicated identity per server, not a personal administrator account.
- Keep host confirmation on for any tool that writes, deletes, sends or
  spends; do not auto-approve write tools.
- Review the effective tool list in the host after every server upgrade;
  tool sets change between versions.

## Untrusted tool output and prompt injection

Tool descriptions, resource contents and tool results can contain text that
tries to instruct the model ("ignore previous instructions", hidden
characters, links). Treat all of it as data:

- Do not let tool output trigger further write actions without confirmation.
- Avoid combining a server that reads untrusted content (web pages, issues,
  e-mail) with a server that can write or exfiltrate in the same session.
- Prefer servers that return structured content over free text.
- Watch for tool descriptions that change after approval ("rug pulls"); pin
  versions so they cannot change silently.

## Pinning and supply chain

- Pin packages to an exact version (`package@1.2.3`) and images by digest;
  never `latest` or an unpinned package runner download.
- Prefer servers published by the vendor of the service they wrap, with
  source, license and release history you can inspect.
- Record the version in the adoption review and let the dependency bot or a
  scheduled review propose updates.

## Host configuration files

| Host | Workspace file | Top-level key | Secrets |
| --- | --- | --- | --- |
| VS Code | `.vscode/mcp.json` | `servers` (plus `inputs`) | `inputs` with `"password": true`, referenced as `${input:id}`; or `envFile` that is not committed |
| Claude Code | `.mcp.json` (project scope) | `mcpServers` | environment expansion `${VAR}` from the user's environment |

Personal servers belong in user configuration, not in the repository. The
two file formats are not interchangeable; keep definitions equivalent when a
project supports both hosts. Start from the
[VS Code template](../assets/mcp-vscode-server.json.template) or the
[Claude template](../assets/mcp-claude-server.json.template).

## Evaluating a server

Fill the [adoption review](../assets/adoption-review.md.template), then:

1. Start the server in the host with synthetic data and record the tool list.
2. Call one read tool and confirm the result and its size.
3. Attempt one write tool and decline the confirmation; confirm nothing
   changed.
4. Remove the server and revoke its identity; confirm the tools disappear.

## Failure modes

- A server installed for one task stays enabled forever with broad tokens.
- Two servers expose overlapping tools and the model calls the wrong one.
- Tool descriptions consume a large share of the context window.
- A server prints logs to standard output and corrupts the stdio stream.

## Primary sources

- MCP, [Specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- MCP, [Transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- MCP, [Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- MCP, [Security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- VS Code, [Add and manage MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- Claude Code, [Connect to tools via MCP](https://code.claude.com/docs/en/mcp)
- OWASP, [LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
