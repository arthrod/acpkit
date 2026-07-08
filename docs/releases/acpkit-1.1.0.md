# ACP Kit 1.1.0

`1.1.0` adds the ACP-backed Pydantic AI provider bridge and tightens the v1
release surface around current framework versions and maintained examples.

## Highlights

- `pydantic-acp` now exports `AcpProvider`, `AcpModel`, and `AcpHostBridge` so
  an existing ACP agent can be consumed as a Pydantic AI v2 provider/model pair.
- `AcpProvider(acp_agent=...)` is the explicit construction API for wrapping an
  ACP agent instance.
- `provider.model()` leaves model selection to the wrapped ACP agent's session
  default; pass a concrete model name only when the ACP agent accepts that
  `session/set_model` id.
- Maintained examples now write generated workspaces and local session state
  under `agent_demos/`, with `.gitignore` ignoring that single runtime output
  directory.
- Workspace package version files are synchronized at `1.1.0`.

## Compatibility

The release gate covers:

- Python 3.11 through 3.13
- Pydantic AI 2.0 through 2.4
- LangChain 1.3.11
- LangGraph 1.2.7
- DeepAgents 0.6.12
- ACP Python SDK 0.9.0

## Migration Notes

Use `AcpProvider` only when the runtime you have is already an ACP agent. If
you are exposing a `pydantic_ai.Agent` through ACP, keep using
`create_acp_agent(...)` or `run_acp(...)`.

If an ACP agent rejects `"agent"` as an explicit model id, call
`provider.model()` without arguments. That path no longer sends
`session/set_model("agent")`; it lets the wrapped agent keep its own default.
