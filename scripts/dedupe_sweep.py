"""Corpus-wide sweep for the `filter_files` duplicate-listing dedupe (Task 1,
2026-09-02-sibling-title-transfer). Manual, read-only diagnostic (never run
by the pipeline, never writes anything under the workspace root).

Some archive.org items list every track twice - once at top level, once
under an <identifier>/ prefix - with identical durations and a title on only
one copy. `junk.filter_files` was fixed to collapse these
(`_dedupe_duplicate_listings`, excluded reason "duplicate-listing"). This
touches every `filter_files` consumer (gather, junk stats, m3u), so the fix
ships gated on this sweep: it runs the OLD (pre-fix) and NEW (current)
`filter_files` over every cached item/format and prints every item whose
kept set actually changes, so each change can be hand-checked before the fix
is trusted corpus-wide.

The OLD behaviour is not reimplemented here - it is the real pre-fix
`junk.py` source, loaded straight out of git history
(98d752ab36b7370e8ec042fffe5a76c95409dfed, the parent of the dedupe commit)
via importlib, so this script calls the actual old code, not a paraphrase of
it. The NEW behaviour is the current `llama.junk.filter_files`, imported
normally.

Usage:
  ./.venv/bin/python scripts/dedupe_sweep.py [--cache DIR] [--limit N]
                                              [--progress N]

  --cache DIR    archive.org metadata cache (default ~/.llama/cache).
                 READ-ONLY: only ever opened for reading.
  --limit N      stop after N cached items (smoke runs).
  --progress N   emit a progress line to stderr every N items.

Prints one line per (item, format) whose kept set changed, then a summary.
"""
import argparse
import importlib.util
import subprocess
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OLD_COMMIT = "98d752ab36b7370e8ec042fffe5a76c95409dfed"
DEFAULT_CACHE = Path.home() / ".llama" / "cache"
FORMATS = ("mp3", "flac")


def _load_old_junk() -> types.ModuleType:
    """Load the real pre-fix junk.py straight from git history (the commit
    before the dedupe fix), so OLD behaviour is the actual old code, not a
    reimplementation of it."""
    src = subprocess.run(
        ["git", "show", f"{OLD_COMMIT}:packages/llama/src/llama/junk.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    spec = importlib.util.spec_from_loader("_old_junk", loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(src, f"<git:{OLD_COMMIT}:junk.py>", "exec"), mod.__dict__)
    return mod


def load_items(cache_dir: Path, limit: int | None):
    import json

    paths = sorted(cache_dir.glob("md_*.json"))
    if limit is not None:
        paths = paths[:limit]
    for path in paths:
        identifier = path.name[len("md_"):-len(".json")]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        files = data.get("files")
        if not isinstance(files, list):
            continue
        yield identifier, files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--progress", type=int, default=None)
    args = ap.parse_args()

    from llama.junk import FORMAT_BY_AUDIO, filter_files as new_filter_files

    old_junk = _load_old_junk()
    old_filter_files = old_junk.filter_files

    n_items = 0
    n_pairs = 0
    n_changed = 0
    changed_items: set[str] = set()

    for i, (identifier, files) in enumerate(load_items(args.cache, args.limit), start=1):
        n_items += 1
        if args.progress and i % args.progress == 0:
            print(f"... {i} items", file=sys.stderr)
        for fmt_name in FORMATS:
            want = FORMAT_BY_AUDIO[fmt_name]
            old_kept, _, _ = old_filter_files(files, want_format=want)
            new_kept, _, _ = new_filter_files(files, want_format=want)
            n_pairs += 1
            old_names = [f["name"] for f in old_kept]
            new_names = [f["name"] for f in new_kept]
            if old_names == new_names:
                continue
            n_changed += 1
            changed_items.add(identifier)
            dropped = sorted(set(old_names) - set(new_names))
            added = sorted(set(new_names) - set(old_names))
            print(
                f"{identifier}\t{fmt_name}\tbefore={len(old_names)}\tafter={len(new_names)}"
                f"\tdropped={dropped}\tadded={added}"
            )

    print(
        f"# items={n_items} item/format pairs={n_pairs} "
        f"changed pairs={n_changed} changed items={len(changed_items)}",
        file=sys.stderr,
    )
    print(
        f"# items={n_items} item/format pairs={n_pairs} "
        f"changed pairs={n_changed} changed items={len(changed_items)}"
    )


if __name__ == "__main__":
    main()
