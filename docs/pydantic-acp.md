# Pydantic ACP Overview

`pydantic-acp` is the primary Pydantic AI adapter in ACP Kit.

Its job is simple: keep your existing `pydantic_ai.Agent` surface intact, then expose it as an ACP server without inventing runtime state the underlying agent cannot actually honor.

Use it when you want ACP-native clients to see truthful:

- models and model switching
- modes and slash commands
- native plan state and plan progress
- approval workflows
- cancellation behavior
- MCP metadata and host-backed tools
- prompt resources such as editor selections, branch diffs, file references, and multimodal input
- persisted ACP sessions and replayable transcript state

## The Three Main Integration Seams

Most integrations use one of these seams.

### `run_acp(...)`

Use `run_acp(...)` when you already have an agent instance and want the smallest supported ACP entrypoint:

```python
from pydantic_ai import Agent
from pydantic_acp import run_acp

agent = Agent("openai:gpt-5", name="demo-agent")

run_acp(agent=agent)
```

This is the fastest path from a normal `pydantic_ai.Agent` to a working ACP server.

If the agent should reuse an existing local Codex login, build the model through
`codex-auth-helper` and pass explicit instructions at factory construction time:

```python
from codex_auth_helper import create_codex_responses_model
from pydantic_ai import Agent

model = create_codex_responses_model(
    "gpt-5.4",
    instructions="You are a helpful coding assistant.",
)

agent = Agent(model, name="codex-agent")
```

On the Pydantic path, `Agent(instructions=...)` can still be layered on top for
agent-owned instructions, but the Codex factory should always receive explicit
`instructions=...`.

### `create_acp_agent(...)`

Use `create_acp_agent(...)` when another runtime should own transport lifecycle but you still want the adapter assembly:

```python
from pydantic_ai import Agent
from pydantic_acp import create_acp_agent

agent = Agent("openai:gpt-5", name="demo-agent")
acp_agent = create_acp_agent(agent=agent)
```

This is the lower-level construction seam behind `run_acp(...)`.

### `agent_factory=...`

Use `agent_factory=` when the session should influence which agent gets built, but a full custom
`AgentSource` would be unnecessary:

```python
from pydantic_ai import Agent
from pydantic_acp import AcpSessionContext, AdapterConfig, MemorySessionStore, run_acp


def build_agent(session: AcpSessionContext) -> Agent[None, str]:
    workspace_name = session.cwd.name
    tenant = str(session.metadata.get("tenant", "general"))
    model_name = "openai:gpt-5.4-mini"
    if workspace_name.endswith("-deep"):
        model_name = "openai:gpt-5.4"

    return Agent(
        model_name,
        name=f"{tenant}-{workspace_name}",
        system_prompt=f"Work inside {workspace_name} for tenant {tenant}.",
    )


run_acp(
    agent_factory=build_agent,
    config=AdapterConfig(session_store=MemorySessionStore()),
)
```

This is the right seam when:

- the model should change by workspace or tenant
- the prompt or instructions should change from session metadata
- the adapter should build one session-specific `Agent(...)` instance per ACP session

If the agent also needs separately-constructed session dependencies, use `AgentSource` instead.

### `AgentSource`

Use `AgentSource` when agent construction depends on session state, request context, or host-owned dependencies:

```python
from pydantic_acp import AgentSource


class WorkspaceAgentSource(AgentSource[MyDeps]):
    async def get_agent(self, session):
        ...

    async def get_deps(self, session):
        ...
```

This is the right seam for provider-backed sessions, workspace-aware coding agents, and host-owned dependency injection.

## What The Adapter Owns

By default, the adapter can own:

- ACP session persistence
- transcript and message-history replay
- built-in model selection
- built-in mode selection
- native ACP plan state
- thinking effort config
- approval flow through an approval bridge
- projection-aware permission prompt rendering and remembered approval policies
- generic or rich projected tool rendering
- host-defined slash commands and prompt capability advertisement

The built-in ownership path is usually enough for:

- internal tools
- local development
- single-tenant ACP agents
- examples and demos

## What The Host Can Own

When your product already has a source of truth, keep that ownership in the host and expose it through providers.

Common provider seams:

- `SessionModelsProvider`
- `SessionModesProvider`
- `ConfigOptionsProvider`
- `PlanProvider`
- `ApprovalStateProvider`
- `NativePlanPersistenceProvider`

Use providers when:

- model ids come from product policy
- mode state is product-owned
- plans must be mirrored into your own storage
- approval metadata already exists elsewhere
- the adapter should expose state, not create it

## Bridges: How ACP-visible Behavior Gets Added

Capability bridges are how the adapter contributes ACP-facing runtime behavior.

Common bridges:

- `PrepareToolsBridge`
  exposes dynamic modes, plan tools, and tool-surface filtering
- `ThinkingBridge`
  exposes ACP-visible thinking effort when the model runtime supports it
- `NativeApprovalBridge`
  powers ACP approval workflows
- `McpBridge`
  exposes MCP metadata and config options
- `HookBridge`
  exposes or suppresses hook activity
- `HistoryProcessorBridge`
  lets the host rewrite or enrich message history

The important rule is that bridges should describe real runtime behavior, not hypothetical UI affordances.

## Runtime Notes

- `Agent(output_type=str | None)` is supported, but a successful `None` result ends the turn without emitting a synthetic `"null"` transcript message.

## A Production-shaped Configuration

```python
from pathlib import Path

from pydantic_ai import Agent
from pydantic_acp import (
    AdapterConfig,
    FileSessionStore,
    NativeApprovalBridge,
    PrepareToolsBridge,
    PrepareToolsMode,
    ThinkingBridge,
    run_acp,
)

agent = Agent("openai:gpt-5", name="workspace-agent")

config = AdapterConfig(
    session_store=FileSessionStore(root=Path(".acp-sessions")),
    approval_bridge=NativeApprovalBridge(enable_persistent_choices=True),
    capability_bridges=[
        ThinkingBridge(),
        PrepareToolsBridge(
            default_mode_id="ask",
            modes=[
                PrepareToolsMode(
                    id="ask",
                    name="Ask",
                    description="Read-only inspection mode.",
                    prepare_func=lambda ctx, tool_defs: list(tool_defs),
                ),
                PrepareToolsMode(
                    id="plan",
                    name="Plan",
                    description="Native ACP plan mode.",
                    prepare_func=lambda ctx, tool_defs: list(tool_defs),
                    plan_mode=True,
                ),
            ],
        ),
    ],
)

run_acp(agent=agent, config=config)
```

This is not the only valid shape, but it shows the real moving parts:

- `FileSessionStore` persists ACP session state
- `NativeApprovalBridge` enables approvals
- `ThinkingBridge` exposes effort selection
- `PrepareToolsBridge` defines ACP-visible modes and plan behavior

## Recommended Reading Order

If you are integrating `pydantic-acp` in a real product:

1. Read [Pydantic Quickstart](getting-started/pydantic-quickstart.md).
2. Read [AdapterConfig](pydantic-acp/adapter-config.md).
3. Read [Models, Modes, and Slash Commands](pydantic-acp/runtime-controls.md).
4. Read [Plans, Thinking, and Approvals](pydantic-acp/plans-thinking-approvals.md).
5. Read [Prompt Resources and Context](pydantic-acp/prompt-resources.md) if your client attaches selections, diffs, file refs, or multimodal input.
6. Read [Providers](providers.md) if the host already owns state.
7. Read [Bridges](bridges.md) if you need ACP-visible runtime extensions.
8. Read [Finance Agent](examples/finance.md) and [Travel Agent](examples/travel.md) for maintained end-to-end examples.

## Common Mistakes

- Treating ACP as a separate agent implementation instead of an adapter layer over your existing agent surface
- letting the adapter advertise UI state the runtime cannot really honor
- mixing built-in state ownership and provider ownership without a clear source of truth
- assuming plan tools exist in every mode instead of explicitly enabling `plan_mode` or `plan_tools`
- using `FileSessionStore(base_dir=...)` instead of `FileSessionStore(root=...)`
- treating `FileSessionStore` like a distributed multi-writer backend instead of a hardened local durable store
- returning a coroutine from `run_event_stream` hooks instead of an async iterable

## Version Compatibility And Private Upstream APIs

`pydantic-acp` currently pins `pydantic-ai-slim==1.92.0`.

That is not accidental. The adapter relies on a specific, tested Pydantic AI
surface and should still be upgraded deliberately.

The current compatibility surface includes function-tool preparation,
output-tool preparation, output validation/processing hooks,
deferred-tool-call hooks, run metadata, and conversation IDs.

ACP Kit also no longer imports Pydantic AI private history-processor modules
directly. History processor support is expressed through ACP Kit's own callable
aliases and passed into the public `Agent(..., history_processors=...)`
interface.

What this means in practice:

- the adapter is less exposed to private upstream type-module churn
- upgrades are still compatibility work, but Pydantic AI integration points stay
  isolated behind ACP Kit bridge and runtime seams
