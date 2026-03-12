from __future__ import annotations

import time
from typing import Any

import streamlit as st

from .types import LLMRequest, LLMResult


class GeminiClient:
    provider = "gemini"

    def __init__(self) -> None:
        self._api_key = st.secrets.get("GEMINI_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def default_model(self) -> str:
        # Stable-ish default for prototype; can be adjusted later.
        return "gemini-1.5-flash"

    def generate(self, request: LLMRequest, *, model: str | None = None) -> LLMResult:
        if not self.is_configured():
            return LLMResult(
                provider=self.provider,
                model_id=model or self.default_model(),
                model_version=None,
                status="error",
                text=None,
                raw=None,
                error_message="GEMINI_API_KEY not configured in Streamlit secrets.",
                latency_ms=None,
            )

        try:
            from google import genai  # type: ignore

            t0 = time.time()
            client = genai.Client(api_key=self._api_key)
            model_id = model or self.default_model()

            resp = client.models.generate_content(
                model=model_id,
                contents=request.prompt,
                config={
                    "temperature": request.temperature,
                    "max_output_tokens": request.max_output_tokens,
                },
            )

            latency_ms = int((time.time() - t0) * 1000)

            text = getattr(resp, "text", None)

            raw: dict[str, Any] = {}
            try:
                raw = resp.model_dump()  # pydantic-ish
            except Exception:  # noqa: BLE001
                try:
                    raw = resp.to_dict()  # fallback
                except Exception:  # noqa: BLE001
                    raw = {"repr": repr(resp)}

            model_version = None
            # Common place in responses; keep best-effort.
            if isinstance(raw, dict):
                model_version = raw.get("modelVersion") or raw.get("model_version")

            # Safety blocks: if no text and feedback indicates blocking
            status = "ok" if text else "ok"
            if not text:
                feedback = raw.get("promptFeedback") if isinstance(raw, dict) else None
                if feedback and feedback.get("blockReason"):
                    status = "blocked"

            return LLMResult(
                provider=self.provider,
                model_id=model_id,
                model_version=model_version,
                status=status,
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
