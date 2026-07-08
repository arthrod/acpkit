from __future__ import annotations as _annotations

import asyncio
from dataclasses import replace

from acp import run_agent
from acp.interfaces import Agent as AcpAgent

from ..config import DEFAULT_AGENT_NAME, AdapterConfig
from ..event_projection import EventProjectionMap
from ..graph_source import (
    CompiledAgentGraph,
    FactoryGraphSource,
    GraphFactory,
    GraphSource,
    StaticGraphSource,
)
from ..projection import ProjectionMap
from .adapter import LangChainAcpAgent

__all__ = ("create_acp_agent", "run_acp")


def create_acp_agent(
    graph: CompiledAgentGraph | None = None,
    *,
    graph_factory: GraphFactory | None = None,
    graph_source: GraphSource | None = None,
    config: AdapterConfig | None = None,
    event_projection_maps: list[EventProjectionMap] | None = None,
    projection_maps: list[ProjectionMap] | None = None,
) -> AcpAgent:
    resolved_source = _resolve_graph_source(
        graph=graph,
        graph_factory=graph_factory,
        graph_source=graph_source,
    )
    resolved_config = _resolve_config(
        config=config,
        event_projection_maps=event_projection_maps,
        graph_name=getattr(graph, "name", None),
        projection_maps=projection_maps,
    )
    return LangChainAcpAgent(resolved_source, config=resolved_config)


def run_acp(
    graph: CompiledAgentGraph | None = None,
    *,
    graph_factory: GraphFactory | None = None,
    graph_source: GraphSource | None = None,
    config: AdapterConfig | None = None,
    event_projection_maps: list[EventProjectionMap] | None = None,
    projection_maps: list[ProjectionMap] | None = None,
) -> None:
    adapter = create_acp_agent(
        graph=graph,
        graph_factory=graph_factory,
        graph_source=graph_source,
        config=config,
        event_projection_maps=event_projection_maps,
        projection_maps=projection_maps,
    )
    asyncio.run(run_agent(adapter))


def _resolve_graph_source(
    *,
    graph: CompiledAgentGraph | None,
    graph_factory: GraphFactory | None,
    graph_source: GraphSource | None,
) -> GraphSource:
    provided_count = sum(provided is not None for provided in (graph, graph_factory, graph_source))
    if provided_count != 1:
        raise ValueError(
            "Exactly one of `graph`, `graph_factory`, or `graph_source` must be provided.",
        )
    if graph is not None:
        return StaticGraphSource(graph)
    if graph_factory is not None:
        return FactoryGraphSource(graph_factory)
    assert graph_source is not None
    return graph_source


def _resolve_config(
    *,
    config: AdapterConfig | None,
    event_projection_maps: list[EventProjectionMap] | None,
    graph_name: str | None,
    projection_maps: list[ProjectionMap] | None,
) -> AdapterConfig:
    resolved_config = config or AdapterConfig()
    if projection_maps is not None or event_projection_maps is not None:
        resolved_config = replace(
            resolved_config,
            event_projection_maps=tuple(
                (
                    event_projection_maps
                    if event_projection_maps is not None
                    else resolved_config.event_projection_maps
                ),
            ),
            projection_maps=tuple(
                (
                    projection_maps
                    if projection_maps is not None
                    else resolved_config.projection_maps
                ),
            ),
        )
    if graph_name is None or resolved_config.agent_name != DEFAULT_AGENT_NAME:
        return resolved_config
    return replace(resolved_config, agent_name=graph_name)
