# pydantic-acp

`pydantic-acp` adapts `pydantic_ai.Agent` instances to the ACP agent interface without rewriting the underlying agent.

The core contract is simple:

1. keep the existing `pydantic_ai.Agent`
2. expose it through ACP
3. only publish ACP-visible state the runtime can actually honor

The package also includes the inverse bridge: an ACP agent can be consumed as a Pydantic AI v2 provider/model pair via `AcpProvider` and `AcpModel`.

## Entry Points

- `run_acp(...)`
- `create_acp_agent(...)`
- `AdapterConfig`
- `AcpSessionContext`
- `StaticAgentSource`
- `FactoryAgentSource`
- `AcpProvider`
- `AcpModel`
- `AcpHostBridge`

## What It Covers

`pydantic-acp` includes:

- ACP session lifecycle, replay, resume, and persistence
- session-local model selection
- mode and slash-command control
- native ACP plan state with structured `TaskPlan`
- approval bridging
- prompt resources including files, embedded resources, images, and audio
- projection maps for filesystem, hooks, web tools, and builtin tool families
- capability bridges for upstream Pydantic AI capabilities
- client-backed filesystem and terminal helpers
- ACP client/provider bridging for consuming ACP agents from the Pydantic AI ecosystem

## Quick Start

Expose a Pydantic AI agent through ACP:

```python
from pydantic_ai import Agent
from pydantic_acp import run_acp

agent = Agent("openai:gpt-5", name="demo-agent")
run_acp(agent=agent)
```

If another runtime should own transport lifecycle:

```python
from acp import run_agent
from pydantic_ai import Agent
from pydantic_acp import AdapterConfig, MemorySessionStore, create_acp_agent

agent = Agent("openai:gpt-5", name="composable-agent")

acp_agent = create_acp_agent(
    agent=agent,
    config=AdapterConfig(session_store=MemorySessionStore()),
)

run_agent(acp_agent)
```

## ACP Client Provider Bridge

`AcpProvider` is the client-side mirror of the ACP server adapter. It wraps an ACP agent as a Pydantic AI v2 `Provider`; `AcpModel` is the model object Pydantic AI agents run against.

```python
from pydantic_ai import Agent
from pydantic_acp import AcpProvider

# `remote_acp_agent` can be any object implementing the ACP Agent interface.
provider = AcpProvider(agent=remote_acp_agent, cwd="/workspace")
model = provider.model("zed-agent")
agent = Agent(model)

result = await agent.run("Summarize the current workspace state.")
print(result.output)
```

This keeps ownership boundaries explicit:

- Pydantic AI owns the outer agent run, output validation, and normal model/provider lifecycle.
- ACP owns the delegated agent session, ACP-visible updates, and any editor or host capabilities requested by that agent.
- `AcpHostBridge` records ACP `session_update` messages and can delegate filesystem, terminal, approval, and extension callbacks to a real ACP host client when one is supplied.
- Pydantic AI function tools are intentionally not executed directly by `AcpModel`; register tools on the ACP agent or expose host capabilities through ACP.

Use this bridge when the thing you have is already an ACP agent and you want it to participate in code that expects a Pydantic AI provider/model. It is not another ACP server adapter and it does not replace `create_acp_agent(...)`.

## Native Plan Mode

`TaskPlan` is the structured native plan output surface.

Use `PrepareToolsBridge` to expose plan mode:

```python
from pydantic_ai import Agent
from pydantic_ai.tools import RunContext, ToolDefinition
from pydantic_acp import (
    AdapterConfig,
    PrepareToolsBridge,
    PrepareToolsMode,
    run_acp,
)


def read_only_tools(
    ctx: RunContext[None],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition]:
    del ctx
    return list(tool_defs)


agent = Agent("openai:gpt-5", name="plan-agent")

run_acp(
    agent=agent,
    config=AdapterConfig(
        capability_bridges=[
            PrepareToolsBridge(
                default_mode_id="plan",
                default_plan_generation_type="structured",
                modes=[
                    PrepareToolsMode(
                        id="plan",
                        name="Plan",
                        description="Return a structured ACP task plan.",
                        prepare_func=read_only_tools,
                        plan_mode=True,
                    ),
                ],
            ),
        ],
    ),
)
```

Important behavior:

- `plan_generation_type="structured"` is the default plan-mode behavior
- `structured` mode expects structured `TaskPlan` output instead of exposing `acp_set_plan`
- switch to `plan_generation_type="tools"` when you explicitly want tool-based native plan recording
- keep `plan_tools=True` when you also want progress tools such as `acp_update_plan_entry`

## Projection Maps

Projection maps decide how known tool families render into ACP-visible updates.

Built-in projection helpers:

- `FileSystemProjectionMap`
- `HookProjectionMap`
- `WebToolProjectionMap`
- `BuiltinToolProjectionMap`

Example:

```python
from pydantic_acp import (
    AdapterConfig,
    BuiltinToolProjectionMap,
    FileSystemProjectionMap,
    HookProjectionMap,
    run_acp,
)

run_acp(
    agent=agent,
    config=AdapterConfig(
        projection_maps=[
            FileSystemProjectionMap(
                default_read_tool="read_file",
                default_write_tool="write_file",
            ),
            HookProjectionMap(
                hidden_event_ids=frozenset({"after_model_request"}),
                event_labels={"before_model_request": "Preparing Request"},
            ),
            BuiltinToolProjectionMap(),
        ],
    ),
)
```

## Capability Bridges

Current built-in bridges include:

- `ThinkingBridge`
- `PrepareToolsBridge`
- `ThreadExecutorBridge`
- `SetToolMetadataBridge`
- `IncludeToolReturnSchemasBridge`
- `WebSearchBridge`
- `WebFetchBridge`
- `ImageGenerationBridge`
- `McpCapabilityBridge`
- `ToolsetBridge`
- `PrefixToolsBridge`
- `OpenAICompactionBridge`
- `AnthropicCompactionBridge`

Use bridges when the runtime should gain upstream Pydantic AI capabilities and ACP-visible metadata without rewriting the adapter core.

## Factories, Sources, And Host-owned State

Use `agent_factory=` when the ACP session should influence which agent gets built:

```python
from pydantic_ai import Agent
from pydantic_acp import AcpSessionContext, AdapterConfig, MemorySessionStore, run_acp


def build_agent(session: AcpSessionContext) -> Agent[None, str]:
    workspace_name = session.cwd.name
    model_name = "openai:gpt-5.4-mini"
    if workspace_name.endswith("-deep"):
        model_name = "openai:gpt-5.4"
    return Agent(model_name, name=f"workspace-{workspace_name}")


run_acp(
    agent_factory=build_agent,
    config=AdapterConfig(session_store=MemorySessionStore()),
)
```

Use `AgentSource` when the agent and its dependencies should be built separately. Use providers when models, modes, config values, plans, or approvals belong to the host layer instead of the adapter.

## Maintained Examples

Maintained runnable examples:

- [finance_agent.py](https://github.com/vcoderun/acpkit/blob/main/examples/pydantic/finance_agent.py)
- [travel_agent.py](https://github.com/vcoderun/acpkit/blob/main/examples/pydantic/travel_agent.py)

Focused docs recipes:

- [Dynamic Factory Agents](https://vcoderun.github.io/acpkit/examples/dynamic-factory/)

## Documentation

- [Pydantic ACP Overview](https://vcoderun.github.io/acpkit/pydantic-acp/)
- [AdapterConfig](https://vcoderun.github.io/acpkit/pydantic-acp/adapter-config/)
- [Plans, Thinking, and Approvals](https://vcoderun.github.io/acpkit/pydantic-acp/plans-thinking-approvals/)
- [Models, Modes, and Slash Commands](https://vcoderun.github.io/acpkit/pydantic-acp/runtime-controls/)
- [Prompt Resources and Context](https://vcoderun.github.io/acpkit/pydantic-acp/prompt-resources/)
- [Session State and Lifecycle](https://vcoderun.github.io/acpkit/pydantic-acp/session-state/)
- [Bridges](https://vcoderun.github.io/acpkit/bridges/)
- [Providers](https://vcoderun.github.io/acpkit/providers/)
- [Host Backends and Projections](https://vcoderun.github.io/acpkit/host-backends/)
- [API Reference](https://vcoderun.github.io/acpkit/api/pydantic_acp/)

## Compatibility Policy

`pydantic-acp` requires `pydantic-ai-slim>=2.0.0,<3`.

The ACP client provider bridge depends on the Pydantic AI v2 `Provider` and `Model` contracts. Upgrades across major Pydantic AI versions should be deliberate because the adapter exposes both server-side ACP translation and client-side ACP provider integration.
