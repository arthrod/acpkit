# ACP Kit 1.0.0

`1.0.0` is the first stable release of the synchronized ACP Kit workspace.

## Install

Install every maintained integration:

```bash
uv add "acpkit[all]>=1.0.0,<2.0.0"
```

```bash
pip install "acpkit[all]>=1.0.0,<2.0.0"
```

Install only one adapter family when preferred:

```bash
uv add "acpkit[pydantic]>=1.0.0,<2.0.0"
uv add "acpkit[langchain]>=1.0.0,<2.0.0"
```

The root extras require matching v1-generation adapters, helpers, and
transports.

## Supported Matrix

The release gate covers:

- Python 3.11 through 3.13
- Pydantic AI 2.0 through 2.4
- LangChain 1.3.11
- LangGraph 1.2.7
- DeepAgents 0.6.12
- ACP Python SDK 0.9.0

## Stable Surface

The v1 compatibility contract covers top-level package exports, documented CLI
behavior, configuration fields, provider and bridge protocols, projection
contracts, and documented persisted session behavior.

Private modules and underscore-prefixed implementation details are not public
API.

See the [versioning policy](https://vcoderun.github.io/acpkit/versioning/), the
[production deployment guide](https://vcoderun.github.io/acpkit/production-deployment/),
and the repository
[changelog](https://github.com/vcoderun/acpkit/blob/main/CHANGELOG.md).
