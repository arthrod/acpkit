from __future__ import annotations as _annotations

from dataclasses import dataclass

__all__ = ("AdapterModel",)


@dataclass(slots=True, frozen=True, kw_only=True)
class AdapterModel:
    """One ACP-visible model option for a LangChain session."""

    model_id: str
    name: str
    description: str | None = None
