# Workspace MCP integrations

The repository configures three remote servers for documentation and
read-only repository context. Matching definitions live in
[Claude's project manifest](../.mcp.json) and
[VS Code's workspace manifest](../.vscode/mcp.json).

| Server | Endpoint | Access and data |
| --- | --- | --- |
| `context7` | `https://mcp.context7.com/mcp/oauth` | OAuth is handled by the MCP host. Library names and documentation questions are sent to Context7; do not include private source or secrets in queries. |
| `microsoft-learn` | `https://learn.microsoft.com/api/mcp` | Public Microsoft documentation; no project credentials are configured. |
| `github` | `https://api.githubcopilot.com/mcp/` | Host-managed OAuth; limited to `repos`, `issues`, `pull_requests`, and `actions`, with upstream read-only and lockdown headers. Queries use the signed-in account's GitHub access. |

GitHub's headers restrict its exposed toolsets; they do not replace account
permissions or host authorization. Issue and pull-request content is untrusted
input. VS Code MCP auto-start remains `never`; hosts can still require trust,
explicit startup, or OAuth consent. No server was started or authenticated as
part of this configuration change.

The broader MCP inventory remains optional. This workspace does not add
GitNexus indexing, browser automation, Postman workspaces, cloud subscriptions,
or organization-specific integrations: they are not needed for the repository's
current tools and would add local execution, account access, or external-service
scope.

## APM boundary

This toolkit keeps `dependencies.mcp` out of portable `apm.yml` packages:
APM materializes declared MCP dependencies into each detected host during
installation. The shared editor capability instead carries inactive,
host-shaped examples and a policy checklist. Its consumer policy template
remains deny-by-default; consumers should add names to `mcp.allow` only after
reviewing their own native endpoint, identity, and tool exposure.
This is why APM audit reports no package MCP dependencies: the repository's
native manifests are checked by the local coverage contract instead.
The catalog's backend, frontend, fullstack, IaC, workflows, AI, and toolkit
profiles include the shared capability, so the same reviewed examples are
available without copying runtime definitions into each package manifest.
The root project policy explicitly allows only the three names above, while
the native configuration contract checks their exact endpoints and read-only
GitHub headers.

These manifests do not grant MCP tools to every generated agent role. The
existing role allowlists remain scoped; a role should receive an MCP tool only
when its task needs it and the host supports a reviewed per-role grant.

To remove these integrations, delete their entries from both native manifests,
remove the names from the root `apm-policy.yml` allowlist, and revoke any
provider OAuth grant through that provider's account settings.

## Sources

- [VS Code MCP server configuration](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)
- [MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [GitHub remote MCP configuration and read-only headers](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md)
- [Context7 client configuration and OAuth](https://context7.com/docs/resources/all-clients)
- [Microsoft Learn MCP server](https://github.com/MicrosoftDocs/mcp)
- [APM MCP dependencies](https://github.com/microsoft/apm/blob/v0.33.0/docs/src/content/docs/producer/author-primitives/mcp-as-primitive.md)
