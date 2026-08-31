"""Census of Track.title_source values across the live show library.

Manual, read-only diagnostic (never run by the pipeline, never writes
anything under the workspace root). Walks every shows/*/show.json and counts
how each track's title got resolved -- the source data for the "MEASURED
DEAD" provenance claim about the whole-tape setlist rung in titles.py.

Usage:
  python scripts/title_source_census.py [root]
      root defaults to ~/.llama (llama's DEFAULT_ROOT). READ-ONLY: only
      opens show.json files under root, never writes there.
"""
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".llama"


def census(root: Path) -> tuple[int, Counter]:
    """Read-only: return (n_shows, Counter of title_source -> track count)
    over every shows/*/show.json under root. Malformed or unreadable
    show.json files are skipped rather than crashing the whole census."""
    counts: Counter = Counter()
    n_shows = 0
    for show_json in sorted(root.glob("shows/*/show.json")):
        try:
            data = json.loads(show_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        n_shows += 1
        for t in data.get("tracks", []):
            counts[t.get("title_source", "?")] += 1
    return n_shows, counts


def main() -> None:
    root = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_ROOT
    n_shows, counts = census(root)
    n_tracks = sum(counts.values())
    print(f"shows={n_shows} tracks={n_tracks}")
    for source, n in counts.most_common():
        print(f"  {source} {n}")


if __name__ == "__main__":
    main()
