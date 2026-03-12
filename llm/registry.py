from __future__ import annotations

from .anthropic_client import AnthropicClient
from .gemini_client import GeminiClient
from .openai_client import OpenAIClient
from .providers import ProviderClient


def available_clients() -> list[ProviderClient]:
    # Instantiate clients (they read keys from Streamlit secrets)
    return [GeminiClient(), OpenAIClient(), AnthropicClient()]


def configured_clients() -> list[ProviderClient]:
    return [c for c in available_clients() if c.is_configured()]
