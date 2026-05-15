"""Mock RSS feed server for E2E testing."""

from __future__ import annotations

import os

from fastapi import FastAPI, Response

app = FastAPI(title="mock-rss")

_counter = {"n": int(os.environ.get("MOCK_RSS_INITIAL", "5"))}
_generation = {"n": 0}


def _build_feed(n: int, generation: int) -> str:
    items = []
    for i in range(n):
        article_id = f"{generation}-{i + 1}"
        items.append(f"""
  <entry>
    <title>Mock article {i + 1}</title>
    <link href="https://example.com/articles/{article_id}"/>
    <id>https://example.com/articles/{article_id}</id>
    <updated>2024-01-{15 + i:02d}T12:00:00Z</updated>
    <published>2024-01-{15 + i:02d}T11:00:00Z</published>
    <summary>This is mock article {i + 1}'s summary content.</summary>
    <content type="html">&lt;p&gt;Full body content for article {i + 1}&lt;/p&gt;</content>
  </entry>""")

    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Mock Feed</title>
  <link href="http://mock-rss:8002"/>
  <updated>2024-01-15T12:00:00Z</updated>
  <id>urn:uuid:mock-feed-id</id>
  {"".join(items)}
</feed>"""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/feed.xml")
def feed() -> Response:
    return Response(
        content=_build_feed(_counter["n"], _generation["n"]),
        media_type="application/atom+xml",
    )


@app.post("/__set_count/{n}")
def set_count(n: int) -> dict[str, int]:
    _counter["n"] = n
    return {"count": n}


@app.post("/__reset")
def reset() -> dict[str, str]:
    _counter["n"] = int(os.environ.get("MOCK_RSS_INITIAL", "5"))
    _generation["n"] += 1
    return {"status": "reset"}
