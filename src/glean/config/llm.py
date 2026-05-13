from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LLMConfig(BaseModel):
    # Plugins may register additional providers, so we accept any string here
    # and defer validation to the registry at construction time.
    model_config = ConfigDict(extra="forbid")

    provider: str = "ollama"
    model: str = "qwen2.5:7b"
    base_url: str | None = None
    api_key: str | None = None
    timeout_s: float = 60.0
