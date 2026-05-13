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

    if is_ranking:
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
