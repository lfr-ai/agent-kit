# Workspace MCP integrations

The repository configures three remote servers for documentation and
read-only repository context. Matching definitions live in
[Claude's project manifest](../.mcp.json) and
[VS Code's workspace manifest](../.vscode/mcp.json). Review date: 2026-11-02;
MCP specification revision 2026-07-28. Facts below come from the vendor
sources listed at the end; no server was started or authenticated for this
review.

## Defaults

Defaults are declared by `shared`, which every profile includes, and are the
only servers configured in this workspace.

| Server | Endpoint | Transport | Authorization | Read-only control | Main risk |
| --- | --- | --- | --- | --- | --- |
| `context7` | `https://mcp.context7.com/mcp/oauth` | http | OAuth handled by the host | documentation lookup only | queries leave the machine; send library names and questions, never private source or secrets |
| `microsoft-learn` | `https://learn.microsoft.com/api/mcp` | http | none; public Microsoft documentation | read-only by nature | queries leave the machine; low |
| `github` | `https://api.githubcopilot.com/mcp/` | http | OAuth handled by the host; uses the signed-in account's access | `X-MCP-Readonly: true`, toolsets limited to `repos,issues,pull_requests,actions`, `X-MCP-Lockdown: true` | issue and pull-request text is untrusted input; lockdown is a best-effort content filter, not a security boundary |

GitHub's headers restrict its exposed tools; they do not replace account
permissions or host authorization. VS Code MCP auto-start remains `never`;
hosts can still require trust, explicit startup, or OAuth consent.

## Opt-in servers

Every other server is delivered by an optional package or proposed below.
Opt-in means the consumer installs the package, then reviews and starts the
server in the host. None is configured in this workspace, because none is
needed for the repository's current tools and each adds local execution,
account access or external-service scope.

| Server | Package | Command or endpoint | Transport | Authorization | Read-only mode | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| `azure` | bicep | `bunx --bun @azure/mcp@2.0.5 server start --read-only` with `--namespace` for the eight read namespaces the package declares (Bicep schema, best practices, Well-Architected guidance, groups, policy, roles, container registries and container apps) | stdio | the local Azure sign-in of the user; no secret in the manifest | `--read-only` plus the namespace allowlist | reads whatever the signed-in identity can read in the exposed namespaces, including role assignments; use a reader-only identity |
| `terraform` | terraform | `docker run -i --rm hashicorp/terraform-mcp-server:1.3.0@sha256:...` with `--toolsets=registry` | stdio | none for registry lookups; a Terraform Cloud token is a separate, unshipped choice | registry toolset only; operations tools stay disabled | module and provider lookups reach the public registry; never add a workspace token to the manifest |
| `playwright` | frontend | `bunx --bun @playwright/mcp@0.0.80 --isolated --headless` | stdio | none | no read-only mode; the in-memory profile limits persistence | drives a real browser, so page content is untrusted; origin filters are not a security boundary |
| `chrome-devtools` | frontend | `bunx --bun chrome-devtools-mcp@1.9.0 --isolated --headless --no-usage-statistics --no-performance-crux` | stdio | none | no read-only mode | can inspect and script a browser page; the flags disable usage statistics and CrUX lookups |
| `shadcn` | frontend | `bunx --bun shadcn@4.21.0 mcp` | stdio | none | none declared | registry lookups and component installs touch the project; review each change |
| `storybook` | frontend | `http://localhost:6006/mcp` | http, loopback | none; the local Storybook process | none declared | exists only while Storybook runs; loopback only |
| `postman` | backend | `https://mcp.postman.com/minimal` | http | OAuth through the host; API-key header for the EU or local server | the minimal mode still includes tools that change collections and environments; no documented read-only switch | modifies a Postman workspace; use a dedicated workspace identity and decline writes |
| `langfuse-docs` | ai | `https://langfuse.com/api/mcp` | http | none; the public documentation server | read-only by nature | queries leave the machine; low. The authenticated Langfuse data-platform server is a different server and is not shipped |
| `temporal-docs` | temporal | `https://temporal.mcp.kapa.ai` | http | MCP OAuth sign-in with Google or GitHub; anonymous requests are rejected | read-only documentation search | queries go to a third-party host and sign-in uses a personal identity |

## Proposals

These are not delivered and not allow-listed. The `identity` and `temporal`
packages own their manifests; a maintainer adds any of these there and updates
the allow list as described under [Policy alignment](#policy-alignment).

### Microsoft Entra: Microsoft MCP Server for Enterprise (identity)

Opt-in, public preview. Recommended for read-only tenant questions that the
`identity` skills raise: users, groups, applications, devices, sign-in and
provisioning reports.

| Item | Value |
| --- | --- |
| Endpoint | `https://mcp.svc.cloud.microsoft/enterprise` |
| Transport and authorization | http; delegated OAuth through Microsoft Entra, with the caller's roles and consented scopes |
| Read-only | yes; the documented tools are `microsoft_graph_suggest_queries`, `microsoft_graph_get` (read-only Graph calls) and `microsoft_graph_list_properties` |
| Preconditions | one-time tenant provisioning by an Application Administrator or Cloud Application Administrator; the global service only (not US Government or China clouds) |
| Limits and audit | 100 calls per minute per user; every call appears in Microsoft Graph activity logs under the server's application ID |
| Risk | directory data (personal data, group membership, authentication methods) enters the model context; the answer is only as narrow as the signed-in user's access, so connect with a reader role, not a privileged administrator; preview terms apply |

Proposed manifest entry for `packages/identity/apm.yml`:

```yaml
dependencies:
  mcp:
    - name: microsoft-entra
      registry: false
      transport: http
      url: https://mcp.svc.cloud.microsoft/enterprise
```

Adding it needs the name in all four places listed under
[Policy alignment](#policy-alignment) and a `tools` allowlist once the schema
accepts one, listing the three tool names above.

Related Azure access-control reads are already in the `azure` server's
read-only namespaces (`role`, `policy`, `group`). The Azure MCP Server can also
be hosted remotely with on-behalf-of authorization
([guide](https://learn.microsoft.com/azure/developer/azure-mcp-server/how-to/deploy-remote-mcp-server-on-behalf-of));
that is a deployment decision for a platform team, not a bundle declaration.

### Temporal MCP server from Temporal (temporal)

Opt-in, pre-release. A read-only server from Temporal that lists configured
namespaces, checks connectivity, reads workflow state and event history, shows
task-queue pollers and backlog, lists search attributes, and runs Visibility
queries. It is not ready for production use according to its own README.

| Item | Value |
| --- | --- |
| Source | the [temporal-mcp repository](https://github.com/temporalio/temporal-mcp) |
| Transport and authorization | stdio for one developer (`--stdio --config <absolute path>`) or one HTTPS server with OpenID Connect sign-in for a team; Temporal Cloud targets use an API key from the environment |
| Read-only | yes by design |
| Distribution | release installer script or the vendor's container image tagged by release version; verify the current release and pin an image digest |
| Risk | event history can hold business payloads; keep codecs and payload visibility under the server's own configuration, and use a dedicated read-only API key |

Ship it as a user-level template, not a bundle declaration: it needs a
per-user configuration file that lists namespaces and credentials, which a
checked-in manifest must not carry. The existing `temporal-docs` entry stays
the default for documentation lookups.

### Considered and not proposed

| Server | Why not |
| --- | --- |
| Sentry (official remote and stdio) | the documented stdio token needs write scopes and no read-only switch was found |
| Datadog (official remote) | OAuth and toolset selection are documented, but no read-only mode was found in the reviewed pages; it is per site and not available for GovCloud |
| `azure-devops` | organization-specific endpoint and identity |
| `gitnexus` | non-commercial license |
| Database and Temporal-endpoint servers | need the consumer's own endpoint and credentials; use the [editor templates](../packages/shared/.apm/skills/kit-editor/references/mcp.md) |

Sentry and Datadog may be added later, with an adoption review, once an
official read-only mode is documented.

## APM delivery

Packages declare reviewed servers under `dependencies.mcp` in their `apm.yml`, and
`apm install` writes them to each detected host (`.mcp.json`, `.github/mcp.json`,
or the user-level files with `apm install -g`). Servers are declared in place
(`registry: false`) with exact pins, because registry entries can move.

| Package | Servers |
| --- | --- |
| shared | context7, microsoft-learn, github |
| backend | postman |
| temporal | temporal-docs |
| frontend | playwright, chrome-devtools, shadcn, storybook |
| bicep | azure |
| terraform | terraform |
| ai | langfuse-docs |
| identity | none |

`dependencies.mcp` entries accept these fields in APM: `name`, `transport`
(`stdio`, `sse`, `http`, `streamable-http`), `command`, `args`, `url`, `env`,
`headers`, `tools` (an allowlist, default `["*"]`), `version`, `registry` and
`package`. This repository's closed schema deliberately accepts less: see
[policy](policy.md#delivered-hooks-and-mcp-servers). A self-defined server is
trusted only when its package is a direct dependency of the consumer; APM skips
transitive self-defined servers unless the consumer passes
`--trust-transitive-mcp`, and the repository policy sets
`trust_transitive: false`. Session compositions omit MCP.

These manifests do not grant MCP tools to every generated agent role. The
existing role allowlists remain scoped; a role should receive an MCP tool only
when its task needs it and the host supports a reviewed per-role grant.

### Pin refresh candidates

The declared pins predate newer releases found in the registries on the review
date. They are not applied because a bump needs a manifest and digest review,
and each pin check must still pass:

| Server | Declared | Newer release seen |
| --- | --- | --- |
| `@azure/mcp` | 2.0.5 | stable 3.0.0 (a major release); the registry's `latest` tag points at a 4.0.0 beta, so never use an unpinned runner |
| `@playwright/mcp` | 0.0.80 | 0.0.84 |
| `chrome-devtools-mcp` | 1.9.0 | 1.12.0 |
| `shadcn` | 4.21.0 | 4.23.0 |
| `hashicorp/terraform-mcp-server` | 1.3.0 | 1.4.1 (resolve its digest before use) |

Dependabot cannot bump `apm.yml` pins, so review them manually.

## Policy alignment

Allowed server names exist in one reviewed list that four places must agree
on, and tests fail when they drift:

1. `mcp.allow` in the root [apm-policy.yml](../apm-policy.yml), which the
   repository's own checks enforce.
2. The generated policy in the toolkit (`_POLICY` in the catalog service),
   which `agent-kit check` compares with the root file.
3. The consumer template `.apm/skills/kit-apm-adopt/assets/apm-policy.yml.template`,
   which must mirror the root `mcp` section.
4. Every `dependencies.mcp` entry in `packages/*/apm.yml`, which must name an
   allow-listed server.

The root policy is the workspace's single allow list: it lists the defaults
and the opt-in servers that packages ship, so that composing any profile
passes. It does not mean the workspace starts them. The workspace's own
manifests (`.mcp.json`, `.vscode/mcp.json`) hold only the defaults. A consumer
repository copies the template and then removes the names it does not use;
removing names is always safe, adding a name needs the review described above.
The policy file also restricts `transport` to `http` and `stdio`, requires
`self_defined: allow` (servers are declared in place) and sets
`trust_transitive: false`.

To add a server: declare it in the owning package, add its name to the shared
list (all four places), review its pin and executables, and add a negative
test. To remove one, delete the declaration first, then the name.

## Authorization guidance

The MCP specification builds authorization on OAuth 2.1: the MCP server is a
resource server that publishes protected resource metadata, and the host
obtains audience-bound tokens with resource indicators. Consequences:

- Prefer servers whose host-run OAuth flow replaces a pasted token.
- A server must not accept tokens that were not issued for it and must not
  forward the client's token to another API.
- Pin npm packages by exact version and containers by digest; a remote
  endpoint cannot be digest-pinned, so re-check its tool list after each
  vendor change.
- Combine a vendor read-only control with a `tools` allowlist where the host
  supports one; they fail independently.

The [authorization reference](../packages/shared/.apm/skills/kit-mcp-integration/references/authorization.md)
in the `kit-mcp-integration` skill has the adopter checklist.

## Removal

To remove these integrations, delete their entries from both native manifests,
remove the names from the root `apm-policy.yml` allowlist and the other places
under [Policy alignment](#policy-alignment), and revoke any provider OAuth
grant through that provider's account settings.

## Sources

- [VS Code MCP server configuration](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)
- [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- [MCP security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [APM MCP dependencies](https://microsoft.github.io/apm/producer/author-primitives/mcp-as-primitive/)
- [GitHub remote MCP configuration and read-only headers](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md)
- [Context7 client configuration and OAuth](https://context7.com/docs/resources/all-clients)
- [Microsoft Learn MCP server](https://github.com/MicrosoftDocs/mcp)
- [Microsoft MCP Server for Enterprise](https://learn.microsoft.com/en-us/graph/mcp-server/overview) and
  [setup](https://learn.microsoft.com/en-us/graph/mcp-server/get-started)
- [Azure MCP Server](https://learn.microsoft.com/azure/developer/azure-mcp-server/overview)
- [Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- [Terraform MCP Server](https://github.com/hashicorp/terraform-mcp-server)
- [Postman MCP Server](https://github.com/postmanlabs/postman-mcp-server)
- [Langfuse Docs MCP server](https://langfuse.com/docs/docs-mcp)
- [Temporal documentation index with the docs MCP server](https://docs.temporal.io/llms.txt)
- [Temporal MCP server (pre-release)](https://github.com/temporalio/temporal-mcp)
- [Sentry MCP](https://github.com/getsentry/sentry-mcp)
- [Datadog MCP Server](https://docs.datadoghq.com/mcp_server/)
