"""Reusable structured-extraction skills configured in YAML."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from glean.config.schema import LLMConfig

# Safe type vocabulary for output_schema field types.
_VALID_FIELD_TYPES = frozenset(
    {
        "str",
        "int",
        "float",
        "bool",
        "str | None",
        "int | None",
        "float | None",
        "bool | None",
        "list[str]",
        "list[int]",
        "list[float]",
    }
)

# Template variable regex — matches {var_name} in prompt strings.
_TEMPLATE_VAR_RE = re.compile(r"\{(\w+)\}")

# Variables available in skill prompt templates (matches Item fields).
ALLOWED_TEMPLATE_VARS = frozenset(
    {
        "title",
        "body",
        "summary",
        "url",
        "source_name",
        "source_type",
    }
)

# JSON Schema type mapping.
_JSON_TYPE_MAP: dict[str, dict[str, Any]] = {
    "str": {"type": "string"},
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "bool": {"type": "boolean"},
    "str | None": {"type": ["string", "null"]},
    "int | None": {"type": ["integer", "null"]},
    "float | None": {"type": ["number", "null"]},
    "bool | None": {"type": ["boolean", "null"]},
    "list[str]": {"type": "array", "items": {"type": "string"}},
    "list[int]": {"type": "array", "items": {"type": "integer"}},
    "list[float]": {"type": "array", "items": {"type": "number"}},
}


class SkillOutputField(BaseModel):
    """Verbose form for a skill output field (alternative to bare type string)."""

    model_config = ConfigDict(extra="forbid")

    type: str = "str"
    description: str | None = None
    required: bool = True

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in _VALID_FIELD_TYPES:
            raise ValueError(
                f"unsupported field type {v!r}. Allowed: {sorted(_VALID_FIELD_TYPES)}"
            )
        return v


class SkillConfig(BaseModel):
    """A named, reusable LLM extraction skill defined in YAML."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    version: str = "1"
    description: str | None = None
    system_prompt: str | None = None
    prompt: str
    output_schema: dict[str, str | SkillOutputField]
    llm: LLMConfig | None = None

    @field_validator("output_schema")
    @classmethod
    def _nonempty_schema(
        cls, v: dict[str, str | SkillOutputField]
    ) -> dict[str, str | SkillOutputField]:
        if not v:
            raise ValueError("output_schema must have at least one field")
        for field_name, field_spec in v.items():
            if isinstance(field_spec, str) and field_spec not in _VALID_FIELD_TYPES:
                raise ValueError(
                    f"output_schema.{field_name}: unsupported type {field_spec!r}. "
                    f"Allowed: {sorted(_VALID_FIELD_TYPES)}"
                )
        return v

    @model_validator(mode="after")
    def _validate_template_vars(self) -> Self:
        used = {m.group(1) for m in _TEMPLATE_VAR_RE.finditer(self.prompt)}
        unknown = used - ALLOWED_TEMPLATE_VARS
        if unknown:
            raise ValueError(
                f"skill {self.name!r} prompt references unknown variables: "
                + ", ".join(f"{{{v}}}" for v in sorted(unknown))
                + f". Allowed: {sorted(ALLOWED_TEMPLATE_VARS)}"
            )
        return self


def skill_output_schema(skill: SkillConfig) -> dict[str, Any]:
    """Convert a SkillConfig.output_schema to a strict JSON Schema dict."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field_name, field_spec in skill.output_schema.items():
        if isinstance(field_spec, str):
            type_str = field_spec
            field_required = " | None" not in type_str
            description: str | None = None
        else:
            type_str = field_spec.type
            field_required = field_spec.required
            description = field_spec.description
        prop = dict(_JSON_TYPE_MAP.get(type_str, {"type": "string"}))
        if description:
            prop["description"] = description
        properties[field_name] = prop
        if field_required:
            required.append(field_name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def render_skill_prompt(template: str, item: Any) -> str:
    """Render a skill's prompt template by binding Item fields."""
    ctx = {
        "title": item.title,
        "body": item.body or "",
        "summary": item.summary or "",
        "url": item.canonical_url,
        "source_name": item.source_name,
        "source_type": item.source_type,
    }
    return template.format_map(ctx)
