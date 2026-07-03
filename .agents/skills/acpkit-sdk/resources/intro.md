# ACP Kit SDK Intro

ACP Kit is the adapter toolkit and monorepo for turning an existing agent surface into a truthful ACP server boundary.

Today the repo ships production-grade adapters for both `pydantic-acp` and `langchain-acp`.
`pydantic-acp` remains the richest reference implementation for ACP-native models, modes, plans,
approvals, MCP metadata, host tools, projection, and session state.

This intro is intentionally short. The canonical deep references should come from the published docs set, not from a second parallel skill-specific spec.

## Core Positioning

ACP Kit is not a new agent framework.

It sits between:

- an existing agent runtime
- ACP clients such as editors and host applications

The central contract is:

> expose ACP state only when the underlying runtime can actually honor it.

That rule drives model selection, mode switching, slash commands, prompt capabilities, native plan
state, approval flow, MCP metadata, external hook events, projection, and host-backed tooling.

## Start With The Real Docs

Use these published docs pages as the primary references:

| Need | Published docs |
| --- | --- |
| Product overview and package map | [ACP Kit Overview](https://vcoderun.github.io/acpkit/) |
| Construction seams and adapter overview | [Pydantic ACP Overview](https://vcoderun.github.io/acpkit/pydantic-acp/) |
| Runtime config and session ownership | [AdapterConfig](https://vcoderun.github.io/acpkit/pydantic-acp/adapter-config/) |
| Models, modes, custom slash commands, thinking | [Models, Modes, and Slash Commands](https://vcoderun.github.io/acpkit/pydantic-acp/runtime-controls/) |
| Plans, approvals, permission presentation, and cancellation | [Plans, Thinking, and Approvals](https://vcoderun.github.io/acpkit/pydantic-acp/plans-thinking-approvals/) |
| Host-owned state patterns | [Providers](https://vcoderun.github.io/acpkit/providers/) |
| ACP-visible extension seams and external hook events | [Bridges](https://vcoderun.github.io/acpkit/bridges/) |
| Host-backed tools, search/list projection, and classification | [Host Backends and Projections](https://vcoderun.github.io/acpkit/host-backends/) |
| Maintained example ladder | [Examples Overview](https://vcoderun.github.io/acpkit/examples/) |
| Pydantic production showcase | [Finance Agent](https://vcoderun.github.io/acpkit/examples/finance/) |
| LangChain production showcase | [LangChain Workspace Graph](https://vcoderun.github.io/acpkit/examples/langchain-workspace/) |
| API surface | [pydantic_acp API](https://vcoderun.github.io/acpkit/api/pydantic_acp/) |

## Construction Seams To Reach For

Use these seams intentionally:

| Seam | Use it when |
| --- | --- |
| `run_acp(agent=...)` | you want the smallest direct path from `pydantic_ai.Agent` to a running ACP server |
| `create_acp_agent(...)` | you need the ACP-compatible agent object before running it |
| `agent_factory=` | session context should influence agent construction, but a full custom source is unnecessary |
| `agent_source=` | you need full control over agent build path, host binding, and session-specific dependencies |
| built-in `AdapterConfig` fields | the adapter can own the relevant session state cleanly |
| providers | the host or product layer should remain the source of truth |
| bridges | the runtime needs ACP-visible capabilities without hard-coding them into the adapter core |

## High-Value Guardrails

- `FileSessionStore` takes `root=Path(...)`, not `base_dir=...`
- `FileSessionStore` is the hardened local durable store: atomic replace writes, local locking, malformed-session tolerance, and stale temp cleanup; it is not a distributed multi-writer backend
- slash mode commands are dynamic; `ask`, `plan`, and `agent` are examples, not built-in global names
- mode ids must not collide with reserved slash command names like `model`, `thinking`, `tools`, `hooks`, or `mcp-servers`
- custom slash commands come from `SlashCommandProvider` or `StaticSlashCommandProvider`, and
  must not collide with built-in commands or mode names
- `AdapterConfig.prompt_capabilities` controls what prompt input families are advertised; do not
  advertise image, audio, or embedded context unless the runtime can honor them
- only one `PrepareToolsMode(..., plan_mode=True)` is allowed
- `plan_tools=True` is how a non-plan execution mode keeps plan progress tools visible
- `PrepareOutputToolsBridge` is the separate seam for structured-output tool preparation in
  current Pydantic AI
- `HookBridge` covers output-tool preparation, output validation, output processing, and
  deferred tool-call observation
- `/thinking` only exists when `ThinkingBridge()` is configured
- native ACP plan state and `PlanProvider` are separate ownership paths
- permission card rendering is `NativeApprovalBridge.tool_call_builder`, not an `AdapterConfig`
  field
- `ApprovalBridge` stays compatible with the legacy no-`projection_map` signature; use
  `ProjectionAwareApprovalBridge` only when the bridge explicitly accepts projected context
- remembered approval policy is live runtime state owned by `ApprovalPolicyStore`, while
  `ApprovalStateProvider` is metadata-only
- `HookBridge(hide_all=True)` suppresses hook listing output, not the underlying hook capability itself
- `ExternalHookEventBridge` is for integrations that already own lifecycle events and want them
  buffered into ACP updates
- custom `run_event_stream` hooks and wrappers must return an async iterable, not a coroutine
- `HostAccessPolicy` is the native typed guardrail surface for host-backed file and terminal access
- `FileSystemProjectionMap` search/list tree rendering is opt-in and based only on tool output;
  it must not read the filesystem
- `ProjectionAwareToolClassifier` classifies only configured projection tool names and delegates
  unknown tools to the base classifier
- `BlackBoxHarness` is the reusable black-box ACP boundary test helper for downstream integrations
- projection helper primitives handle diff previews, truncation, command summaries, and guardrail-aware caution text without each integration rebuilding that shaping logic
- the compatibility manifest schema gives integrations one typed, reviewable declaration of which ACP surfaces are implemented, partial, intentionally not used, or planned

## New Native Surfaces

### PromptCapabilities, SlashCommandProvider, And StaticSlashCommandProvider

Reach for `AdapterConfig.prompt_capabilities` when the runtime's prompt input support differs from
the defaults. Use `SlashCommandProvider` or `StaticSlashCommandProvider` when a product integration
needs commands beyond the built-in model, mode, config, thinking, tools, hooks, and MCP surfaces.

Custom command handlers can return transcript updates, text, or a handled/fallthrough decision. The
default result refreshes the session surface so visible commands and related state stay synchronized.

Read next:

- https://vcoderun.github.io/acpkit/pydantic-acp/runtime-controls/
- https://vcoderun.github.io/acpkit/pydantic-acp/adapter-config/

### ApprovalPolicyStore And PermissionToolCallBuilder

Reach for `ApprovalPolicyStore` when remembered approval policy needs to live somewhere other than
session metadata. Reach for `PermissionToolCallBuilder` when native approvals should render custom
permission cards while keeping the ACP approval lifecycle unchanged.

Keep the builder on `NativeApprovalBridge.tool_call_builder`. If a custom approval bridge needs
projected file or command context, implement `ProjectionAwareApprovalBridge` rather than widening the
legacy `ApprovalBridge` protocol.

Read next:

- https://vcoderun.github.io/acpkit/pydantic-acp/plans-thinking-approvals/
- https://vcoderun.github.io/acpkit/providers/

### ExternalHookEventBridge And ProjectionAwareToolClassifier

Reach for `ExternalHookEventBridge` when hook-like lifecycle events come from an external runtime and
should appear through the normal buffered bridge update path. Reach for
`ProjectionAwareToolClassifier` when configured projection maps should also drive ACP tool-kind
classification for reads, writes, bash, and search tools.

Read next:

- https://vcoderun.github.io/acpkit/bridges/
- https://vcoderun.github.io/acpkit/host-backends/

### HostAccessPolicy

Reach for `HostAccessPolicy` when an integration needs one reusable, typed place to evaluate file and command risk.

It gives you:

- `allow / warn / deny` policy decisions
- file path evaluation against session cwd and workspace root
- command cwd evaluation plus heuristic path-like argument inspection
- UI-friendly evaluation outputs such as `headline`, `message`, and `recommendation`
- backend-side `deny` enforcement before ACP host requests are sent

Minimal example:

```python
from pathlib import Path

from pydantic_acp import HostAccessPolicy

policy = HostAccessPolicy.strict()
evaluation = policy.evaluate_path(
    '../notes.txt',
    session_cwd=Path('/workspace/app'),
    workspace_root=Path('/workspace/app'),
)
```

Read next:

- https://vcoderun.github.io/acpkit/host-backends/
- https://vcoderun.github.io/acpkit/projection-cookbook/

### BlackBoxHarness

Reach for `BlackBoxHarness` when an integration needs proof, not just implementation.

It gives you a reusable way to test:

- session create/load
- prompts at the ACP boundary
- approval queueing
- visible updates
- replay after reload

Use it to prove that an ACP integration is truthful without rebuilding a recording client and update parser for every project.

Minimal example:

```python
session = asyncio.run(harness.new_session(cwd=str(tmp_path)))
harness.queue_permission_selected('allow_once')
response = asyncio.run(harness.prompt_text('Write the workspace note.'))
```

Read next:

- https://vcoderun.github.io/acpkit/integration-testing/

### CompatibilityManifest

Reach for `CompatibilityManifest` after the integration already has real seams and at least one black-box proof path.

It is for reviewability, not runtime behavior. Write it in Python, validate it in tests, and optionally render it into Markdown for humans.

Minimal example:

```python
from acpkit import CompatibilityManifest, SurfaceSupport

manifest = CompatibilityManifest(
    integration_name='workspace-agent',
    adapter='pydantic-acp',
    surfaces={
        'session.load': SurfaceSupport(
            status='implemented',
            owner='adapter',
            mapping='FileSessionStore + load_session',
        ),
    },
)
```

Read next:

- https://vcoderun.github.io/acpkit/compatibility-matrix-template/

## Reference Files In This Skill

These skill-local references are only routing aids back into the docs and source tree:

- `SKILL.md`
- `resources/intro.md`
- `examples/README.md`
- `scripts/list_examples.py`
- `scripts/list_public_exports.py`

Use them to find the right docs page or package surface quickly, not as independent source-of-truth
specs.
