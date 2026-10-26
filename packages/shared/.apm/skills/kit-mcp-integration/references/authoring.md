# Authoring an MCP server

A good MCP server is a small, typed, well-documented API whose caller is a
model. The model only sees tool names, descriptions, input schemas and
results, so those are the user interface. Review date: 2026-10-23; examples
target the v2 Python SDK, which speaks the 2026-07-28 protocol revision.

## Design the toolset

| Decision | Guidance |
| --- | --- |
| Scope | one server per service or domain; a handful of tools that map to user tasks, not one tool per internal function |
| Names | verb and noun in `snake_case` (`search_notes`, `read_note`); unique across servers the host is likely to load |
| Descriptions | one sentence on what it does and when to use it; mention the follow-up tool when there is a sequence |
| Parameters | typed, with bounds (`min_length`, `max_length`, `ge`, `le`, `pattern`) and a description each; prefer enumerations over free text |
| Results | structured data (dataclass, TypedDict or model) with only the fields the model needs; truncate large text with a stated limit |
| Side effects | read-only by default; split write tools from read tools so hosts can confirm them separately |
| Resources and prompts | expose stable documents as resources and reusable instructions as prompts instead of tools that just return text |

## Errors the model can act on

- Validate input at the tool boundary and fail with a message that names the
  fix ("call `search_notes` to find note names"), not a stack trace.
- Never include secrets, internal host names or full file system paths in
  messages; tool results reach the model and may be logged by the host.
- Distinguish "nothing found" (empty result) from "failed" (error result).
- Apply timeouts to every outbound call and return a clear error when a
  dependency is unavailable.

## Security checklist

- Contain every path under a configured root; resolve before checking.
- Never run shell commands built from tool arguments; use argument lists
  (see the `kit-secure-code` skill).
- Read credentials from the environment (stdio) or validate access tokens
  issued for this server (HTTP); never accept a token meant for another API.
- For HTTP servers: bind to loopback in development, validate `Origin`, use
  HTTPS in deployment, and rate-limit expensive tools.
- Treat any content fetched from elsewhere as untrusted and return it as data;
  do not let it change tool behavior.
- Log to standard error (stdio servers must keep standard output for the
  protocol); log tool names and counts, not arguments that may hold data.

## Python SDK essentials

Start from the [server template](../assets/mcp_server.py.template):

- `server = MCPServer("name")`, then `@server.tool()` on typed functions; the
  input schema comes from the annotations, and `Annotated[..., Field(...)]`
  adds bounds and descriptions.
- `server.run()` serves stdio; pass the Streamable HTTP transport option for a
  remote deployment.
- An exception raised in a tool becomes an error result whose text is the
  exception message.
- v1 code imports `FastMCP` from `mcp.server.fastmcp`; v2 renamed it to
  `MCPServer` in `mcp.server`. Follow the pinned version's migration guide.

Pin `mcp` exactly in the manifest and lockfile; the protocol revision and
SDK APIs change between major versions.

## Testing

1. **Unit**: call the tool functions directly with a temporary directory and
   environment; cover success, empty, invalid input and missing
   configuration.
2. **In-memory protocol**: connect `Client(server)` without a transport and
   assert the exact tool list and an error result for bad input
   ([test template](../assets/test_mcp_server.py.template)).
3. **Inspector**: run the MCP Inspector against the real process (for
   example `mcp dev` from the SDK's CLI extra, run through the locked
   toolchain), check every schema and description, and call each tool once.
4. **Host**: add the server to one host with synthetic data, confirm discovery,
   one read call, and a declined write call.

Record the SDK version, protocol revision, host and results in the adoption
review.

## Anti-patterns

- A single `run(command: str)` tool that executes anything.
- Returning whole files or database tables when a summary would do.
- Tool descriptions that contain instructions to the model about other tools
  or servers.
- Printing to standard output in a stdio server.
- Silently catching exceptions and returning success.

## Primary sources

- MCP, [Server concepts: tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- MCP Python SDK, [documentation](https://py.sdk.modelcontextprotocol.io/) and [What's new in v2](https://py.sdk.modelcontextprotocol.io/whats-new/)
- MCP, [Inspector](https://modelcontextprotocol.io/docs/tools/inspector)
- MCP, [Security best practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- Pydantic, [Fields](https://docs.pydantic.dev/latest/concepts/fields/)
