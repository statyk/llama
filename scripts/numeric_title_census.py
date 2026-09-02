"""Census of pure-4-digit tag titles across the archive.org metadata cache
(evidence for the `is_real_title` numeric-title widening in titles.py).

Manual, read-only diagnostic (never run by the pipeline, never writes
anything under the cache root). Walks every cached item and, for BOTH
delivery-format preference lists (`llama.junk.FORMAT_BY_AUDIO["mp3"]` and
`["flac"]`), runs the REAL `llama.junk.filter_files` and
`llama.titles.clean_tag_titles` over the resulting kept set, then
reimplements `llama.stages.gather._recover_format_titles`'s logic locally
(same algorithm, swappable is-real-title predicate) to also surface a title
that only a DIFFERENT lossless-title format carries when the delivered
format's own tags are too sparse.

**Corrected 2026-09-02, fix round 1**: the first cut of this script tried
`("mp3", "flac")` and broke on the first format with a non-empty KEPT set --
which hid any pure-4-digit title carried only by a format that lost that
race but still has tags (`turkuaz2018-01-18`: mp3 kept 13 files, all
untagged; its flac copy is fully tagged, including "1662", and would never
be checked once mp3's 13-file kept set short-circuited the loop). This cut
checks both formats independently and never breaks early.

**Also corrected**: the `title_fraction`-crossing arm now uses a FROZEN
letters-only predicate for "old" (rather than calling the live
`llama.titles.is_real_title`, which -- once the widening it measures has
landed -- makes "old" and "new" the same function and silently pins every
crossing counter to 0, a defect this script shipped with in its first cut).
Both `_old_is_real_title`/`_new_is_real_title` below are local and frozen;
neither reads `llama.titles.is_real_title`, so this script's own numbers stay
reproducible regardless of what titles.py currently ships.

Reports: pure-4-digit tag-title count and distinct values (direct tags from
either delivery format, plus recovered titles when recovery would fire);
items carrying >=2 such titles on one item (the STOP condition named in the
Task 2 brief); for every pure-4-digit title, whether it equals the item's
own `metadata.year` (a cheap, read-only corroborating signal that it's a
taper's date stamp rather than a song title -- never a verdict on its own);
and how many items would cross `gather._RECOVER_BELOW` (0.5) or move to/from
1.0 in `title_fraction`, on either delivery path, if a bare 4-digit title
counted as real.

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

from llama.junk import FORMAT_BY_AUDIO, LOSSLESS_TITLE_FORMATS, filter_files
from llama.stages.gather import _RECOVER_BELOW, _RECOVER_SIBLING_ABOVE
from llama.titles import clean_tag_titles, sibling_format_titles

IACACHE = Path("/Users/shawn/projects/llama-setlist-analysis/iacache")
LLAMA_CACHE = Path.home() / ".llama" / "cache"

_PURE_4DIGIT = re.compile(r"\d{4}")

_DELIVERY_FORMATS = ("mp3", "flac")


def _old_is_real_title(cleaned: str) -> bool:
    """Frozen copy of the pre-2026-09-02 predicate (letters-only). Never
    imported from titles.py -- see the module docstring's "Also corrected"."""
    return sum(ch.isascii() and ch.isalpha() for ch in cleaned) >= 3


def _new_is_real_title(cleaned: str) -> bool:
    """Frozen copy of the post-widening predicate. Kept independent of
    titles.py for the same reproducibility reason as `_old_is_real_title`."""
    return _old_is_real_title(cleaned) or bool(_PURE_4DIGIT.fullmatch(cleaned))


def _frac(titles: list[str], predicate) -> float:
    return (sum(1 for t in titles if predicate(t)) / len(titles)) if titles else 0.0


def _frozen_recover(files, kept, ordering, predicate):
    """Reimplementation of `gather._recover_format_titles`, parameterized on
    an is-real-title predicate instead of calling the live production one --
    so this script can compute the OLD and NEW recovery outcome independent
    of whichever predicate titles.py currently ships."""
    titles = clean_tag_titles(kept)
    if _frac(titles, predicate) >= _RECOVER_BELOW:
        return None
    for fmt in LOSSLESS_TITLE_FORMATS:
        if fmt == ordering.get("format"):
            continue
        other, _excluded, _ordering2 = filter_files(files, want_format=fmt)
        recovered = sibling_format_titles(kept, other)
        if recovered and _frac(list(recovered.values()), predicate) >= _RECOVER_SIBLING_ABOVE:
            return recovered
    return None


def _item_year(metadata: dict) -> str | None:
    y = metadata.get("year")
    if isinstance(y, str) and re.fullmatch(r"\d{4}", y):
        return y
    date = metadata.get("date")
    if isinstance(date, str) and re.match(r"^\d{4}", date):
        return date[:4]
    return None


def census(cache_dir: Path, sample_n: int, progress_every: int = 250) -> None:
    items_total = 0
    items_with_kept = 0
    item_pure4: dict[str, dict] = {}  # identifier -> {"values": set, "year": str|None, "sources": dict}
    distinct_values: Counter = Counter()
    crosses_0_5: set[str] = set()
    crosses_1_0: set[str] = set()

    for path in sorted(cache_dir.glob("*.json")):
        items_total += 1
        if progress_every and items_total % progress_every == 0:
            print(f"... {items_total} items scanned", file=sys.stderr)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        files = data.get("files") or []
        metadata = data.get("metadata") or {}
        identifier = metadata.get("identifier", path.stem)
        item_year = _item_year(metadata)

        had_kept_any = False
        pure4_here: set[str] = set()
        sources: dict[str, list[str]] = {}

        for fmt_key in _DELIVERY_FORMATS:
            kept, _excluded, ordering = filter_files(files, FORMAT_BY_AUDIO[fmt_key])
            if not kept:
                continue
            had_kept_any = True
            own_titles = clean_tag_titles(kept)
            own_pure4 = [t for t in own_titles if _PURE_4DIGIT.fullmatch(t)]
            if own_pure4:
                pure4_here.update(own_pure4)
                sources.setdefault(f"tags:{fmt_key}", []).extend(own_pure4)

            old_frac = _frac(own_titles, _old_is_real_title)
            new_frac = _frac(own_titles, _new_is_real_title)
            if (old_frac >= _RECOVER_BELOW) != (new_frac >= _RECOVER_BELOW):
                crosses_0_5.add(identifier)
            if (old_frac == 1.0) != (new_frac == 1.0):
                crosses_1_0.add(identifier)

            rec_old = _frozen_recover(files, kept, ordering, _old_is_real_title)
            rec_new = _frozen_recover(files, kept, ordering, _new_is_real_title)
            if (rec_old is not None) != (rec_new is not None):
                # Recovery firing/not-firing IS itself a 0.5-threshold event.
                crosses_0_5.add(identifier)
            if rec_new is not None:
                rec_titles = list(rec_new.values())
                rec_pure4 = [t for t in rec_titles if _PURE_4DIGIT.fullmatch(t)]
                if rec_pure4:
                    pure4_here.update(rec_pure4)
                    sources.setdefault(f"recovered-via:{fmt_key}", []).extend(rec_pure4)
                if rec_old is not None:
                    old_r = _frac(list(rec_old.values()), _old_is_real_title)
                    new_r = _frac(rec_titles, _new_is_real_title)
                    if (old_r == 1.0) != (new_r == 1.0):
                        crosses_1_0.add(identifier)

        if had_kept_any:
            items_with_kept += 1
        if pure4_here:
            item_pure4[identifier] = {"values": sorted(pure4_here), "year": item_year, "sources": sources}
            for v in pure4_here:
                distinct_values[v] += 1

    two_or_more = [(ident, d["values"]) for ident, d in item_pure4.items() if len(d["values"]) >= 2]
    pure4_total = sum(len(d["values"]) for d in item_pure4.values())
    own_year_matches = sum(
        1 for d in item_pure4.values() for v in d["values"] if d["year"] is not None and v == d["year"]
    )

    print(f"# scripts/numeric_title_census.py (2026-09-02, corrected fix round 1)")
    print(f"# corpus: {cache_dir}")
    print(f"items_total={items_total} items_with_kept_files={items_with_kept}")
    print(f"items_with_pure4_tag_title={len(item_pure4)} pure4_tag_titles_total={pure4_total}")
    print(f"distinct_pure4_values={len(distinct_values)}: "
          + ", ".join(f"{v}x{n}" for v, n in distinct_values.most_common()))
    print(f"items_with_2_or_more_pure4_titles={len(two_or_more)}")
    for ident, vals in two_or_more:
        print(f"  {ident}: {vals}")
    print(f"pure4_titles_equal_to_own_item_metadata_year={own_year_matches} / {pure4_total}")
    print(f"title_fraction crosses gather._RECOVER_BELOW (0.5)={len(crosses_0_5)}")
    for ident in sorted(crosses_0_5):
        print(f"  {ident}")
    print(f"title_fraction crosses to/from 1.0={len(crosses_1_0)}")
    for ident in sorted(crosses_1_0):
        print(f"  {ident}")
    print(f"sample (up to {sample_n}) identifier, title, sources, item_year, matches_own_year:")
    shown = 0
    for ident, d in item_pure4.items():
        if shown >= sample_n:
            break
        for v in d["values"]:
            matches = d["year"] is not None and v == d["year"]
            print(f"  {ident}\t{v}\t{d['sources']}\t{d['year']}\t{matches}")
        shown += 1


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
