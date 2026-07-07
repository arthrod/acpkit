from __future__ import annotations as _annotations

from .base import BufferedCapabilityBridge, CapabilityBridge
from .capability_support import (
    AnthropicCompactionBridge,
    HarnessCodeModeBridge,
    HarnessFileSystemBridge,
    HarnessShellBridge,
    ImageGenerationBridge,
    IncludeToolReturnSchemasBridge,
    McpCapabilityBridge,
    OpenAICompactionBridge,
    PrefixToolsBridge,
    SetToolMetadataBridge,
    ThreadExecutorBridge,
    ToolsetBridge,
    WebFetchBridge,
    WebSearchBridge,
)
from .external_hooks import EventEmissionMode, ExternalHookEventBridge
from .history_processor import (
    HistoryProcessorBridge,
    HistoryProcessorCallable,
    HistoryProcessorContextual,
    HistoryProcessorPlain,
    HistoryProcessorWithContextAsync,
    HistoryProcessorWithContextSync,
)
from .hooks import HookBridge
from .mcp import McpBridge, McpServerDefinition, McpToolDefinition
from .prepare_tools import (
    PlanGenerationType,
    PrepareOutputToolsBridge,
    PrepareOutputToolsMode,
    PrepareToolsBridge,
    PrepareToolsMode,
)
from .thinking import ThinkingBridge

__all__ = (
    "AnthropicCompactionBridge",
    "BufferedCapabilityBridge",
    "CapabilityBridge",
    "EventEmissionMode",
    "ExternalHookEventBridge",
    "HarnessCodeModeBridge",
    "HarnessFileSystemBridge",
    "HarnessShellBridge",
    "HistoryProcessorBridge",
    "HistoryProcessorCallable",
    "HistoryProcessorContextual",
    "HistoryProcessorPlain",
    "HistoryProcessorWithContextAsync",
    "HistoryProcessorWithContextSync",
    "HookBridge",
    "ImageGenerationBridge",
    "IncludeToolReturnSchemasBridge",
    "McpBridge",
    "McpCapabilityBridge",
    "McpServerDefinition",
    "McpToolDefinition",
    "OpenAICompactionBridge",
    "PlanGenerationType",
    "PrefixToolsBridge",
    "PrepareOutputToolsBridge",
    "PrepareOutputToolsMode",
    "PrepareToolsBridge",
    "PrepareToolsMode",
    "SetToolMetadataBridge",
    "ThinkingBridge",
    "ThreadExecutorBridge",
    "ToolsetBridge",
    "WebFetchBridge",
    "WebSearchBridge",
)
