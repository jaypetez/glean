from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest


def _load_new_plugin_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "new_plugin.py"
    if not script_path.exists():
        pytest.fail("scripts/new_plugin.py is missing")
    spec = spec_from_file_location("new_plugin_script", script_path)
    if spec is None or spec.loader is None:
        pytest.fail("Unable to import scripts/new_plugin.py")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_repo_file(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(root: Path) -> None:
    _write_repo_file(root, "feeds.example.yaml", "# sample\nfeeds:\n")
    _write_repo_file(
        root,
        "src/glean/sources/registry.py",
        "from __future__ import annotations\n\n"
        "def _import_builtins() -> None:\n"
        "    from glean.sources import rss  # noqa: F401\n\n"
        "_import_builtins()\n",
    )
    _write_repo_file(
        root,
        "src/glean/sinks/registry.py",
        "from __future__ import annotations\n\n"
        "def _import_builtins() -> None:\n"
        "    from glean.sinks import webhook  # noqa: F401\n\n"
        "_import_builtins()\n",
    )
    _write_repo_file(
        root,
        "src/glean/llm/registry.py",
        "from __future__ import annotations\n\n"
        "def _import_builtins() -> None:\n"
        "    from glean.llm import openai_provider  # noqa: F401\n\n"
        "_import_builtins()\n",
    )
    _write_repo_file(
        root,
        "src/glean/search/registry.py",
        "from __future__ import annotations\n\n"
        "def _import_builtins() -> None:\n"
        "    from glean.search import searxng  # noqa: F401\n\n"
        "_import_builtins()\n",
    )


def test_generate_source_scaffold_creates_expected_artifacts(tmp_path: Path) -> None:
    module = _load_new_plugin_module()
    _make_repo(tmp_path)

    module.generate_plugin("source", "demo", repo_root=tmp_path)

    plugin_text = (tmp_path / "src/glean/sources/demo.py").read_text(encoding="utf-8")
    test_text = (tmp_path / "tests/test_source_demo.py").read_text(encoding="utf-8")
    registry_text = (tmp_path / "src/glean/sources/registry.py").read_text(encoding="utf-8")
    feed_text = (tmp_path / "feeds.example.yaml").read_text(encoding="utf-8")

    assert "from __future__ import annotations" in plugin_text
    assert "from glean.security.ssrf import validate_url" in plugin_text
    assert '@register_source("demo")' in plugin_text
    assert "class DemoSource:" in plugin_text
    assert '>>> source = DemoSource(url="https://example.com/feed")' in plugin_text
    assert "pass" in plugin_text
    assert "..." not in plugin_text
    assert "import respx" in test_text
    assert 'respx.get("https://example.com/feed")' in test_text
    assert "from glean.sources import demo, rss  # noqa: F401" in registry_text
    assert "\n\n    from glean.sources.demo" not in registry_text
    assert "# Generated scaffold: source demo" in feed_text
    assert "#     - type: demo" in feed_text


def test_generate_sink_scaffold_creates_http_smoke_test(tmp_path: Path) -> None:
    module = _load_new_plugin_module()
    _make_repo(tmp_path)

    module.generate_plugin("sink", "archive", repo_root=tmp_path)

    plugin_text = (tmp_path / "src/glean/sinks/archive.py").read_text(encoding="utf-8")
    test_text = (tmp_path / "tests/test_sink_archive.py").read_text(encoding="utf-8")
    registry_text = (tmp_path / "src/glean/sinks/registry.py").read_text(encoding="utf-8")

    assert "from glean.security.ssrf import validate_url" in plugin_text
    assert '@register_sink("archive")' in plugin_text
    assert "class ArchiveSink:" in plugin_text
    assert "pass" in plugin_text
    assert "import respx" in test_text
    assert 'respx.post("https://example.com/hook")' in test_text
    assert "from glean.sinks import archive, webhook  # noqa: F401" in registry_text


def test_generate_search_scaffold_uses_search_directory(tmp_path: Path) -> None:
    module = _load_new_plugin_module()
    _make_repo(tmp_path)

    module.generate_plugin("search", "lookup", repo_root=tmp_path)

    plugin_path = tmp_path / "src/glean/search/lookup.py"
    assert plugin_path.exists()
    plugin_text = plugin_path.read_text(encoding="utf-8")
    test_text = (tmp_path / "tests/test_search_lookup.py").read_text(encoding="utf-8")
    registry_text = (tmp_path / "src/glean/search/registry.py").read_text(encoding="utf-8")

    assert "from glean.security.ssrf import validate_url" in plugin_text
    assert '@register_backend("lookup")' in plugin_text
    assert "class LookupBackend:" in plugin_text
    assert 'respx.get("https://example.com/search")' in test_text
    assert "from glean.search import lookup, searxng  # noqa: F401" in registry_text


def test_generate_llm_scaffold_rejects_duplicates(tmp_path: Path) -> None:
    module = _load_new_plugin_module()
    _make_repo(tmp_path)

    module.generate_plugin("llm", "demo", repo_root=tmp_path)

    plugin_text = (tmp_path / "src/glean/llm/demo.py").read_text(encoding="utf-8")
    test_text = (tmp_path / "tests/test_llm_demo.py").read_text(encoding="utf-8")
    registry_text = (tmp_path / "src/glean/llm/registry.py").read_text(encoding="utf-8")

    assert '@register_provider("demo")' in plugin_text
    assert "class DemoProvider:" in plugin_text
    assert "pass" in plugin_text
    assert 'respx.post("https://example.com/v1/rank")' in test_text
    assert "from glean.llm import demo, openai_provider  # noqa: F401" in registry_text

    with pytest.raises(module.PluginScaffoldError, match="already exist"):
        module.generate_plugin("llm", "demo", repo_root=tmp_path)


def test_generate_llm_scaffold_wraps_long_registry_import_line(tmp_path: Path) -> None:
    module = _load_new_plugin_module()
    _make_repo(tmp_path)
    _write_repo_file(
        tmp_path,
        "src/glean/llm/registry.py",
        "from __future__ import annotations\n\n"
        "def _import_builtins() -> None:\n"
        "    from glean.llm import "
        "anthropic_provider, ollama_provider, openai_provider  # noqa: F401\n\n"
        "_import_builtins()\n",
    )

    module.generate_plugin("llm", "smoke_llm", repo_root=tmp_path)

    registry_text = (tmp_path / "src/glean/llm/registry.py").read_text(encoding="utf-8")
    assert "from glean.llm import (  # noqa: F401" in registry_text
    assert "        anthropic_provider," in registry_text
    assert "        ollama_provider," in registry_text
    assert "        openai_provider," in registry_text
    assert "        smoke_llm," in registry_text
    assert "    )" in registry_text


def test_generate_plugin_validates_inputs(tmp_path: Path) -> None:
    module = _load_new_plugin_module()
    _make_repo(tmp_path)

    with pytest.raises(module.PluginScaffoldError, match="source, sink, llm, search"):
        module.generate_plugin("widget", "demo", repo_root=tmp_path)

    with pytest.raises(module.PluginScaffoldError, match=r"\^\[a-z\]\[a-z0-9_\]\*\$"):
        module.generate_plugin("source", "Demo", repo_root=tmp_path)
