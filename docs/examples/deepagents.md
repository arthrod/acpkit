# DeepAgents Compatibility Example

Source:

- [`examples/langchain/deepagents_graph.py`](https://github.com/vcoderun/acpkit/blob/main/examples/langchain/deepagents_graph.py)

This example is the maintained DeepAgents-facing showcase for `langchain-acp`.

It demonstrates:

- a Codex-backed `ChatOpenAI` model created through `codex-auth-helper`
- wiring a DeepAgents graph through `langchain-acp`
- `DeepAgentsCompatibilityBridge`
- `DeepAgentsProjectionMap`
- tool-based plan compatibility through `write_todos`
- approval handling around a deterministic mock write tool

Install the optional dependency first:

```bash
uv add "langchain-acp[deepagents]"
```

```bash
pip install "langchain-acp[deepagents]"
```

Run it:

```bash
uv run python -m examples.langchain.deepagents_graph
```

Required local state:

```text
~/.codex/auth.json
```

Use the configured native ACP target when launching through the root CLI. This
preserves the example's session store, modes, native plans, compatibility
bridge, and projections:

```bash
acpkit run examples.langchain.deepagents_graph:acp_agent
```

`deepagents` must be installed before this target handles a session.
