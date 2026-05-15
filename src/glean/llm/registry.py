from __future__ import annotations

from collections.abc import Callable
from typing import Any

from glean.llm.base import LLMProvider

_REGISTRY: dict[str, Callable[..., LLMProvider]] = {}


_ProviderFactory = Callable[..., LLMProvider]


def register_provider(name: str) -> Callable[[_ProviderFactory], _ProviderFactory]:
    def decorator(cls: _ProviderFactory) -> _ProviderFactory:
        _REGISTRY[name] = cls
        return cls

    return decorator


def build_provider(spec: dict[str, Any]) -> LLMProvider:
    name = spec.get("provider")
    if not name:
        raise ValueError(f"llm spec missing 'provider': {spec!r}")
    factory = _REGISTRY.get(name)
    if factory is None:
        raise ValueError(f"unknown llm provider: {name!r}. registered: {sorted(_REGISTRY)}")
    kwargs = {k: v for k, v in spec.items() if k != "provider"}
    return factory(**kwargs)


def _import_builtins() -> None:
    from glean.llm import anthropic_provider, ollama_provider, openai_provider  # noqa: F401


_import_builtins()
