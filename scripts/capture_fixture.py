"""Capture a real archive.org metadata response as a test fixture.

Usage: python scripts/capture_fixture.py <identifier> [out.json]
"""
import json
import sys
from pathlib import Path

import httpx


def main() -> None:
    identifier = sys.argv[1]
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(f"tests/fixtures/{identifier}.json")
    data = httpx.get(f"https://archive.org/metadata/{identifier}", timeout=60).json()
    slim = {
        "metadata": data.get("metadata", {}),
        "files": [
            {k: f[k] for k in ("name", "source", "original", "format", "length", "md5", "title") if k in f}
            for f in data.get("files", [])
        ],
        "reviews": data.get("reviews", []),
    }
    out.write_text(json.dumps(slim, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
