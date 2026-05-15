from __future__ import annotations

import sys
from pathlib import Path


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: normalize_utf8.py <path> [<path> ...]")
    for raw_path in sys.argv[1:]:
        path = Path(raw_path)
        text = _decode(path.read_bytes())
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\\data\\state.db", "/data/state.db")
        text = text.replace("\\etc\\glean\\feeds.yaml", "/etc/glean/feeds.yaml")
        path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
