"""Manual refresh for the vendored jerrybase dataset (never run by the pipeline).

Usage:
  python scripts/refresh_jerrybase.py [ref]
      ref defaults to "main". Downloads deadstream's set_breaks.csv at that ref,
      prints a row-count and artist-coverage diff against the vendored copy, then
      overwrites the vendored file. Reminds the operator to update the README SHA.
"""
import csv
import io
import sys
from collections import Counter
from pathlib import Path

import httpx

VENDORED = Path(__file__).resolve().parent.parent / "packages" / "llama" / "src" / "llama" / "data" / "set_breaks.csv"
RAW_URL = ("https://raw.githubusercontent.com/eichblatt/deadstream/"
           "{ref}/timemachine/metadata/set_breaks.csv")


def _coverage(text: str) -> tuple[int, Counter]:
    rows = list(csv.DictReader(io.StringIO(text)))
    return len(rows), Counter(r["artist"] for r in rows)


def _require_artist_column(text: str) -> None:
    """Exit cleanly (message + non-zero status, no traceback) when the CSV has
    no 'artist' column, rather than crashing deep inside _coverage."""
    fields = csv.DictReader(io.StringIO(text)).fieldnames
    if not fields or "artist" not in fields:
        print(f"error: downloaded CSV has no 'artist' column (columns: {fields}); "
              f"refusing to overwrite {VENDORED}", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    ref = sys.argv[1] if len(sys.argv) > 1 else "main"
    url = RAW_URL.format(ref=ref)
    print(f"fetching {url}")
    resp = httpx.get(url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    new_text = resp.text
    _require_artist_column(new_text)

    old_text = VENDORED.read_text(encoding="utf-8") if VENDORED.exists() else ""
    old_n, old_cov = _coverage(old_text) if old_text else (0, Counter())
    new_n, new_cov = _coverage(new_text)

    print(f"rows: {old_n} -> {new_n} ({new_n - old_n:+d})")
    artists = sorted(set(old_cov) | set(new_cov))
    for a in artists:
        o, n = old_cov.get(a, 0), new_cov.get(a, 0)
        if o != n:
            print(f"  {a}: {o} -> {n} ({n - o:+d})")

    VENDORED.write_bytes(resp.content)  # exact upstream bytes (no CRLF rewrite)
    print(f"wrote {VENDORED}")
    print(f"REMINDER: update the pinned commit SHA in {VENDORED.parent / 'README.md'} "
          f"(ref was '{ref}').")


if __name__ == "__main__":
    main()
