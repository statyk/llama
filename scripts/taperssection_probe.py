"""Read-only premise probes for the Taper's Section allowlist (live archive.org).

  python scripts/taperssection_probe.py fields [--creator Phish] [--count 100]
      One scrape page of collection:taperssection items; fraction carrying each field.
  python scripts/taperssection_probe.py garcia [--count 1000]
      Garcia/JGB taperssection items (one page) whose date has two JGB jerrybase
      events and predates 1995-08-09; also counts jerrybase rows on dates whose
      title/description names another act.
  python scripts/taperssection_probe.py lineage [--work DIR]
      Scrape every exact-creator "Phish" taperssection item (cached under --work), compare
      today's scoring.lineage_class with ts_rules.classify, and write lineage.md and
      lineage-dates.csv into the evidence dir.
  python scripts/taperssection_probe.py dates [--work DIR]
      date_disagrees rate per survey artist (exact-creator filtered).
`fields` and `garcia` write nothing; `lineage` and `dates` cache raw scrapes under --work
(outside the repo) and `lineage` writes the evidence files.
"""
import argparse
import csv
import json
import random
import re
import sys
import tempfile
import time
from pathlib import Path

from llama import jerrybase, ts_rules
from llama.models import RecordingSummary
from llama.scoring import lineage_class as today_class
from llama.taperssection import norm_creator
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
    creator starts with `creator` after norm_creator folding (80% of the page)."""
    params = {"q": query, "fields": ",".join(fields), "count": count}
    if cursor:
        params["cursor"] = cursor
    for attempt in range(tries):
        data = client._get(SCRAPE_URL, params).json()
        items = data.get("items", [])
        ok = bool(items) and (creator is None or sum(norm_creator(str(d.get("creator", ""))).startswith(norm_creator(creator)) for d in items) >= 0.8 * len(items))
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


# ---------------------------------------------------------------- Checkpoint A
EVIDENCE = Path(__file__).resolve().parent.parent / "docs/superpowers/2026-11-09-taperssection-evidence"
DEFAULT_WORK = Path("/private/tmp/claude-501/cpa-probe-work")
SCRAPE_FIELDS = ["identifier", "creator", "date", "title", "description", "source",
                 "lineage", "addeddate", "downloads"]
SURVEY = ["Phish", "Jerry Garcia", "Gov't Mule", "Dave Matthews Band", "Trey Anastasio",
          "Trey Anastasio Band", "Pavement", "Medeski Martin & Wood", "Allman Brothers Band",
          "Black Crowes", "Wilco", "Warren Haynes", "Neil Young & Crazy Horse", "Sonic Youth",
          "Primus", "Bruce Hornsby", "Pearl Jam", "Mike Gordon", "Nine Inch Nails"]
SEED = 20261109


def scrape_creator(creator: str, work: Path) -> list[dict]:
    """All collection:taperssection docs for creator (fuzzy), cached raw under `work`."""
    work.mkdir(parents=True, exist_ok=True)
    cache = work / ("scrape-" + re.sub(r"[^a-z0-9]+", "-", creator.lower()).strip("-") + ".json")
    if cache.exists():
        return json.loads(cache.read_text())
    q = f'collection:taperssection AND creator:"{creator}"'
    with tempfile.TemporaryDirectory() as td:
        c = IAClient(Path(td))
        data = _page(c, q, SCRAPE_FIELDS, 1000, creator)
        total = data.get("total")
        items = list(data.get("items", []))
        while data.get("cursor") and len(items) < (total or 0):
            data = _page(c, q, SCRAPE_FIELDS, 1000, creator, cursor=data["cursor"])
            items += data.get("items", [])
    seen, out = set(), []
    for d in items:
        if d["identifier"] not in seen:
            seen.add(d["identifier"])
            out.append(d)
    print(f"{creator}: total={total} fetched={len(items)} unique={len(out)}", file=sys.stderr)
    cache.write_text(json.dumps(out))
    return out


def exact_recs(creator: str, docs: list[dict]) -> list[RecordingSummary]:
    want = norm_creator(creator)
    recs = []
    for d in docs:
        cr = d.get("creator")
        vals = cr if isinstance(cr, list) else [cr]
        if not any(isinstance(v, str) and norm_creator(v) == want for v in vals):
            continue
        dl = d.get("downloads")
        recs.append(RecordingSummary(
            identifier=d["identifier"], title=str(d.get("title") or ""),
            date=(str(d["date"])[:10] if d.get("date") else None),
            description=_s(d.get("description")), creator=_s(cr if isinstance(cr, str) else (cr or [None])[0]),
            addeddate=_s(d.get("addeddate")), source=_s(d.get("source")), lineage=_s(d.get("lineage")),
            downloads=int(dl) if str(dl).isdigit() else 0))
    return recs


def _s(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, list):
        v = " ".join(str(x) for x in v)
    return str(v)


def today_of(r: RecordingSummary) -> str:
    return today_class(r.identifier, {"lineage": r.lineage or "", "source": r.source or "", "title": r.title})


def group_by_date(recs):
    g: dict[str, list[RecordingSummary]] = {}
    for r in recs:
        g.setdefault(r.date or "", []).append(r)
    return g


def ship_status(classes: list[str], rule: str = "a") -> str:
    """Aud-only entry: 'aud' ships; any unknown (none aud) holds under (a), ships aud under (b);
    otherwise no allowed tape (also when no recording remains)."""
    if "aud" in classes:
        return "aud"
    if "unknown" in classes:
        return "unknown-hold" if rule == "a" else "aud"
    return "no-allowed"


def desc_lines(desc: str | None, n: int = 6) -> list[str]:
    if not desc:
        return []
    import html as _h
    t = ts_rules._TAG.sub("", ts_rules._BREAK.sub("\n", desc))
    out = [ln.strip() for ln in _h.unescape(t).splitlines() if ln.strip()]
    return [ln[:700] for ln in out[:n]]


GENERIC = {"omni", "bk", "mic", "mics"}


def _fields(r):
    """(name, text) evidence fields, as classify reads them."""
    out = [("identifier", r.identifier), ("title", r.title), ("source", r.source or ""),
           ("lineage", r.lineage or "")]
    out += [("source-line", ln) for ln in ts_rules.source_lines(r.description)]
    return out


def lexicon_hits(recs):
    """word -> list of identifiers it fired on, mirroring classify's token view."""
    hits: dict[str, list[str]] = {}
    sets = {"MIC": ts_rules.MIC_WORDS, "POS": ts_rules.POSITION_WORDS,
            "SBD": ts_rules._SBD_WORDS, "MATRIX": ts_rules._MATRIX_WORDS,
            "FM": ts_rules._FM_WORDS, "WEBCAST": ts_rules._WEBCAST_WORDS}
    for r in recs:
        f = _fields(r)
        all_t = set(); non_id = set(); toks_ordered = []
        for i, (_, t) in enumerate(f):
            tk = ts_rules._tokens(t)
            all_t.update(tk)
            if i:
                non_id.update(tk)
            toks_ordered += tk + ["|"]
        for setname, ws in sets.items():
            for w in ws:
                if setname == "MIC" and w.isdigit():
                    fired = w in non_id
                else:
                    fired = w in all_t
                if fired:
                    hits.setdefault(f"{setname}:{w}", []).append(r.identifier)
        if ts_rules._has_phrase(toks_ordered, {"taper", "tapers"}, {"section"}) or any(
                a == "taper" and b == "s" and c == "section" for a, b, c in zip(toks_ordered, toks_ordered[1:], toks_ordered[2:])):
            hits.setdefault("PHRASE:taper section", []).append(r.identifier)
        nid = []
        for _, t in f[1:]:
            nid += ts_rules._tokens(t) + ["|"]
        if ts_rules._has_phrase(nid, *ts_rules._NAK_MIC):
            hits.setdefault("PHRASE:cm 100/300/700", []).append(r.identifier)
    return hits


def board_as_position(recs):
    """Recordings with an sbd/board/patch/stream marker AND a mic/position word in one field."""
    gear = (ts_rules.MIC_WORDS - ts_rules._NUMERIC_MICS) | ts_rules.POSITION_WORDS
    marks = ts_rules._SBD_WORDS | ts_rules._WEBCAST_WORDS
    out = []
    for r in recs:
        for name, t in _fields(r):
            tk = set(ts_rules._tokens(t))
            m, g = tk & marks, tk & gear
            if m and g:
                out.append((r, name, sorted(m), sorted(g), t[:200]))
                break
    return out


def generic_only(recs):
    out = []
    for r in recs:
        if ts_rules.classify(r) != "aud":
            continue
        toks = []
        non_id = set()
        for i, (_, t) in enumerate(_fields(r)):
            tk = ts_rules._tokens(t); toks += tk + ["|"]
            if i:
                non_id.update(tk)
        s = set(toks) - ts_rules.DECK_WORDS
        mics = (s & (ts_rules.MIC_WORDS - ts_rules._NUMERIC_MICS)) | ((non_id - ts_rules.DECK_WORDS) & ts_rules._NUMERIC_MICS)
        ev = mics | (s & ts_rules.POSITION_WORDS)
        if ev and ev <= GENERIC:
            out.append((r, sorted(ev)))
    return out


def cmd_lineage(a) -> int:
    work = Path(a.work)
    docs = scrape_creator("Phish", work)
    recs = exact_recs("Phish", docs)
    dated = [r for r in recs if r.date]
    print(f"scraped {len(docs)} docs; exact-creator Phish {len(recs)}; with date {len(dated)}", file=sys.stderr)
    g = group_by_date(dated)
    ndates = len(g)
    T = {r.identifier: today_of(r) for r in recs}
    C = {r.identifier: ts_rules.classify(r) for r in recs}
    DD = {r.identifier: ts_rules.date_disagrees(r) for r in recs}

    # per-recording csv (covers the per-date tables)
    with open(EVIDENCE / "lineage-dates.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "identifier", "today_class", "classify_class", "date_disagrees"])
        for d in sorted(g):
            for r in sorted(g[d], key=lambda r: r.identifier):
                w.writerow([d, r.identifier, T[r.identifier], C[r.identifier], int(DD[r.identifier])])

    def dclasses(d, m, drop=False):
        return [m[r.identifier] for r in g[d] if not (drop and DD[r.identifier])]

    # (ii) coverage. "unknown under today's rule" = no recording of the date has class
    # aud/sbd/matrix (today's lineage_class never returns fm); placed = classify gives some
    # recording a non-unknown class.
    unk_today = [d for d in g if all(c == "unknown" for c in dclasses(d, T))]
    placed = [d for d in unk_today if any(c != "unknown" for c in dclasses(d, C))]
    placed_aud = [d for d in unk_today if "aud" in dclasses(d, C)]
    n_unk_cls = [d for d in g if all(c == "unknown" for c in dclasses(d, C))]
    from collections import Counter
    st_today = Counter(ship_status(dclasses(d, T)) for d in g)
    st_cls = Counter(ship_status(dclasses(d, C)) for d in g)
    st_cls_dd = Counter(ship_status(dclasses(d, C, True)) for d in g)
    st_b = Counter(ship_status(dclasses(d, C), "b") for d in g)
    st_b_dd = Counter(ship_status(dclasses(d, C, True), "b") for d in g)
    cls_counts = Counter(C.values()); t_counts = Counter(T.values())
    # (iv)
    dropped = [r for r in dated if DD[r.identifier]]
    touched = {r.date for r in dropped}
    emptied = [d for d in g if all(DD[r.identifier] for r in g[d])]
    pct = lambda n, d: f"{n}/{d} = {100 * n / max(d, 1):.1f}%"

    L = []
    L.append("# Phish lineage classifier measurement (Checkpoint A, Step 1)\n")
    L.append("Generated by `./.venv/bin/python scripts/taperssection_probe.py lineage` (live scrape, cached under "
             f"`{work}`). HEAD classifier: `ts_rules.classify` / `date_disagrees`, RULE currently 'a'.\n")
    L.append("## Catalogue\n")
    L.append(f"- scraped docs for `collection:taperssection AND creator:\"Phish\"`: {len(docs)} (unique identifiers)")
    L.append(f"- exact creator (`norm_creator == 'phish'`): {len(recs)} recordings; {len(dated)} with a date; **{ndates} distinct dates**")
    L.append(f"- today's `scoring.lineage_class` over recordings: {dict(t_counts)}")
    L.append(f"- `ts_rules.classify` over recordings: {dict(cls_counts)}\n")
    L.append("## (i) Per-date classes\n")
    L.append("Per recording, grouped by date: [lineage-dates.csv](lineage-dates.csv) "
             "(columns date, identifier, today_class, classify_class, date_disagrees). "
             f"{len(recs)} rows.\n")
    L.append("## (ii) Coverage\n")
    L.append("Definition: a date is **unknown under today's rule** when no recording on it has class aud, sbd or matrix "
             "(`scoring.lineage_class` returns only aud/sbd/matrix/unknown; it has no fm class). "
             "A date is **placed** by `classify` when at least one recording gets a class other than unknown "
             "(aud, sbd, matrix, fm or webcast); 'placed aud' when one gets aud.\n")
    L.append(f"- dates unknown under today's rule: {pct(len(unk_today), ndates)} (spec baseline: 1,502 of 1,882)")
    L.append(f"- of those, placed by `classify` (any class): **{pct(len(placed), len(unk_today))}**")
    L.append(f"- of those, placed aud: {pct(len(placed_aud), len(unk_today))}")
    L.append(f"- dates still all-unknown under `classify`: {pct(len(n_unk_cls), ndates)}\n")
    L.append("### Aud-only entry, ship status per date\n")
    L.append("Status: `aud` = at least one aud recording (ships aud); `unknown-hold` = no aud but an unknown recording "
             "(holds for review under rule (a)); `no-allowed` = only forbidden classes (or nothing left). "
             "Under rule (b), unknown reads as aud. Spec baseline for today's rule: 190 aud, 190 no allowed tape, 1,502 unknown of 1,882.\n")
    L.append("| scenario | aud | unknown-hold | no-allowed |")
    L.append("|---|---|---|---|")
    for name, c in [("today's lineage_class, rule (a)", st_today), ("classify, rule (a), before date check", st_cls),
                    ("classify, rule (a), after date check", st_cls_dd), ("classify, rule (b), before date check", st_b),
                    ("classify, rule (b), after date check", st_b_dd)]:
        L.append(f"| {name} | {c['aud']} | {c['unknown-hold']} | {c['no-allowed']} |")
    L.append(f"\n(Total dates {ndates}. Dates emptied by the date check are counted as no-allowed in the after-check rows.)\n")

    # (iii) sample
    rng = random.Random(SEED)
    sample = rng.sample(sorted(g), min(50, ndates))
    L.append(f"## (iii) Random sample of 50 dates (seed {SEED}, `random.Random(seed).sample(sorted(dates), 50)`)\n")
    L.append("Each recording: identifier, title, `source`, today's class, `classify` class, source lines, first ~6 non-empty "
             "description lines (HTML stripped), blank `label:`.\n")
    for i, d in enumerate(sample, 1):
        L.append(f"### {i}. {d}\n")
        for r in sorted(g[d], key=lambda r: r.identifier):
            L.append(f"- **{r.identifier}**")
            L.append(f"  - title: {r.title}")
            L.append(f"  - source field: {r.source!r}")
            L.append(f"  - today: {T[r.identifier]} | classify: {C[r.identifier]} | date_disagrees: {DD[r.identifier]}")
            sl = ts_rules.source_lines(r.description)
            L.append(f"  - source lines: {sl if sl else '(none)'}")
            dl = desc_lines(r.description)
            L.append("  - description (first lines):")
            for ln in dl:
                L.append(f"    > {ln}")
            if not dl:
                L.append("    > (no description)")
            L.append("  - label:")
        L.append("")

    # (iv)
    L.append("## (iv) date_disagrees drop count\n")
    L.append(f"- recordings dropped: {pct(len(dropped), len(dated))}")
    L.append(f"- dates touched: {pct(len(touched), ndates)}")
    L.append(f"- dates emptied (every recording dropped): {pct(len(emptied), ndates)}")
    L.append("- first 15 dropped (identifier, date, title):")
    for r in dropped[:15]:
        L.append(f"  - {r.identifier} | {r.date} | {r.title}")
    L.append("")

    # (v)
    hits = lexicon_hits(recs)
    L.append("## (v) Lexicon hit counts (recordings fired on, 3 example identifiers)\n")
    L.append("Token view mirrors `classify`: identifier, title, source, lineage, source lines; purely numeric mic models count outside the identifier only. A word fires on a recording regardless of which class wins.\n")
    L.append("| word | recordings | examples |")
    L.append("|---|---|---|")
    for k, v in sorted(hits.items(), key=lambda kv: (kv[0].split(":")[0], -len(kv[1]), kv[0])):
        L.append(f"| {k} | {len(v)} | {', '.join(v[:3])} |")
    zero = [f"{n}:{w}" for n, ws in (("MIC", ts_rules.MIC_WORDS), ("POS", ts_rules.POSITION_WORDS)) for w in sorted(ws) if f"{n}:{w}" not in hits]
    L.append(f"\nMIC/POSITION words that fired on zero Phish recordings ({len(zero)}): {', '.join(zero)}\n")
    bp = board_as_position(recs)
    only_board = [x for x in bp if "board" in x[2] and not (set(x[2]) - {"board"})]
    L.append("### Board-as-position candidates\n")
    L.append(f"A marker (sbd/soundboard/board/patch/patched/webcast/stream words) and a mic or position word in the same field: "
             f"**{len(bp)} recordings**; of those, marker is only the word `board`: **{len(only_board)}**. Classes of all {len(bp)} under classify: {dict(Counter(C[x[0].identifier] for x in bp))}.\n")
    show = only_board[:15] + [x for x in bp if x not in only_board][:max(0, 15 - len(only_board[:15]))]
    L.append("Examples (board-only first), showing identifier, field, matched markers/gear, text:")
    for r, name, m, gw, t in show[:15]:
        L.append(f"- {r.identifier} [{name}] markers={m} gear={gw} class={C[r.identifier]} :: {t}")
    L.append("")
    go = generic_only(recs)
    L.append("### Aud only via generic tokens (omni, bk, mic, mics)\n")
    L.append(f"**{len(go)} recordings** are classified aud with no evidence beyond those tokens "
             f"(by token: {dict(Counter(t for _, ev in go for t in ev))}). Examples:")
    for r, ev in go[:15]:
        L.append(f"- {r.identifier} tokens={ev} title={r.title!r} source={r.source!r}")
    L.append("")
    inline = [r for r in recs if r.description and re.search(r"\bsource\s*:", r.description, re.I)
              and not ts_rules.source_lines(r.description)]
    L.append("### Descriptions with a `Source:` that `source_lines` misses\n")
    L.append(f"{len(inline)} of {len(recs)} recordings have `Source:` somewhere in the description but no line "
             "that begins with it (the source text sits inside a longer line, typically a description with no line breaks), "
             f"so `classify` cannot read it. Classes of those under classify: {dict(Counter(C[r.identifier] for r in inline))}. "
             "Examples: " + ", ".join(r.identifier for r in inline[:5]) + "\n")
    (EVIDENCE / "lineage.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:40]))
    return 0


def cmd_dates(a) -> int:
    work = Path(a.work)
    rows = ["| artist | exact-creator items | dated | date_disagrees | rate | dates | dates emptied |",
            "|---|---|---|---|---|---|---|"]
    for name in SURVEY:
        docs = scrape_creator(name, work)
        recs = exact_recs(name, docs)
        dated = [r for r in recs if r.date]
        dd = [r for r in dated if ts_rules.date_disagrees(r)]
        g = group_by_date(dated)
        emptied = sum(1 for d in g if all(ts_rules.date_disagrees(r) for r in g[d]))
        rows.append(f"| {name} | {len(recs)} | {len(dated)} | {len(dd)} | {100 * len(dd) / max(len(dated), 1):.1f}% | {len(g)} | {emptied} |")
        print(rows[-1], file=sys.stderr)
    print("\n".join(rows))
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
    for n in ("lineage", "dates"):
        x = sub.add_parser(n)
        x.add_argument("--work", default=str(DEFAULT_WORK))
    a = p.parse_args(argv)
    return {"fields": cmd_fields, "garcia": cmd_garcia, "lineage": cmd_lineage, "dates": cmd_dates}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
