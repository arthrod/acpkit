# pydantic-acp 0.9.7 Harness Changelog

This changelog covers the harness-specific changes for `pydantic-acp` 0.9.7.

## Added

- Added `HarnessFileSystemBridge` for exposing `pydantic-ai-harness` filesystem tools through ACP.
- Added `HarnessShellBridge` for attaching bounded harness shell execution to Pydantic ACP agents.
- Added `HarnessCodeModeBridge` for runs that intentionally expose harness CodeMode execution.
- Added `HarnessFileSystemProjectionMap`, `HarnessShellProjectionMap`, and
  `HarnessCodeModeProjectionMap` so harness tool calls render as structured ACP transcript updates.
- Added a maintained harness example at
  [mock_harness_agent.py](https://github.com/vcoderun/acpkit/blob/main/examples/pydantic/mock_harness_agent.py).
- Added dedicated harness capability documentation at
  [Harness-backed Capabilities](https://github.com/vcoderun/acpkit/blob/main/docs/pydantic-acp/harness-capabilities.md).

## Changed

- The maintained harness example now uses real `pydantic-ai-harness` filesystem and shell
  capabilities instead of mock tool behavior.
- The native ACP target exposes filesystem and shell by default:

  ```bash
  uv run acpkit run examples.pydantic.mock_harness_agent:acp_agent
  ```

- CodeMode is opt-in and only enabled by the script entrypoint:

  ```bash
  uv run python -m examples.pydantic.mock_harness_agent --codemode
  ```

- The harness example supports provider override through `ACP_HARNESS_MODEL`.
- The harness example supports Codex-backed construction through `ACP_HARNESS_CODEX_MODEL`.
- The Codex-backed path passes explicit `instructions=` into the Codex model factory and still uses
  `Agent(instructions=...)` for agent-owned behavior.

## Projection Improvements

- `read_file` now renders as a read-specific card with a numbered text preview.
- `read_file` no longer appears as a fake diff.
- File write and edit tools keep write-oriented projection.
- Shell tools render command status and bounded output previews.
- CodeMode tools render execution-oriented transcript cards instead of raw payloads.

## Documentation

- Updated the Pydantic ACP overview with harness bridge and projection guidance.
- Updated the package README with installable usage examples.
- Updated the examples README with default versus `--codemode` behavior.
- Added the harness guide to the MkDocs navigation.

## Validation

Validated with:

- `make check`
- `uv run pytest tests/pydantic/test_examples.py tests/pydantic/test_projection.py -q`
- `uv run pytest --cov=. --cov-branch`

Latest recorded coverage from the full coverage run:

- Line coverage: `100% (22503 / 22503)`
- Branch coverage: `100% (3760 / 3760)`
