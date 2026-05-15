from __future__ import annotations

import json
import sys
from pathlib import Path

from glean.config.schema import Config


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: dump_schema.py <output-path>")

    output_path = Path(sys.argv[1])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = Config.model_json_schema()
    payload = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    output_path.write_text(payload, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
