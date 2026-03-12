from __future__ import annotations

from typing import Protocol

from .types import LLMRequest, LLMResult


class ProviderClient(Protocol):
    provider: str

    def is_configured(self) -> bool:
        ...

    def default_model(self) -> str:
        ...

    def generate(self, request: LLMRequest, *, model: str | None = None) -> LLMResult:
        ...
