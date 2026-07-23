from __future__ import annotations as _annotations

from dataclasses import dataclass

__all__ = ("AdapterPromptCapabilities",)


@dataclass(frozen=True, slots=True, kw_only=True)
class AdapterPromptCapabilities:
    audio: bool = True
    image: bool = True
    embedded_context: bool = True
