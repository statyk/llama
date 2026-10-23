#!/usr/bin/env python3
"""Piece 3 census, stage 2: classify dump.jsonl into classes A-D, write
census.json and the hand-check packets. Read-only on the library (it reads
only dump.jsonl and the overnight verdicts).

Run: /Users/shawn/projects/llama/.venv/bin/python census.py
"""
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from llama import placeholders as P
from llama.structure import contains_sequence, fuzzy_norm_title, fuzzy_title_eq, is_filler
from llama.titles import (_GLUED_NUM_PREFIX, _JOINED_NUM_PREFIX, _TRACK_NUM_PREFIX, clean_tag_title,
                          clean_tag_titles, is_placeholder_text, is_real_title)
from llama.structure import hygienic_title

HERE = Path(__file__).resolve().parent
VERDICTS = Path.home() / ".llama-harness/t3/verdicts"
PK = HERE / "packets"
random.seed(3)

# ---------------------------------------------------------------- load
rows = []
meta = None
for line in (HERE / "dump.jsonl").open():
    r = json.loads(line)
    if "_meta" in r:
        meta = r["_meta"]
        continue
    rows.append(r)
by = {r["slug"]: r for r in rows}

verdicts = {}
for f in VERDICTS.glob("*.json"):
    try:
        v = json.loads(f.read_text())
        verdicts[v.get("slug", f.stem)] = v
    except Exception:
        pass


def vtags(slug):
    return set(verdicts.get(slug, {}).get("root_causes", []) or [])


def basis(r):
    """Which tracks the census judges, and from where."""
    if r.get("replayed") and "extract_setlist" not in (r.get("needs_llm") or []):
        return r["tracks"], ("replay" if not r.get("needs_llm") else "replay(needs-llm:structure-only)")
    if r.get("replayed"):
        return r["tracks"], "replay(needs-llm:extract_setlist)"
    return r.get("stored_tracks") or [], "stored(unreplayable)"


def statecol(r):
    s = r.get("state", "?")
    if s == "delivered" and r.get("voiced"):
        return "voiced"
    return s


def would_hold(r):
    if r.get("replayed"):
        return bool(r.get("flags"))
    return bool(r.get("stored_flags"))


def n(x):
    return fuzzy_norm_title(x or "")


def eqt(a, b):
    na, nb = n(a), n(b)
    return bool(na) and (na == nb or fuzzy_title_eq(na, nb))


def witnesses(r, title):
    """Cross-sources naming `title`: own description text, own parse,
    canonical (incl. setlist.fm), corroboration vocab, donors' tags, overrides."""
    w = []
    t = n(title)
    if not t:
        return w
    desc = r.get("description") or ""
    if desc and contains_sequence(desc, [title]):
        w.append("own-desc-text")
    if any(eqt(title, x) for x in r.get("own_parse") or []):
        w.append("own-parse")
    if any(eqt(title, x["title"]) for x in r.get("canonical") or []):
        w.append(f"canonical({r.get('canonical_source')})")
    if t in set(r.get("corroboration") or []):
        w.append("corroboration")
    for d in r.get("donors") or []:
        if any(eqt(title, x) for x in d["titles"]):
            w.append(f"donor:{d['id']}")
            break
    if any(eqt(title, x) for x in (r.get("override_titles") or {}).values()):
        w.append("operator-override")
    return w


# ---------------------------------------------------------------- class A
SPELLED = re.compile(r"^(?:track|trk|tr|cut)\s*[-_#.]?\s*(?:" + "|".join(P.NUMBER_WORDS)
                     + r"|\d{1,3})\b", re.I)
DISC_PREFIX = re.compile(r"^\s*(?:disc|disk|cd|d)\s*\d+\s*[-:.,)]?\s*(?:t(?:rack)?\s*\d+)?", re.I)
SET_PREFIX = re.compile(r"^\s*(?:set\s*(?:\d|i{1,3}|one|two|three)|s\d)\s*[-:.)]\s*\S", re.I)
BARE_NUM = re.compile(r"^\s*\d{1,3}\s*[.)]?\s*$")
EXT_TAIL = re.compile(r"\.(?:mp3|flac|shn|wav|ogg)\b", re.I)
STEMISH = re.compile(r"(?:^|[\s_-])(?:[sd]\d{1,2})?t\d{2,3}(?:$|[\s_.-])|\d{2,4}[-_.]\d{2}[-_.]\d{2}", re.I)


def _positions(k):
    out = {k["n"]}
    nums = re.findall(r"(\d+)", Path(k["file"]).stem)
    if nums:
        out.add(int(nums[-1]))
    return out


def a_shape(title, r, k):
    """Shape label for a resolved title, or None when it looks like a title.
    Uses llama's own predicates where one exists; the extra shapes (spelled
    prefix with text, disc/set prefix, stem-ish residue inside a longer
    string, extension) are census-only detectors and are labelled so."""
    t = title.strip()
    if not t:
        return "blank"
    if P.is_placeholder(t):
        return "2b:placeholder-vocab"
    if P.is_timestamp(t):
        return "2b:bare-timestamp"
    if is_real_title(t) and P.is_residue(t):
        return "2b:residue"
    if P.starts_with_timestamp(t):
        return "leading-timestamp+text"
    lead = re.match(r"^(\d{1,3})", t)
    posn = lead and (lead.group(1).startswith("0") or int(lead.group(1)) in _positions(k))
    if _GLUED_NUM_PREFIX.match(t):
        return "glued-num-prefix" if posn else "ambiguous:glued-number-led"
    if _JOINED_NUM_PREFIX.match(t):
        return "joined-num-prefix(=position)" if posn else "ambiguous:joined-number-led"
    if SPELLED.match(t):
        return "track-word-prefix+text"
    if BARE_NUM.match(t):
        return ("bare-number(=position or 0-led)" if (posn or re.search(r"[.)]\s*$", t))
                else "ambiguous:bare-number")
    if _TRACK_NUM_PREFIX.match(t):
        return "spaced-num-prefix(=position)" if posn else "ambiguous:number-led-title"
    if P.is_date_like(t):
        return "ambiguous:date-like"
    if P.looks_like_filename(t):
        return "filename-shape"
    stems = {Path(x["file"]).stem.lower() for x in r["_basis"]}
    if (t.lower() in stems or Path(t).stem.lower() in stems) and re.search(r"\d", t):
        return "filename-stem"
    if EXT_TAIL.search(t):
        return "audio-extension-inside"
    if STEMISH.search(t):
        return "stem/date-residue-inside"
    if DISC_PREFIX.match(t) and re.match(r"^\s*(?:disc|disk|cd)", t, re.I):
        return "disc-prefix+text"
    if SET_PREFIX.match(t):
        return "set-prefix+text"
    art = n(r.get("artist"))
    if art and n(t) == art:
        return "ambiguous:artist-name"
    it = n(r.get("item_title"))
    if it and n(t) == it:
        return "item-title"
    return None


def class_a(r):
    tracks = r["_basis"]
    hits = []
    resolved = [k for k in tracks if k["src"] != "unresolved"]
    rec_junk = P.recording_level_junk([k["title"] for k in resolved], r.get("item_title")) \
        if len(resolved) == len(tracks) else False
    for k in resolved:
        if k["src"] == "override":
            continue
        sh = a_shape(k["title"], r, k)
        if sh is None and rec_junk:
            sh = "2b:recording-level-same-string"
        if sh:
            hits.append({"n": k["n"], "title": k["title"], "src": k["src"], "shape": sh,
                         "ambiguous": sh.startswith("ambiguous:")})
    return hits


DEMOTE_NOTE = re.compile(r"^placeholder tag title: track (\d+) '(.*)' demoted to unresolved$")


def class_a_reverse(r):
    """Real-looking tags that current code leaves unresolved (or replaces):
    either a 2b demotion or an is_real_title rejection 2a did not rescue.
    Placeholder vocabulary, filename shapes and a string repeated on 3+
    tracks are not candidates (a placeholder witnessed by a placeholder is
    no evidence). A bare-timestamp tag needs a witness other than the
    selected recording's own description (descriptions list durations)."""
    from llama.titles import tag_core
    out = []
    kept = {k["name"]: k for k in r.get("kept") or []}
    demoted = {int(m.group(1)) for m in (DEMOTE_NOTE.match(x) for x in r.get("notes") or []) if m}
    raws = [clean_tag_title((kept.get(k["file"]) or {}).get("raw_title")) for k in r["_basis"]]
    rep = Counter(x.lower() for x in raws if x)
    for k, raw in zip(r["_basis"], raws):
        if not raw or k["src"] in ("tags", "sibling-format", "override"):
            continue
        core = tag_core(raw)
        if (not core or P.is_placeholder(core) or P.looks_like_filename(core)
                or (len(raws) >= 3 and rep[raw.lower()] == len(raws))):
            continue
        if is_real_title(core) and P.is_residue(core):
            continue
        if is_real_title(core) and k["n"] not in demoted:
            continue      # a real tag that lost to another rung is not this class
        if not any(ch.isalnum() for ch in core):
            continue
        if k["src"] != "unresolved" and (eqt(k["title"], core) or contains_sequence(k["title"], [core])):
            continue      # another rung already shipped this title
        if re.fullmatch(r"0\d{1,2}", core):
            continue      # a zero-led bare number is a track number
        w = [x for x in witnesses(r, core) if x != "operator-override"]
        if re.fullmatch(r"\d{1,3}", core):
            w = [x for x in w if x != "own-desc-text"]   # numbered description lines
        if P.is_timestamp(core):
            w = [x for x in w if x not in ("own-desc-text", "own-parse") and "chosen" not in x]
        ov = (r.get("override_titles") or {}).get(str(k["n"]))
        if ov and eqt(ov, core):
            w.append("operator-override-same-position")
        if not w:
            continue
        kind = ("2b-demoted" if k["n"] in demoted else "not-real-title(no 2a rescue)")
        shape = ("numeric" if re.fullmatch(r"[\d\s.:#/-]+", core) else
                 "timestamp" if P.is_timestamp(core) else
                 "short" if sum(c.isalpha() for c in core) < 3 else "other")
        out.append({"n": k["n"], "tag": raw, "core": core, "kind": kind, "shape": shape,
                    "witness": w, "now": k["title"], "now_src": k["src"]})
    return out


# ---------------------------------------------------------------- class B
UNK = re.compile(r"^(?:research asserts unknown song|briefing mentions unknown song): (.*)$")


def class_b(r):
    flags = r.get("flags") if r.get("replayed") else r.get("stored_flags")
    flags = flags or []
    unk = [(f, UNK.match(f).group(1)) for f in flags if UNK.match(f)]
    if not unk:
        return None
    tracks = r["_basis"]
    unres = [k for k in tracks if k["src"] == "unresolved"]
    per = []
    for f, song in unk:
        w = [x for x in witnesses(r, song) if x != "operator-override"]
        opw = any(eqt(song, x) for x in (r.get("override_titles") or {}).values())
        if w and unres:
            cls = "echo-plausible"
        elif w:
            cls = "witnessed-but-no-unresolved"
        elif unres:
            cls = "unwitnessed-untitled-tape"
        else:
            cls = "unwitnessed"
        per.append({"flag": f, "song": song, "class": cls, "witness": w, "operator_override_names_it": opw})
    echo = [p for p in per if p["class"] == "echo-plausible"]
    rest = [f for f in flags if f not in {p["flag"] for p in echo}]
    return {"unknown": per, "n_unresolved": len(unres), "n_tracks": len(tracks),
            "n_echo": len(echo), "all_echo": len(echo) == len(per),
            "flags_after_collapse": rest,
            "held_only_by_echo_plus_unresolved": bool(echo) and set(rest) <= {"unresolved track titles"},
            "held_only_by_echo_plus_unresolved_plus_lowconf": bool(echo) and set(rest) <= {
                "unresolved track titles", "low-confidence structure alignment"}}


# ---------------------------------------------------------------- class C
def _canon(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def class_c(r):
    of = r.get("other_formats") or {}
    if not of or r.get("format_recovered") is None:
        return None
    kept = r.get("kept") or []
    if not kept:
        return None
    deliv = clean_tag_titles([{"name": k["name"], "title": k["raw_title"]} for k in kept])
    dmap = {k["name"]: t for k, t in zip(kept, deliv)}
    shipped = {k["file"]: k for k in r["_basis"]}
    out = []
    for fmt, o in of.items():
        if not o.get("bijection") or not o.get("titles"):
            continue
        for name, other in o["titles"].items():
            if name not in dmap:
                continue        # operator-excluded after the recovery basis
            d = dmap[name]
            if d == other:
                continue
            dr, orl = is_real_title(d), is_real_title(other)
            if not orl and not other.strip():
                cat = "other-blank"
            elif not dr and not d.strip():
                cat = "delivered-blank"
            elif not orl:
                cat = "other-not-real"
            elif not dr:
                cat = "delivered-not-real"
            elif is_placeholder_text(d) or is_placeholder_text(other):
                cat = "one-side-placeholder"
            elif _canon(d) == _canon(other):
                cat = "case/punct/space"
            elif n(d) == n(other) or fuzzy_title_eq(n(d), n(other)):
                cat = "normalizes-equal"
            elif contains_sequence(d, [other]):
                cat = "delivered-wraps-other(prefix/suffix junk)"
            elif contains_sequence(other, [d]):
                cat = "other-wraps-delivered"
            else:
                cat = "substantive"
            wd = [x for x in witnesses(r, d) if dr] if dr else []
            wo = [x for x in witnesses(r, other)] if orl else []
            sh = shipped.get(name)
            out.append({"file": name, "fmt": fmt, "delivered": d, "other": other, "cat": cat,
                        "w_delivered": wd, "w_other": wo,
                        "shipped": sh["title"] if sh else None, "shipped_src": sh["src"] if sh else None,
                        "n": sh["n"] if sh else None})
        break   # first bijective lossless format, as recovery tries them in order
    return {"recovered": r.get("format_recovered"), "delivered_fraction": r.get("delivered_fraction"),
            "other_fraction": next((o.get("fraction") for o in of.values() if o.get("bijection")), None),
            "diffs": out}


# ---------------------------------------------------------------- class D
NUMLINE = re.compile(r"^\s*(?:(?:d|cd|disc)\s*\d+\s*)?(?:t(?:rack)?\s*)?(\d{1,3})\s*[.):\-]?\s+(\S.*)$", re.I)


def numbered_lines(desc):
    import html as H
    text = re.sub(r"<br\s*/?>", "\n", desc or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = H.unescape(text)
    out = []
    for ln in text.splitlines():
        m = NUMLINE.match(ln)
        if m and not re.match(r"^\s*\d{1,2}[:/]\d", ln):
            out.append(m.group(2).strip())
    return out


def class_d(r):
    tracks = r["_basis"]
    if not tracks:
        return None
    unres = [k for k in tracks if k["src"] == "unresolved"]
    own = r.get("own_parse") or []
    nl = numbered_lines(r.get("description"))
    T = len(tracks)
    songlike = sum(1 for k in tracks if k["src"] == "unresolved" or not is_filler(k["title"]))
    res = {"n_tracks": T, "n_songlike": songlike, "n_own_parse": len(own),
           "own_conf": r.get("own_parse_conf"), "n_numbered_lines": len(nl),
           "n_unresolved": len(unres), "canonical_n": len(r.get("canonical") or []),
           "canonical_source": r.get("canonical_source"), "canonical_conf": r.get("canonical_conf")}
    lists = {}
    if len(own) == T:
        lists["own_parse"] = own
    if len(nl) == T and nl != own:
        lists["numbered_lines"] = nl
    res["exact"] = sorted(lists)
    res["off_by_one"] = sorted(k for k, L in (("own_parse", own), ("numbered_lines", nl))
                               if L and abs(len(L) - T) == 1)
    if not unres or not lists:
        res["in_class"] = False
        return res
    res["in_class"] = True
    key = "own_parse" if "own_parse" in lists else "numbered_lines"
    L = lists[key]
    res["list_used"] = key
    gain, agree, disagree, ovagree, ovdis = [], 0, 0, 0, 0
    agree_rows = []
    for k, cand in zip(tracks, L):
        if k["src"] == "unresolved":
            ok = hygienic_title(cand, set()) and not is_placeholder_text(cand)
            gain.append({"n": k["n"], "cand": cand, "hygienic": ok})
        elif k["src"] in ("tags", "sibling-format", "sibling-align") and not is_filler(k["title"]):
            if eqt(k["title"], cand) or contains_sequence(cand, [k["title"]]) or contains_sequence(k["title"], [cand]):
                agree += 1
            else:
                disagree += 1
                agree_rows.append((k["n"], k["title"], cand))
    for pos, ov in (r.get("override_titles") or {}).items():
        i = int(pos) - 1
        if 0 <= i < len(L):
            if eqt(ov, L[i]) or contains_sequence(L[i], [ov]) or contains_sequence(ov, [L[i]]):
                ovagree += 1
            else:
                ovdis += 1
    res.update({"gain": gain, "n_gain": sum(1 for g in gain if g["hygienic"]),
                "tag_agree": agree, "tag_disagree": disagree, "disagree_rows": agree_rows[:10],
                "override_agree": ovagree, "override_disagree": ovdis})
    # why the whole-tape `setlist` rung did not fire
    why = []
    if r.get("canonical_source") != "chosen":
        why.append(f"canonical source {r.get('canonical_source')}")
    if res["canonical_n"] != T:
        why.append(f"canonical {res['canonical_n']} items != {T} tracks")
    if r.get("canonical_conf") == "low":
        why.append("canonical confidence low")
    if key == "numbered_lines" and len(own) != T:
        why.append(f"parse_setlist kept {len(own)} of {len(nl)} numbered lines")
    res["setlist_rung_blocked_by"] = why or ["(rung conditions met: demoted-2b or placeholder item)"]
    tagged = any(k["src"] != "unresolved" for k in tracks)
    res["gap_rung"] = ("wholly untagged: no anchors, setlist-gap cannot fire" if not tagged else
                       "partly tagged: gap rung needs count-forced anchored runs")
    return res


# ---------------------------------------------------------------- run
classes = {"A": [], "A_ambiguous": [], "A_rev": [], "B": [], "C": [], "D": [], "D_offby1": []}
basis_counts = Counter()
for r in rows:
    tr, src = basis(r)
    r["_basis"] = tr
    r["_basis_src"] = src
    basis_counts[src] += 1
    common = {"slug": r["slug"], "state": statecol(r), "stored_held": r.get("state") == "held",
              "would_hold": would_hold(r), "basis": src, "family": r.get("family"),
              "identifier": r.get("identifier"), "flags": r.get("flags") if r.get("replayed") else r.get("stored_flags"),
              "verdict_tags": sorted(vtags(r["slug"]))}
    a = class_a(r)
    if [t for t in a if not t["ambiguous"]]:
        classes["A"].append({**common, "tracks": [t for t in a if not t["ambiguous"]]})
    if [t for t in a if t["ambiguous"]]:
        classes["A_ambiguous"].append({**common, "tracks": [t for t in a if t["ambiguous"]]})
    ar = class_a_reverse(r)
    if ar:
        classes["A_rev"].append({**common, "demotions": ar})
    b = class_b(r)
    if b:
        classes["B"].append({**common, **b})
    c = class_c(r)
    if c and c["diffs"]:
        classes["C"].append({**common, **c})
    d = class_d(r)
    if d and d["in_class"]:
        classes["D"].append({**common, **d})
    elif d and d["off_by_one"] and d["n_unresolved"]:
        classes["D_offby1"].append({**common, **{k: d[k] for k in ("n_tracks", "n_own_parse",
                                    "n_numbered_lines", "n_unresolved", "off_by_one")}})


def table(items, ntracks):
    st = Counter(i["state"] for i in items)
    return {"shows": len(items), "tracks": sum(ntracks(i) for i in items),
            "by_state": dict(st), "not_held_now": sum(1 for i in items if not i["stored_held"]),
            "silent_under_current_code": sum(1 for i in items if not i["would_hold"]),
            "family": sum(1 for i in items if i["family"])}


summary = {}
summary["meta"] = meta
summary["basis"] = dict(basis_counts)
summary["n_shows"] = len(rows)
summary["states"] = dict(Counter(statecol(r) for r in rows))
A = classes["A"]
summary["A"] = table(A, lambda i: len(i["tracks"]))
summary["A"]["by_shape"] = dict(Counter(t["shape"] for i in A for t in i["tracks"]).most_common())
summary["A"]["by_shape_src"] = dict(Counter(f"{t['shape']} | {t['src']}" for i in A for t in i["tracks"]).most_common())
summary["A"]["shapes_by_state"] = {sh: dict(Counter(i["state"] for i in A if any(t["shape"] == sh for t in i["tracks"])))
                                   for sh in summary["A"]["by_shape"]}
summary["A"]["silent_by_shape"] = dict(Counter(t["shape"] for i in A if not i["would_hold"] for t in i["tracks"]))
AR = classes["A_rev"]
summary["A_rev"] = table(AR, lambda i: len(i["demotions"]))
summary["A_rev"]["by_kind"] = dict(Counter(d["kind"] for i in AR for d in i["demotions"]))
summary["A_rev"]["by_shape"] = dict(Counter(d["shape"] for i in AR for d in i["demotions"]))
summary["A_rev"]["now_src"] = dict(Counter(d["now_src"] for i in AR for d in i["demotions"]))
summary["A_rev"]["witness_sources"] = dict(Counter(w.split(":")[0].split("(")[0] for i in AR for d in i["demotions"] for w in d["witness"]))
summary["A_rev"]["operator_confirmed"] = sum(1 for i in AR for d in i["demotions"] if "operator-override-same-position" in d["witness"])
summary["A_rev"]["top_cores"] = dict(Counter(d["core"] for i in AR for d in i["demotions"]).most_common(30))
summary["A_ambiguous"] = table(classes["A_ambiguous"], lambda i: len(i["tracks"]))
summary["A_ambiguous"]["by_shape"] = dict(Counter(t["shape"] for i in classes["A_ambiguous"] for t in i["tracks"]))
B = classes["B"]
summary["B"] = table(B, lambda i: len(i["unknown"]))
summary["B"]["flag_classes"] = dict(Counter(u["class"] for i in B for u in i["unknown"]))
summary["B"]["shows_any_echo"] = sum(1 for i in B if i["n_echo"])
summary["B"]["shows_all_echo"] = sum(1 for i in B if i["all_echo"])
summary["B"]["held_only_echo_plus_unresolved"] = sum(1 for i in B if i["held_only_by_echo_plus_unresolved"])
summary["B"]["held_only_echo_plus_unresolved_lowconf"] = sum(1 for i in B if i["held_only_by_echo_plus_unresolved_plus_lowconf"])
summary["B"]["with_unresolved"] = sum(1 for i in B if i["n_unresolved"])
C = classes["C"]
summary["C"] = table(C, lambda i: len(i["diffs"]))
summary["C"]["recovered_shows"] = sum(1 for i in C if i["recovered"])
summary["C"]["by_cat_not_recovered"] = dict(Counter(d["cat"] for i in C if not i["recovered"] for d in i["diffs"]))
summary["C"]["by_cat_recovered"] = dict(Counter(d["cat"] for i in C if i["recovered"] for d in i["diffs"]))


def side(d):
    a, b = bool(d["w_delivered"]), bool(d["w_other"])
    return "both" if a and b else "delivered" if a else "other" if b else "neither"


summary["C"]["witness_side_substantive"] = dict(Counter(side(d) for i in C if not i["recovered"] for d in i["diffs"] if d["cat"] == "substantive"))
summary["C"]["witness_side_delivered_blank_or_not_real"] = dict(Counter(side(d) for i in C if not i["recovered"] for d in i["diffs"] if d["cat"] in ("delivered-blank", "delivered-not-real")))
summary["C"]["shipped_src_delivered_blank"] = dict(Counter(d["shipped_src"] for i in C if not i["recovered"] for d in i["diffs"] if d["cat"] in ("delivered-blank", "delivered-not-real")))
summary["C"]["shows_with_substantive"] = sum(1 for i in C if not i["recovered"] and any(d["cat"] == "substantive" for d in i["diffs"]))
summary["C"]["shows_delivered_placeholder_other_real"] = sum(1 for i in C if not i["recovered"] and any(d["cat"] == "one-side-placeholder" and is_placeholder_text(d["delivered"]) and is_real_title(d["other"]) for d in i["diffs"]))
summary["C"]["tracks_delivered_placeholder_other_real"] = sum(1 for i in C if not i["recovered"] for d in i["diffs"] if d["cat"] == "one-side-placeholder" and is_placeholder_text(d["delivered"]) and is_real_title(d["other"]))
summary["C"]["shows_with_delivered_blank"] = sum(1 for i in C if not i["recovered"] and any(d["cat"] in ("delivered-blank", "delivered-not-real") for d in i["diffs"]))
D = classes["D"]
summary["D"] = table(D, lambda i: i["n_unresolved"])
summary["D"]["list_used"] = dict(Counter(i["list_used"] for i in D))
summary["D"]["tracks_gainable_hygienic"] = sum(i["n_gain"] for i in D)
summary["D"]["tag_agree"] = sum(i["tag_agree"] for i in D)
summary["D"]["tag_disagree"] = sum(i["tag_disagree"] for i in D)
summary["D"]["override_agree"] = sum(i["override_agree"] for i in D)
summary["D"]["override_disagree"] = sum(i["override_disagree"] for i in D)
summary["D"]["shows_with_tags_all_agree"] = sum(1 for i in D if i["tag_agree"] and not i["tag_disagree"])
summary["D"]["shows_with_tags_some_disagree"] = sum(1 for i in D if i["tag_disagree"])
summary["D"]["wholly_untagged"] = sum(1 for i in D if i["gap_rung"].startswith("wholly"))
summary["D"]["setlist_rung_blocked_by"] = dict(Counter(re.sub(r"\d+", "N", w) for i in D for w in i["setlist_rung_blocked_by"]))
summary["D"]["tag_position_agreement_rate"] = round(summary["D"]["tag_agree"] / max(1, summary["D"]["tag_agree"] + summary["D"]["tag_disagree"]), 3)
summary["D"]["override_position_agreement_rate"] = round(summary["D"]["override_agree"] / max(1, summary["D"]["override_agree"] + summary["D"]["override_disagree"]), 3)
summary["D_offby1"] = {"shows": len(classes["D_offby1"]),
                       "by_state": dict(Counter(i["state"] for i in classes["D_offby1"])),
                       "unresolved_tracks": sum(i["n_unresolved"] for i in classes["D_offby1"])}
sets = {k: {i["slug"] for i in v} for k, v in classes.items() if k not in ("D_offby1", "A_ambiguous")}
union = set().union(*sets.values())
summary["union"] = {"shows": len(union),
                    "not_held_now": sum(1 for s in union if by[s].get("state") != "held"),
                    "silent": sum(1 for s in union if not would_hold(by[s]))}
summary["overlaps"] = {f"{a}&{b}": len(sets[a] & sets[b]) for a in sets for b in sets if a < b}
# overnight-seed cross-check
seed = {"A": "placeholder-titles-shipped", "B": "flags-echo-untitled-tape",
        "C": "same-item-other-format-has-titles", "D": "description-positional-titles"}
summary["seed_crosscheck"] = {}
for k, tag in seed.items():
    tagged = {s for s, v in verdicts.items() if tag in (v.get("root_causes") or [])}
    summary["seed_crosscheck"][k] = {"tag": tag, "tagged": len(tagged), "in_library": len(tagged & set(by)),
                                     "tagged_and_in_class": len(tagged & sets[k]),
                                     "tagged_not_in_class": sorted(tagged & set(by) - sets[k])[:40]}
rev = {s for s, v in verdicts.items() if any(re.search(r"false-demotion|demoted", c) for c in (v.get("root_causes") or []))}
summary["seed_crosscheck"]["A_rev"] = {"tagged": len(rev), "tagged_and_in_class": len(rev & sets["A_rev"]),
                                       "tagged_not_in_class": sorted(rev & set(by) - sets["A_rev"])[:40]}

(HERE / "census.json").write_text(json.dumps({"summary": summary, "classes": classes}, indent=1, default=str))
print(json.dumps(summary, indent=1, default=str))


# ---------------------------------------------------------------- packets
def track_table(r, extra_cols, extra):
    hdr = "| n | filename | dur | shipped title | title_source | matched | " + " | ".join(extra_cols) + " |"
    sep = "|" + "---|" * (6 + len(extra_cols))
    lines = [hdr, sep]
    for k in r["_basis"]:
        ex = extra(k)
        dur = f"{k['dur']:.0f}s" if k.get("dur") else "?"
        lines.append(f"| {k['n']} | {k['file']} | {dur} | {k['title']} | {k['src']} | {k['matched']} | "
                     + " | ".join(str(x).replace("|", "/") for x in ex) + " |")
    return "\n".join(lines)


def desc_block(r):
    d = r.get("description") or "(none)"
    if len(d) > 6000:
        d = d[:6000] + "\n...[trimmed]"
    return "```\n" + d + "\n```"


def verdict_block(slug):
    v = verdicts.get(slug)
    if not v:
        return "(no overnight verdict: show was not held overnight)"
    out = [f"action: {json.dumps(v.get('action'))[:800]}", f"root_causes: {v.get('root_causes')}",
           f"show_correct_after_action: {v.get('show_correct_after_action')}"]
    ev = v.get("evidence")
    if ev:
        out.append("evidence: " + json.dumps(ev)[:2000])
    for f in v.get("flags") or []:
        out.append(f"- flag `{f.get('flag')}`: {f.get('verdict')} ({f.get('confidence')}) -- {f.get('why')}")
    return "\n".join(out)


def head(r, cls, why):
    tr = r["_basis"]
    return (f"# {r['slug']} -- class {cls}\n\n"
            f"- picked because: {why}\n- artist: {r.get('artist')} (Garcia family: {r.get('family')})\n"
            f"- date: {r.get('date')}\n- selected item: {r.get('identifier')}  (https://archive.org/details/{r.get('identifier')})\n"
            f"- item title: {r.get('item_title')}\n"
            f"- library state: {statecol(r)}; held now: {r.get('state') == 'held'}; "
            f"current code would hold: {would_hold(r)}\n"
            f"- titles basis: {r['_basis_src']} (operator `overrides.titles` STRIPPED, to show what a fresh get ships)\n"
            f"- operator title overrides in the library: {r.get('override_titles') or 'none'}\n"
            f"- review flags (current code, titles-overrides stripped): {r.get('flags') if r.get('replayed') else r.get('stored_flags')}\n"
            f"- review flags (current code, as the library has it): {r.get('asis_flags')}\n"
            f"- canonical setlist source: {r.get('canonical_source')} ({len(r.get('canonical') or [])} items, conf {r.get('canonical_conf')})\n"
            f"- tracks: {len(tr)}\n")


def write_packets(cls, picks):
    d = PK / cls
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.md"):
        f.unlink()
    idx = []
    for item, why in picks:
        r = by[item["slug"]]
        md = [head(r, cls, why)]
        if cls == "A":
            hit = {t["n"]: t for t in item["tracks"]}
            md.append("## Tracks (A: `shape` = why the census thinks the shipped title is placeholder-like)\n")
            md.append(track_table(r, ["A shape", "raw tag (delivered)"],
                                  lambda k: [hit[k["n"]]["shape"] if k["n"] in hit else "",
                                             _raw(r, k["file"])]))
        elif cls == "A_rev":
            dm = {x["n"]: x for x in item["demotions"]}
            md.append("## Tracks (A-reverse: 2b demoted the raw tag; `witness` = cross-sources naming that tag)\n")
            md.append(track_table(r, ["demoted tag", "witness"],
                                  lambda k: [dm[k["n"]]["tag"] if k["n"] in dm else "",
                                             ", ".join(dm[k["n"]]["witness"]) if k["n"] in dm else ""]))
        elif cls == "B":
            md.append("## Unknown-song flags\n")
            for u in item["unknown"]:
                md.append(f"- `{u['flag']}` -> census: {u['class']}; witnesses: {u['witness'] or 'none'}")
            md.append(f"\nflags left if echo flags collapsed: {item['flags_after_collapse']}\n")
            md.append("## Tracks\n")
            md.append(track_table(r, ["raw tag"], lambda k: [_raw(r, k["file"])]))
        elif cls == "C":
            dm = {x["file"]: x for x in item["diffs"]}
            md.append(f"## Tracks (C: delivered-format tag vs other-format tag for the same stem; "
                      f"recovery fired: {item['recovered']}; delivered fraction {item['delivered_fraction']}, "
                      f"other {item['other_fraction']})\n")
            md.append(track_table(r, ["delivered tag (cleaned)", "other-format tag (cleaned)", "category", "witness delivered", "witness other"],
                                  lambda k: ([dm[k["file"]]["delivered"], dm[k["file"]]["other"], dm[k["file"]]["cat"],
                                              ",".join(dm[k["file"]]["w_delivered"]), ",".join(dm[k["file"]]["w_other"])]
                                             if k["file"] in dm else [_clean(r, k["file"]), "(same)", "", "", ""])))
        elif cls == "D":
            L = item.get("list_used")
            lst = (r.get("own_parse") if L == "own_parse" else numbered_lines(r.get("description")))
            md.append(f"## Tracks (D: candidate = item N of the selected description's `{L}` list, by position; "
                      f"{item['n_tracks']} tracks, own parse {item['n_own_parse']} ({item['own_conf']}), "
                      f"numbered lines {item['n_numbered_lines']}; setlist rung blocked by: {item['setlist_rung_blocked_by']}; {item['gap_rung']})\n"
                      )
            md.append(track_table(r, ["positional candidate"], lambda k: [lst[k["n"] - 1] if k["n"] - 1 < len(lst) else ""]))
        md.append("\n## Canonical setlist (as gather built it)\n")
        md.append(", ".join(f"[{c['set']}] {c['title']}" for c in (r.get("canonical") or [])) or "(empty)")
        md.append("\n## Selected recording's own parse_setlist items\n")
        md.append(f"({r.get('own_parse_conf')}) " + " / ".join(r.get("own_parse") or []))
        if cls == "C" or r.get("other_formats"):
            md.append("\n## Other-format copies of the same item\n")
            for fmt, o in (r.get("other_formats") or {}).items():
                md.append(f"- {fmt}: {o['n']} kept files, stem bijection {o['bijection']}, title fraction {o['fraction']}")
        if r.get("donors"):
            md.append("\n## Sibling recordings' tag titles (load_donor_tapes)\n")
            for dn in r["donors"][:4]:
                md.append(f"- {dn['id']}: " + " / ".join(dn["titles"]))
        md.append("\n## Gather/vet notes\n")
        md.append("\n".join(f"- {x}" for x in (r.get("notes") or [])) or "(none)")
        md.append("\n## Selected item description (verbatim)\n")
        md.append(desc_block(r))
        md.append("\n## Overnight adjudication\n")
        md.append(verdict_block(r["slug"]))
        (d / f"{r['slug']}.md").write_text("\n".join(md) + "\n")
        idx.append({"slug": r["slug"], "why": why})
    (d / "index.json").write_text(json.dumps(idx, indent=1))


def _raw(r, fname):
    for k in r.get("kept") or []:
        if k["name"] == fname:
            return k["raw_title"]
    return ""


def _clean(r, fname):
    return clean_tag_title(_raw(r, fname))


def stratified(items, key, total=30):
    """Round-robin over strata (key(item)), shuffled within each."""
    groups = defaultdict(list)
    for i in items:
        groups[key(i)].append(i)
    for g in groups.values():
        random.shuffle(g)
    out = []
    keys = sorted(groups)
    while len(out) < total and any(groups.values()):
        for k in keys:
            if groups[k] and len(out) < total:
                out.append((groups[k].pop(), k))
    return out


def held_lbl(i):
    return "held" if i["stored_held"] else ("silent" if not i["would_hold"] else "not-held-but-would-hold")


write_packets("A", [(i, f"stratum {k}") for i, k in stratified(
    A, lambda i: f"{held_lbl(i)}/{Counter(t['shape'] for t in i['tracks']).most_common(1)[0][0]}/{'fam' if i['family'] else 'nonfam'}")])
write_packets("A_rev", [(i, f"stratum {k}") for i, k in stratified(
    AR, lambda i: f"{held_lbl(i)}/{i['demotions'][0]['kind']}/{i['demotions'][0]['shape']}")])
write_packets("B", [(i, f"stratum {k}") for i, k in stratified(
    B, lambda i: f"{held_lbl(i)}/{'all-echo' if i['all_echo'] else 'mixed' if i['n_echo'] else 'no-echo'}/{'fam' if i['family'] else 'nonfam'}")])
write_packets("C", [(i, f"stratum {k}") for i, k in stratified(
    [i for i in C if not i["recovered"]],
    lambda i: f"{held_lbl(i)}/{Counter(d['cat'] for d in i['diffs']).most_common(1)[0][0]}")])
write_packets("D", [(i, f"stratum {k}") for i, k in stratified(
    D, lambda i: f"{held_lbl(i)}/{i['list_used']}/{'untagged' if i['gap_rung'].startswith('wholly') else 'partly-tagged'}/{'fam' if i['family'] else 'nonfam'}")])


# ---------------------------------------------------------------- extras
def _sub(items, pred):
    xs = [i for i in items if pred(i)]
    return {"shows": len(xs), "by_state": dict(Counter(i["state"] for i in xs)),
            "silent_under_current_code": sum(1 for i in xs if not i["would_hold"]),
            "not_held_now": sum(1 for i in xs if not i["stored_held"])}


extras = {
    "C_substantive": _sub(C, lambda i: not i["recovered"] and any(d["cat"] == "substantive" for d in i["diffs"])),
    "C_substantive_other_side_witnessed_only": _sub(C, lambda i: not i["recovered"] and any(
        d["cat"] == "substantive" and d["w_other"] and not d["w_delivered"] for d in i["diffs"])),
    "C_delivered_placeholder_other_real": _sub(C, lambda i: not i["recovered"] and any(
        d["cat"] == "one-side-placeholder" and is_placeholder_text(d["delivered"]) and is_real_title(d["other"]) for d in i["diffs"])),
    "C_delivered_blank_other_real": _sub(C, lambda i: not i["recovered"] and any(
        d["cat"] in ("delivered-blank", "delivered-not-real") for d in i["diffs"])),
    "C_cosmetic_only": _sub(C, lambda i: not i["recovered"] and all(
        d["cat"] in ("case/punct/space", "normalizes-equal", "other-blank", "other-not-real") for d in i["diffs"])),
    "B_asis_unknown_flag_shows": sum(1 for r in rows if any(UNK.match(f) for f in r.get("asis_flags") or [])),
    "B_shows_with_title_overrides": sum(1 for i in B if by[i["slug"]].get("override_titles")),
    "D_asis_still_unresolved": sum(1 for i in D if any(t["src"] == "unresolved" for t in by[i["slug"]].get("asis_tracks") or [])),
    "A_rev_silent_tracks_shipped_wrong": sum(1 for i in AR if not i["would_hold"] for d in i["demotions"]),
    "A_silent_shows_by_shape": dict(Counter(sh for i in A if not i["would_hold"] for sh in {t["shape"] for t in i["tracks"]})),
}
d = json.loads((HERE / "census.json").read_text())
d["summary"]["extras"] = extras
(HERE / "census.json").write_text(json.dumps(d, indent=1, default=str))
print(json.dumps(extras, indent=1))
