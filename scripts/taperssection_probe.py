"""Read-only premise probes for the Taper's Section allowlist (live archive.org).

  python scripts/taperssection_probe.py fields [--creator Phish] [--count 100]
      One scrape page of collection:taperssection items; fraction carrying each field.
  python scripts/taperssection_probe.py garcia [--count 1000]
      Garcia/JGB taperssection items (one page) whose date has two JGB jerrybase
      events and predates 1995-08-09; also counts jerrybase rows on dates whose
      title/description names another act.
Writes nothing; the cache dir is a temp dir.
"""
import argparse
import re
import sys
import tempfile
import time
from pathlib import Path

from llama import jerrybase
from llama.ia_client import SCRAPE_URL, IAClient

FIELDS = ["identifier", "creator", "addeddate", "source", "lineage", "downloads",
          "date", "title", "description"]
OTHER_ACTS = re.compile(r"legion of mary|acoustic|grisman|reconstruction|old and in the way|"
                        r"garcia.{0,3}saunders|saunders", re.I)


def _page(client: IAClient, query: str, fields: list[str], count: int,
          creator: str | None = None, tries: int = 12, cursor: str | None = None) -> dict:
    """One scrape page. The scrape endpoint was measured (2026-11-09) answering
    {"total": 0} for valid queries and, once, a different query's page (the
    whole collection, filter ignored), so retry until total > 0 and every item's
    creator starts with `creator` (80% of the page)."""
    params = {"q": query, "fields": ",".join(fields), "count": count}
    if cursor:
        params["cursor"] = cursor
    for attempt in range(tries):
        data = client._get(SCRAPE_URL, params).json()
        items = data.get("items", [])
        ok = bool(items) and (creator is None or sum(str(d.get("creator", "")).startswith(creator) for d in items) >= 0.8 * len(items))
        print(f"scrape attempt {attempt + 1}: total={data.get('total')} items={len(items)} ok={ok}",
              file=sys.stderr)
        if ok:
            return data
        time.sleep(10)
    raise SystemExit(f"scrape never served a consistent page for {query!r}")


def cmd_fields(a) -> int:
    with tempfile.TemporaryDirectory() as td:
        c = IAClient(Path(td))
        q = f'collection:taperssection AND creator:"{a.creator}"'
        data = _page(c, q, FIELDS, a.count, a.creator)
        items = list(data.get("items", []))
        for _ in range(a.pages - 1):
            if not data.get("cursor"):
                break
            data = _page(c, q, FIELDS, a.count, a.creator, cursor=data["cursor"])
            items += data.get("items", [])
    print(f"query: {q}\ntotal={data.get('total')} page={len(items)}")
    for f in FIELDS:
        n = sum(1 for d in items if d.get(f) not in (None, "", []))
        print(f"{f:12s} {n}/{len(items)} = {n / max(len(items), 1):.0%}")
    return 0


def cmd_garcia(a) -> int:
    with tempfile.TemporaryDirectory() as td:
        c = IAClient(Path(td))
        q = 'collection:taperssection AND creator:"Jerry Garcia"'
        data = _page(c, q, FIELDS, a.count, "Jerry Garcia")
        items = list(data.get("items", []))
        for _ in range(a.pages - 1):
            if not data.get("cursor"):
                break
            data = _page(c, q, FIELDS, a.count, "Jerry Garcia", cursor=data["cursor"])
            items += data.get("items", [])
    print(f"query: {q}\ntotal={data.get('total')} fetched={len(items)}")
    n_jgb = n_two = n_other = 0
    terms: dict[str, int] = {}
    for d in items:
        date = str(d.get("date", ""))[:10]
        ev = jerrybase.lookup("Jerry Garcia Band", date)
        if not ev:
            continue
        n_jgb += 1
        text = f"{d.get('title', '')} {d.get('description', '')}"
        hit = OTHER_ACTS.search(text)
        other = bool(hit)
        if hit:
            k = hit.group(0).lower()
            terms[k] = terms.get(k, 0) + 1
        n_other += other
        if len(ev) > 1 and date < "1995-08-09":
            n_two += 1
            if a.verbose:
                print(f"TWO-EVENT {d['identifier']} {date} src={str(d.get('source', ''))[:60]!r}")
        if other:
            print(f"OTHER-ACT {d['identifier']} {date} title={d.get('title')!r}")
    print("other-act terms:", terms)
    print(f"items with a JGB jerrybase row: {n_jgb}; naming another act: {n_other}; "
          f"two-event pre-1995-08-09: {n_two}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fields")
    f.add_argument("--creator", default="Phish")
    f.add_argument("--count", type=int, default=100)
    f.add_argument("--pages", type=int, default=1)
    g = sub.add_parser("garcia")
    g.add_argument("--count", type=int, default=1000)
    g.add_argument("--pages", type=int, default=2)
    g.add_argument("--verbose", action="store_true")
    a = p.parse_args(argv)
    return {"fields": cmd_fields, "garcia": cmd_garcia}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
