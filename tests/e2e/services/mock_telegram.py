"""Minimal mock of Telegram Bot API for E2E testing."""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request

app = FastAPI(title="mock-telegram")

_messages: list[dict[str, Any]] = []


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/bot{token}/{method}", methods=["GET", "POST"])
async def bot_method(token: str, method: str, request: Request) -> dict[str, Any]:
    """Catch-all handler for any Bot API call."""
    body: dict[str, Any] = dict(request.query_params)
    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            raw_body = await request.body()
            body = dict(parse_qsl(raw_body.decode())) if raw_body else body

    if method == "sendMessage":
        msg = {
            "message_id": len(_messages) + 1,
            "chat": {"id": body.get("chat_id"), "type": "supergroup"},
            "date": int(time.time()),
            "text": body.get("text", ""),
            "_received_token": token,
        }
        _messages.append(msg)
        return {"ok": True, "result": msg}

    if method == "getMe":
        return {
            "ok": True,
            "result": {
                "id": 12345,
                "is_bot": True,
                "first_name": "MockBot",
                "username": "mockbot",
                "can_join_groups": True,
                "can_read_all_group_messages": True,
                "supports_inline_queries": False,
            },
        }

    if method == "getUpdates":
        return {"ok": True, "result": []}

    # Generic OK for anything else
    return {"ok": True, "result": True}


@app.get("/__messages")
def get_messages() -> list[dict[str, Any]]:
    return _messages


@app.post("/__reset")
def reset() -> dict[str, str]:
    _messages.clear()
    return {"status": "reset"}
