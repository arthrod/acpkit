# Codex-Backed LangChain Graph

Source:

- [`examples/langchain/codex_graph.py`](https://github.com/vcoderun/acpkit/blob/main/examples/langchain/codex_graph.py)

This example demonstrates the helper-to-adapter path for LangChain:

- `codex-auth-helper` builds a Codex-backed `ChatOpenAI`
- `langchain.agents.create_agent(...)` owns the graph
- `langchain-acp` exposes that graph through ACP

The model factory call must pass `instructions=` explicitly:

```python
model = create_codex_chat_openai(
    "gpt-5.4",
    instructions="You are a helpful coding assistant.",
)
```

Run it:

```bash
uv run python -m examples.langchain.codex_graph
```

Required local state:

```text
~/.codex/auth.json
```

Override the default model when needed:

```bash
CODEX_MODEL=gpt-5.4-mini uv run python -m examples.langchain.codex_graph
```

If you have not logged in yet:

```bash
codex login
```

Install the helper with LangChain support:

```bash
uv add "codex-auth-helper[langchain]"
```

```bash
pip install "codex-auth-helper[langchain]"
```
