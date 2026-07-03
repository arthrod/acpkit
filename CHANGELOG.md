# Changelog

ACP Kit uses synchronized versions for `acpkit`, `pydantic-acp`, `langchain-acp`,
`codex-auth-helper`, and `acpremote`.

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

[1.0.0]: https://github.com/vcoderun/acpkit/releases/tag/v1.0.0
