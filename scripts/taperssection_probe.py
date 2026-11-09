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
  python scripts/taperssection_probe.py variant [--work DIR]
      Re-run coverage (ii) and the ship table under classify_variant (in-line source labels,
      probe-only) and upsert the "Variant: ..." section of lineage.md.
  python scripts/taperssection_probe.py precision [--work DIR]
      Score classify and classify_variant against lineage-labels.csv (hand labels of the 50-date
      sample), fill the label: lines in (iii) and upsert the "Precision (...)" section.
  python scripts/taperssection_probe.py product [--work DIR]
      Coverage, the aud-only ship table and hand-label precision under the PRODUCT
      ts_rules.classify (after Task 2b); upserts the "Task 2b: product classifier after the
      ruling" section of lineage.md (appends it the first time).
  python scripts/taperssection_probe.py dump [--only 1,2] [--chars N]
      Labelling aid: the sample's recordings with full evidence text, classes hidden.
`lineage` rewrites lineage.md whole: re-run `variant` and `precision` after it (the hand-written
"Precision: systematic lexicon errors" and "For the operator" sections must be restored by hand).
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


# ------------------------------------------------- variant: in-line source labels
# Probe-only. The scrape endpoint serves `description` with every line break and tag
# collapsed, so ts_rules.source_lines (line-anchored) sees one line. When a description
# has no line break, this variant splits it at in-line labels instead.
_INLINE_LABEL = re.compile(
    r"(?<![a-z0-9])(?:sources?(?:\s+info(?:rmation)?)?|src|lineage|transfers?)\s*:", re.I)
# The next "Label:"-shaped token: one word (letters/apostrophe) then a colon, not a URL.
_NEXT_LABEL = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z']{0,24}\s*:(?!//)")
SEG_CAP = 250


def inline_source_segments(text: str) -> list[str]:
    """Each in-line source label to the next Label:-shaped token, capped at SEG_CAP chars."""
    out = []
    for m in _INLINE_LABEL.finditer(text):
        rest = text[m.end():m.end() + SEG_CAP]
        nxt = _NEXT_LABEL.search(rest)
        body = rest[:nxt.start()] if nxt else rest
        seg = (m.group(0) + " " + body).strip()
        if body.strip():
            out.append(re.sub(r"\s+", " ", seg))
    return out


def source_lines_variant(description: str | None) -> list[str]:
    """ts_rules.source_lines, except a description with no line break is split at in-line
    labels (a line-start "Source: ..." becomes a capped segment, not the whole text)."""
    if not description:
        return []
    import html as _h
    text = _h.unescape(ts_rules._TAG.sub("", ts_rules._BREAK.sub("\n", description)))
    if "\n" in text.strip():
        return ts_rules.source_lines(description)
    return inline_source_segments(text)


def classify_variant(rec: RecordingSummary) -> str:
    """ts_rules.classify with source_lines swapped for source_lines_variant (probe only)."""
    orig = ts_rules.source_lines
    ts_rules.source_lines = source_lines_variant
    try:
        return ts_rules.classify(rec)
    finally:
        ts_rules.source_lines = orig


def coverage_tables(g, T, M, DD):
    """(coverage dict, ship Counters) for classifier map M against today's map T."""
    from collections import Counter
    dcl = lambda d, m, drop=False: [m[r.identifier] for r in g[d] if not (drop and DD[r.identifier])]
    unk_today = [d for d in g if all(c == "unknown" for c in dcl(d, T))]
    cov = {
        "unk_today": len(unk_today),
        "placed": sum(1 for d in unk_today if any(c != "unknown" for c in dcl(d, M))),
        "placed_aud": sum(1 for d in unk_today if "aud" in dcl(d, M)),
        "all_unknown": sum(1 for d in g if all(c == "unknown" for c in dcl(d, M))),
        "recs": dict(Counter(M.values())),
    }
    ship = {
        "rule (a), before date check": Counter(ship_status(dcl(d, M)) for d in g),
        "rule (a), after date check": Counter(ship_status(dcl(d, M, True)) for d in g),
        "rule (b), before date check": Counter(ship_status(dcl(d, M), "b") for d in g),
        "rule (b), after date check": Counter(ship_status(dcl(d, M, True), "b") for d in g),
    }
    return cov, ship


def upsert_section(md: str, heading: str, body: str) -> str:
    """Replace the `## heading` section (to the next `## ` or EOF), or append it."""
    start = md.find(f"\n## {heading}")
    block = f"\n## {heading}\n\n{body.rstrip()}\n"
    if start < 0:
        return md.rstrip("\n") + "\n" + block
    nxt = md.find("\n## ", start + 4)
    return md[:start] + block + (md[nxt:] if nxt >= 0 else "")


def load_phish(work: Path):
    docs = scrape_creator("Phish", work)
    recs = exact_recs("Phish", docs)
    g = group_by_date([r for r in recs if r.date])
    return docs, recs, g


VARIANT_HEADING = "Variant: in-line source labels (probe-only)"


def cmd_variant(a) -> int:
    _, recs, g = load_phish(Path(a.work))
    T = {r.identifier: today_of(r) for r in recs}
    C = {r.identifier: ts_rules.classify(r) for r in recs}
    V = {r.identifier: classify_variant(r) for r in recs}
    DD = {r.identifier: ts_rules.date_disagrees(r) for r in recs}
    nd = len(g)
    cc, sc = coverage_tables(g, T, C, DD)
    cv, sv = coverage_tables(g, T, V, DD)
    pct = lambda n, d: f"{n}/{d} = {100 * n / max(d, 1):.1f}%"
    nseg = sum(1 for r in recs if source_lines_variant(r.description))
    nsl = sum(1 for r in recs if ts_rules.source_lines(r.description))
    from collections import Counter
    moves = Counter((C[i], V[i]) for i in C if C[i] != V[i])
    L = ["`./.venv/bin/python scripts/taperssection_probe.py variant` (cached scrape). `classify_variant` is "
         "`ts_rules.classify` with `source_lines` replaced by `source_lines_variant`: a description with no line "
         "break (every scraped Phish description: 0 of 11,133 has one) is split at in-line labels "
         "`Source(s)( info):`, `Src:`, `Lineage:`, `Transfer(s):` (case-insensitive, word-anchored); each label runs "
         f"to the next one-word `Label:` token, capped at {SEG_CAP} chars. A description that *starts* with `Source:` "
         "is read by `classify` as one source line spanning the whole description (setlist and notes included); the "
         "variant reads only the capped segment. Product code is unchanged.\n",
         f"- recordings with at least one source line: classify {pct(nsl, len(recs))}; variant {pct(nseg, len(recs))}",
         f"- recording classes: classify {cc['recs']}; variant {cv['recs']}",
         f"- recordings whose class changes (classify -> variant): {sum(moves.values())}: "
         + ", ".join(f"{a}->{b} {n}" for (a, b), n in moves.most_common()) + "\n",
         "### Coverage (ii), side by side\n",
         "| measure | classify | classify_variant |", "|---|---|---|",
         f"| dates unknown under today's rule | {cc['unk_today']} | {cv['unk_today']} |",
         f"| of those, placed (any class) | {pct(cc['placed'], cc['unk_today'])} | {pct(cv['placed'], cv['unk_today'])} |",
         f"| of those, placed aud | {pct(cc['placed_aud'], cc['unk_today'])} | {pct(cv['placed_aud'], cv['unk_today'])} |",
         f"| dates still all-unknown | {pct(cc['all_unknown'], nd)} | {pct(cv['all_unknown'], nd)} |\n",
         "### Aud-only entry, ship status per date, side by side\n",
         f"Total dates {nd}; cells are aud / unknown-hold / no-allowed.\n",
         "| scenario | classify | classify_variant |", "|---|---|---|"]
    for k in sc:
        f = lambda c: f"{c['aud']} / {c['unknown-hold']} / {c['no-allowed']}"
        L.append(f"| {k} | {f(sc[k])} | {f(sv[k])} |")
    md = (EVIDENCE / "lineage.md").read_text()
    (EVIDENCE / "lineage.md").write_text(upsert_section(md, VARIANT_HEADING, "\n".join(L)))
    print("\n".join(L))
    return 0


def cmd_dump(a) -> int:
    """Labelling aid: the 50 sample dates' recordings with full evidence text, classes hidden."""
    import html as _h
    _, recs, g = load_phish(Path(a.work))
    sample = random.Random(SEED).sample(sorted(g), min(50, len(g)))
    for i, d in enumerate(sample, 1):
        if a.only and str(i) not in a.only.split(","):
            continue
        print(f"=== {i}. {d}")
        for r in sorted(g[d], key=lambda r: r.identifier):
            desc = _h.unescape(ts_rules._TAG.sub(" ", r.description or ""))
            desc = re.sub(r"\s+", " ", desc)
            print(f"--- {r.identifier}\n title: {r.title}\n source: {r.source!r} lineage: {r.lineage!r}\n"
                  f" desc: {desc[:a.chars]}")
    return 0


LABELS = EVIDENCE / "lineage-labels.csv"
CLASSES = ["aud", "sbd", "matrix", "fm", "webcast", "unknown"]


def _ev_tokens(r, lines_fn):
    """(all tokens, non-identifier tokens) as classify sees r with the given source_lines."""
    parts = [r.identifier, r.title, r.source or "", r.lineage or "", *lines_fn(r.description)]
    allt, nid = set(), set()
    for i, t in enumerate(parts):
        tk = ts_rules._tokens(t)
        allt.update(tk)
        if i:
            nid.update(tk)
    return allt, nid


def _aud_evidence(r, lines_fn):
    allt, nid = _ev_tokens(r, lines_fn)
    u = allt - ts_rules.DECK_WORDS
    mics = (u & (ts_rules.MIC_WORDS - ts_rules._NUMERIC_MICS)) | ((nid - ts_rules.DECK_WORDS) & ts_rules._NUMERIC_MICS)
    return mics | (u & ts_rules.POSITION_WORDS)


def _markers(r, lines_fn):
    allt, _ = _ev_tokens(r, lines_fn)
    m = ts_rules._SBD_WORDS | ts_rules._MATRIX_WORDS | ts_rules._FM_WORDS | ts_rules._WEBCAST_WORDS
    return allt & m


def _fill_labels(md: str, lab: dict) -> str:
    out, cur = [], None
    for ln in md.split("\n"):
        m = re.match(r"- \*\*(.+)\*\*$", ln)
        if m:
            cur = m.group(1)
        if ln.startswith("  - label:") and cur in lab:
            ln = f"  - label: **{lab[cur][0]}** ({lab[cur][1]})" if lab[cur][1] else f"  - label: **{lab[cur][0]}**"
        out.append(ln)
    return "\n".join(out)


def cmd_precision(a) -> int:
    from collections import Counter
    _, recs, g = load_phish(Path(a.work))
    lab = {row["identifier"]: (row["label"], row["note"]) for row in csv.DictReader(open(LABELS))}
    sample = random.Random(SEED).sample(sorted(g), min(50, len(g)))
    srecs = [r for d in sample for r in sorted(g[d], key=lambda r: r.identifier)]
    missing = [r.identifier for r in srecs if r.identifier not in lab]
    if missing:
        raise SystemExit(f"unlabelled: {missing[:5]}")
    C = {r.identifier: ts_rules.classify(r) for r in srecs}
    V = {r.identifier: classify_variant(r) for r in srecs}
    T = {r.identifier: lab[r.identifier][0] for r in srecs}
    n = len(srecs)
    pct = lambda k, d: f"{k}/{d} = {100 * k / max(d, 1):.1f}%"
    L = [f"Labels: [lineage-labels.csv](lineage-labels.csv) (identifier, label, note), hand-labelled from the full "
         "scraped description, identifier, title and `source` field (metadata API read once, for `phish-02.16.03`). "
         "Labeller was independent: classes were hidden while labelling. A truly undeterminable tape is labelled "
         "`unknown`. A satellite/TV broadcast is labelled `fm` (broadcast). A patchwork of a board tape with "
         "audience fills is labelled `sbd` (it is not an aud-only tape). `./.venv/bin/python "
         "scripts/taperssection_probe.py precision` regenerates this section and fills the `label:` lines in (iii).\n",
         f"- truth over the {n} recordings of the 50 dates: {dict(Counter(T.values()))}\n"]
    for name, M in (("classify", C), ("classify_variant", V)):
        conf = Counter((M[i], T[i]) for i in T)
        L += [f"### Confusion, {name} (rows) vs label (columns)\n",
              "| " + name + " \\ label | " + " | ".join(CLASSES) + " | total |",
              "|---" * (len(CLASSES) + 2) + "|"]
        for c in CLASSES:
            row = [conf[(c, t)] for t in CLASSES]
            if sum(row):
                L.append(f"| {c} | " + " | ".join(str(x) for x in row) + f" | {sum(row)} |")
        said_aud = [i for i in T if M[i] == "aud"]
        false_aud = [i for i in said_aud if T[i] != "aud"]
        said_non = [i for i in T if M[i] in ("sbd", "matrix", "fm", "webcast")]
        false_non = [i for i in said_non if T[i] == "aud"]
        wrong_non = [i for i in said_non if T[i] not in ("aud", M[i])]
        unk = [i for i in T if M[i] == "unknown"]
        unk_t = Counter(T[i] for i in unk)
        unk_non = sum(v for k, v in unk_t.items() if k not in ("aud", "unknown"))
        true_aud = sum(1 for i in T if T[i] == "aud")
        L += ["",
              f"- placed (not unknown): {pct(n - len(unk), n)}",
              f"- **false-aud** (says aud, truth non-aud): {len(false_aud)} of {len(said_aud)} aud calls"
              f" (aud precision {pct(len(said_aud) - len(false_aud), len(said_aud))})"
              + (": " + ", ".join(f"{i} [{T[i]}]" for i in false_aud) if false_aud else ""),
              f"- **false-non-aud** (says sbd/matrix/fm/webcast, truth aud): {len(false_non)} of {len(said_non)} non-aud calls"
              + (": " + ", ".join(f"{i} [{M[i]}]" for i in false_non) if false_non else ""),
              f"- non-aud class wrong within non-aud (e.g. sbd for fm): {len(wrong_non)}"
              + (": " + ", ".join(f"{i} [{M[i]} vs {T[i]}]" for i in wrong_non) if wrong_non else ""),
              f"- aud recall (truly aud tapes it calls aud): {pct(true_aud - sum(1 for i in T if T[i] == 'aud' and M[i] != 'aud'), true_aud)}",
              f"- **unknown under {name}**: {len(unk)}; truth {dict(unk_t)}; truly non-aud (sbd/matrix/fm/webcast): "
              f"**{pct(unk_non, len(unk))}**; truly aud {pct(unk_t['aud'], len(unk))}; undeterminable {unk_t['unknown']}"]
        if unk_non:
            L.append("  - truly non-aud unknowns (rule (b) would ship these as aud): "
                     + "; ".join(f"{i} [{T[i]}: {lab[i][1]}]" for i in unk if T[i] not in ("aud", "unknown")))
        L.append("")

    # per date, aud-only entry
    L += ["### Per date, aud-only entry: would-ship-aud correctness\n",
          "Truth per date: `has-aud` if any recording is labelled aud, else `no-aud`. Predicted status as in (ii), "
          "before the date check. `ships, clean` = every recording the entry would treat as aud is truly aud; "
          "`ships, mixed` = it ships (a true aud exists among them) but one or more treated-as-aud recordings are "
          "truly non-aud (selection could pick it); `ships wrongly` = it ships but no treated-as-aud recording is "
          "truly aud.\n",
          "| classifier, rule | ships, clean | ships, mixed | ships wrongly | holds (truth has-aud) | holds (truth no-aud) | no-allowed (truth has-aud) | no-allowed (truth no-aud) |",
          "|---|---|---|---|---|---|---|---|"]
    detail = []
    for name, M in (("classify", C), ("classify_variant", V)):
        for rule in ("a", "b"):
            cnt = Counter()
            for d in sample:
                ids = [r.identifier for r in g[d]]
                truth = "has-aud" if any(T[i] == "aud" for i in ids) else "no-aud"
                st = ship_status([M[i] for i in ids], rule)
                if st == "aud":
                    as_aud = [i for i in ids if M[i] == "aud" or (rule == "b" and M[i] == "unknown")]
                    good = [i for i in as_aud if T[i] == "aud"]
                    k = "clean" if len(good) == len(as_aud) else ("mixed" if good else "wrong")
                    if k != "clean":
                        detail.append(f"{name} rule ({rule}) {d}: {k}; non-aud treated as aud: "
                                      + ", ".join(f"{i} [{M[i]}->{T[i]}]" for i in as_aud if T[i] != "aud"))
                    cnt[k] += 1
                elif st == "unknown-hold":
                    cnt["hold-" + truth] += 1
                else:
                    cnt["none-" + truth] += 1
                    if truth == "has-aud":
                        detail.append(f"{name} rule ({rule}) {d}: no-allowed but truth has aud: "
                                      + ", ".join(f"{i} [{M[i]}]" for i in ids if T[i] == "aud"))
            L.append(f"| {name}, ({rule}) | {cnt['clean']} | {cnt['mixed']} | {cnt['wrong']} | {cnt['hold-has-aud']} | "
                     f"{cnt['hold-no-aud']} | {cnt['none-has-aud']} | {cnt['none-no-aud']} |")
    truth_dates = Counter("has-aud" if any(T[r.identifier] == "aud" for r in g[d]) else "no-aud" for d in sample)
    L += ["", f"Truth over the 50 dates: {dict(truth_dates)}.", ""]
    L += ["Non-clean dates:"] + [f"- {x}" for x in detail] + [""]

    # board-as-position, generic tokens
    L += ["### Board/SBD as a position, and generic-token-only aud, in the sample\n",
          "Recordings where a board/patch/sbd/stream marker and a mic or position word are both in the evidence "
          "(under either view), with the verdict:\n"]
    for r in srecs:
        for name, fn, M in (("classify", ts_rules.source_lines, C), ("variant", source_lines_variant, V)):
            mk = _markers(r, fn) & (ts_rules._SBD_WORDS | ts_rules._WEBCAST_WORDS)
            ev = _aud_evidence(r, fn)
            if mk and ev:
                ok = "correct" if M[r.identifier] == T[r.identifier] else "WRONG"
                L.append(f"- {r.identifier} ({name}): markers {sorted(mk)}, aud evidence {sorted(ev)[:4]} -> "
                         f"{M[r.identifier]}; label {T[r.identifier]}: {ok} ({lab[r.identifier][1]})")
    L.append("")
    L.append("Recordings called aud on generic tokens only (`omni`, `bk`, `mic`, `mics`):\n")
    found = False
    for r in srecs:
        for name, fn, M in (("classify", ts_rules.source_lines, C), ("variant", source_lines_variant, V)):
            ev = _aud_evidence(r, fn)
            if M[r.identifier] == "aud" and ev and ev <= GENERIC:
                found = True
                ok = "correct" if T[r.identifier] == "aud" else "WRONG"
                L.append(f"- {r.identifier} ({name}): {sorted(ev)}; label {T[r.identifier]}: {ok}")
    if not found:
        L.append("- none in the sample")
    L.append("")

    # every disagreement, for the lexicon review
    L += ["### Every disagreement with the label (excluding unknown calls)\n",
          "| identifier | classify | variant | label | marker / aud evidence (variant view) | note |", "|---|---|---|---|---|---|"]
    for r in srecs:
        i = r.identifier
        if (C[i] not in ("unknown", T[i])) or (V[i] not in ("unknown", T[i])):
            L.append(f"| {i} | {C[i]} | {V[i]} | {T[i]} | {sorted(_markers(r, source_lines_variant))} / "
                     f"{sorted(_aud_evidence(r, source_lines_variant))[:4]} | {lab[i][1]} |")
    L.append("")
    md = (EVIDENCE / "lineage.md").read_text()
    md = _fill_labels(md, lab)
    md = upsert_section(md, f"Precision (hand-labelled, n={n} recordings, 50 dates)", "\n".join(L))
    (EVIDENCE / "lineage.md").write_text(md)
    print("\n".join(L))
    return 0



# ------------------------------------------------- product: the classifier after the 2b ruling
PRODUCT_HEADING = "Task 2b: product classifier after the ruling"
# The probe variant's numbers as recorded in lineage.md ("Variant: ..." and "Precision (...)"),
# measured at c2ac9c1c, before Task 2b changed ts_rules.
VARIANT_RECORDED = {
    "recs": "{'unknown': 2345, 'matrix': 163, 'aud': 7406, 'sbd': 1150, 'fm': 65, 'webcast': 4}",
    "placed": "1113/1237 = 90.0%", "placed_aud": "1077/1237 = 87.1%", "all_unknown": "124/1881 = 6.6%",
    "a_before": "1465 / 191 / 225", "a_after": "1399 / 165 / 317",
    "b_before": "1656 / 0 / 225", "b_after": "1564 / 0 / 317",
    "false_aud": "0 of 152", "false_non_aud": "14 of 47", "wrong_non": "3",
    "aud_recall": "152/217 = 70.0%", "placed_sample": "199/255 = 78.0%",
    "unk": "56; truly non-aud 1/56 = 1.8%; truly aud 51; undeterminable 4",
    "dates_a": "37 / 0 / 0 / 7 / 1 / 1 / 4",
}


def precision_stats(M: dict, T: dict) -> dict:
    """Scores classifier map M against hand labels T (identifier -> class)."""
    from collections import Counter
    said_aud = [i for i in T if M[i] == "aud"]
    said_non = [i for i in T if M[i] in ("sbd", "matrix", "fm", "webcast")]
    unk = [i for i in T if M[i] == "unknown"]
    unk_t = Counter(T[i] for i in unk)
    true_aud = [i for i in T if T[i] == "aud"]
    return {
        "conf": Counter((M[i], T[i]) for i in T),
        "said_aud": said_aud,
        "false_aud": [i for i in said_aud if T[i] != "aud"],
        "said_non": said_non,
        "false_non": [i for i in said_non if T[i] == "aud"],
        "wrong_non": [i for i in said_non if T[i] not in ("aud", M[i])],
        "unk": unk,
        "unk_t": unk_t,
        "unk_non": [i for i in unk if T[i] not in ("aud", "unknown")],
        "recall": (sum(1 for i in true_aud if M[i] == "aud"), len(true_aud)),
    }


def date_outcomes(sample, g, M: dict, T: dict, rule: str = "a"):
    """Per sampled date, aud-only entry, before the date check: counts and non-clean details."""
    from collections import Counter
    cnt, detail = Counter(), []
    for d in sample:
        ids = [r.identifier for r in g[d]]
        truth = "has-aud" if any(T[i] == "aud" for i in ids) else "no-aud"
        st = ship_status([M[i] for i in ids], rule)
        if st == "aud":
            as_aud = [i for i in ids if M[i] == "aud" or (rule == "b" and M[i] == "unknown")]
            good = [i for i in as_aud if T[i] == "aud"]
            k = "clean" if len(good) == len(as_aud) else ("mixed" if good else "wrong")
            if k != "clean":
                detail.append(f"{d}: ships {k}")
            cnt[k] += 1
        elif st == "unknown-hold":
            cnt["hold-" + truth] += 1
        else:
            cnt["none-" + truth] += 1
            if truth == "has-aud":
                detail.append(f"{d}: no-allowed but truth has aud: "
                              + ", ".join(f"{i} [{M[i]}]" for i in ids if T[i] == "aud"))
    return cnt, detail


def cmd_product(a) -> int:
    """Coverage, ship table and hand-label precision under the PRODUCT ts_rules.classify."""
    from collections import Counter
    _, recs, g = load_phish(Path(a.work))
    T = {r.identifier: today_of(r) for r in recs}
    P = {r.identifier: ts_rules.classify(r) for r in recs}
    DD = {r.identifier: ts_rules.date_disagrees(r) for r in recs}
    cov, ship = coverage_tables(g, T, P, DD)
    nd = len(g)
    pct = lambda n, d: f"{n}/{d} = {100 * n / max(d, 1):.1f}%"
    f3 = lambda c: f"{c['aud']} / {c['unknown-hold']} / {c['no-allowed']}"
    nsl = sum(1 for r in recs if ts_rules.source_lines(r.description))
    lab = {row["identifier"]: (row["label"], row["note"]) for row in csv.DictReader(open(LABELS))}
    sample = random.Random(SEED).sample(sorted(g), min(50, len(g)))
    srecs = [r for d in sample for r in sorted(g[d], key=lambda r: r.identifier)]
    L = {r.identifier: lab[r.identifier][0] for r in srecs}
    S = precision_stats({i: P[i] for i in L}, L)
    n = len(L)
    V = VARIANT_RECORDED
    cnt, detail = date_outcomes(sample, g, P, L, "a")
    out = [
        "`./.venv/bin/python scripts/taperssection_probe.py product` (cached scrape; no re-scrape). "
        "Classifier: the product `ts_rules.classify` after the Checkpoint A ruling (B: in-line source "
        "labels, segments bounded at the next label, a setlist start or 200 chars, fill sources skipped; "
        "C: patch needs board context, board-as-position, matrix needs a board, broadcast words read fm). "
        "The variant column is the probe-only `classify_variant` as recorded above at c2ac9c1c.\n",
        f"- recordings with at least one source line: {pct(nsl, len(recs))}",
        f"- recording classes: product {dict(Counter(P.values()))}; variant {V['recs']}\n",
        "### Coverage (ii)\n",
        "| measure | product | variant (recorded) |", "|---|---|---|",
        f"| of the {cov['unk_today']} dates unknown today, placed (any class) | {pct(cov['placed'], cov['unk_today'])} | {V['placed']} |",
        f"| of those, placed aud | {pct(cov['placed_aud'], cov['unk_today'])} | {V['placed_aud']} |",
        f"| dates still all-unknown | {pct(cov['all_unknown'], nd)} | {V['all_unknown']} |\n",
        f"### Aud-only entry, ship status per date ({nd} dates; aud / unknown-hold / no-allowed)\n",
        "Rule (a) is the ruling; rule (b) rows are for comparison only.\n",
        "| scenario | product | variant (recorded) |", "|---|---|---|",
        f"| **rule (a), after date check** | **{f3(ship['rule (a), after date check'])}** | {V['a_after']} |",
        f"| rule (a), before date check | {f3(ship['rule (a), before date check'])} | {V['a_before']} |",
        f"| rule (b), after date check | {f3(ship['rule (b), after date check'])} | {V['b_after']} |",
        f"| rule (b), before date check | {f3(ship['rule (b), before date check'])} | {V['b_before']} |\n",
        f"### Precision against the hand labels ({n} recordings, 50 dates)\n",
        "| measure | product | variant (recorded) |", "|---|---|---|",
        f"| **false-aud** (says aud, label non-aud) | **{len(S['false_aud'])} of {len(S['said_aud'])}** | {V['false_aud']} |",
        f"| **false-non-aud** (says sbd/matrix/fm/webcast, label aud) | **{len(S['false_non'])} of {len(S['said_non'])}** | {V['false_non_aud']} |",
        f"| non-aud class wrong within non-aud | {len(S['wrong_non'])} | {V['wrong_non']} |",
        f"| aud recall | {pct(*S['recall'])} | {V['aud_recall']} |",
        f"| placed (not unknown) | {pct(n - len(S['unk']), n)} | {V['placed_sample']} |",
        f"| **still-unknown** | **{len(S['unk'])}; truly non-aud {pct(len(S['unk_non']), len(S['unk']))}; "
        f"truly aud {S['unk_t']['aud']}; undeterminable {S['unk_t']['unknown']}** | {V['unk']} |",
        f"| sampled dates, rule (a): ships clean / mixed / wrongly / holds (has-aud) / holds (no-aud) / "
        f"no-allowed (has-aud) / no-allowed (no-aud) | {cnt['clean']} / {cnt['mixed']} / {cnt['wrong']} / "
        f"{cnt['hold-has-aud']} / {cnt['hold-no-aud']} / {cnt['none-has-aud']} / {cnt['none-no-aud']} | {V['dates_a']} |\n",
        "Confusion, product (rows) vs label (columns):\n",
        "| product \\ label | " + " | ".join(CLASSES) + " |", "|---" * (len(CLASSES) + 1) + "|",
    ]
    for c in CLASSES:
        row = [S["conf"][(c, t)] for t in CLASSES]
        if sum(row):
            out.append(f"| {c} | " + " | ".join(str(x) for x in row) + " |")
    out.append("")
    for name, ids in (("false-aud", S["false_aud"]), ("false-non-aud", S["false_non"]),
                      ("non-aud class wrong", S["wrong_non"]), ("still-unknown, truly non-aud", S["unk_non"])):
        out.append(f"- {name}: " + ("; ".join(f"{i} [{P[i]} vs {L[i]}: {lab[i][1]}]" for i in ids) or "none"))
    out.append("- non-clean sampled dates under rule (a): " + ("; ".join(detail) or "none"))
    md = (EVIDENCE / "lineage.md").read_text()
    (EVIDENCE / "lineage.md").write_text(upsert_section(md, PRODUCT_HEADING, "\n".join(out)))
    print("\n".join(out))
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


def cmd_venue(a) -> int:
    """3(g): run ts_measure.parse_title_venue over a seeded sample of Phish titles."""
    from llama.ts_measure import parse_title_venue

    docs = scrape_creator("Phish", Path(a.work))
    titled = sorted((d for d in docs if d.get("title")), key=lambda d: d["identifier"])
    sample = random.Random(a.seed).sample(titled, min(a.n, len(titled)))
    rows, parsed = [], 0
    for d in sample:
        v, c = parse_title_venue(d["title"])
        parsed += v is not None
        rows.append(f"| {d['title'].replace('|', '/')} | {v} | {c} |")
    print(f"sample {len(sample)} of {len(titled)}; parsed {parsed}; not parsed {len(sample) - parsed}", file=sys.stderr)
    print("| title | venue | city |\n|---|---|---|\n" + "\n".join(rows))
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
    dm = sub.add_parser("dump")
    dm.add_argument("--work", default=str(DEFAULT_WORK))
    dm.add_argument("--only", default="")
    dm.add_argument("--chars", type=int, default=900)
    for n in ("lineage", "dates", "variant", "precision", "venue", "product"):
        x = sub.add_parser(n)
        x.add_argument("--work", default=str(DEFAULT_WORK))
        if n == "venue":
            x.add_argument("--n", type=int, default=100)
            x.add_argument("--seed", type=int, default=7)
    a = p.parse_args(argv)
    return {"fields": cmd_fields, "garcia": cmd_garcia, "lineage": cmd_lineage, "dates": cmd_dates,
            "variant": cmd_variant, "precision": cmd_precision, "product": cmd_product, "venue": cmd_venue, "dump": cmd_dump}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
