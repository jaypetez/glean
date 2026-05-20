from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from glean.llm.base import LLMProvider
from glean.llm.embedding import EmbeddingProvider

_REGISTRY: dict[str, Callable[..., LLMProvider]] = {}
# AGENT: Embedding providers — registered with @register_embedding_provider
# Run `make new-plugin LAYER=llm NAME=<name>_embedding` if you add a new one.
_EMBEDDING_PROVIDERS: dict[str, type[EmbeddingProvider]] = {}


_ProviderFactory = Callable[..., LLMProvider]
_EmbeddingProviderDecorator = TypeVar("_EmbeddingProviderDecorator", bound=type[object])


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


def register_embedding_provider(
    name: str,
) -> Callable[[_EmbeddingProviderDecorator], _EmbeddingProviderDecorator]:
    def decorator(cls: _EmbeddingProviderDecorator) -> _EmbeddingProviderDecorator:
        _EMBEDDING_PROVIDERS[name] = cast(type[EmbeddingProvider], cls)
        return cls

    return decorator


def build_embedding_provider(spec: dict[str, Any]) -> EmbeddingProvider:
    name = spec.get("provider")
    if not name:
        raise ValueError(f"embedding spec missing 'provider': {spec!r}")
    factory = _EMBEDDING_PROVIDERS.get(name)
    if factory is None:
        raise ValueError(
            f"unknown embedding provider: {name!r}. registered: {sorted(_EMBEDDING_PROVIDERS)}"
        )
    kwargs = {k: v for k, v in spec.items() if k != "provider"}
    return cast(Callable[..., EmbeddingProvider], factory)(**kwargs)


def _import_builtins() -> None:
    # AGENT: To add a new LLM provider, run `make new-plugin LAYER=llm NAME=<name>`
    # which appends the import below automatically. See docs/plugins/llm.md.
    from glean.llm import (  # noqa: F401
        anthropic_provider,
        ollama_embedding,
        ollama_provider,
        openai_embedding,
        openai_provider,
    )


_import_builtins()
