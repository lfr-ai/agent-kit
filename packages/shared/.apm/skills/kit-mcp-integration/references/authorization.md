# MCP authorization and tool-scoping controls

Authorization decides which identity a server acts as and which tokens it
accepts. Tool scoping decides which of the server's tools an agent can call.
Both are needed: a read-only identity behind an unrestricted tool list still
exposes every read, and a tool allowlist over a broad token still limits only
what the host offers. Review date: 2026-11-02; the specification revision is
2026-07-28.

## Authorization model for HTTP transports

| Role | Responsibility | Adopter check |
| --- | --- | --- |
| MCP server | OAuth 2.1 resource server; publishes OAuth 2.0 Protected Resource Metadata (RFC 9728) and accepts only tokens issued for it | the vendor documents the metadata endpoint and the scopes it asks for |
| MCP client (host) | OAuth 2.1 client; discovers the authorization server from the metadata, requests the scopes the server challenges for, and binds the token to the server with a resource indicator (RFC 8707) | the host's own sign-in, not a pasted token, obtains the credential |
| Authorization server | Authenticates the user and issues audience-bound tokens | an organization-controlled tenant where possible, with consent and conditional-access policy |

- stdio servers do not use this flow. The process inherits the user's
  environment, so the credential is whatever that environment holds. Review it
  as the user's own access.
- Client registration prefers Client ID Metadata Documents; Dynamic Client
  Registration is deprecated in the current specification and kept for older
  authorization servers.
- Scopes follow least privilege: the server challenges for the scope a call
  needs, and the client requests that scope and widens it only through the
  step-up flow. A host or server that requests every scope up front is a
  finding.

## Resource indicators and audience

1. Treat the token audience as part of the server's identity. A token issued
   for server A is not a credential for server B, even when both sit behind the
   same identity provider.
2. In a review record the audience (resource identifier) the host requests and
   confirm the server's metadata names the same URL as the endpoint in the
   configuration.
3. Prefer one registration and one consent per server. A shared "gateway" token
   that several servers accept erases the audience boundary.

## No token passthrough

A server must not accept a token that was not issued for it and must not
forward the client's token to a downstream API. Passthrough circumvents the
downstream rate limits and audit trail, breaks accountability (the downstream
log shows the wrong caller) and enables a confused-deputy path. A server that
needs a downstream API obtains its own token (for example through an
on-behalf-of exchange) and the downstream audit log then shows the server.

For adopters:

- Ask the vendor whether the server forwards the client token or exchanges it.
- Do not paste a personal access token into a third-party remote server's
  header when an OAuth flow exists.
- A server that proxies to a third-party authorization server must obtain the
  user's consent for each client; one static client ID shared by all clients is
  the confused-deputy precondition the security guidance describes.

## Remote metadata and request forgery

The client fetches metadata URLs that the server controls. Hosts that run
inside a corporate network should block requests to private ranges and
link-local addresses during discovery, and should accept only HTTPS metadata
URLs outside loopback development. Servers that fetch user-supplied URLs have
the same exposure; check for an egress allowlist.

## Tool scoping with `tools`

APM `dependencies.mcp` entries accept an optional `tools` list, an allowlist of
tool names whose default is every tool (`["*"]`). It is a host-side filter and
not an authorization control, so it limits the offered surface without changing
the identity behind it.

```yaml
dependencies:
  mcp:
    - name: example-docs
      registry: false
      transport: http
      url: https://docs.example.com/mcp
      tools: [search_docs, fetch_page]
```

| Question | Guidance |
| --- | --- |
| Does the server expose writes? | List the read tools you need by name; never leave `["*"]` on a write-capable server |
| Does the server have a read-only mode? | Use the vendor's flag or header too (`--read-only`, `X-MCP-Readonly`) and keep the allowlist; the two controls fail independently |
| Does a server upgrade add tools? | The allowlist hides them until a reviewer adds them; compare the host's tool list after every pin change |
| Are names stable? | Tool names are vendor contracts that can change; a renamed tool silently disappears from the allowlist, so test the expected list |

In Agent Kit's source checkout, `task verify -- source` checks the closed
schema, which accepts only
`name`, `registry`, `transport`, `url`, `command`, `args` and `headers`. A
`tools` field in a bundle manifest therefore needs a reviewed schema change
first; consumers who write their own manifest can use it today.

## Pinning

- Pin npm servers to an exact version, container servers to an image digest and
  remote servers to the endpoint path the vendor documents. A remote endpoint
  cannot be digest-pinned, so review its tool list after each vendor release
  note and after any unexplained behavior change.
- Do not use registry resolution for a reviewed server: registry entries move.
  Declare it in place (`registry: false`) so the pin is in the repository.
- Remote servers and vendor-hosted docs servers send queries to a third party.
  Record that in the adoption review as data egress, with the data
  classification.
- Never put a secret in a header or argument. Use host-resolved indirection
  (`${input:id}` in VS Code, `${VAR}` expansion in Claude Code) and keep the
  value in the user's environment or a secret manager.

## Acceptance checks

- The review names the audience, the scopes requested and the identity.
- The server is either stdio with an environment credential reviewed as the
  user's own access, or HTTP with an OAuth flow that the host runs.
- The effective tool list (after `tools` and vendor read-only controls) was
  observed in the host and recorded.
- No committed file holds a token, and no header besides vendor option headers
  appears in source.
- Removal revokes the grant at the authorization server, not only in the host.

## Primary sources

- MCP, [Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- MCP, [Security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- IETF, [RFC 8707: Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html)
- IETF, [RFC 9728: OAuth 2.0 Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728)
- APM, [MCP servers as a primitive](https://microsoft.github.io/apm/producer/author-primitives/mcp-as-primitive/)
- GitHub, [Remote server configuration and read-only headers](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md)
