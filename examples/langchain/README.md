# langchain-acp Examples

All maintained LangChain examples live under `examples/langchain/`.

They are tested against LangChain 1.3.11, LangGraph 1.2.7, and DeepAgents 0.6.12. The package
declares those versions as minimums, and the repository lockfile records the exact tested stack.

- `codex_graph.py`
  Smallest Codex-backed LangChain example. It uses `codex_auth_helper.create_codex_chat_openai(...)`
  directly and passes `instructions=` to the Responses request so you can see the exact LangChain
  integration surface without extra wrappers.
- `workspace_graph.py`
  Codex-backed workspace graph with real file read/write tools, session-aware
  `graph_from_session(...)`, and file projection for `langchain-acp`. The demo workspace is created
  under the current working directory as `.workspace-graph/` so the graph interacts with the
  workspace you launched it from instead of writing next to the example source file.
- `deepagents_graph.py`
  Codex-backed DeepAgents compatibility example with real workspace tools,
  `DeepAgentsCompatibilityBridge`, and `DeepAgentsProjectionMap`. Its workspace is created under the
  current working directory as `.deepagents-graph/`. It calls the real
  `deepagents.create_deep_agent(...)` constructor; no mock DeepAgents module is used.

All three examples use the local Codex auth flow through `codex-auth-helper`. By default they use
`CODEX_MODEL=gpt-5.4`; set `CODEX_MODEL` before running them when you want a different Codex model.

The LangChain-specific Codex hook is the `instructions=` argument:

```python
from codex_auth_helper import create_codex_chat_openai

model = create_codex_chat_openai(
    "gpt-5.4",
    instructions=(
        "You are a careful workspace assistant. "
        "Read files before editing them and explain concrete observations."
    ),
)
```

That string is passed through to the OpenAI Responses request that backs `ChatOpenAI`. Use it when
you want repo- or task-specific system behavior without introducing another wrapper layer.
`create_codex_chat_openai(...)` requires `instructions`; there is no implicit default.

## Model And Mode Controls

The maintained examples also expose ACP session controls for model and mode selection.

- `available_models` advertises the model ids the client can switch to.
- `available_modes` advertises the runtime modes the client can switch to.
- `default_model_id` and `default_mode_id` seed new sessions.
- `graph_from_session(...)` reads `session.session_model_id` and `session.session_mode_id` and
  rebuilds the graph with the selected Codex model and mode-specific instructions.

In practice that means a client can switch model or mode through ACP session controls and the next
prompt turn will run against a newly built LangChain graph that reflects those choices.

## Runnable Demo

```bash
uv run python -m examples.langchain.workspace_graph
uv run python -m examples.langchain.deepagents_graph
uv run python -m examples.langchain.codex_graph
```

Or expose the module-level graph directly through the root CLI:

```bash
acpkit run examples.langchain.workspace_graph:graph
acpkit run examples.langchain.deepagents_graph:graph
```

If you want the session-aware graph factory path instead of the module-level `graph`, run the module
directly with `python -m ...`. That path creates the demo workspace under your launch directory and
avoids the fixed import-time graph root.

The workspace graph example also works as a remote ACP host:

```bash
acpkit serve examples.langchain.workspace_graph:graph --host 0.0.0.0 --port 8080
acpkit run --addr ws://127.0.0.1:8080/acp/ws
```
