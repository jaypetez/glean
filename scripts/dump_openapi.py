from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, cast

from glean.api.app import make_app


class _DocState:
    async def ping(self) -> None:
        pass


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: dump_openapi.py <output-path>")

    output_path = Path(sys.argv[1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("GLEAN_API_KEY", "docs-openapi-placeholder-key")
    os.environ.setdefault("GLEAN_UI_DIST", "__missing_ui_dist__")
    os.environ.pop("GLEAN_TEST_MODE", None)

    app = make_app(cast(Any, _DocState()), Path("/data/state.db"))
    schema = app.openapi()
    payload = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    output_path.write_text(payload, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
