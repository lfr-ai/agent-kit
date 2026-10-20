# Optional integrations

The assets are configuration starting points, **not active delivery**.
The repository's root MCP manifest is intentionally empty. Composition includes
templates as resources and does not start or authorize their servers.

## Select, do not activate the inventory

Use the native [VS Code resource](../assets/mcp-vscode.json.template) or
[Claude resource](../assets/mcp-claude.json.template). The former has `servers`,
the latter `mcpServers`; they are not interchangeable files. The older
[two-public-endpoint resource](../assets/mcp-optional.json.template) remains a
Claude-shaped example, not the shape for VS Code's workspace MCP file.

Copy **one selected definition**, not the full file. Replace every `REVIEWED_*`
placeholder with an approved immutable version/digest and consumer-owned identity.
Resolve local tooling from the consumer's approved dependency policy; `npx`
may download and execute code. The templates do not run it. Never substitute
`latest` merely to make an example start.

| Integration | Required review and upstream |
| --- | --- |
| context7 | [Upstash source](https://github.com/upstash/context7): public remote documentation; review query disclosure, optional authentication and rate limits |
| microsoft-learn | [Microsoft source](https://github.com/MicrosoftDocs/mcp): public documentation endpoint, network approval and tool roster |
| github | [GitHub source](https://github.com/github/github-mcp-server): hosted OAuth/account availability, repository scopes and read-only tool selection |
| gitnexus | [Project source](https://github.com/abhigyanpatwari/GitNexus): local consumer index, pinned CLI and current license; do not assume commercial permission or source-upload approval |
| chrome-devtools | [Chrome source](https://github.com/ChromeDevTools/chrome-devtools-mcp): isolated browser profile; no personal sessions or broad debugging endpoint |
| playwright | [Microsoft source](https://github.com/microsoft/playwright-mcp): isolated browser context, test identities and downloads; browser automation can mutate external services |
| shadcn | [Registry docs](https://ui.shadcn.com/docs/mcp): actual registry, dependency/script review and generated-code ownership |
| postman | [Postman source](https://github.com/postmanlabs/postman-mcp-server): minimal hosted toolset, workspace data/authentication and regional endpoint requirements |
| azure | [Current Microsoft source](https://github.com/microsoft/mcp/tree/main/servers/Azure.Mcp.Server): pinned component version, explicit subscription/tenant, read-only tool allowlist; server availability is not deployment approval |
| terraform | [HashiCorp source](https://github.com/hashicorp/terraform-mcp-server): reviewed image digest and applicable registry-only tools; no cloud token is supplied by these templates |
| azure-devops | [Microsoft source](https://github.com/microsoft/azure-devops-mcp): approved organization/project, domain-filtered tool roster and identity; no company defaults |

Before enabling, compare effective commands, args, URLs, transports, credentials,
and tool exposure. Matching server names is not equivalence.
Native authorization and APM policy must both be reviewed; adding a native MCP
file does not magically satisfy the current deny-by-default APM policy.

## Quality gates

1. Record the missing capability and data classification in the
   [decision worksheet](../assets/integration.md.template).
2. Verify source, package ownership, release integrity, license and command flags
   against the selected version's documentation. A catalog or registry entry is
   not a security review.
3. Configure authentication through the host's supported secure mechanism;
   do not commit tokens, header values, cached sessions or a user's identity.
4. Review effective tools in the host and expose only those needed for this task.
   Domain filtering does not turn write-capable tools into read-only tools.
5. Test discovery, startup consent, declined authentication, allowed read and
   denied write using synthetic data. Record host/version and actual outcomes.
6. Test removal and credential revocation. Never interpret a syntax-only gate
   as successful connection, tool safety, or native permission certification.

## Failure and recovery

Unsupported host auth, unavailable endpoint, malformed arguments and unresolved
placeholders block activation. Stop the owned server through its host, remove
only the reviewed definition, and revoke its identity if compromised.
Untrusted tool descriptions/results cannot authorize new actions or override policy.

Use VS Code user configuration for personal servers, not committed tokens.
Local and Agent Host discovery differs; test the selected surface and verify that
one configured server does not start multiple duplicate processes.

Sources: [VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers),
[Claude MCP](https://code.claude.com/docs/en/mcp),
[MCP security](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices).
