# Changelog

ACP Kit uses synchronized versions for `acpkit`, `pydantic-acp`, `langchain-acp`,
`codex-auth-helper`, and `acpremote`.

## [1.1.1] - 2026-07-09

### Added

- `pydantic-acp` now exposes `create_acp_model(...)`, allowing ACP agents to be
  consumed as Pydantic AI models through the public factory surface.
- `create_acp_model(acp_command=...)` can launch a local stdio ACP command and
  use it as an ACP-backed Pydantic AI model, enabling external ACP agent servers
  to participate in Pydantic AI orchestration.

### Fixed

- ACP-backed model tests now validate command transport and cleanup at the model
  boundary instead of depending on Pydantic AI output retry formatting details.
- Coverage metadata now reflects full line and branch coverage for the ACP
  provider and stdio command bridge paths.

## [1.1.0] - 2026-07-07

### Added

- Pydantic AI v2 ACP client provider bridge (`AcpProvider`, `AcpModel`,
  `AcpHostBridge`) in `pydantic-acp`, enabling ACP agents to be consumed as
  Pydantic AI providers with model profiles, streaming, tool calls, approvals,
  sessions, and projections.
- Public export of the provider bridge surface from `pydantic_acp`.

### Changed

- `pydantic-acp` now requires Pydantic AI v2.
- Dev dependency aligned with Pydantic AI v2.
- `AcpProvider` construction now uses the explicit `acp_agent=` keyword for
  ACP agent instances.
- `provider.model()` now leaves ACP model selection to the wrapped agent's
  session default; pass a concrete model name only when the ACP agent accepts
  that `session/set_model` id.
- Maintained examples now write generated workspaces and local session state
  under `agent_demos/`, with `.gitignore` ignoring that single runtime output
  directory.
- Workspace packages synchronized to `1.1.0`.

### Fixed

- Type-safety and forward-reference handling in the ACP provider bridge.
- Default ACP provider models no longer send `session/set_model("agent")` to
  wrapped ACP agents that reject `"agent"` as an explicit remote model id.
- `AcpProvider.model(history_mode=...)` no longer mutates the provider-wide
  default history mode for other model instances created from the same
  provider.

## [1.0.0] - 2026-07-03

This is the first stable release of the synchronized ACP Kit workspace.

### Added

- Pydantic AI 2.0 through 2.4 compatibility, including agent capabilities,
  harness-backed filesystem, shell, and code-mode bridges, prompt resources,
  approvals, model and mode controls, native plans, hooks, and projections.
- LangChain 1.3, LangGraph 1.2, and DeepAgents 0.6 integration with graph
  factories, session persistence, approvals, native plans, capability bridges,
  structured event projection, and tool projection maps.
- `acpremote` SDK and CLI support for exposing ACP agents or stdio commands over
  WebSocket and mirroring remote ACP endpoints locally.
- `codex-auth-helper` factories for Pydantic AI Responses models and LangChain
  chat models using local Codex authentication.
- Explicit public API inventories through package-level `__all__` declarations.

### Changed

- All workspace packages now report `1.0.0` and use production/stable package
  metadata.
- Root extras require matching v1 adapter, helper, and transport packages.
- Release validation now checks synchronized versions, tag alignment, changelog
  coverage, built artifact metadata, and clean-environment installation.
- Maintained examples and skills now document production boundaries, persistent
  sessions, workspace confinement, authentication, and real-model configuration.

### Fixed

- LangChain cancellation now interrupts blocked graph streams while preserving
  normal external task cancellation.
- LangChain session reload preserves existing MCP servers when the caller omits
  replacement state.
- Streamed LangChain tool calls wait for complete JSON arguments before emitting
  a truthful tool-call start.
- Pydantic session titles are emitted consistently after the first prompt.
- Codex token refresh is serialized across sync and async callers, and Responses
  models always disable server-side storage.
- Remote metadata fetches are bounded and WebSocket, ACP stream, reconnect, and
  failure paths close every owned resource deterministically.
- CLI target import failures retain actionable root-cause details.

[1.1.1]: https://github.com/vcoderun/acpkit/releases/tag/v1.1.1
[1.1.0]: https://github.com/vcoderun/acpkit/releases/tag/v1.1.0
[1.0.0]: https://github.com/vcoderun/acpkit/releases/tag/v1.0.0
