# pydantic-acp Examples

All maintained examples live under `examples/pydantic/`.

The repo now keeps three opinionated examples instead of a ladder of tiny one-off demos.

- `finance_agent.py`
  session-aware finance workspace with `ask/plan/trade` modes, structured ACP plans, approval-gated note writes, and file diff projection
- `travel_agent.py`
  travel-planning runtime with `Hooks` projection, approval-gated trip file writes, and prompt-model override behavior for image and audio prompts
- `mock_harness_agent.py`
  real model-backed harness agent using pydantic-ai-harness filesystem and shell capabilities, with optional code-mode support

## Runnable Demos

Finance agent:

```bash
uv run python -m examples.pydantic.finance_agent
```

The default model is `TestModel`, so the example runs without credentials. Set
`ACP_FINANCE_MODEL` when you want a live model.

Travel agent:

```bash
uv run python -m examples.pydantic.travel_agent
```

The travel example defaults to a deterministic local router. Set `MODEL_NAME` when you want a live
base model and `ACP_TRAVEL_MEDIA_MODEL` when you want a dedicated media fallback.

Harness agent:

Install `pydantic-ai-harness` before running this example against a real ACP host. Install
`pydantic-ai-harness[code-mode]` if you plan to pass `--codemode`. By default it uses the OpenRouter
model string configured in the example. Set `ACP_HARNESS_MODEL` to any pydantic-ai model name when
you want a different provider-backed model string, or set `ACP_HARNESS_CODEX_MODEL` to build a
Codex-backed model through `codex-auth-helper`. Provider-backed model strings still require that
provider's normal credentials, such as `OPENAI_API_KEY` for `openai:...`.

For root-package dispatch, use the native ACP target:

```bash
uv run acpkit run examples.pydantic.mock_harness_agent:acp_agent
```

The native target defaults to filesystem and shell bridges only. To enable the CodeMode bridge for a
script-launched run, pass `--codemode`:

```bash
uv run python -m examples.pydantic.mock_harness_agent --codemode
```

Detailed harness bridge and projection guide:

- [Harness-backed Capabilities](https://github.com/vcoderun/acpkit/blob/main/docs/pydantic-acp/harness-capabilities.md)

## Projection Highlights

`finance_agent.py` demonstrates:

- `FileSystemProjectionMap` read previews and write diffs
- structured native plan generation in ACP plan mode
- remembered approvals for mutating finance note writes

`travel_agent.py` demonstrates:

- `HookProjectionMap` with custom labels and hidden events
- file read/write diffs inside a generated trip workspace
- prompt-model override behavior for image and audio prompts

`mock_harness_agent.py` demonstrates:

- `HarnessFileSystemBridge` for pydantic-ai-harness file tools
- `HarnessShellBridge` for bounded shell command tools
- opt-in `HarnessCodeModeBridge` for code-mode execution tools when `--codemode` is passed
- real model construction with `ACP_HARNESS_MODEL` and optional Codex-backed construction through `ACP_HARNESS_CODEX_MODEL`
