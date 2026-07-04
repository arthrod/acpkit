# LangChain Workspace Graph

Source:

- [`examples/langchain/workspace_graph.py`](https://github.com/vcoderun/acpkit/blob/main/examples/langchain/workspace_graph.py)

This example is the maintained plain-LangChain showcase.

It demonstrates:

- a Codex-backed `ChatOpenAI` model created through `codex-auth-helper`
- a module-level `graph`, `config`, configured `acp_agent`, and `main()`
- a session-aware `graph_from_session(...)` factory
- `acpkit run examples.langchain.workspace_graph:acp_agent`
- filesystem read and write projection through `FileSystemProjectionMap`
- a small seeded workspace for deterministic ACP rendering
- a clean remote-host path through `acpkit serve ...` and `acpkit run --addr ...`

Run it:

```bash
uv run python -m examples.langchain.workspace_graph
```

Required local state:

```text
~/.codex/auth.json
```

Override the default model when needed:

```bash
CODEX_MODEL=gpt-5.4-mini uv run python -m examples.langchain.workspace_graph
```

Or expose the configured native ACP target through the root CLI. This preserves
the graph factory, persistent sessions, model and mode controls, and projection
map:

```bash
acpkit run examples.langchain.workspace_graph:acp_agent
```

Or host it remotely through ACP Remote:

```bash
acpkit serve examples.langchain.workspace_graph:acp_agent --host 0.0.0.0 --port 8081
acpkit run --addr ws://127.0.0.1:8081/acp/ws
```
