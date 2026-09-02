"""Census of pure-4-digit tag titles across the archive.org metadata cache
(evidence for the `is_real_title` numeric-title widening in titles.py).

Manual, read-only diagnostic (never run by the pipeline, never writes
anything under the cache root). Walks every cached item, runs the REAL
`llama.junk.filter_files` and `llama.titles.clean_tag_titles` over its file
list (delivery format preference: mp3 then flac, llama's own
`FORMAT_BY_AUDIO` order), and reports:

  - how many cleaned tag titles are a bare 4-digit string (`^\\d{4}$`),
    per item and in total, and their distinct values
  - items carrying >=2 such titles on one tape (the STOP condition named in
    the Task 2 brief: two-or-more pure-4-digit titles on one item is the
    shape of a taper stamping every file with the recording's own year, not
    of a real numeric song title)
  - for every pure-4-digit title, whether it equals the item's OWN
    `metadata.year` (a strong, cheap signal it is a date stamp rather than a
    song title -- llama never guesses song identity, so this is read-only
    corroborating evidence, not a verdict)
  - how many items would cross `gather._RECOVER_BELOW` (0.5) or move to/from
    1.0 in `title_fraction` if a bare 4-digit title counted as real

Usage:
  ./.venv/bin/python scripts/numeric_title_census.py [cache_dir]
      cache_dir defaults to the iacache corpus this repo's other census
      scripts measure against:
      /Users/shawn/projects/llama-setlist-analysis/iacache
      (falls back to ~/.llama/cache if that path does not exist).
      READ-ONLY: only ever opened for reading.

  --sample N   print up to N hand-checkable pure-4-digit-title rows
               (identifier, title, item year, own-year match) (default 25)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.stages.gather import _RECOVER_BELOW
from llama.titles import clean_tag_titles, is_real_title, title_fraction

IACACHE = Path("/Users/shawn/projects/llama-setlist-analysis/iacache")
LLAMA_CACHE = Path.home() / ".llama" / "cache"

_PURE_4DIGIT = re.compile(r"^\d{4}$")


def _item_year(metadata: dict) -> str | None:
    y = metadata.get("year")
    if isinstance(y, str) and re.fullmatch(r"\d{4}", y):
        return y
    date = metadata.get("date")
    if isinstance(date, str) and re.match(r"^\d{4}", date):
        return date[:4]
    return None


def census(cache_dir: Path, sample_n: int) -> None:
    items_total = 0
    items_with_kept = 0
    pure4_total = 0
    pure4_items: list[tuple[str, list[str], str | None]] = []  # (identifier, titles, item_year)
    distinct_values: Counter = Counter()
    crosses_0_5 = 0
    crosses_1_0 = 0
    two_or_more_items: list[tuple[str, list[str]]] = []
    own_year_matches = 0
    sample_rows: list[tuple[str, str, str | None, bool]] = []

    for path in sorted(cache_dir.glob("*.json")):
        items_total += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        files = data.get("files") or []
        metadata = data.get("metadata") or {}
        identifier = metadata.get("identifier", path.stem)
        item_year = _item_year(metadata)

        kept: list[dict] = []
        for fmt_key in ("mp3", "flac"):
            k, _excluded, _ordering = filter_files(files, FORMAT_BY_AUDIO[fmt_key])
            if k:
                kept = k
                break
        if not kept:
            continue
        items_with_kept += 1

        titles = clean_tag_titles(kept)
        pure4 = [t for t in titles if _PURE_4DIGIT.match(t)]
        if pure4:
            pure4_total += len(pure4)
            pure4_items.append((identifier, pure4, item_year))
            for v in pure4:
                distinct_values[v] += 1
            if len(pure4) >= 2:
                two_or_more_items.append((identifier, pure4))
            for v in pure4:
                matches_own_year = item_year is not None and v == item_year
                if matches_own_year:
                    own_year_matches += 1
                if len(sample_rows) < sample_n:
                    sample_rows.append((identifier, v, item_year, matches_own_year))

        old_frac = title_fraction(titles)
        new_titles_real = [is_real_title(t) or bool(_PURE_4DIGIT.match(t)) for t in titles]
        new_frac = (sum(new_titles_real) / len(titles)) if titles else 0.0
        if pure4:
            old_side = old_frac >= _RECOVER_BELOW
            new_side = new_frac >= _RECOVER_BELOW
            if old_side != new_side:
                crosses_0_5 += 1
            old_is_1 = old_frac == 1.0
            new_is_1 = new_frac == 1.0
            if old_is_1 != new_is_1:
                crosses_1_0 += 1

    print(f"# scripts/numeric_title_census.py (2026-09-02)")
    print(f"# corpus: {cache_dir}")
    print(f"items_total={items_total} items_with_kept_files={items_with_kept}")
    print(f"items_with_pure4_tag_title={len(pure4_items)} pure4_tag_titles_total={pure4_total}")
    print(f"distinct_pure4_values={len(distinct_values)}: "
          + ", ".join(f"{v}x{n}" for v, n in distinct_values.most_common()))
    print(f"items_with_2_or_more_pure4_titles={len(two_or_more_items)}")
    for ident, vals in two_or_more_items:
        print(f"  {ident}: {vals}")
    print(f"pure4_titles_equal_to_own_item_metadata_year={own_year_matches} / {pure4_total}")
    print(f"title_fraction crosses gather._RECOVER_BELOW (0.5)={crosses_0_5}")
    print(f"title_fraction crosses to/from 1.0={crosses_1_0}")
    print(f"sample (up to {sample_n}) identifier, title, item_year, matches_own_year:")
    for ident, v, year, matches in sample_rows:
        print(f"  {ident}\t{v}\t{year}\t{matches}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cache_dir", nargs="?", default=None)
    parser.add_argument("--sample", type=int, default=25)
    args = parser.parse_args()
    if args.cache_dir:
        cache_dir = Path(args.cache_dir).expanduser()
    elif IACACHE.exists():
        cache_dir = IACACHE
    else:
        cache_dir = LLAMA_CACHE
    census(cache_dir, args.sample)


if __name__ == "__main__":
    main()
