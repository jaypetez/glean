"""Minimal mock of the Ollama API for E2E testing."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

app = FastAPI(title="mock-ollama")

_calls: list[dict[str, Any]] = []


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(request: Request) -> dict[str, Any]:
    body = await request.json()
    _calls.append(body)

    # Detect intent from the system prompt
    messages = body.get("messages", [])
    system_content = ""
    user_content = ""
    for m in messages:
        if m.get("role") == "system":
            system_content = m.get("content", "")
        elif m.get("role") == "user":
            user_content = m.get("content", "")

    is_ranking = "0 and 1" in system_content or "score 0-1" in system_content.lower()

    fmt = body.get("format")
    if isinstance(fmt, dict) and fmt.get("type") == "object":
        content = _build_structured_response(fmt, user_content)
    elif is_ranking:
        content = "0.8"
    else:
        # Summarize: extract title from user content if present
        first_line = user_content.split("\n", 1)[0] if user_content else ""
        if first_line.startswith("TITLE:"):
            title = first_line.removeprefix("TITLE:").strip()
            content = f"Mock summary of: {title}"
        else:
            content = "Mock LLM output."

    return {
        "model": body.get("model", "mock"),
        "message": {"role": "assistant", "content": content},
        "done": True,
        "total_duration": 1000,
        "load_duration": 100,
        "prompt_eval_count": 10,
        "eval_count": 20,
    }


def _build_structured_response(schema: dict[str, Any], user_content: str) -> str:
    """Return a JSON string matching the JSON Schema, with deterministic mock values."""
    import json

    properties = schema.get("properties", {})
    result: dict[str, Any] = {}
    for field_name, field_spec in properties.items():
        field_type = field_spec.get("type")
        if isinstance(field_type, list):
            field_type = next((t for t in field_type if t != "null"), "string")
        if field_type == "string":
            if field_name in ("summary", "one_liner", "tldr", "title", "item_title"):
                first_line = user_content.split("\n", 1)[0] if user_content else ""
                title_hint = (
                    first_line.removeprefix("TITLE:").strip()
                    if first_line.startswith("TITLE:")
                    else "mock"
                )
                result[field_name] = f"mock-{field_name}: {title_hint}"
            else:
                result[field_name] = f"mock-{field_name}"
        elif field_type == "integer":
            result[field_name] = 1
        elif field_type == "number":
            result[field_name] = 0.5
        elif field_type == "boolean":
            result[field_name] = True
        elif field_type == "array":
            items_type = field_spec.get("items", {}).get("type", "string")
            if items_type == "string":
                result[field_name] = ["mock-item"]
            elif items_type == "integer":
                result[field_name] = [1]
            elif items_type == "number":
                result[field_name] = [1.0]
            else:
                result[field_name] = []
        else:
            result[field_name] = None
    return json.dumps(result)


@app.post("/api/generate")
async def generate(request: Request) -> dict[str, Any]:
    body = await request.json()
    return {
        "model": body.get("model", "mock"),
        "response": "Mock generation",
        "done": True,
    }


@app.get("/api/tags")
def tags() -> dict[str, Any]:
    return {"models": [{"name": "mock-model:latest"}]}


@app.get("/__calls")
def get_calls() -> list[dict[str, Any]]:
    return _calls


@app.post("/__reset")
def reset() -> dict[str, str]:
    _calls.clear()
    return {"status": "reset"}
