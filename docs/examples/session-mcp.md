# Session MCP Agent

The maintained session MCP showcase is
[`examples/pydantic/session_mcp_agent.py`](https://github.com/vcoderun/acpkit/blob/main/examples/pydantic/session_mcp_agent.py).

It demonstrates the ACP client-owned MCP path:

- ACP clients attach servers through `session/new.mcpServers`
- `SessionMcpBridge` converts those session payloads into Pydantic AI `MCPToolset` capabilities
- `/mcp-servers` remains the observability surface for attached servers
- env and header values are used for the MCP connection but only names are published in metadata

## Run It

```bash
uv run python -m examples.pydantic.session_mcp_agent
```

Without `ACP_SESSION_MCP_MODEL`, the example uses `TestModel` so startup stays credential-free.
Set `ACP_SESSION_MCP_MODEL` when you want a live model to call attached MCP tools.

## Client Payload Shape

```json
{
  "mcpServers": [
    {
      "name": "repo",
      "type": "http",
      "url": "https://repo.example/mcp",
      "headers": [{"name": "Authorization", "value": "Bearer ..."}]
    },
    {
      "name": "local-docs",
      "command": "python",
      "args": ["docs_mcp_server.py"],
      "env": [{"name": "DOCS_ROOT", "value": "agent_demos/docs"}]
    }
  ]
}
```

## Key Patterns

- the module exports `agent_factory`, `config`, `acp_agent`, and `main`
- `AgentBridgeBuilder` is used inside the factory so each session gets its own MCP toolset
- `SessionMcpBridge(include_instructions=True, include_return_schema=True)` keeps MCP instructions and tool return schemas in the Pydantic AI request path
- without `SessionMcpBridge`, the same payload is stored and listed but not connected as tools
