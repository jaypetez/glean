from __future__ import annotations

import sys
from pathlib import Path


def _strip_existing_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    marker = "\n---\n"
    end = text.find(marker, len("---\n"))
    if end == -1:
        return text
    return text[end + len(marker) :].lstrip("\n")


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: prepend_frontmatter.py <path> <title> <description>")

    path = Path(sys.argv[1])
    title = sys.argv[2].replace("\\u2014", chr(0x2014))
    description = sys.argv[3]
    body = _strip_existing_frontmatter(path.read_text(encoding="utf-8"))
    frontmatter = f'---\ntitle: "{title}"\ndescription: {description}\n---\n\n'
    path.write_text(frontmatter + body, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
