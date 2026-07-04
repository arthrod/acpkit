# pydantic-acp Examples

These maintained examples are executable ACP agents, not isolated snippets.
They use bounded workspaces, explicit projections, and persistent local session
state.

## Setup

From the repository root:

```bash
uv sync --extra dev --extra pydantic
```

For the harness example:

```bash
uv sync --extra dev --extra pydantic --extra codex
```

## Finance Agent

The finance example demonstrates mode-aware tool preparation, native structured
plans, approval-gated writes, persisted plan snapshots, and file projections.

Run offline with the deterministic Pydantic AI `TestModel`:

```bash
uv run python -m examples.pydantic.finance_agent
```

Use a real Pydantic AI model:

```bash
ACP_FINANCE_MODEL="openai:gpt-5.4-mini" \
uv run python -m examples.pydantic.finance_agent
```

The agent reads and writes only under `.finance-agent/` in the server working
directory. The `trade` mode exposes the write tool, and every write still
requires ACP approval.

## Travel Agent

The travel example projects Pydantic AI hooks, handles image/audio-aware model
selection, and requires approval for trip-file writes:

```bash
ACP_TRAVEL_MODEL="openai:gpt-5.4-mini" \
ACP_TRAVEL_MEDIA_MODEL="openai:gpt-5.4" \
uv run python -m examples.pydantic.travel_agent
```

Without `ACP_TRAVEL_MODEL`, the example uses `TestModel` for an offline startup
check. Files stay inside `examples/pydantic/.travel-agent/`.

## Harness Agent

The harness example uses real `pydantic-ai-harness` filesystem and shell
capabilities. Code mode is opt-in:

```bash
ACP_HARNESS_MODEL="openrouter:google/gemini-3-flash-preview" \
uv run python -m examples.pydantic.mock_harness_agent
```

```bash
ACP_HARNESS_CODEX_MODEL="gpt-5.4" \
uv run python -m examples.pydantic.mock_harness_agent --codemode
```

The shell bridge blocks destructive and network-oriented commands, disables
interactive processes, bounds runtime and output, and confines work to
`examples/pydantic/.harness-agent/`. `--codemode` is the only path that enables
the code-mode bridge.

## Session Storage

All examples use `FileSessionStore` under `.acp-sessions/`. Override the parent
directory when needed:

```bash
ACP_EXAMPLE_SESSION_DIR="/var/lib/acpkit/sessions" \
uv run python -m examples.pydantic.finance_agent
```

This file store is suitable for one process. Replace it with an
application-owned store before running multiple replicas.

## Production Boundaries

- Keep model credentials in environment variables or a secret manager.
- Treat approval callbacks as authorization boundaries, not UI decoration.
- Place remote ACP hosting behind TLS and authentication.
- Narrow filesystem and shell policies further for the deployed workload.

Detailed walkthroughs are available in the
[examples documentation](https://vcoderun.github.io/acpkit/examples/).
