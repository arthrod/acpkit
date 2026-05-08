# Security Guidance

ACP Kit exposes existing agent runtimes. The adapter should stay honest about what the underlying
runtime can enforce, and deployment code should treat host files, credentials, and remote command
execution as privileged surfaces.

## File Session Stores

`FileSessionStore` is a local durable store, not a distributed database or a multi-host
coordination layer.

Use it when an editor, CLI, or local service needs sessions to survive process restarts. Do not
share the same store root between unrelated users or untrusted processes.

File-backed session ids are validated before they become filenames:

- allowed characters are ASCII letters, digits, `_`, and `-`
- the maximum length is 128 characters
- path separators, dots, whitespace, and shell metacharacters are rejected
- malformed JSON files are skipped by load/list flows instead of crashing the adapter

Store roots should live in a directory owned by the service user. If session content can include
sensitive prompts, tool results, or workspace paths, apply normal host-level file permissions and
backup policies.

## Codex Auth State

`codex-auth-helper` reads and refreshes local Codex credentials. Treat its auth state file like a
credential store.

Current writes use a private temp file, `fsync`, atomic replace, and `0600` permissions on POSIX
systems. Operators should still keep the parent directory private and avoid copying auth state into
logs, examples, test fixtures, or container images.

## acpremote

`acpremote` is transport infrastructure. It can expose an existing ACP agent or a stdio command over
WebSocket, so deployment policy matters.

Recommended defaults:

- bind to loopback unless a reverse proxy owns TLS and authentication
- allowlist command-backed servers instead of accepting arbitrary command strings
- keep environment overrides minimal and avoid forwarding secrets that the child process does not need
- configure command termination timeouts for command-backed transports
- monitor long-running remote sessions and close idle connections at the hosting layer

Command-backed transports terminate the child process when the WebSocket flow ends and fall back to
`kill` after the configured timeout. This prevents normal disconnect cleanup from waiting forever on
a process that ignores termination.

## Release Workflow

Project CI and publish workflows should install from `uv.lock` with `uv sync --frozen`. Package
publishing should use PyPI trusted publishing rather than long-lived API tokens whenever the target
PyPI project is configured for it.
