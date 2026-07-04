# Production Deployment

ACP Kit adapts an existing runtime to ACP. Production safety still depends on
how the application owns sessions, credentials, tools, approvals, and
transport.

## Preserve The Configured Adapter

When custom configuration matters, export a native ACP target:

```python
from pydantic_acp import AdapterConfig, FileSessionStore, create_acp_agent

config = AdapterConfig(session_store=FileSessionStore(".acp-sessions"))
acp_agent = create_acp_agent(agent=agent, config=config)
```

Then target `module:acp_agent` from `acpkit run` or `acpkit serve`. Targeting a
raw framework `agent` or `graph` asks the root package to materialize a default
adapter and therefore cannot preserve module-local configuration it was not
given.

## Session Storage

`MemorySessionStore` is process-local and ephemeral. `FileSessionStore` is
durable for one process but is not a distributed coordination layer.

For multiple replicas, implement the adapter's `SessionStore` protocol with:

- atomic reads and writes
- optimistic concurrency or equivalent conflict handling
- tenant and authorization boundaries
- retention and deletion policies
- encryption appropriate for transcript contents

Do not share one file-store directory between unrelated users or concurrent
replicas.

## Models And Credentials

- Load provider credentials from environment variables or a secret manager.
- Keep `~/.codex/auth.json` machine-local, private, and out of images and logs.
- Pass explicit Codex `instructions=` through `codex-auth-helper`.
- Treat ACP model ids as allowlisted application configuration.
- Validate new provider and framework versions before widening package bounds.

## Tools, Capabilities, And Approvals

- Expose only tools the active mode can honor.
- Keep approval-required mutations approval-required after tool preparation.
- Scope filesystem roots and reject traversal before access.
- Deny secrets, VCS metadata, private keys, and unrelated host paths.
- Bound shell runtime and output, disable interactive commands, and avoid
  unrestricted network tools.
- Enable harness code mode only when the deployment explicitly requires it.
- Keep projection maps aligned with real tool names and schemas so ACP clients
  do not display misleading activity.

## Remote Transport

- Bind to loopback unless a trusted edge owns public exposure.
- Terminate public connections with TLS.
- Require bearer authentication or equivalent edge authentication.
- Configure WebSocket, metadata, stream, command, and output limits.
- Ensure reverse-proxy idle timeouts permit expected agent turns.
- Close remote connections and child commands during graceful shutdown.

`acpremote` transports ACP; it does not add framework authorization or adapt a
raw Pydantic AI or LangChain runtime by itself.

## Release And Upgrade Gate

Deploy published wheels, not an editable checkout:

```bash
uv add "acpkit[all]>=1.0.0,<2.0.0"
```

Before upgrading, run application-level tests for session reload, cancellation,
approvals, plans, tool projection, and remote reconnects against the declared
compatibility matrix.

Repository maintainers run:

```bash
make release RELEASE_TAG=v1.0.0
```

This validates source, documentation, compatibility, artifacts, and clean
installation before publishing.

## Deployment Checklist

- configured `acp_agent` target selected
- persistent store ownership defined
- credentials excluded from logs and artifacts
- models and tools allowlisted
- mutations approval-gated
- filesystem and shell scopes bounded
- TLS and authentication enabled for remote traffic
- graceful shutdown tested
- supported framework matrix verified
- wheel installation smoke-tested
