from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from glean.security.ssrf import SSRFValidationError, validate_provider_base_url


class LLMConfig(BaseModel):
    # Plugins may register additional providers, so we accept any string here
    # and defer validation to the registry at construction time.
    model_config = ConfigDict(extra="forbid")

    provider: str = "ollama"
    model: str = "qwen2.5:7b"
    base_url: str | None = None
    api_key: str | None = None
    timeout_s: float = 60.0

    @model_validator(mode="after")
    def _validate_base_url(self) -> Self:
        if self.base_url is None:
            return self
        try:
            validate_provider_base_url(self.provider, self.base_url)
        except SSRFValidationError as exc:
            raise ValueError(f"base_url: {exc}") from exc
        return self
