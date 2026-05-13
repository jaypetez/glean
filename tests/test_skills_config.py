"""Tests for SkillConfig parsing and validation."""
from __future__ import annotations

import textwrap
from collections.abc import Callable

import pytest

from glean.config import load_config
from glean.config.loader import ConfigError
from glean.config.skills import (
    SkillConfig,
    SkillOutputField,
    render_skill_prompt,
    skill_output_schema,
)
from glean.sources.base import Item


def test_skill_config_valid() -> None:
    skill = SkillConfig(
        name="deal-finder",
        prompt="Extract from {title}\n{body}",
        output_schema={"title": "str", "price": "str | None", "summary": "str"},
    )

    assert skill.name == "deal-finder"
    assert len(skill.output_schema) == 3


def test_skill_llm_override_parses() -> None:
    skill = SkillConfig(
        name="with-llm",
        prompt="Extract from {title}",
        output_schema={"summary": "str"},
        llm={"provider": "openai", "model": "gpt-4o-mini"},
    )

    assert skill.llm is not None
    assert skill.llm.provider == "openai"
    assert skill.llm.model == "gpt-4o-mini"


def test_skill_unknown_template_var_rejected() -> None:
    with pytest.raises(ValueError, match="unknown variables"):
        SkillConfig(
            name="bad",
            prompt="Extract {nonexistent} from {title}",
            output_schema={"r": "str"},
        )


def test_skill_unknown_field_type_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported type"):
        SkillConfig(
            name="bad",
            prompt="x",
            output_schema={"r": "uuid"},
        )


def test_skill_empty_schema_rejected() -> None:
    with pytest.raises(ValueError, match="at least one field"):
        SkillConfig(name="bad", prompt="x", output_schema={})


def test_skill_verbose_field_form() -> None:
    skill = SkillConfig(
        name="x",
        prompt="from {title}",
        output_schema={
            "summary": SkillOutputField(
                type="str", description="One liner", required=True
            ),
            "score": SkillOutputField(type="float | None", required=False),
        },
    )

    schema = skill_output_schema(skill)

    assert schema["properties"]["summary"]["description"] == "One liner"
    assert schema["properties"]["score"] == {"type": ["number", "null"]}
    assert "summary" in schema["required"]
    assert "score" not in schema["required"]


def test_skill_output_schema_json_mapping() -> None:
    skill = SkillConfig(
        name="s",
        prompt="from {title}",
        output_schema={
            "name": "str",
            "count": "int",
            "price": "float | None",
            "tags": "list[str]",
        },
    )

    schema = skill_output_schema(skill)

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["name"] == {"type": "string"}
    assert schema["properties"]["price"] == {"type": ["number", "null"]}
    assert schema["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert "name" in schema["required"]
    assert "price" not in schema["required"]


def test_render_skill_prompt() -> None:
    item = Item(
        canonical_url="https://x",
        title="Hello",
        body="World",
        source_name="src",
        source_type="rss",
    )

    rendered = render_skill_prompt("T={title}, B={body}, U={url}", item)

    assert rendered == "T=Hello, B=World, U=https://x"


def test_apply_skill_unknown_skill_name_rejected_at_load(
    write_yaml: Callable[[str], object],
) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: ollama, model: x}
        feeds:
          - name: f
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: rss
                url: https://example.com
            pipeline:
              - apply_skill:
                  skill: does-not-exist
        """
    )

    with pytest.raises(ConfigError, match="unknown skill"):
        load_config(write_yaml(yaml))


def test_apply_skill_missing_skill_param_rejected_at_load(
    write_yaml: Callable[[str], object],
) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: ollama, model: x}
        feeds:
          - name: f
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: rss
                url: https://example.com
            pipeline:
              - apply_skill: {}
        """
    )

    with pytest.raises(ConfigError, match="missing 'skill'"):
        load_config(write_yaml(yaml))


def test_duplicate_skill_names_rejected(write_yaml: Callable[[str], object]) -> None:
    yaml = textwrap.dedent(
        """
        defaults:
          llm: {provider: ollama, model: x}
        skills:
          - name: dup
            prompt: "x"
            output_schema: {summary: str}
          - name: dup
            prompt: "y"
            output_schema: {summary: str}
        feeds:
          - name: f
            schedule: "every 1h"
            chat_id: -1
            sources:
              - type: rss
                url: https://example.com
            pipeline: [dedup]
        """
    )

    with pytest.raises(ConfigError, match="duplicate skill name"):
        load_config(write_yaml(yaml))
