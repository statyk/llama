"""Capture real API responses as test fixtures.

Usage:
  python scripts/capture_fixture.py <identifier> [out.json]
      archive.org metadata, slimmed to the fields tests use.
  python scripts/capture_fixture.py --setlistfm "<artist>" <YYYY-MM-DD> [out.json]
      setlist.fm search response (requires SETLISTFM_API_KEY).
"""
import json
import os
import sys
from pathlib import Path

import httpx

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "packages" / "llama" / "tests" / "fixtures"


def capture_ia(identifier: str, out: Path | None) -> None:
    out = out or FIXTURES_DIR / f"{identifier}.json"
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


def capture_setlistfm(artist: str, date: str, out: Path | None) -> None:
    key = os.environ["SETLISTFM_API_KEY"]
    y, m, d = date.split("-")
    out = out or FIXTURES_DIR / f"slfm_{artist.lower().replace(' ', '_')}_{date.replace('-', '_')}.json"
    resp = httpx.get(
        "https://api.setlist.fm/rest/1.0/search/setlists",
        params={"artistName": artist, "date": f"{d}-{m}-{y}"},
        headers={"x-api-key": key, "accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    out.write_text(json.dumps(resp.json(), indent=2))
    print(f"wrote {out}")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--setlistfm":
        capture_setlistfm(args[1], args[2], Path(args[3]) if len(args) > 3 else None)
    else:
        capture_ia(args[0], Path(args[1]) if len(args) > 1 else None)


if __name__ == "__main__":
    main()
