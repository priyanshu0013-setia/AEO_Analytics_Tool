from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    temperature: float
    max_output_tokens: int


@dataclass(frozen=True)
class LLMResult:
    provider: str
    model_id: str
    model_version: str | None
    status: str  # ok | blocked | error
    text: str | None
    raw: dict[str, Any] | None
    error_message: str | None
    latency_ms: int | None
