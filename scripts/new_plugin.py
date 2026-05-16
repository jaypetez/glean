from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
REPO_ROOT = Path(__file__).resolve().parents[1]


class PluginScaffoldError(RuntimeError):
    """Raised when the scaffold request cannot be fulfilled safely."""


@dataclass(frozen=True, slots=True)
class LayerDefinition:
    layer: str
    package: str
    class_suffix: str
    registry_path: str
    render_module: Callable[[str, str], str]
    render_test: Callable[[str, str], str]
    render_feed_snippet: Callable[[str], str]


@dataclass(frozen=True, slots=True)
class ScaffoldResult:
    plugin_path: Path
    test_path: Path
    registry_path: Path
    feeds_path: Path


LAYER_DEFINITIONS: dict[str, LayerDefinition] = {}


def _camel_case(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _source_module(name: str, class_name: str) -> str:
    return dedent(
        f'''
        from __future__ import annotations

        from typing import Any, ClassVar

        from glean.security.ssrf import validate_url
        from glean.sources.base import FetchContext, Item
        from glean.sources.registry import register_source


        @register_source("{name}")
        class {class_name}:
            """TODO: describe the {name} source.

            Example:
                >>> source = {class_name}(url="https://example.com/feed")
                >>> source.type
                '{name}'
            """

            type: ClassVar[str] = "{name}"

            def __init__(self, url: str, *, name: str | None = None) -> None:
                self.url = validate_url(url)
                self.name = name or "{name}"

            async def fetch(self, ctx: FetchContext) -> list[Item]:
                response = await ctx.http.get(self.url)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    return []
                raw_items = payload.get("items")
                if not isinstance(raw_items, list):
                    return []
                source_name = self._source_name(payload)
                items: list[Item] = []
                for raw_item in raw_items:
                    if not isinstance(raw_item, dict):
                        continue
                    url = str(raw_item.get("url", "")).strip()
                    title = str(raw_item.get("title", "")).strip()
                    if not url or not title:
                        continue
                    items.append(
                        Item(
                            canonical_url=url,
                            title=title,
                            body=str(raw_item.get("body", "")).strip(),
                            source_type=self.type,
                            source_name=source_name,
                            raw=raw_item,
                        )
                    )
                return items

            def _source_name(self, payload: dict[str, Any]) -> str:
                """TODO: customize how the display name is derived from the payload."""
                del payload
                pass
                return self.name
        '''
    ).lstrip()


def _source_test(name: str, class_name: str) -> str:
    return dedent(
        f"""
        from __future__ import annotations

        import httpx
        import pytest
        import respx

        from glean.sources.{name} import {class_name}

        pytestmark = pytest.mark.asyncio


        @respx.mock
        async def test_{name}_source_fetches_json_items(fetch_context) -> None:
            route = respx.get("https://example.com/feed").mock(
                return_value=httpx.Response(
                    200,
                    json={{
                        "items": [
                            {{
                                "url": "https://example.com/1",
                                "title": "First item",
                                "body": "Hello from the scaffold.",
                            }}
                        ]
                    }},
                )
            )
            source = {class_name}(url="https://example.com/feed", name="Scaffold")

            items = await source.fetch(fetch_context)

            assert len(items) == 1
            assert items[0].canonical_url == "https://example.com/1"
            assert items[0].title == "First item"
            assert items[0].body == "Hello from the scaffold."
            assert items[0].source_name == "Scaffold"
            assert route.called
        """
    ).lstrip()


def _source_feed_snippet(name: str) -> str:
    return (
        dedent(
            f"""

          # Generated scaffold: source {name}
          # - name: example-{name}-source
          #   schedule: "every 1h"
          #   chat_id: ${{TELEGRAM_CHAT_AI}}
          #   sources:
          #     - type: {name}
          #       url: https://example.com/feed
          #   pipeline:
          #     - dedup
        """
        ).rstrip()
        + "\n"
    )


def _sink_module(name: str, class_name: str) -> str:
    return dedent(
        f'''
        from __future__ import annotations

        from typing import Any, ClassVar

        import httpx

        from glean.security.ssrf import validate_url
        from glean.sinks.base import SendContext
        from glean.sinks.registry import register_sink


        @register_sink("{name}")
        class {class_name}:
            """TODO: describe the {name} sink.

            Example:
                >>> sink = {class_name}(url="https://example.com/hook", required=False)
                >>> sink.required
                False
            """

            type: ClassVar[str] = "{name}"

            def __init__(
                self,
                url: str,
                *,
                required: bool = True,
                timeout_s: float = 10.0,
            ) -> None:
                self.url = validate_url(url)
                self.required = required
                self._client = httpx.AsyncClient(timeout=timeout_s, follow_redirects=False)

            async def send(self, ctx: SendContext) -> None:
                payload = self._build_payload(ctx)
                response = await self._client.post(self.url, json=payload)
                response.raise_for_status()

            def _build_payload(self, ctx: SendContext) -> dict[str, Any]:
                """TODO: adapt the payload shape for the target service."""
                pass
                return {{
                    "feed": ctx.feed,
                    "intro": ctx.intro,
                    "messages": list(ctx.messages),
                }}

            async def aclose(self) -> None:
                await self._client.aclose()
        '''
    ).lstrip()


def _sink_test(name: str, class_name: str) -> str:
    return dedent(
        f"""
        from __future__ import annotations

        import json

        import httpx
        import pytest
        import respx

        from glean.config.schema import RenderConfig
        from glean.sinks.base import SendContext
        from glean.sinks.{name} import {class_name}
        from glean.sources.base import Item

        pytestmark = pytest.mark.asyncio


        @respx.mock
        async def test_{name}_sink_posts_messages() -> None:
            route = respx.post("https://example.com/hook").mock(return_value=httpx.Response(202))
            sink = {class_name}(url="https://example.com/hook")
            ctx = SendContext(
                feed="scaffold",
                items=[Item(canonical_url="https://example.com/1", title="First item")],
                messages=["Hello from the scaffold."],
                intro="Daily digest",
                render=RenderConfig(),
            )

            await sink.send(ctx)
            await sink.aclose()

            assert route.called
            request = route.calls.last.request
            assert json.loads(request.content) == {{
                "feed": "scaffold",
                "intro": "Daily digest",
                "messages": ["Hello from the scaffold."],
            }}
        """
    ).lstrip()


def _sink_feed_snippet(name: str) -> str:
    return (
        dedent(
            f"""

          # Generated scaffold: sink {name}
          # - name: example-{name}-sink
          #   schedule: "every 1h"
          #   sinks:
          #     - type: {name}
          #       url: https://example.com/hook
          #   sources:
          #     - type: rss
          #       url: https://example.com/feed.xml
          #   pipeline:
          #     - dedup
        """
        ).rstrip()
        + "\n"
    )


def _llm_module(name: str, class_name: str) -> str:
    return dedent(
        f'''
        from __future__ import annotations

        from typing import Any, ClassVar

        import httpx

        from glean.llm.registry import register_provider
        from glean.security.ssrf import validate_provider_base_url
        from glean.sources.base import Item


        @register_provider("{name}")
        class {class_name}:
            """TODO: describe the {name} provider.

            Example:
                >>> provider = {class_name}(model="demo-model", base_url="https://example.com/v1")
                >>> provider.name
                '{name}'
            """

            name: ClassVar[str] = "{name}"

            def __init__(
                self,
                model: str = "demo-model",
                *,
                base_url: str = "https://example.com/v1",
                timeout_s: float = 10.0,
            ) -> None:
                self.model = model
                self.base_url = validate_provider_base_url("{name}", base_url).rstrip("/")
                self._client = httpx.AsyncClient(timeout=timeout_s, follow_redirects=False)

            async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
                response = await self._client.post(
                    f"{{self.base_url}}/{{path.lstrip('/')}}",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {{}}

            def _extra_payload(self) -> dict[str, Any]:
                """TODO: add provider-specific request fields."""
                pass
                return {{}}

            async def rank(self, item: Item, prompt: str) -> float:
                payload = await self._post(
                    "/rank",
                    {{
                        "model": self.model,
                        "prompt": prompt,
                        "title": item.title,
                        "body": item.body,
                        **self._extra_payload(),
                    }},
                )
                return float(payload.get("score", 0.0))

            async def summarize(self, item: Item, prompt: str) -> str:
                payload = await self._post(
                    "/summarize",
                    {{
                        "model": self.model,
                        "prompt": prompt,
                        "title": item.title,
                        "body": item.body,
                        **self._extra_payload(),
                    }},
                )
                return str(payload.get("summary", ""))

            async def digest(self, items: list[Item], prompt: str) -> str:
                payload = await self._post(
                    "/digest",
                    {{
                        "model": self.model,
                        "prompt": prompt,
                        "items": [item.title for item in items],
                        **self._extra_payload(),
                    }},
                )
                return str(payload.get("digest", ""))

            async def extract(
                self,
                item: Item,
                prompt: str,
                output_schema: dict[str, Any],
                *,
                system_prompt: str | None = None,
            ) -> dict[str, Any]:
                payload = await self._post(
                    "/extract",
                    {{
                        "model": self.model,
                        "prompt": prompt,
                        "system_prompt": system_prompt,
                        "title": item.title,
                        "body": item.body,
                        "output_schema": output_schema,
                        **self._extra_payload(),
                    }},
                )
                extracted = payload.get("data")
                return extracted if isinstance(extracted, dict) else {{}}

            async def aclose(self) -> None:
                await self._client.aclose()
        '''
    ).lstrip()


def _llm_test(name: str, class_name: str) -> str:
    return dedent(
        f"""
        from __future__ import annotations

        import json

        import httpx
        import pytest
        import respx

        from glean.llm.{name} import {class_name}
        from glean.sources.base import Item

        pytestmark = pytest.mark.asyncio


        @respx.mock
        async def test_{name}_provider_rank_posts_payload() -> None:
            route = respx.post("https://example.com/v1/rank").mock(
                return_value=httpx.Response(200, json={{"score": 0.75}})
            )
            provider = {class_name}(base_url="https://example.com/v1")
            item = Item(
                canonical_url="https://example.com/1",
                title="First item",
                body="Hello from the scaffold.",
            )

            score = await provider.rank(item, "Rank this")
            await provider.aclose()

            assert score == 0.75
            request = route.calls.last.request
            assert json.loads(request.content) == {{
                "model": "demo-model",
                "prompt": "Rank this",
                "title": "First item",
                "body": "Hello from the scaffold.",
            }}
        """
    ).lstrip()


def _llm_feed_snippet(name: str) -> str:
    return (
        dedent(
            f"""

          # Generated scaffold: llm {name}
          # - name: example-{name}-llm
          #   schedule: "every 1h"
          #   llm:
          #     provider: {name}
          #     model: demo-model
          #     base_url: https://example.com/v1
          #   sources:
          #     - type: rss
          #       url: https://example.com/feed.xml
          #   pipeline:
          #     - dedup
          #     - summarize:
          #         prompt: "One sentence."
        """
        ).rstrip()
        + "\n"
    )


def _search_module(name: str, class_name: str) -> str:
    return dedent(
        f'''
        from __future__ import annotations

        from typing import Any, ClassVar

        import httpx

        from glean.search.base import SearchResult
        from glean.search.registry import register_backend
        from glean.security.ssrf import validate_url


        @register_backend("{name}")
        class {class_name}:
            """TODO: describe the {name} backend.

            Example:
                >>> backend = {class_name}(base_url="https://example.com")
                >>> backend.name
                '{name}'
            """

            name: ClassVar[str] = "{name}"

            def __init__(self, *, base_url: str) -> None:
                self.base_url = validate_url(base_url).rstrip("/")

            async def search(
                self,
                query: str,
                *,
                http: httpx.AsyncClient,
                limit: int = 10,
            ) -> list[SearchResult]:
                response = await http.get(
                    f"{{self.base_url}}/search",
                    params={{"q": query, "limit": limit, **self._extra_params()}},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    return []
                raw_results = payload.get("results")
                if not isinstance(raw_results, list):
                    return []
                results: list[SearchResult] = []
                for raw_result in raw_results[:limit]:
                    if not isinstance(raw_result, dict):
                        continue
                    url = str(raw_result.get("url", "")).strip()
                    if not url:
                        continue
                    results.append(
                        SearchResult(
                            url=url,
                            title=str(raw_result.get("title", "")).strip(),
                            snippet=str(raw_result.get("snippet", "")).strip(),
                            engine=self.name,
                            raw=raw_result,
                        )
                    )
                return results

            def _extra_params(self) -> dict[str, Any]:
                """TODO: add backend-specific query parameters."""
                pass
                return {{}}
        '''
    ).lstrip()


def _search_test(name: str, class_name: str) -> str:
    return dedent(
        f"""
        from __future__ import annotations

        import httpx
        import pytest
        import respx

        from glean.search.{name} import {class_name}

        pytestmark = pytest.mark.asyncio


        @respx.mock
        async def test_{name}_backend_reads_json_results(http_client) -> None:
            route = respx.get("https://example.com/search").mock(
                return_value=httpx.Response(
                    200,
                    json={{
                        "results": [
                            {{
                                "url": "https://example.com/1",
                                "title": "First item",
                                "snippet": "Hello from the scaffold.",
                            }}
                        ]
                    }},
                )
            )
            backend = {class_name}(base_url="https://example.com")

            results = await backend.search("needle", http=http_client, limit=2)

            assert len(results) == 1
            assert results[0].url == "https://example.com/1"
            assert results[0].title == "First item"
            assert results[0].snippet == "Hello from the scaffold."
            params = route.calls.last.request.url.params
            assert params["q"] == "needle"
            assert params["limit"] == "2"
        """
    ).lstrip()


def _search_feed_snippet(name: str) -> str:
    return (
        dedent(
            f"""

          # Generated scaffold: search {name}
          # - name: example-{name}-search
          #   schedule: "every 1h"
          #   chat_id: ${{TELEGRAM_CHAT_AI}}
          #   sources:
          #     - type: search
          #       query: "example query"
          #       engine: {name}
          #       base_url: https://example.com
          #   pipeline:
          #     - dedup
        """
        ).rstrip()
        + "\n"
    )


LAYER_DEFINITIONS = {
    "source": LayerDefinition(
        layer="source",
        package="sources",
        class_suffix="Source",
        registry_path="src/glean/sources/registry.py",
        render_module=_source_module,
        render_test=_source_test,
        render_feed_snippet=_source_feed_snippet,
    ),
    "sink": LayerDefinition(
        layer="sink",
        package="sinks",
        class_suffix="Sink",
        registry_path="src/glean/sinks/registry.py",
        render_module=_sink_module,
        render_test=_sink_test,
        render_feed_snippet=_sink_feed_snippet,
    ),
    "llm": LayerDefinition(
        layer="llm",
        package="llm",
        class_suffix="Provider",
        registry_path="src/glean/llm/registry.py",
        render_module=_llm_module,
        render_test=_llm_test,
        render_feed_snippet=_llm_feed_snippet,
    ),
    "search": LayerDefinition(
        layer="search",
        package="search",
        class_suffix="Backend",
        registry_path="src/glean/search/registry.py",
        render_module=_search_module,
        render_test=_search_test,
        render_feed_snippet=_search_feed_snippet,
    ),
}


def _registry_import_line(definition: LayerDefinition, name: str, class_name: str) -> str:
    del class_name
    return f"    from glean.{definition.package} import {name}  # noqa: F401\n"


def _scaffold_paths(definition: LayerDefinition, name: str, repo_root: Path) -> ScaffoldResult:
    return ScaffoldResult(
        plugin_path=repo_root / "src" / "glean" / definition.package / f"{name}.py",
        test_path=repo_root / "tests" / f"test_{definition.layer}_{name}.py",
        registry_path=repo_root / definition.registry_path,
        feeds_path=repo_root / "feeds.example.yaml",
    )


def _validate_inputs(layer: str, name: str) -> LayerDefinition:
    definition = LAYER_DEFINITIONS.get(layer)
    if definition is None:
        allowed = ", ".join(LAYER_DEFINITIONS)
        raise PluginScaffoldError(f"layer must be one of: {allowed}")
    if not NAME_PATTERN.fullmatch(name):
        raise PluginScaffoldError(f"name must match ^[a-z][a-z0-9_]*$: {name!r}")
    return definition


def _ensure_files_exist(*paths: Path) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        joined = ", ".join(missing)
        raise PluginScaffoldError(f"required scaffold files are missing: {joined}")


def _preflight_conflicts(
    paths: ScaffoldResult,
    registry_text: str,
    registry_import: str,
    feeds_text: str,
    feeds_marker: str,
) -> None:
    conflicts: list[str] = []
    if paths.plugin_path.exists():
        conflicts.append(str(paths.plugin_path))
    if paths.test_path.exists():
        conflicts.append(str(paths.test_path))
    if registry_import in registry_text:
        conflicts.append(str(paths.registry_path))
    if feeds_marker in feeds_text:
        conflicts.append(str(paths.feeds_path))
    if conflicts:
        joined = ", ".join(conflicts)
        raise PluginScaffoldError(f"scaffold artifacts already exist: {joined}")


def _format_registry_import(indent: str, module: str, names: list[str]) -> list[str]:
    single_line = f"{indent}from {module} import {', '.join(names)}  # noqa: F401"
    if len(single_line) <= 100:
        return [single_line]
    wrapped_lines = [f"{indent}from {module} import (  # noqa: F401"]
    wrapped_lines.extend(f"{indent}    {name}," for name in names)
    wrapped_lines.append(f"{indent})")
    return wrapped_lines


def _append_registry_import(registry_text: str, registry_import: str) -> str:
    marker = "\n\n_import_builtins()\n"
    if marker not in registry_text:
        raise PluginScaffoldError("could not find _import_builtins() footer in registry.py")

    import_pattern = (
        r"^(?P<indent>\s*)from\s+(?P<module>glean\.[^.]+)\s+"
        r"import\s+(?P<name>[a-z0-9_]+)\s+# noqa: F401\n$"
    )
    import_match = re.match(import_pattern, registry_import)
    if import_match is None:
        raise PluginScaffoldError("could not parse registry import line")

    indent = import_match.group("indent")
    module = import_match.group("module")
    target_prefix = f"{indent}from {module} import "
    prefix, suffix = registry_text.split(marker, 1)
    lines = prefix.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith(target_prefix):
            continue
        remainder = line[len(target_prefix) :]
        if remainder == "(  # noqa: F401":
            names = []
            end_index = index + 1
            while end_index < len(lines) and lines[end_index].strip() != ")":
                current = lines[end_index].strip().rstrip(",")
                if current:
                    names.append(current)
                end_index += 1
            if end_index >= len(lines):
                raise PluginScaffoldError("unterminated registry import block")
        elif remainder.endswith("  # noqa: F401"):
            names_part = remainder[: -len("  # noqa: F401")]
            names = [part.strip() for part in names_part.split(",") if part.strip()]
            end_index = index
        else:
            continue
        updated_names = sorted({*names, import_match.group("name")})
        replacement = _format_registry_import(indent, module, updated_names)
        lines[index : end_index + 1] = replacement
        return "\n".join(lines) + marker + suffix

    raise PluginScaffoldError("could not find built-in import line in registry.py")


def _append_feed_snippet(feeds_text: str, snippet: str) -> str:
    if not feeds_text.endswith("\n"):
        feeds_text += "\n"
    return feeds_text + snippet


def generate_plugin(layer: str, name: str, *, repo_root: Path = REPO_ROOT) -> ScaffoldResult:
    definition = _validate_inputs(layer, name)
    class_name = f"{_camel_case(name)}{definition.class_suffix}"
    paths = _scaffold_paths(definition, name, repo_root)
    _ensure_files_exist(paths.registry_path, paths.feeds_path)

    registry_text = paths.registry_path.read_text(encoding="utf-8")
    feeds_text = paths.feeds_path.read_text(encoding="utf-8")
    registry_import = _registry_import_line(definition, name, class_name)
    feed_snippet = definition.render_feed_snippet(name)
    feed_marker = f"# Generated scaffold: {layer} {name}"
    _preflight_conflicts(paths, registry_text, registry_import, feeds_text, feed_marker)

    paths.plugin_path.parent.mkdir(parents=True, exist_ok=True)
    paths.test_path.parent.mkdir(parents=True, exist_ok=True)
    paths.plugin_path.write_text(
        definition.render_module(name, class_name),
        encoding="utf-8",
    )
    paths.test_path.write_text(
        definition.render_test(name, class_name),
        encoding="utf-8",
    )
    paths.registry_path.write_text(
        _append_registry_import(registry_text, registry_import),
        encoding="utf-8",
    )
    paths.feeds_path.write_text(
        _append_feed_snippet(feeds_text, feed_snippet),
        encoding="utf-8",
    )
    return paths


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold a new glean plugin.",
    )
    parser.add_argument("layer", help="One of: source, sink, llm, search")
    parser.add_argument("name", help="Plugin name using snake_case")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = generate_plugin(args.layer, args.name)
    except PluginScaffoldError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    plugin_display = result.plugin_path.relative_to(REPO_ROOT)
    print(
        "Created "
        f"{plugin_display} + test + registry import + feeds.example.yaml entry. "
        "Next: run `make check` and edit the TODO blocks."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
