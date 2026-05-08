---
name: "pydantic-acp"
description: "Use for `pydantic-acp` tasks: exposing `pydantic_ai.Agent` through ACP, adapter config/runtime ownership, prompt capabilities, slash commands, approvals, plans, hooks, projections, host-backed tools, and Pydantic-specific examples."
---

# pydantic-acp Skill

Use this skill when the task is primarily about the `pydantic-acp` adapter package.

This is the richest ACP adapter in the repo and the clearest expression of the project rule:

> expose ACP state only when the underlying runtime can actually honor it.

In this package that rule affects:

- model selection
- mode switching
- config options
- prompt capability advertisement
- ACP-native plans
- approval flows
- host-backed files and terminal access
- tool projection
- hook visibility
- external hook event projection
- custom slash commands
- session replay

## Start Here

If you only need the shortest high-signal path:

1. read `Quick Routing`
2. open the [adapter config module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/config.py) and the [package entrypoint](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/__init__.py) for public-surface questions
3. open the [runtime adapter](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/adapter.py) for lifecycle and dispatch questions
4. then branch into approvals, projections, host, plans, slash commands, or prompt capabilities

## Quick Routing

| If the task is about... | Use this skill? | Open first |
| --- | --- | --- |
| `run_acp(agent=...)` or `create_acp_agent(...)` | Yes | [package entrypoint](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/__init__.py), [adapter config module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/config.py), [runtime adapter](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/adapter.py) |
| approvals, permission presentation, or remembered policy | Yes | [approvals module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/approvals.py), [approval store module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/approval_store.py), [permission presentation module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/permission_presentation.py), [prompt-execution runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_prompt_execution.py) |
| plans or plan generation | Yes | [prepare-tools bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/prepare_tools.py), [native plan runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_native_plan_runtime.py), [models module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/models.py) |
| filesystem / terminal ownership | Yes | [host context module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/context.py), [filesystem host backend](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/filesystem.py), [terminal host backend](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/terminal.py), [host policy module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/policy.py) |
| hook visibility or external hook projection | Yes | [hooks bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/hooks.py), [external hooks bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/external_hooks.py), [hook-introspection runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/hook_introspection.py), [hook projection module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/hook_projection.py) |
| slash commands / model / mode surface | Yes | [custom slash command module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/slash.py), [slash-commands runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/slash_commands.py), [adapter-prompt runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_adapter_prompt.py), [providers module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/providers.py) |
| prompt capabilities or multimodal input flags | Yes | [prompt capabilities module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/prompt_capabilities.py), [adapter config module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/config.py), [prompt/resources docs](https://github.com/vcoderun/acpkit/blob/main/docs/pydantic-acp/prompt-resources.md) |
| filesystem search/list projection or tool classification | Yes | [projection module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/projection.py), [host backends docs](https://github.com/vcoderun/acpkit/blob/main/docs/host-backends.md), [projection cookbook](https://github.com/vcoderun/acpkit/blob/main/docs/projection-cookbook.md) |
| Codex auth refresh or `auth.json` | No, pair with `codex-auth-helper` | [Codex helper package](https://github.com/vcoderun/acpkit/tree/main/packages/helpers/codex-auth-helper) |
| remote hosting or WebSocket transport | No, pair with `acpremote` | [remote transport package](https://github.com/vcoderun/acpkit/tree/main/packages/transports/acpremote) |

## Package Boundary

`pydantic-acp` is the adapter layer for `pydantic_ai.Agent`.

It owns:

- truthful ACP capability advertisement for a Pydantic runtime
- session-scoped model, mode, and config state
- ACP-native plan state and plan updates
- approval lifecycle and remembered approval policies
- hook introspection and hook projection
- external hook event buffering
- custom slash command discovery and handling
- host-backed filesystem and terminal ownership
- tool projection maps
- session store semantics and transcript replay

It does not own:

- Codex auth file parsing or token refresh
- WebSocket transport
- root CLI target loading

## Do Not Confuse With

- `pydantic-acp` vs `codex-auth-helper`
  the helper builds a Codex-backed model; this package exposes the Pydantic runtime through ACP
- `pydantic-acp` vs `acpremote`
  this package adapts a Pydantic runtime; `acpremote` only transports ACP
- `pydantic-acp` vs `acpkit-sdk`
  this package owns adapter semantics; `acpkit` owns CLI target loading and dispatch

## Primary References

Package references:

- [Raw skill](https://raw.githubusercontent.com/vcoderun/acpkit/main/.agents/skills/pydantic-acp/SKILL.md)
- [Raw overview docs](https://raw.githubusercontent.com/vcoderun/acpkit/main/docs/pydantic-acp.md)
- [Raw host backends docs](https://raw.githubusercontent.com/vcoderun/acpkit/main/docs/host-backends.md)
- [Raw projection cookbook](https://raw.githubusercontent.com/vcoderun/acpkit/main/docs/projection-cookbook.md)
- [Raw runtime controls docs](https://raw.githubusercontent.com/vcoderun/acpkit/main/docs/pydantic-acp/runtime-controls.md)
- [Raw plans, thinking, and approvals docs](https://raw.githubusercontent.com/vcoderun/acpkit/main/docs/pydantic-acp/plans-thinking-approvals.md)
- [Raw prompt/resources docs](https://raw.githubusercontent.com/vcoderun/acpkit/main/docs/pydantic-acp/prompt-resources.md)
- [Raw API docs](https://raw.githubusercontent.com/vcoderun/acpkit/main/docs/api/pydantic_acp.md)
- [Rendered overview](https://vcoderun.github.io/acpkit/pydantic-acp/)
- [Source tree](https://github.com/vcoderun/acpkit/tree/main/packages/adapters/pydantic-acp)

Cross-skill references:

- [Root package skill](https://raw.githubusercontent.com/vcoderun/acpkit/main/.agents/skills/acpkit-sdk/SKILL.md)
- [Codex helper skill](https://raw.githubusercontent.com/vcoderun/acpkit/main/.agents/skills/codex-auth-helper/SKILL.md)
- [Remote transport skill](https://raw.githubusercontent.com/vcoderun/acpkit/main/.agents/skills/acpremote/SKILL.md)

## Public Surface

High-value public seams:

- `run_acp(agent=...)`
- `create_acp_agent(...)`
- `AdapterConfig(...)`
- `MemorySessionStore`
- `FileSessionStore`
- `AdapterPromptCapabilities`
- `NativeApprovalBridge`
- `PermissionToolCallBuilder`
- `ApprovalPolicyStore`
- `PrepareToolsBridge`
- `PrepareToolsMode`
- `PrepareOutputToolsBridge`
- `PrepareOutputToolsMode`
- `ThinkingBridge`
- `HookBridge`
- `SlashCommandProvider`
- `StaticSlashCommandProvider`
- `ExternalHookEventBridge`
- `ProjectionAwareToolClassifier`
- `ClientHostContext`
- `CompatibilityManifest`
- `BlackBoxHarness`

Package entrypoint:

- [Package entrypoint](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/__init__.py)

## Current Pydantic AI Compatibility

`pydantic-acp` currently targets `pydantic-ai-slim==1.92.0`.

When working on this surface, remember:

- `PrepareToolsBridge` owns function-tool preparation and mode-specific plan tool visibility
- `PrepareOutputToolsBridge` owns structured-output tool preparation and session metadata for output-tool modes
- `HookBridge` covers output-tool preparation, output validation, output processing, and deferred tool-call observation
- prompt runtime passes ACP session identity through Pydantic AI `conversation_id` and run `metadata`
- `run_stream_events()` returns an async context manager in current Pydantic AI; keep direct async-iterable fallback only for tests and compatibility fakes
- `OpenAICompactionBridge` must not pass deprecated `instructions=` into upstream `OpenAICompaction`

## Module Guide

| Subsystem | Key files | Use them for |
| --- | --- | --- |
| public surface and construction | [package entrypoint](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/__init__.py), [adapter config module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/config.py), [prompt capabilities module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/prompt_capabilities.py), [agent source module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/agent_source.py), [agent type definitions](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/agent_types.py), [models module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/models.py), [providers module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/providers.py) | public API shape, construction seams, prompt capability flags, provider contracts |
| approvals | [approvals module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/approvals.py), [approval store module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/approval_store.py), [permission presentation module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/permission_presentation.py), [prompt-execution runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_prompt_execution.py), [prompt runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_prompt_runtime.py) | deferred approvals, remembered policy, permission cards, projection-aware approval context |
| bridges | [base bridge module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/base.py), [capability-support bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/capability_support.py), [external hooks bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/external_hooks.py), [history-processor bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/history_processor.py), [hooks bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/hooks.py), [MCP bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/mcp.py), [prepare-tools bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/prepare_tools.py), [thinking bridge](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/bridges/thinking.py) | optional capability wiring, external event projection, and extension seams |
| projection | [projection module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/projection.py), [projection helper module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/projection_helpers.py), [projection text helpers](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/_projection_text.py), [projection risk helpers](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/_projection_risk.py), [hook projection module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/hook_projection.py) | ACP-visible transcript cards and rendering |
| host ownership | [host context module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/context.py), [filesystem host backend](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/filesystem.py), [terminal host backend](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/terminal.py), [host policy module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/policy.py), [path policy helpers](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/_policy_paths.py), [command policy helpers](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/host/_policy_commands.py) | path safety, command safety, client-backed host behavior |
| runtime core | [runtime adapter](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/adapter.py), [runtime server](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/server.py), [bridge manager](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/bridge_manager.py), [hook-introspection runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/hook_introspection.py), [session surface module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/session_surface.py), [slash-commands runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/slash_commands.py) | adapter lifecycle, runtime update emission, slash command behavior |
| runtime helpers | [adapter-mixins runtime helpers](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_adapter_mixins.py), [adapter-prompt runtime helpers](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_adapter_prompt.py), [agent-state runtime helpers](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_agent_state.py), [native plan runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_native_plan_runtime.py), [prompt-model runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_prompt_model_runtime.py), [session-lifecycle runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_session_lifecycle.py), [session-model runtime](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_session_model_runtime.py), [session runtime helpers](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_session_runtime.py), [session-surface runtime helpers](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/runtime/_session_surface_runtime.py) | narrower runtime bugs that need subsystem-level edits |
| session storage | [session-state module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/session/state.py), [session-store module](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/session/store.py) | persisted sessions, replay, load/fork/resume/close/list |
| ACP testing helpers | [testing fakes](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/testing/fakes.py), [testing harness](https://github.com/vcoderun/acpkit/blob/main/packages/adapters/pydantic-acp/src/pydantic_acp/testing/harness.py) | testing the ACP boundary itself |

## Construction Seams

### `run_acp(agent=...)`

Use this when the caller already has one agent instance and wants the narrowest path to a running
ACP server.

### `create_acp_agent(...)`

Use this when the ACP-compatible agent object is needed before it is run.

Common reasons:

- combine with `acpremote`
- embed into another runner
- test the ACP object directly

### `agent_factory=`

Use this when ACP session state should influence agent construction but full custom source control
is unnecessary.

Typical cases:

- model-aware variants
- workspace-root binding
- mode-aware tools or instructions

### `agent_source=`

Use this when the caller needs total control over agent materialization.

Typical cases:

- precise host-context injection
- complex dependency wiring
- custom source behavior that outgrows a factory callback

## Plans, Modes, Models, and Slash Commands

`pydantic-acp` is the repo's most complete ACP-native session surface.

It supports:

- model selection
- mode switching
- config options
- ACP-native plans
- `Tool Plans` or `Structured Plans` plan generation
- custom slash command providers
- session replay and fork/resume/load/close/list lifecycle
- slash command discovery and rendering

This package should be the reference answer whenever the question is:

- "can ACP expose model switching truthfully?"
- "where do slash commands come from?"
- "how does plan state survive reload?"

## Bridges and Projections

High-value bridges include:

- `PrepareToolsBridge`
- `PrepareOutputToolsBridge`
- `ThinkingBridge`
- `HookBridge`
- `ThreadExecutorBridge`
- `SetToolMetadataBridge`
- `IncludeToolReturnSchemasBridge`
- `WebSearchBridge`
- `WebFetchBridge`
- `ImageGenerationBridge`
- `McpCapabilityBridge`
- `ToolsetBridge`
- `PrefixToolsBridge`
- `ExternalHookEventBridge`
- `OpenAICompactionBridge`
- `AnthropicCompactionBridge`

High-value projection families include:

- `FileSystemProjectionMap`
- `WebToolProjectionMap`
- `BuiltinToolProjectionMap`
- `HookProjectionMap`
- `CompositeProjectionMap`
- `ProjectionAwareToolClassifier`

Important rule:

- bridges affect runtime behavior and metadata
- projection maps affect ACP-visible transcript rendering
- `FileSystemProjectionMap` search/list tree rendering is opt-in and never reads the filesystem
- `ProjectionAwareToolClassifier` classifies only configured tool names and delegates unknown tools

Split those concerns before editing.

## Host Ownership

This package has the repo's strongest host-side ownership model.

Relevant public ideas:

- `ClientHostContext`
- filesystem backend
- terminal backend
- `HostAccessPolicy`

Use this skill when the task is about:

- safe writes
- command warnings
- diff projection before approval
- path normalization
- client-owned host resources

## Prompt and Model Ownership

This package also owns the more subtle Pydantic-specific surfaces:

- prompt-to-input conversion
- prompt capability advertisement through `AdapterPromptCapabilities`
- prompt-model override providers
- media-aware model routing
- transcript-to-history rebuilding
- model restore paths during replay/load

When the question involves image/audio/resources plus model selection, this package is usually the
correct home.

## Common Workflows

### Minimal Pydantic ACP server

```python
from pydantic_ai import Agent
from pydantic_acp import run_acp

agent = Agent('openai:gpt-5')
run_acp(agent=agent)
```

### ACP object first, run later

Use `create_acp_agent(...)` when another runner or transport layer should own startup.

### Session-aware construction

Use `agent_factory=` when session state should change the built agent.

### Codex-backed Pydantic model plus ACP

Use `codex-auth-helper` to construct the model, then expose through `pydantic-acp`.

### Remote-hosted Pydantic ACP

Adapt with `pydantic-acp`, then expose with `acpremote`.

## Public Examples

Maintained public examples:

- [Pydantic public examples](https://raw.githubusercontent.com/vcoderun/acpkit/main/examples/pydantic/README.md)
- [Finance agent example](https://github.com/vcoderun/acpkit/blob/main/examples/pydantic/finance_agent.py)
- [Travel agent example](https://github.com/vcoderun/acpkit/blob/main/examples/pydantic/travel_agent.py)

Use `finance_agent.py` for:

- ACP-native plans
- approvals
- projected file diffs
- workspace/file ownership

Use `travel_agent.py` for:

- hook projection
- prompt-model overrides
- media prompt behavior

Skill-local example index:

- [Skill-local example index](https://github.com/vcoderun/acpkit/blob/main/.agents/skills/pydantic-acp/examples/README.md)

Cross-package Codex-backed example:

- [Codex-backed agent example](https://github.com/vcoderun/acpkit/blob/main/.agents/skills/codex-auth-helper/examples/codex_responses_agent.py)

## Handoff Rules

Pair or switch to:

- `codex-auth-helper`
  when a local Codex login is being turned into a Pydantic AI model
- `acpkit-sdk`
  when this adapter is being reached through `acpkit run ...` or `acpkit serve ...`
- `acpremote`
  when the adapted agent is then exposed remotely over WebSocket

Stay in this skill when the main issue is:

- ACP runtime truthfulness
- provider state
- plan/approval behavior
- host policy
- projection
- session lifecycle

## Guardrails

- Do not describe `pydantic-acp` as transport.
- Do not promise ACP state the active `pydantic_ai.Agent` cannot honor.
- Do not route LangChain or DeepAgents questions through this skill.
- Do not answer Codex auth refresh questions from here unless the adapter integration itself is
  the point.
- Do not add `permission_tool_call_builder` to `AdapterConfig`; permission rendering belongs on
  `NativeApprovalBridge.tool_call_builder`.
- Keep `ApprovalBridge` compatible with the legacy no-`projection_map` signature. Use
  `ProjectionAwareApprovalBridge` only for bridges that explicitly accept projected context.
- Do not make custom slash commands collide with built-in commands or mode names.
- Treat `ExternalHookEventBridge.metadata_key=None` as the way to suppress bridge metadata
  publication.
- If the task is really about remote transport, move to `acpremote`.
