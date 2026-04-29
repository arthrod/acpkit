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
- approval-gated file writes

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

If you want the module-level compiled graph directly, the example exports `graph` when `deepagents` is installed:

```bash
acpkit run examples.langchain.deepagents_graph:graph
```

If `deepagents` is not installed, use the module as a recipe and keep `main()` or `graph_from_session(...)` as the entrypoint instead.
