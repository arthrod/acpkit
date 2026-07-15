# ACP Kit 1.4.0

`1.4.0` upgrades the synchronized ACP Kit workspace to
`agent-client-protocol==0.11.0` while preserving the adapter behavior that was
previously available through the supported SDK surface.

## Highlights

- `pydantic-acp`, `langchain-acp`, and `acpremote` implement the ACP 0.11
  public protocol contracts end to end.
- Model selection is a selectable `"model"` session config option. ACP Kit no
  longer sends the removed `session/set_model` wire request.
- Plan updates remain truthful for every client: complete updates are the
  default, while content/removal deltas require an advertised `plan`
  capability.
- Form and URL elicitation are exposed through typed
  `AcpSessionContext.create_elicitation(...)` and delegated to real host
  clients when the Pydantic provider bridge is used.
- `additional_directories` and `AcpMcpServer` descriptors survive session
  lifecycle operations. An ACP descriptor is preserved and displayed, but not
  connected as a tool transport because the public ACP SDK does not provide an
  ACP-MCP router.

## Migration

Use config-option selection when an ACP client or adapter needs to change the
model:

```python
from pydantic_acp import AdapterConfig, AdapterModel

config = AdapterConfig(
    available_models=[AdapterModel(model_id="fast", name="Fast")],
    default_model_id="fast",
)
```

When a client supports plan deltas, enable them explicitly and retain the
complete-update fallback for older clients:

```python
from langchain_acp import AdapterConfig

config = AdapterConfig(
    plan_id="research-plan",
    plan_update_mode="content",
)
```

Applications that need client input should pass a concrete ACP 0.11
elicitation mode to the session context. The call rejects unsupported client
capabilities rather than silently inventing a UI flow.

```python
from acp.schema import ElicitationFormSessionMode, ElicitationSchema
from pydantic_acp import AcpSessionContext


async def confirm(session: AcpSessionContext) -> None:
    await session.create_elicitation(
        "Confirm the deployment.",
        ElicitationFormSessionMode(
            session_id=session.session_id,
            requested_schema=ElicitationSchema(),
        ),
    )
```

## Compatibility

- Python 3.11 through 3.13
- Pydantic AI 2.0.0 through 2.9.1
- LangChain 1.3.11 or newer
- LangGraph 1.2.7 or newer
- DeepAgents 0.6.12 or newer through the optional extra
- ACP Python SDK 0.11.0

The release validation suite covers all repository tests with 100% line
coverage, strict linting and typing, documentation build validation, framework
compatibility matrices, and release metadata checks.
