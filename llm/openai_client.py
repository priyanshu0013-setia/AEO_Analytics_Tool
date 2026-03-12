from __future__ import annotations

import time
from typing import Any

import streamlit as st

from .types import LLMRequest, LLMResult


class OpenAIClient:
    provider = "openai"

    def __init__(self) -> None:
        self._api_key = st.secrets.get("OPENAI_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def default_model(self) -> str:
        return "gpt-4o-mini"

    def generate(self, request: LLMRequest, *, model: str | None = None) -> LLMResult:
        if not self.is_configured():
            return LLMResult(
                provider=self.provider,
                model_id=model or self.default_model(),
                model_version=None,
                status="error",
                text=None,
                raw=None,
                error_message="OPENAI_API_KEY not configured in Streamlit secrets.",
                latency_ms=None,
            )

        try:
            from openai import OpenAI  # type: ignore

            t0 = time.time()
            client = OpenAI(api_key=self._api_key)
            model_id = model or self.default_model()

            resp = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": request.prompt}],
                temperature=request.temperature,
                max_tokens=request.max_output_tokens,
            )
            latency_ms = int((time.time() - t0) * 1000)

            text = None
            if resp.choices and resp.choices[0].message:
                text = resp.choices[0].message.content

            raw: dict[str, Any] = resp.model_dump()  # type: ignore

            return LLMResult(
                provider=self.provider,
                model_id=model_id,
                model_version=raw.get("model") if isinstance(raw, dict) else None,
                status="ok",
                text=text,
                raw=raw,
                error_message=None,
                latency_ms=latency_ms,
            )
        except Exception as e:  # noqa: BLE001
            return LLMResult(
                provider=self.provider,
                model_id=model or self.default_model(),
                model_version=None,
                status="error",
                text=None,
                raw=None,
                error_message=str(e),
                latency_ms=None,
            )
