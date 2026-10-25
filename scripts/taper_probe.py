#!/usr/bin/env python3
"""Read-only yield gate and marker-form probe for the taper set/encore reader.

Spec `docs/superpowers/specs/2026-10-22-taper-set-markers-design.md`, "Measurement and
acceptance": the pre-build gate, run on the `llama.taper` prototype (nothing is wired into
gather). Two subcommands, both writing only under `--out`:

  gate   the 339-ish yes/partial rows of `classified.jsonl` (tracks from the adjudication
         bundle's pre-adjudication track table, description from the cache), then every
         library show (tracks from its `show.json`).
  forms  per recognised form / void / veto rule, the matching lines over every cached
         `md_*.json` description and notes field, plus a sample file for review.
  score  grade a STRIPPED candidate replay arm (`replay_holds.py run --strip-structure-overrides`)
         against the adjudicator's targets (`--arm`), by `primary`; filler-only differences are
         their own class, and the 8 known disagreements are scored by the spec's restated
         expectations instead of as misses.
  delta  compare two `gate` output dirs (`--old`, `--new`): rows newly owned and newly not
         owned, each with its reason, for the gate rows and the library pass.

Run it with the tree's own interpreter: `./.venv/bin/python scripts/taper_probe.py gate
--out ~/.llama-harness/piece2/gate`. The library, the cache and the bundles are only read;
an `--out` overlapping `--root` or `--bundles` is refused (exit 2).

Judgment calls (each errs toward the taper owning LESS):
  * The in-scope set is fixed from `classified.jsonl` alone, before the reader runs.
  * The target match rate counts exact song-level matches only; filler-only differences are
    reported as their own class and are NOT in the headline numerator.
  * A show whose tables cannot give tracks and `today_sets` of equal length is skipped.
  * Library shows with an operator structure override (`set_breaks`/`encore_after`, or
    `structure.source == "override"`) are counted and skipped.

Approximate, direction mixed (NOT under the heading above):
  * G1's predicate (`decide_taper(today_reaches_llm=...)`: canonical items, no anchoring,
    step-1 coverage under the threshold) needs a gather, which the probe does not run. It
    passes a STORED proxy instead (`stored_llm_path`), explicitly on every call: the stored
    show's `structure.alignment` is `llm`, or its `review_flags` hold `low-confidence
    structure alignment` -- the old gather reached the LLM branch, and the LLM won or did
    not. It errs both ways: False where today's code would now reach the LLM branch but the
    stored gather did not (the probe owns more), True where today's code would now anchor
    or align (the probe owns less). Each row records it as `today_llm`; the summaries count
    the rows it is True on and the rows G1 declined.
"""
from __future__ import annotations

import argparse
import contextlib
import html
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import llama
from llama import jerrybase, taper
from llama.models import Track
from llama.setlist import (_INLINE_MARKER, _NUM_PREFIX, _TRACK_PREFIX, _enumerated_prefix,
                           _split_songs)
from llama.songs import GD_SHORTHAND
from llama.structure import is_filler

IN_SCOPE_PRIMARY = ("desc-set-header", "desc-disc-with-set", "desc-inline-marker")
# The probe's own fixed worded-form test over `marker_quote` (case-insensitive): a numbered
# set written as words/digits, not a bare digit or numeral. Independent of the reader.
WORDED_FORM = re.compile(
    r"\bset\s*(?:[1-3]|one|two|three|i{1,3})\b|\b(?:first|second|third|1st|2nd|3rd)\s+set\b",
    re.I)
DEFAULT_ROOT = Path("~/.llama").expanduser()
DEFAULT_BUNDLES = Path("~/.llama-harness/t3/bundles").expanduser()
DEFAULT_EVIDENCE = (Path(__file__).resolve().parents[1]
                    / "docs/superpowers/2026-10-22-taper-set-markers-evidence")
SAMPLE_SEED = 20261022
SAMPLE_OTHERS = 30
TIER_ORDER = ("songs moved", "labels renamed", "encore folded", "encore added",
              "sets merged", "sets split", "filler only")
NO_MATCH = re.compile(r"(?!)")


class Skip(Exception):
    """A row/show the probe cannot evaluate: `skipped: <why>`."""


def _overlaps(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


# --- in-scope set (no reader involved) ---

def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def in_scope(row: dict) -> bool:
    return (row.get("taper_explicit") == "yes" and row.get("primary") in IN_SCOPE_PRIMARY
            and bool(WORDED_FORM.search(row.get("marker_quote") or "")))


# --- inputs ---

_SHOW_JSON = re.compile(r"## show.json.*?\n(\{.*?\n\})\n", re.S)
_TRACK_TABLE = re.compile(r"tracks \(n \| set.*?\n((?:\d+ \|.*\n)+)")


def parse_bundle(path: Path) -> tuple[dict, list[Track]]:
    """(show.json block, pre-adjudication tracks) from a bundle, as `sort1.py` reads it,
    except that the right-hand columns are indexed from the END (a title may contain ' | ')."""
    try:
        b = path.read_text()
    except OSError:
        raise Skip("no bundle")
    m = _SHOW_JSON.search(b)
    if not m:
        raise Skip("no show.json block in bundle")
    try:
        sj = json.loads(m.group(1))
    except ValueError:
        raise Skip("unparseable show.json block")
    tm = _TRACK_TABLE.search(b)
    if not tm:
        raise Skip("no track table in bundle")
    tracks = []
    try:
        for ln in tm.group(1).splitlines():
            p = [x.strip() for x in ln.split(" | ")]
            if len(p) < 7:
                raise ValueError(ln)
            dur = p[-2]
            tracks.append(Track(
                index=int(p[0]), set=p[1], title=" | ".join(p[2:-4]), title_source=p[-4],
                matched={"True": True, "False": False}.get(p[-3]),
                duration_sec=float(dur) if dur not in ("", "None") else None,
                filename=p[-1]))
    except ValueError as e:
        raise Skip(f"unparseable track row: {e}")
    if not tracks:
        raise Skip("empty track table")
    return sj, tracks


def load_meta(root: Path, identifier: str) -> dict:
    try:
        md = json.loads((root / "cache" / f"md_{identifier}.json").read_text())
    except (OSError, ValueError):
        raise Skip("no cached metadata")
    meta = md.get("metadata", md)
    if not isinstance(meta, dict):
        raise Skip("cached metadata is not an object")
    return meta


def aliases_for(artist: str | None) -> dict[str, str]:
    return GD_SHORTHAND if artist and jerrybase.is_family_artist(artist) else {}


G1_REASON = "veto: no encore on today's LLM path"


def stored_llm_path(sj: dict) -> bool:
    """The probe's offline stand-in for gather's `today_reaches_llm` (module docstring)."""
    return ((sj.get("structure") or {}).get("alignment") == "llm"
            or "low-confidence structure alignment" in (sj.get("review_flags") or []))


def decide(tracks: list[Track], meta: dict, artist: str | None, today_sets: list[str],
           today_llm: bool):
    if len(today_sets) != len(tracks):
        raise Skip("today_sets not parallel to tracks")
    return taper.decide_taper(tracks, meta, aliases=aliases_for(artist), today_sets=today_sets,
                              today_reaches_llm=today_llm)


# --- R4 collateral: a probe-local switch-off of ruling R4's widened veto inputs ---

@contextlib.contextmanager
def r4_disabled():
    """Disable only the R4 pieces of `taper._encore_like`: the ` E`/`(E)`/`[E]`/`, E` line
    ending, the split-item exactly `E`/`E<digit>`/`ENC` test (covers an own-line `[E]`), and
    the leading `\\d{1,3}\\s+` strip before the line-start test. Restored on exit."""
    saved = (taper._ENCORE_LIKE_END, taper._ENCORE_LIKE_ITEM, taper._LEADING_NUMBER)
    taper._ENCORE_LIKE_END = taper._ENCORE_LIKE_ITEM = taper._LEADING_NUMBER = NO_MATCH
    try:
        yield
    finally:
        taper._ENCORE_LIKE_END, taper._ENCORE_LIKE_ITEM, taper._LEADING_NUMBER = saved


def r4_alone(decision, tracks, meta, artist, today_sets, today_llm: bool) -> bool:
    """Not owned for `veto: encore-like text` and owned with the R4 rules off."""
    if decision.placement is not None or decision.reason != "veto: encore-like text":
        return False
    with r4_disabled():
        return decide(tracks, meta, artist, today_sets, today_llm).placement is not None


# --- label arithmetic ---

def breaks_of(sets: list[str]) -> tuple[list[int], int | None]:
    """Breaks (index of the first track of each new set) and the first encore start."""
    out, enc = [], None
    for i in range(1, len(sets)):
        if sets[i] != sets[i - 1]:
            if sets[i] == "encore" and enc is None:
                enc = i
            else:
                out.append(i)
    return out, enc


def target_labels(n: int, t_breaks: list[int] | None, t_enc: int | None) -> list[str]:
    """Per-track labels of the adjudicator's `--set-breaks`/`--set-encore` (breaks are track
    numbers a break falls after; the encore begins after track `t_enc`)."""
    br = sorted(t_breaks or [])
    out = []
    for pos in range(n):  # pos is 0-based; track number pos+1
        if t_enc is not None and pos >= t_enc:
            out.append("encore")
        else:
            out.append(str(1 + sum(1 for b in br if b <= pos)))
    return out


def compare(labels: list[str], other: list[str], tracks: list[Track]) -> str:
    """`match` | `filler-only` (differs only on filler tracks) | `miss`."""
    if labels == other:
        return "match"
    if all(a == b for a, b, t in zip(labels, other, tracks) if not is_filler(t.title)):
        return "filler-only"
    return "miss"


def _runs(labels: list[str]) -> list[int]:
    out: list[int] = []
    prev = None
    for lab in labels:
        if lab == prev:
            out[-1] += 1
        else:
            out.append(1)
            prev = lab
    return out


def numbered_count(labels: list[str], tracks: list[Track]) -> int:
    """Distinct numbered (non-encore) set labels over the non-filler tracks."""
    return len({lab for lab, t in zip(labels, tracks)
                if lab != "encore" and not is_filler(t.title)})


def sets_merged(stored: list[str], new: list[str], tracks: list[Track]) -> bool:
    """The taper's numbered-set count is lower than the stored one (any tier)."""
    return numbered_count(new, tracks) < numbered_count(stored, tracks)


def tier(stored: list[str], new: list[str], tracks: list[Track]) -> str | None:
    """One tier per differing owned show (first rule wins); None when labels are equal.
    Encore presence is decided before run equality, so an encore relabelled as a numbered
    set (or the reverse) is never filed as a rename."""
    if stored == new:
        return None
    nf = [i for i, t in enumerate(tracks) if not is_filler(t.title)]
    s = [stored[i] for i in nf]
    t = [new[i] for i in nf]
    if s == t:
        return "filler only"
    s_enc, t_enc = "encore" in s, "encore" in t
    if s_enc and not t_enc:
        return "encore folded"
    if t_enc and not s_enc:
        return "encore added"
    same_enc = [x == "encore" for x in s] == [x == "encore" for x in t]
    if same_enc and _runs(s) == _runs(t):
        return "labels renamed"
    ns, nt = numbered_count(stored, tracks), numbered_count(new, tracks)
    if nt < ns:
        return "sets merged"
    if nt > ns:
        return "sets split"
    return "songs moved"


# --- gate ---

def _status(decision) -> str:
    if decision.placement is not None:
        return "owned"
    if decision.reason and decision.reason.startswith("unplaced"):
        return f"unplaced({decision.reason})"
    return f"not-asserted({decision.reason})"


def gate_rows(root: Path, bundles: Path, evidence: Path) -> list[dict]:
    classified = read_jsonl(evidence / "classified.jsonl")
    sort1 = {r["slug"]: r for r in json.loads((evidence / "sort1.json").read_text())}
    scope = {r["slug"]: in_scope(r) for r in classified}  # fixed before the reader runs
    rows = []
    for c in classified:
        if c.get("taper_explicit") not in ("yes", "partial"):
            continue
        slug = c["slug"]
        s1 = sort1.get(slug, {})
        row = {"slug": slug, "primary": c.get("primary"), "taper_explicit": c["taper_explicit"],
               "in_scope": scope[slug], "renum": bool(s1.get("renum"))}
        try:
            sj, tracks = parse_bundle(bundles / f"{slug}.md")
            meta = load_meta(root, sj["identifier"])
            today = [t.set for t in tracks]
            today_llm = stored_llm_path(sj)
            d = decide(tracks, meta, sj.get("artist"), today, today_llm)
        except (Skip, KeyError) as e:
            row["status"] = f"skipped: {e.args[0] if e.args else e!r}"
            rows.append(row)
            continue
        row["status"] = _status(d)
        row["reason"] = d.reason
        row["source"] = d.source
        row["today_llm"] = today_llm
        tb, te = s1.get("t_breaks"), s1.get("t_enc")
        row["has_target"] = tb is not None or te is not None
        row["r4_alone"] = r4_alone(d, tracks, meta, sj.get("artist"), today, today_llm)
        if d.placement is not None and row["has_target"]:
            row["match"] = compare(list(d.placement.sets), target_labels(len(tracks), tb, te),
                                   tracks)
        rows.append(row)
    return rows


def gate_summary(rows: list[dict]) -> str:
    scoped = [r for r in rows if r["in_scope"]]
    skipped = [r for r in scoped if r["status"].startswith("skipped")]
    evaluated = [r for r in scoped if not r["status"].startswith("skipped")]
    owned = [r for r in evaluated if r["status"] == "owned"]
    ratio = f"{len(owned)}/{len(scoped)}" + (f" = {len(owned) / len(scoped):.3f}" if scoped else "")
    renum = [r for r in owned if r["renum"]]
    no_target = [r for r in owned if not r["renum"] and not r["has_target"]]
    graded = [r for r in owned if not r["renum"] and r["has_target"]]
    match = [r for r in graded if r["match"] == "match"]
    filler = [r for r in graded if r["match"] == "filler-only"]
    miss = [r for r in graded if r["match"] == "miss"]

    def rate(n):
        return f"{n}/{len(graded)}" + (f" = {n / len(graded):.3f}" if graded else "")

    out = ["# taper yield gate (prototype; nothing wired into gather)",
           f"yes/partial rows: {len(rows)}",
           f"in-scope rows (yes, worded form, 3 primaries): {len(scoped)}"
           f" (skipped, unevaluable: {len(skipped)})",
           f"ownership ratio (owned / in-scope): {ratio}",
           f"target match rate (exact, owned with target, not renum): {rate(len(match))}",
           f"  filler-only differences (own class, not in numerator): {len(filler)}",
           f"  match incl. filler-only: {rate(len(match) + len(filler))}",
           f"  misses: {len(miss)}",
           f"owned renum rows (not graded): {len(renum)}",
           f"owned rows with no target (not graded): {len(no_target)}", "", "## counts by primary"]
    by = defaultdict(Counter)
    for r in rows:
        by[r["primary"]][("scope " if r["in_scope"] else "out ") + r["status"].split("(")[0]] += 1
    for prim in sorted(by, key=str):
        out.append(f"{prim}: " + ", ".join(f"{k}={v}" for k, v in sorted(by[prim].items())))
    out += ["", "## in-scope status counts"]
    for k, v in sorted(Counter(r["status"] for r in scoped).items()):
        out.append(f"{v:4d}  {k}")
    out += _g1_lines(rows)
    r4 = [r for r in rows if r.get("r4_alone")]
    r4s = [r for r in scoped if r.get("r4_alone")]
    out += ["", f"## R4 collateral: not owned for `veto: encore-like text`, owned with R4 off",
            f"all yes/partial rows: {len(r4)}; in-scope: {len(r4s)}"]
    out += [f"  {r['slug']}{' (in scope)' if r['in_scope'] else ''}" for r in r4]

    def listing(title, rs, extra=lambda r: ""):
        out.extend(["", f"## {title} ({len(rs)})"] + [f"  {r['slug']}{extra(r)}" for r in rs])

    listing("in-scope rows (all)", scoped, lambda r: f"  {r['status']}")
    listing("owned renum rows", renum)
    listing("owned rows with no target", no_target)
    listing("misses", miss)
    listing("filler-only", filler)
    listing("skipped in-scope rows", skipped, lambda r: f"  {r['status']}")
    return "\n".join(out) + "\n"


def _g1_lines(rows: list[dict]) -> list[str]:
    proxy = [r for r in rows if r.get("today_llm")]
    g1 = [r for r in rows if r.get("reason") == G1_REASON]
    return (["", "## G1 (stored proxy for today's LLM path; module docstring)",
             f"rows with the proxy True: {len(proxy)}; declined for `{G1_REASON}`: {len(g1)}"]
            + [f"  {r['slug']}" for r in g1])


# --- library ---

def _override_skip(show: Path, sj: dict) -> str | None:
    if (sj.get("structure") or {}).get("source") == "override":
        return "operator structure override"
    p = show / "overrides.json"
    if not p.exists():
        return None
    try:
        o = json.loads(p.read_text())
    except (OSError, ValueError):
        return "unreadable overrides.json"
    if o.get("set_breaks") is not None or o.get("encore_after") is not None:
        return "operator structure override"
    return None


def library_rows(root: Path) -> list[dict]:
    rows = []
    for show in sorted((root / "shows").glob("*/")):
        sjp = show / "show.json"
        if not sjp.exists():
            continue
        row = {"slug": show.name}
        try:
            sj = json.loads(sjp.read_text())
            why = _override_skip(show, sj)
            if why:
                raise Skip(why)
            tracks = [Track.model_validate(t) for t in sj["tracks"]]
            if not tracks:
                raise Skip("no tracks")
            meta = load_meta(root, sj["identifier"])
            today = [t.set for t in tracks]
            today_llm = stored_llm_path(sj)
            d = decide(tracks, meta, sj.get("artist"), today, today_llm)
        except (Skip, KeyError, ValueError, TypeError) as e:
            row["status"] = f"skipped: {e.args[0] if e.args else repr(e)}"
            rows.append(row)
            continue
        row["status"] = _status(d)
        row["reason"] = d.reason
        row["today_llm"] = today_llm
        row["r4_alone"] = r4_alone(d, tracks, meta, sj.get("artist"), today, today_llm)
        if d.placement is not None:
            row["stored"] = today
            row["taper"] = list(d.placement.sets)
            row["tier"] = tier(today, row["taper"], tracks)
            row["sets_merged"] = sets_merged(today, row["taper"], tracks)
        rows.append(row)
    return rows


def library_summary(rows: list[dict]) -> str:
    skipped = [r for r in rows if r["status"].startswith("skipped")]
    ev = [r for r in rows if not r["status"].startswith("skipped")]
    owned = [r for r in ev if r["status"] == "owned"]
    tiers = defaultdict(list)
    for r in owned:
        if r["tier"]:
            tiers[r["tier"]].append(r["slug"])
    out = ["# taper library pass (prototype; nothing wired into gather)",
           f"shows with show.json: {len(rows)}",
           f"skipped: {len(skipped)}"]
    for k, v in sorted(Counter(r["status"] for r in skipped).items()):
        out.append(f"  {v:5d}  {k}")
    out += [f"evaluated: {len(ev)}",
            f"taper-owned: {len(owned)}",
            f"  owned, labels identical to stored: {sum(1 for r in owned if not r['tier'])}",
            f"  owned, labels differ: {sum(len(v) for v in tiers.values())}", "", "## tiers"]
    for name in TIER_ORDER:
        out.append(f"{name}: {len(tiers[name])}")
    rng = random.Random(SAMPLE_SEED)
    for name in TIER_ORDER:
        slugs = sorted(tiers[name])
        if name == "sets merged":
            out += ["", f"## every row: sets merged ({len(slugs)})"] + [f"  {x}" for x in slugs]
            continue
        pick = sorted(rng.sample(slugs, min(10, len(slugs))))
        out += ["", f"## sample: {name} ({len(pick)} of {len(slugs)})"] + [f"  {s}" for s in pick]
    merged = [r for r in owned if r.get("sets_merged")]
    out += ["", f"## numbered-set count decreased (any tier), EVERY row ({len(merged)})"]
    out += [f"  {r['slug']}  [{r['tier']}]" for r in merged]
    out += _g1_lines(rows)
    r4 = [r for r in ev if r.get("r4_alone")]
    out += ["", "## R4 collateral: not owned for `veto: encore-like text`, owned with R4 off",
            f"shows: {len(r4)}"] + [f"  {r['slug']}" for r in r4]
    out += ["", "## not-owned reasons"]
    for k, v in sorted(Counter(r["status"] for r in ev if r["status"] != "owned").items(),
                       key=lambda kv: -kv[1])[:40]:
        out.append(f"  {v:5d}  {k}")
    return "\n".join(out) + "\n"


# --- forms ---

def _clean(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    return re.sub(r"<[^>]+>", "\n", text)


def _set_form(m: re.Match) -> str:
    if m.group("ordn"):
        return "set header: 1st/2nd/3rd Set"
    if m.group("ord"):
        return "set header: First/Second/Third Set"
    return "set header: Set N/one/I"


# Checkpoint A additions (ruling (b)'s annotation, the veto gap).
_ANNOTATED = re.compile(r"\(\s*\d{1,3}:\d{2}")


def _header_form(core: str):
    """(form name, match) for the numbered-set header regex matching `core`, if any."""
    m = taper._SET_HEADER.match(core)
    if m:
        return _set_form(m), m
    m = taper._DISC_SET_HEADER.match(core)
    if m:
        return "set header: Disc N + Set M (disc first)", m
    m = taper._SET_DISC_HEADER.match(core)
    if m:
        return "set header: Set M + Disc N (set first, ruling c)", m
    return None, None


def line_hits(text: str) -> list[tuple[str, str]]:
    """(form or rule, line) hits for one text: marker forms and veto rules per line."""
    hits: list[tuple[str, str]] = []
    cleaned = html.unescape(_clean(text))
    for ln in cleaned.splitlines():
        held = taper._split_set_and_encore(ln.strip())
        if held:
            hits.append(("rule: set-and-encore header held before the inline split", ln.strip()))
        if len(_INLINE_MARKER.findall(held[1] if held else ln)) > 0:
            hits.append(("inline-split marker (mid-line Set/E/Encore)", ln.strip()))
    lines = taper._preprocess(text)
    enumerated = _enumerated_prefix(lines)
    for line in lines:
        if not line:
            continue
        if taper._SET_FOUR_PLUS.search(line):
            hits.append(("void input: set 4 or higher", line))
        core = _TRACK_PREFIX.sub("", line)
        if enumerated:
            core = _NUM_PREFIX.sub("", core)
        form, mm = _header_form(core)
        e = taper._ENCORE_HEADER.match(core) if not mm else None
        eh = taper._E_HEADER.match(core) if not (mm or e) else None
        rest = core
        if mm:
            hits.append((form, line))
            if mm.group("cont"):
                hits.append(("rule: continuation header (Set N cont.)", line))
            if mm.group("andenc"):
                hits.append(("rule: header naming set and encore", line))
            head = core[:mm.start("rest")] if mm.group("rest") is not None else core
            if _ANNOTATED.search(head):
                hits.append(("rule: header + (duration|time) (ruling b)", line))
            rest = mm.group("rest") or ""
        elif e:
            ordinal = re.match(r"^[-–—*~=\[\]()\s]*(?:1st|2nd|3rd|first|second|third)", core, re.I)
            hits.append(("encore header: ordinal encore" if ordinal
                         else "encore header: Encore/Encores", line))
            rest = e.group("rest") or ""
        elif eh:
            word = re.match(r"^[-–—*~=\s]*(enc)(?!\w)", core, re.I)
            hits.append(("encore header: ENC" if word else "encore header: E/E<digit>", line))
            rest = eh.group("rest") or ""
        if (e or eh) and taper._ENCORE_NONE.match(rest):
            hits.append(("void input: encore none / no encore / n/a", line))
        song_side = not (mm or e or eh)
        probe = core if song_side else rest
        # `_scan` tests a song line's encore words on the whole line, a marker line's on the rest.
        if taper._ENCORE_WORDS.search(line if song_side else rest):
            hits.append(("veto: encore word (\\bencores?\\b | \\benc\\b)", line))
        p = probe.strip()
        if taper._ENCORE_LIKE_START.match(p):
            hits.append(("veto: line starts E. / E) / E<digit> / (E)", line))
        elif taper._ENCORE_LIKE_START.match(taper._LEADING_NUMBER.sub("", p)):
            hits.append(("veto R4(d): same start after a bare number strip", line))
        if taper._ENCORE_LIKE_END.search(p):
            hits.append(("veto R4(b): line ends ' E' / '(E)' / '[E]' / ', E'", line))
        if any(taper._ENCORE_LIKE_ITEM.match(t.strip(taper._ITEM_DECOR))
               for t, _ in _split_songs(p)):
            hits.append(("veto R4(a,c): split item exactly E / E<digit> / ENC", line))
        if (re.search(r"\bencor\b", line if song_side else rest, re.I)
                or taper._ENCORE_GLUED.match(p) or taper._ENCORE_E_SPACE.match(p)
                or taper._ENCORE_DECORATED_E.search(p)):
            hits.append(("veto Checkpoint A gap: Encor / 9E. / E Title / E~ / -e-", line))
    return hits


def _creator(meta: dict) -> str:
    c = meta.get("creator")
    if isinstance(c, list):
        c = c[0] if c else ""
    return str(c or "")


def forms_scan(root: Path):
    """(per-form line counts, per-form file counts, hits per form, text-level reasons)."""
    lines, files = Counter(), Counter()
    hits: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    reasons: Counter = Counter()
    n = 0
    for p in sorted((root / "cache").glob("md_*.json")):
        try:
            md = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        meta = md.get("metadata", md) if isinstance(md, dict) else {}
        if not isinstance(meta, dict):
            continue
        n += 1
        ident = p.stem[3:]
        creator = _creator(meta)
        seen = set()
        for fld in ("description", "notes"):
            text = taper._field_text(meta.get(fld))
            if not text:
                continue
            for form, ln in line_hits(text):
                lines[form] += 1
                seen.add(form)
                hits[form].append((ident, creator, fld, ln))
            r = taper.read_taper_structure(text)
            why = "asserts" if r.asserts else (r.reason or "")
            reasons[(fld, "cross-check" if why.startswith("cross-check") else why)] += 1
        for f in seen:
            files[f] += 1
    return n, lines, files, hits, reasons


def forms_outputs(root: Path) -> tuple[str, str]:
    n, lines, files, hits, reasons = forms_scan(root)
    rng = random.Random(SAMPLE_SEED)
    summ = [f"# taper marker forms over {n} cached items (description and notes fields)",
            f"{'lines':>7} {'items':>6}  form / rule"]
    for form in sorted(lines):
        summ.append(f"{lines[form]:7d} {files[form]:6d}  {form}")
    summ += ["", "## text-level reader outcome (per non-empty field)"]
    for (fld, why), v in sorted(reasons.items(), key=lambda kv: (kv[0][0], -kv[1])):
        summ.append(f"{v:7d}  {fld}: {why}")
    samples = [f"# every hit on a family artist plus {SAMPLE_OTHERS} random others per form "
               f"(seed {SAMPLE_SEED})"]
    for form in sorted(hits):
        fam = [h for h in hits[form] if jerrybase.is_family_artist(h[1])]
        others = [h for h in hits[form] if h not in fam]
        pick = rng.sample(others, min(SAMPLE_OTHERS, len(others)))
        samples += ["", f"## {form}: {len(hits[form])} lines; family {len(fam)}, "
                    f"others sampled {len(pick)} of {len(others)}"]
        for kind, group in (("family", fam), ("other", pick)):
            for ident, creator, fld, ln in group:
                samples.append(f"[{kind}] {ident} ({creator}) {fld}: {ln[:300]}")
    return "\n".join(summ) + "\n", "\n".join(samples) + "\n"


# --- score (a stripped candidate replay arm against the adjudicator's targets) ---

OUT_OF_SCOPE_PRIMARY = ("filename-set", "track-title-set-label")
# The 8 known disagreements (spec, "What the evidence says"): the adjudicator's target differs
# from the taper's own labels, so a mismatch is expected there, not a miss. Each entry is the
# restated expectation, then the checker's key.
NO_ENCORE_EXPECTATION = ("the disputed boundary is an encore the taper did not label: if the taper "
                         "owns the show its last set runs to the end of the tape (no encore label "
                         "ships); if not owned it is computed as today")
NOT_ASSERTED_EXPECTATION = ("one numbered set plus an encore marker asserts nothing (spec section 2): "
                            "the taper must NOT own it; owned is a reader defect, declined is "
                            "computed as today")
OWNED_SHIPS_EXPECTATION = ("where the taper owns the structure its structure ships, an expected "
                           "disagreement with the adjudicator; if not owned it is computed as today")
EXPECTED_DISAGREEMENTS = {
    "derektrucksband-2005-01-09": ("no-encore", NO_ENCORE_EXPECTATION),
    "darkstarorchestra-2007-05-08": ("no-encore", NO_ENCORE_EXPECTATION),
    "thedead-2009-04-29": ("no-encore", NO_ENCORE_EXPECTATION),
    "gratefuldead-1970-05-15-spans": (
        "stays-held", "stays held by `tape spans` (a hold, whatever the taper owns)"),
    "deadandcompany-2018-06-16": ("not-asserted", NOT_ASSERTED_EXPECTATION),
    "gratefuldead-1981-12-31": ("ships", OWNED_SHIPS_EXPECTATION),
    "stevekimockband-2003-03-11": ("no-encore", NO_ENCORE_EXPECTATION),
    "ekoostikhookah-2009-12-31": ("not-asserted", NOT_ASSERTED_EXPECTATION),
}


def compare_filler(labels: list[str], other: list[str], filler: list[bool]) -> str:
    """`compare`, over the arm's per-track `filler` flags: `match` | `filler-only` | `miss`."""
    if labels == other:
        return "match"
    if all(a == b for a, b, f in zip(labels, other, filler) if not f):
        return "filler-only"
    return "miss"


def _expectation(kind: str, r: dict, graded: str | None) -> tuple[str, str]:
    """(verdict, detail) of one known disagreement against its arm row."""
    owned = bool(r.get("taper_owned"))
    sets = r.get("sets") or []
    if kind == "stays-held":
        flags = list(r.get("gather_flags") or [])
        held = r.get("outcome") in ("still-held", "still-held-package")
        if held and any(f.startswith("tape spans") for f in flags):
            return "as expected", "held by a `tape spans` flag"
        return "UNEXPECTED", f"outcome {r.get('outcome')!r}, gather flags {flags}"
    if not owned:
        return "as expected", f"declined, computed as today ({r.get('taper_reason')})"
    if kind == "not-asserted":
        return "UNEXPECTED", "owned, but one numbered set plus an encore asserts nothing"
    if kind == "no-encore":
        if "encore" in sets:
            return "UNEXPECTED", "owned, but an encore label ships"
        return "as expected", "owned, no encore label ships (last set runs to the end)"
    if graded == "match":
        return "as expected", "owned; the shipped structure happens to equal the adjudicator's"
    return "as expected", f"owned; the taper's structure ships, differing from the target ({graded})"


def _to_position(v, names: list[str] | None):
    """A stripped override value as a 1-based track position: a filename (piece 4) through
    `names`, an int (a base arm) as is, anything else (None) unchanged. A filename not in
    `names` stays a string, so it equals nothing numeric."""
    if isinstance(v, str) and names and v in names:
        return names.index(v) + 1
    return v


def _arm_filenames(a: dict, arm: dict, slug: str) -> list[str] | None:
    """The row's own `filenames`, else the library's show.json for `slug` (a base arm row has
    none)."""
    if a.get("filenames"):
        return list(a["filenames"])
    try:
        sj = json.loads((Path(arm.get("root") or ".") / "shows" / slug / "show.json").read_text())
        return [t["filename"] for t in sj["tracks"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _fix_applied(stripped: dict | None, t_breaks, t_enc, names: list[str] | None = None) -> bool:
    """A renumbered row is gradable when the overrides strip mode removed ARE the
    adjudicator's target: its include/exclude edits (kept) and its `--set-breaks`/
    `--set-encore` (stripped) were all applied, so the stripped replay is in the target's
    own numbering. Nothing stripped (or a different value) means the library does not hold
    the adjudicator's fix. Filename-valued keys are read as the track positions they name
    in `names` (the row's `filenames`); int values (base arms) are used as is."""
    if not stripped:
        return False
    got = [_to_position(v, names) for v in stripped.get("set_breaks") or []]
    return (sorted(got) == sorted(t_breaks or [])
            and _to_position(stripped.get("encore_after"), names) == t_enc)


def score_rows(arm: dict, evidence: Path) -> list[dict]:
    classified = read_jsonl(evidence / "classified.jsonl")
    sort1 = {r["slug"]: r for r in json.loads((evidence / "sort1.json").read_text())}
    shows = arm["shows"]
    rows = []
    for c in classified:
        if c.get("taper_explicit") not in ("yes", "partial"):
            continue
        slug = c["slug"]
        s1 = sort1.get(slug, {})
        row = {"slug": slug, "primary": c.get("primary"), "taper_explicit": c["taper_explicit"],
               "in_scope": in_scope(c), "renum": bool(s1.get("renum"))}
        a = shows.get(slug)
        graded = None
        if a is None:
            row["class"] = "absent from arm"
        elif a.get("unreplayable") is not None:
            row["class"], row["why"] = "unreplayable", a["unreplayable"]
        elif not a.get("taper_owned"):
            row["class"], row["why"] = "declined", a.get("taper_reason") or a.get("outcome")
        else:
            tb, te = s1.get("t_breaks"), s1.get("t_enc")
            sets = list(a.get("sets") or [])
            row["sets"] = sets
            row["owned_breaks"] = breaks_of(sets)
            if tb is None and te is None:
                row["class"] = "owned, no target"
            elif row["renum"] and not _fix_applied(a.get("stripped"), tb, te,
                                                   _arm_filenames(a, arm, slug)):
                row["class"] = "owned, renumbered target (not graded)"
            elif max([*(tb or []), te or 0], default=0) > len(sets):
                row["class"] = "owned, target does not fit the tape (not graded)"
            else:
                graded = compare_filler(sets, target_labels(len(sets), tb, te),
                                        list(a.get("filler") or [False] * len(sets)))
                row["class"] = graded
                row["target"] = [tb, te]
        if slug in EXPECTED_DISAGREEMENTS and a is not None:
            kind, text = EXPECTED_DISAGREEMENTS[slug]
            row["known_disagreement"] = text
            row["verdict"], row["detail"] = _expectation(kind, a, graded)
            row["graded_class"] = row["class"]
            row["class"] = "known disagreement"
        elif slug in EXPECTED_DISAGREEMENTS:
            row["known_disagreement"] = EXPECTED_DISAGREEMENTS[slug][1]
            row["verdict"], row["detail"] = "UNEXPECTED", "absent from the arm"
        rows.append(row)
    return rows


def score_summary(rows: list[dict]) -> str:
    scoped = lambda r: r["primary"] not in OUT_OF_SCOPE_PRIMARY
    inscope = [r for r in rows if scoped(r)]
    out_of_scope = [r for r in rows if not scoped(r)]
    by_class = Counter(r["class"] for r in inscope)
    graded = by_class["match"] + by_class["filler-only"] + by_class["miss"]
    core = [r for r in rows if r["in_scope"]]

    def headline(rs):
        c = Counter(r["class"] for r in rs)
        n = c["match"] + c["filler-only"] + c["miss"]
        return (f"{len(rs)} rows: match {c['match']}, filler-only {c['filler-only']}, "
                f"miss {c['miss']} (of {n} graded); declined {c['declined']}, "
                f"known disagreements {c['known disagreement']}")

    out = ["# taper score: stripped candidate arm vs the adjudicator's targets",
           f"yes/partial rows: {len(rows)}; yes/partial excluding filename/track-tag: "
           f"{len(inscope)}; reported apart as out of scope: {len(out_of_scope)}",
           f"IN SCOPE (yes, worded form, 3 desc primaries; the gate's definition): "
           f"{headline(core)}",
           f"  of which yes: {headline([r for r in core if r['taper_explicit'] == 'yes'])}",
           f"  of which partial: {headline([r for r in core if r['taper_explicit'] == 'partial'])}",
           f"graded (owned, with a target; renumbered rows only when the adjudicator's fix is applied): {graded}",
           f"  match (exact, song level): {by_class['match']}",
           f"  filler-only differences (own class, not matches, not misses): {by_class['filler-only']}",
           f"  misses: {by_class['miss']}",
           f"declined (not taper-owned, computed as today): {by_class['declined']}",
           f"known disagreements (scored by expectation): {by_class['known disagreement']}",
           "", "## counts by primary (in scope)"]
    by = defaultdict(Counter)
    for r in inscope:
        by[r["primary"]][r["class"]] += 1
    for prim in sorted(by, key=str):
        out.append(f"{prim}: " + ", ".join(f"{k}={v}" for k, v in sorted(by[prim].items())))
    out += ["", "## all classes (in scope)"]
    out += [f"{v:4d}  {k}" for k, v in sorted(by_class.items(), key=lambda kv: (-kv[1], kv[0]))]

    def listing(title, rs, extra=lambda r: ""):
        out.extend(["", f"## {title} ({len(rs)})"] + [f"  {r['slug']}{extra(r)}" for r in rs])

    known = [r for r in rows if "known_disagreement" in r]
    out += ["", f"## the 8 known disagreements ({len(known)} scored)"]
    for r in known:
        out += [f"  {r['slug']}: {r.get('verdict')}  -- {r.get('detail')}",
                f"      expectation: {r['known_disagreement']}"]
    listing("misses", [r for r in inscope if r["class"] == "miss"],
            lambda r: f"  [{r['primary']}] owned {r['owned_breaks']} target {r['target']}")
    listing("filler-only", [r for r in inscope if r["class"] == "filler-only"],
            lambda r: f"  [{r['primary']}]")
    listing("declines", [r for r in inscope if r["class"] == "declined"],
            lambda r: f"  [{r['primary']}] {r.get('why')}")
    listing("owned, not graded", [r for r in inscope if r["class"].startswith("owned,")],
            lambda r: f"  [{r['primary']}] {r['class']}")
    listing("unreplayable / absent", [r for r in inscope
                                       if r["class"] in ("unreplayable", "absent from arm")],
            lambda r: f"  {r['class']} {r.get('why', '')}")
    listing("out of scope (filename / track-tag rows)", out_of_scope,
            lambda r: f"  [{r['primary']}] {r['class']}")
    return "\n".join(out) + "\n"


# --- delta (two gate runs) ---

def _rows_by_slug(path: Path) -> dict[str, dict]:
    return {r["slug"]: r for r in read_jsonl(path)} if path.exists() else {}


def _owned(r: dict | None) -> bool:
    return bool(r) and r.get("status") == "owned"


def _why(r: dict | None) -> str:
    if not r:
        return "absent"
    return r.get("reason") or r.get("status") or ""


def delta_rows(old: dict[str, dict], new: dict[str, dict], scope_only: bool = False):
    """(newly owned, newly not owned, owned in both with different labels)."""
    slugs = sorted(set(old) | set(new))
    if scope_only:
        slugs = [s for s in slugs if (new.get(s) or old.get(s) or {}).get("in_scope")]
    gained = [(s, _why(old.get(s)), new[s]) for s in slugs
              if _owned(new.get(s)) and not _owned(old.get(s))]
    lost = [(s, _why(new.get(s)), old[s]) for s in slugs
            if _owned(old.get(s)) and not _owned(new.get(s))]
    moved = [(s, old[s], new[s]) for s in slugs if _owned(old.get(s)) and _owned(new.get(s))
             and old[s].get("taper") != new[s].get("taper")]
    return gained, lost, moved


def delta_summary(old_dir: Path, new_dir: Path) -> str:
    out = [f"# taper probe delta: {old_dir} -> {new_dir}"]
    og, ng = _rows_by_slug(old_dir / "gate_rows.jsonl"), _rows_by_slug(new_dir / "gate_rows.jsonl")
    o_scope = {s for s, r in og.items() if r.get("in_scope")}
    n_scope = {s for s, r in ng.items() if r.get("in_scope")}
    out.append(f"in-scope rows: old {len(o_scope)}, new {len(n_scope)}, "
               f"identical set: {o_scope == n_scope}")
    for title, old, new, scope_only in (
            ("gate rows, in scope", og, ng, True), ("gate rows, all yes/partial", og, ng, False),
            ("library", _rows_by_slug(old_dir / "library_rows.jsonl"),
             _rows_by_slug(new_dir / "library_rows.jsonl"), False)):
        gained, lost, moved = delta_rows(old, new, scope_only)
        out += ["", f"## {title}: newly owned {len(gained)}, newly not owned {len(lost)}, "
                    f"owned in both with different labels {len(moved)}"]
        out.append("### newly not owned, by reason")
        for k, v in sorted(Counter(w for _, w, _ in lost).items(), key=lambda kv: -kv[1]):
            out.append(f"  {v:4d}  {k}")
        out.append("### newly owned, by old reason")
        for k, v in sorted(Counter(w for _, w, _ in gained).items(), key=lambda kv: -kv[1]):
            out.append(f"  {v:4d}  {k}")
        out.append("### newly owned rows")
        for s, w, r in gained:
            extra = f" [{r['tier']}]" if r.get("tier") else ""
            extra += f" match={r['match']}" if r.get("match") else ""
            out.append(f"  {s}{extra}  (was: {w})")
        out.append("### newly not owned rows")
        out += [f"  {s}  ({w})" for s, w, _ in lost]
        out.append("### owned in both, labels changed")
        out += [f"  {s}  [{o.get('tier')}] -> [{n.get('tier')}]" for s, o, n in moved]
    return "\n".join(out) + "\n"


# --- CLI ---

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("gate", "forms", "delta", "score"))
    ap.add_argument("--old", type=Path, help="delta: the earlier gate output dir")
    ap.add_argument("--new", type=Path, help="delta: the later gate output dir")
    ap.add_argument("--arm", type=Path, help="score: a stripped candidate arm JSON")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--bundles", type=Path, default=DEFAULT_BUNDLES)
    ap.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    out = args.out.expanduser()
    for guarded in (args.root, args.bundles):
        if _overlaps(out, guarded.expanduser()):
            print(f"refusing: --out {out} overlaps {guarded}", file=sys.stderr)
            return 2
    print(f"llama: {llama.__file__}", file=sys.stderr)
    out.mkdir(parents=True, exist_ok=True)
    root = args.root.expanduser()
    if args.cmd == "gate":
        rows = gate_rows(root, args.bundles.expanduser(), args.evidence)
        _write_jsonl(out / "gate_rows.jsonl", rows)
        (out / "gate_summary.txt").write_text(gate_summary(rows))
        lib = library_rows(root)
        _write_jsonl(out / "library_rows.jsonl", lib)
        (out / "library_summary.txt").write_text(library_summary(lib))
        print((out / "gate_summary.txt").read_text().split("## counts by primary")[0])
    elif args.cmd == "score":
        if not args.arm:
            print("score needs --arm", file=sys.stderr)
            return 2
        arm = json.loads(args.arm.expanduser().read_text())
        if not arm.get("structure_overrides_stripped"):
            print("refusing: score needs an arm replayed with --strip-structure-overrides",
                  file=sys.stderr)
            return 2
        if arm.get("root") and _overlaps(out, Path(arm["root"]).expanduser()):
            print(f"refusing: --out {out} overlaps the arm's library {arm['root']}", file=sys.stderr)
            return 2
        rows = score_rows(arm, args.evidence)
        _write_jsonl(out / "score_rows.jsonl", rows)
        text = score_summary(rows)
        (out / "score_summary.txt").write_text(text)
        print(text.split("## all classes")[0])
    elif args.cmd == "delta":
        if not (args.old and args.new):
            print("delta needs --old and --new", file=sys.stderr)
            return 2
        text = delta_summary(args.old.expanduser(), args.new.expanduser())
        (out / "delta_summary.txt").write_text(text)
        print(text.split("### newly owned rows")[0])
    else:
        summ, samples = forms_outputs(root)
        (out / "forms_summary.txt").write_text(summ)
        (out / "forms_samples.txt").write_text(samples)
        print(summ)
    return 0


if __name__ == "__main__":
    sys.exit(main())
