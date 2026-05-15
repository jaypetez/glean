"""Minimal mock of SearXNG JSON API for E2E testing."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

app = FastAPI(title="mock-searxng")

_queries: list[dict[str, Any]] = []
_generation = {"n": 0}

_MOCK_RESULTS = [
    {
        "url": "https://example.com/search/1",
        "title": "Mock Search Result 1",
        "content": "This is mock search snippet 1 about the query topic.",
        "engine": "mock",
        "engines": ["mock"],
        "score": 1.2,
        "category": "general",
        "publishedDate": "2024-01-15T12:00:00Z",
    },
    {
        "url": "https://example.com/search/2",
        "title": "Mock Search Result 2",
        "content": "This is mock search snippet 2 with different content.",
        "engine": "mock",
        "engines": ["mock"],
        "score": 0.9,
        "category": "general",
        "publishedDate": None,
    },
    {
        "url": "https://example.com/search/3",
        "title": "Mock Search Result 3",
        "content": "Third mock result for diversity.",
        "engine": "mock",
        "engines": ["mock"],
        "score": 0.7,
        "category": "general",
    },
]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search")
def search(q: str, format: str = "html") -> dict[str, Any]:
    _queries.append({"q": q, "format": format})
    if format != "json":
        # Match real SearXNG behavior: 403 if json format not enabled
        raise HTTPException(status_code=403, detail="format not enabled")
    results = [
        {**result, "url": f"{result['url']}?generation={_generation['n']}"}
        for result in _MOCK_RESULTS
    ]
    return {
        "query": q,
        "number_of_results": len(results),
        "results": results,
        "answers": [],
        "corrections": [],
        "infoboxes": [],
        "suggestions": [],
        "unresponsive_engines": [],
    }


@app.get("/__queries")
def get_queries() -> list[dict[str, Any]]:
    return _queries


@app.post("/__reset")
def reset() -> dict[str, str]:
    _queries.clear()
    _generation["n"] += 1
    return {"status": "reset"}
