#!/usr/bin/env python3
"""Read-only gate probe for title hygiene (held-backlog piece 3; plan Task 13, spec
`docs/superpowers/specs/2026-10-22-title-hygiene-design.md`, Acceptance 1).

`dump` runs the UNWIRED `gather.title_inputs` + `gather.title_cascade` over the library on
two views and writes one JSON line per show to `<out>/dump.jsonl`:

  fresh-get view  a shadow of the show dir whose `overrides.json` has `titles`,
                  `set_breaks` and `encore_after` removed (`replay_holds._shadow`): what a
                  fresh `llama get` would ship. Arms `none`, `all`, `all-<slice>`.
  as-is view      the show dir itself, every override kept. Arm `none` only.

Per view, today's title block is captured by wrapping `gather.accept_short_tags` and
`gather._sibling_transfer` (in-process module patches, so each `--jobs` worker installs its
own) while `replay.compute_legs` runs: the tracks just after 2a, the operator notes up to
that point and sibling-align's notes. The cascade's inputs are then BUILT by `title_inputs`
from the same cached metadata, overrides, candidate and events, with `build` calling
`build_canonical` cache-only (provider None); no field is reconstructed from the captures.
Gate 0 (`gate0`, `gate0_as_is`): arm `none` equals today on that view in per-track titles
and sources, operator notes and sibling notes; `gate0_diff` names the first difference.

Every arm containing `slice5` gets `cosmetic_strip` over the cascade's tracks, last; a
position it changed carries a `+5` suffix on its path.

The `alt_*` fields are the plan-reading alternatives Task 14 only tabulates, computed on
the fresh-get view's `all` arm. Positions in them, as in `record`, are 0-BASED; `n` in
`today` is 1-based.

Read-only: the library and cache are only read; per-show scratch lives under a temp dir
removed at exit; the one file written is `dump.jsonl` (atomically). An `--out` overlapping
the library root, or a `llama` imported from outside this tree, is refused (exit 2). No LLM
call is made. Run with the tree's own interpreter:
`./.venv/bin/python scripts/title_hygiene_probe.py dump --jobs 6 --out ~/.llama-harness/piece3/gate`.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import shutil
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path

import llama
from llama import jerrybase, title_hygiene
from llama.catalog import derive_state
from llama.config import DEFAULT_ROOT, load_config
from llama.desc_list import DescList, clean_entries, clean_one, read_numbered
from llama.junk import FORMAT_BY_AUDIO
from llama.ledger import Ledger
from llama.models import Provenance, Show
from llama.replay import (CacheOnlyIA, classify, code_identity, compute_legs, config_fingerprint,
                          setlistfm_client, setlistfm_configured)
from llama.stages import gather as G
from llama.structure import (LOOSE_TITLE_RATIO, align, fuzzy_norm_title, fuzzy_title_eq,
                             gap_span, is_filler, unresolved_runs)
from llama.title_cosmetics import cosmetic_strip
from llama.title_hygiene import (ALL_SLICES, INDEPENDENT_SOURCES, block_size_mismatch, duplicate,
                                 judge)
from llama.titles import tag_core
from llama.workspace import ShowWorkspace, read_model, read_overrides

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_holds  # noqa: E402  (the shadow and the identity/overlap guards)

FRESH_KEYS = ("titles", "set_breaks", "encore_after")
ARMS: dict[str, frozenset[str]] = {"none": frozenset(), "all": ALL_SLICES,
                                   **{f"all-{s}": ALL_SLICES - {s} for s in sorted(ALL_SLICES)}}
PROGRESS_EVERY = 100


# --- the capture wrappers (module patches; installed once per process) ----------------------

_CAP: dict = {"armed": False}
_ORIG: dict = {}


def _install() -> None:
    if _ORIG:
        return
    _ORIG["short"], _ORIG["sib"] = G.accept_short_tags, G._sibling_transfer

    def accept_short_tags(tracks, *a, **kw):
        out, notes = _ORIG["short"](tracks, *a, **kw)
        if _CAP["armed"]:
            # compute_gather's `op_notes` up to 2a (2a's own notes are appended after).
            _CAP["prefix"] = list(sys._getframe(1).f_locals["op_notes"])
            _CAP["tracks"], _CAP["short"] = list(out), list(notes)
        return out, notes

    def _sibling_transfer(*a, **kw):
        out, notes = _ORIG["sib"](*a, **kw)
        if _CAP["armed"]:
            _CAP["sib"] = list(notes)
        return out, notes

    G.accept_short_tags = accept_short_tags
    G._sibling_transfer = _sibling_transfer


def _uninstall() -> None:
    if _ORIG:
        G.accept_short_tags, G._sibling_transfer = _ORIG["short"], _ORIG["sib"]
        _ORIG.clear()


# --- per-process state ------------------------------------------------------------------------

_W: dict = {}


def _init(config_path: str, scratch_root: str) -> None:
    logging.disable(logging.CRITICAL)
    cfg = load_config(Path(config_path))
    _W.update(
        cfg=cfg, ia=CacheOnlyIA(cfg.root / "cache"), slfm=setlistfm_client(cfg),
        delivered={e.performance_id for e in Ledger(cfg.root / "ledger.jsonl").entries()
                   if e.status == "delivered"},
        scratch=Path(scratch_root) / f"w{os.getpid()}")
    _install()


# --- JSON ---------------------------------------------------------------------------------------

def _js(obj):
    """JSON-ready form: dataclasses by field (plus DDecision's `shift`), sets sorted, tuples as
    lists, dict keys as strings (json's own rule, applied here so rows compare equal)."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {f.name: _js(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        if isinstance(obj, title_hygiene.DDecision):
            out["shift"] = obj.shift
        return out
    if isinstance(obj, dict):
        return {str(k): _js(v) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        return sorted(_js(v) for v in obj)
    if isinstance(obj, (list, tuple)):
        return [_js(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return _js(obj.model_dump())
    return obj


def _cleaned(c) -> dict:
    return {"text": c.text, "durations": list(c.durations), "filler_marked": c.filler_marked,
            "leader_stripped": c.leader_stripped,
            "trailing_time_stripped": c.trailing_time_stripped}


def _desc_list(d: DescList | str) -> dict:
    if isinstance(d, str):
        return {"reason": d}
    return {"reason": None, "reader": d.reader, "n": len(d.raws),
            "boundaries": list(d.boundaries),
            "entries": [{"raw": r, "block": b, **_cleaned(c)}
                        for r, c, b in zip(d.raws, d.cleaned, d.blocks)]}


# --- the alternatives' own rules -----------------------------------------------------------------

def adjacent_duplicate_cleaned(cands: dict[int, str], tracks) -> tuple[int, str, str] | None:
    """`title_hygiene.adjacent_duplicate` with `clean_one` applied to a NEIGHBOUR's current
    title as well (a candidate is already cleaned). The ruling question (Task 5): the built
    check 2 compares a cleaned candidate with the neighbour's raw title."""
    for pos in sorted(cands):
        for nb in (pos - 1, pos + 1):
            if nb < 0 or nb >= len(tracks):
                continue
            if nb in cands:
                other = cands[nb]
            elif tracks[nb].title_source != "unresolved" and tracks[nb].title.strip():
                other = clean_one(tracks[nb].title).text
            else:
                continue
            if duplicate(cands[pos], other):
                return pos, cands[pos], other
    return None


def bracketed_s(tracks, paths) -> dict:
    """R4: the stricter non-chosen S alternative. The S-filled positions (`S`, `S-deferred`)
    are set back to unresolved; a run of unresolved tracks may keep its S fills only when
    `structure.gap_span` (verbatim, its leading-edge branch included) closes it with
    anchors = positions carrying an independent (`INDEPENDENT_SOURCES`), song-like title."""
    fills = [i for i, p in enumerate(paths) if p.split("+")[0] in ("S", "S-deferred")]
    pre = [t.model_copy(update={"title_source": "unresolved"}) if i in fills else t
           for i, t in enumerate(tracks)]
    anchors = {i: (0, 0) for i, t in enumerate(pre)
               if t.title_source in INDEPENDENT_SOURCES and not is_filler(t.title)}
    runs, remain, remain_both = [], [], []
    for lo, hi in unresolved_runs(pre):
        inside = [i for i in fills if lo <= i <= hi]
        if not inside:
            continue
        closed = gap_span(anchors, lo, hi, len(pre)) is not None
        both = (lo - 1) in anchors and (hi + 1) in anchors
        runs.append({"lo": lo, "hi": hi, "left": (lo - 1) in anchors,
                     "right": (hi + 1) in anchors, "closed": closed, "both_sides": both})
        if closed:
            remain += inside
        if both:
            remain_both += inside
    return {"fills": fills, "remain": remain,
            "dropped": [i for i in fills if i not in remain], "runs": runs,
            "remain_both_sides": remain_both,
            "dropped_both_sides": [i for i in fills if i not in remain_both]}


def c2_arms(a: str, b: str) -> dict:
    """Which of `loosely_same_title`'s arms make two titles agree, on cleaned copies.
    `strict` is core equality or `fuzzy_title_eq`; `containment` its containment arm.
    `containment_only`: the titles agree ONLY through that arm (containment, cores differ,
    ratio below LOOSE_TITLE_RATIO, both cores of 3+ letters)."""
    na, nb = fuzzy_norm_title(clean_one(a).text), fuzzy_norm_title(clean_one(b).text)
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, na, nb).ratio() if na and nb else None
    containment = bool(na and nb and (na in nb or nb in na))
    only = (containment and na != nb and ratio < LOOSE_TITLE_RATIO
            and not title_hygiene._short_core(na) and not title_hygiene._short_core(nb))
    return {"strict": bool(na and nb and (na == nb or fuzzy_title_eq(na, nb))),
            "containment": containment, "containment_only": only,
            "ratio": round(ratio, 4) if ratio is not None else None,
            "agrees": title_hygiene.agrees(a, b)}


# --- one view -------------------------------------------------------------------------------------

def _inputs(view: ShowWorkspace, stored: Show, prov: Provenance):
    cfg, ia, slfm = _W["cfg"], _W["ia"], _W["slfm"]
    md = ia.metadata(stored.identifier)
    meta = md.get("metadata", {})
    cand = prov.candidate
    artist = str(G._creator(meta) or cand.collection)
    events = jerrybase.lookup(artist, cand.date) if cfg.jerrybase.enabled else []

    def build(kept):
        return G.build_canonical(ia, cand, stored.identifier, meta, kept, artist, events,
                                 setlistfm=slfm, provider=None)
    inp = G.title_inputs(md, read_overrides(view), ia=ia, candidate=cand,
                         identifier=stored.identifier, artist=artist,
                         want=FORMAT_BY_AUDIO[cfg.audio_format], events=events, build=build)
    return inp, artist, meta


def inputs_for(config_path: Path, slug: str):
    """`title_inputs` for a show dir as it stands (the as-is view); for tests. Reads only."""
    _init(str(config_path), tempfile.gettempdir())
    try:
        ws = ShowWorkspace(_W["cfg"].root / "shows" / slug)
        return _inputs(ws, read_model(ws.show, Show), read_model(ws.provenance, Provenance))[0]
    finally:
        _uninstall()


def _today(view: ShowWorkspace, scratch: Path):
    """compute_legs over the view, with the capture armed. Returns (legs | None, error,
    capture | None)."""
    _CAP.clear()
    _CAP.update(armed=True, sib=[])
    legs, err = None, None
    try:
        legs = compute_legs(view, config=_W["cfg"], ia=_W["ia"], slfm=_W["slfm"], scratch=scratch)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:300]
    finally:
        _CAP["armed"] = False
        shutil.rmtree(scratch, ignore_errors=True)
    cap = None
    if "tracks" in _CAP:
        cap = {"tracks": _CAP["tracks"], "op_notes": _CAP["prefix"] + _CAP["short"],
               "struct_notes": list(_CAP["sib"])}
    return legs, err, cap


def first_difference(today: dict, tracks, op_notes, struct_notes) -> str | None:
    t0 = today["tracks"]
    if len(t0) != len(tracks):
        return f"track count: {len(t0)} != {len(tracks)}"
    for i, (a, b) in enumerate(zip(t0, tracks)):
        if a.title != b.title:
            return f"track {i + 1} title: {a.title!r} != {b.title!r}"
        if a.title_source != b.title_source:
            return f"track {i + 1} source: {a.title_source!r} != {b.title_source!r}"
    for name, x, y in (("op_notes", today["op_notes"], op_notes),
                       ("struct_notes", today["struct_notes"], struct_notes)):
        for i in range(max(len(x), len(y))):
            a = x[i] if i < len(x) else None
            b = y[i] if i < len(y) else None
            if a != b:
                return f"{name}[{i}]: {a!r} != {b!r}"
    return None


def _run_arm(inp, enabled: frozenset[str]):
    out = G.title_cascade(inp, enabled=enabled)
    tracks, paths, strip_notes = list(out.tracks), list(out.paths), []
    if "slice5" in enabled:
        tracks, strip_notes, changed = cosmetic_strip(tracks)
        for i in changed:
            paths[i] += "+5"
    coverage = align(tracks, inp.cb.setlist, aliases=inp.family_aliases).coverage
    return out, tracks, paths, strip_notes, coverage


def _arm_row(out, tracks, paths, strip_notes, coverage) -> dict:
    return {"tracks": [{"title": t.title, "source": t.title_source} for t in tracks],
            "paths": paths, "self_filled": out.self_filled,
            "op_notes": list(out.op_notes) + strip_notes, "struct_notes": list(out.struct_notes),
            "record": _js(out.record), "coverage": coverage}


def _view(view: ShowWorkspace, stored: Show, prov: Provenance, scratch: Path,
          arms: dict[str, frozenset[str]], *, capture_all: bool = False) -> dict:
    """One view: today (captured), the inputs, and each arm. `gate0` compares arm `none`."""
    legs, err, cap = _today(view, scratch)
    res = {"legs": legs, "error": err, "cap": cap, "inp": None, "arms": {}, "gate0": None,
           "gate0_diff": None, "raw": {}, "dup_calls": []}
    if cap is None:
        return res
    try:
        inp, artist, meta = _inputs(view, stored, prov)
    except Exception as e:
        res["gate0"], res["gate0_diff"] = False, f"title_inputs raised {type(e).__name__}: {e}"
        return res
    res.update(inp=inp, artist=artist, meta=meta)
    for name, enabled in arms.items():
        calls: list = []
        real_dup = title_hygiene.adjacent_duplicate
        if capture_all and name == "all":
            def spy(cands, tracks):
                hit = real_dup(cands, tracks)
                f1 = sys._getframe(1)
                rung = ("D" if f1.f_code.co_name == "decide_d" else
                        "S-deferred" if f1.f_back.f_code.co_name == "apply_deferred_setlist"
                        else "S")
                calls.append((rung, dict(cands), list(tracks), hit))
                return hit
            title_hygiene.adjacent_duplicate = spy
        try:
            out, tracks, paths, strip_notes, coverage = _run_arm(inp, enabled)
        except Exception as e:
            res["arms"][name] = {"error": f"{type(e).__name__}: {e}"[:300]}
            if name == "none":
                res["gate0"], res["gate0_diff"] = False, f"cascade raised {type(e).__name__}: {e}"
            continue
        finally:
            title_hygiene.adjacent_duplicate = real_dup
        res["arms"][name] = _arm_row(out, tracks, paths, strip_notes, coverage)
        res["raw"][name] = (out, tracks, paths)
        if name == "all":
            res["dup_calls"] = calls
        if name == "none":
            diff = first_difference(cap, out.tracks, out.op_notes, out.struct_notes)
            res["gate0"], res["gate0_diff"] = diff is None, diff
    return res


# --- the alternatives -----------------------------------------------------------------------------

def _layer_titles(inp, record) -> list[str]:
    """The tag layer the cascade's later rungs read: after C when C ran."""
    if record.lossless is not None:
        return list(record.lossless.titles)
    return list(G.tag_layer(inp.kept, inp.format_titles, inp.tag_gate_basis)[0])


def _s_candidates(inp, record, titles: list[str]) -> list[dict]:
    """Every S candidate (a position reaching today's S branch, with a count-matched canonical
    not `low`), cleaned as `_s_check` cleans them (the leader vote over all of them), and
    check 1's verdict with and without the own-tag-core exemption."""
    canonical = inp.cb.setlist
    if canonical.confidence == "low" or len(canonical.items) != len(inp.kept):
        return []
    order = sorted(record.s_positions)
    cleaned = clean_entries([canonical.items[p].title for p in order])
    out = []
    for p, c in zip(order, cleaned):
        stem = os.path.splitext(os.path.basename(inp.kept[p]["name"]))[0]
        core = tag_core(titles[p] if p < len(titles) else "")
        kw = dict(track_no=p + 1, first=p == 0, stem=stem, metadata_norms=inp.metadata_norms)
        h = judge(c, own_core=core, **kw)
        h0 = judge(c, own_core="", **kw)
        out.append({"pos": p, "raw": canonical.items[p].title, **_cleaned(c),
                    "own_core": core, "judge": _js(h), "judge_without_exemption": _js(h0)})
    return out


def _alternatives(v: dict) -> dict:
    """The `alt_*` fields, from the fresh-get view's `all` arm."""
    keys = ("alt_bare_number", "alt_hygiene_all_entries", "alt_encore_restart", "alt_c1",
            "alt_bracketed_s", "alt_encore_fold", "alt_check2_cleaned", "alt_c2_containment",
            "alt_filler_confirm")
    alt = dict.fromkeys(keys)
    alt["s_candidates"] = []
    inp = v["inp"]
    if inp is None or "all" not in v["raw"]:
        return alt
    out, tracks, paths = v["raw"]["all"]
    rec, n = out.record, len(inp.kept)
    titles = _layer_titles(inp, rec)
    used = inp.desc.used
    filenames = [f["name"] for f in inp.kept]
    stems = [os.path.splitext(os.path.basename(f))[0] for f in filenames]

    # R14 (and R19's S half): bare-number S candidates and the exemption.
    s_cands = _s_candidates(inp, rec, titles)
    alt["s_candidates"] = s_cands
    alt["alt_bare_number"] = [
        {"pos": c["pos"], "text": c["text"], "own_core": c["own_core"], "judge": c["judge"],
         "exemption_decided": c["judge"] != c["judge_without_exemption"]}
        for c in s_cands if title_hygiene._BARE_NUMBER.match(c["text"])]

    # R15: show-level check-1 failures over EVERY entry of the count-matched list.
    if used is not None:
        pre_d_open = sorted({i for i, t in enumerate(out.tracks) if t.title_source == "unresolved"}
                            | set(rec.d.fills if rec.d is not None else ())
                            | set(rec.deferred_applied))
        fails = []
        for i, c in enumerate(used.cleaned):
            h = judge(c, track_no=i + 1, first=i == 0, stem=stems[i] if i < n else "",
                      own_core=tag_core(titles[i] if i < len(titles) else ""),
                      metadata_norms=inp.metadata_norms)
            if h.scope == "show":
                fails.append({"pos": i, "check": h.check, "text": c.text,
                              "candidate": i in pre_d_open})
        alt["alt_hygiene_all_entries"] = {
            "d_ran": rec.d is not None, "candidates": pre_d_open, "failures": fails,
            "extra": [f for f in fails if not f["candidate"]]}

    # R16: a numbering restart after an `Encore` header.
    desc = G._description(v["meta"])
    default, enc = read_numbered(desc), read_numbered(desc, encore_header=True)
    alt["alt_encore_restart"] = {
        "default": "admitted" if isinstance(default, DescList) else default,
        "encore_header": "admitted" if isinstance(enc, DescList) else enc,
        "admits_new": isinstance(enc, DescList) and not isinstance(default, DescList),
        "count_matched": isinstance(enc, DescList) and len(enc.raws) == n}

    # R17: C1's per-target verdicts and the (c) adoptions where (a) or (b) disagreed.
    ll = rec.lossless
    if ll is not None:
        verdicts = {i: v_ for i, v_ in ll.c1_verdicts.items()}
        alt["alt_c1"] = {
            "declined": ll.declined, "c_holds": ll.c_holds,
            "targets": [{"pos": i, "a": va, "b": vb, "adopted": ll.changed.get(i) == "C1"}
                        for i, (va, vb) in sorted(verdicts.items())],
            "would_pass_alone": sum(1 for va, vb in verdicts.values() if va or vb),
            "via_c_where_ab_disagreed": sorted(
                i for i, (va, vb) in verdicts.items()
                if ll.changed.get(i) == "C1" and not (va or vb) and (va is False or vb is False))}

    # R4: the stricter non-chosen S alternative.
    if inp.cb.source == "chosen":
        alt["alt_bracketed_s"] = {"applies": False}
    else:
        alt["alt_bracketed_s"] = {"applies": True, **bracketed_s(out.tracks, list(out.paths))}

    # R10: the encore fold.
    if used is not None:
        fold = block_size_mismatch(filenames, used)
        no_fold = block_size_mismatch(filenames, used, fold_encore=False)
        alt["alt_encore_fold"] = {"fold": fold, "no_fold": no_fold, "differs": fold != no_fold,
                                  "wholly_untagged": rec.wholly_untagged}

    # Task 5's ruling: check 2 with cleaned neighbour titles.
    fills_of = {"D": sorted(rec.d.fills) if rec.d is not None else [],
                "S": sorted(rec.s_plan.fills), "S-deferred": list(rec.deferred_applied)}
    calls, would = [], {"D": [], "S": [], "S-deferred": []}
    for rung, cands, nbs, hit in v["dup_calls"]:
        cleaned_hit = adjacent_duplicate_cleaned(cands, nbs)
        calls.append({"rung": rung, "built": _js(hit), "cleaned": _js(cleaned_hit)})
        if hit is None and cleaned_hit is not None:
            would[rung] = fills_of[rung]
    alt["alt_check2_cleaned"] = {"calls": calls, "would_decline": would}

    # Task 8's ruling: C2 replacements agreeing with the reference only through containment.
    if ll is not None:
        ref_a = [c.text for c in used.cleaned] if used is not None and len(used.cleaned) == n \
            else None
        canon = inp.cb.setlist.items
        ref = ref_a if ref_a is not None else ([it.title for it in canon] if len(canon) == n
                                               else None)
        rows = []
        for i, c in sorted(ll.changed.items()):
            if c != "C2" or ref is None:
                continue
            arms = c2_arms(ll.titles[i], ref[i])
            rows.append({"pos": i, "lossless": ll.titles[i], "ref": ref[i],
                         "reference": "list" if ref_a is not None else "canonical", **arms})
        alt["alt_c2_containment"] = {"c2": rows,
                                     "containment_only": [r["pos"] for r in rows
                                                          if r["containment_only"]]}

    # Slice-4 confirmations whose entry was `Filler:`-marked.
    if used is not None:
        alt["alt_filler_confirm"] = [i for i in rec.short4 if used.cleaned[i].filler_marked]
    else:
        alt["alt_filler_confirm"] = []
    return alt


# --- one show ---------------------------------------------------------------------------------------

def _voiced(slug: str) -> bool | None:
    delivery = _W["cfg"].delivery_path
    if delivery is None:
        return None
    try:
        m = json.loads((Path(delivery) / slug / "manifest.json").read_text())
    except (OSError, ValueError):
        return False
    return isinstance(m, dict) and m.get("dj_audio") is not None


def one(d: str) -> dict:
    d = Path(d)
    ws = ShowWorkspace(d)
    scratch = _W["scratch"] / d.name
    shadow_root = _W["scratch"] / ".shadow"
    row: dict = {"slug": d.name, "unreplayable": None, "gate0": None, "gate0_as_is": None,
                 "gate0_diff": None, "gate0_as_is_diff": None}
    try:
        row["state"] = derive_state(ws, _W["delivered"])[0]
    except Exception as e:
        row["state"] = f"error: {e}"[:200]
    row["voiced"] = _voiced(d.name) if row["state"] == "delivered" else False
    misses = len(_W["slfm"].misses) if _W["slfm"] is not None else 0
    try:
        stored = read_model(ws.show, Show)
        prov = read_model(ws.provenance, Provenance)
    except Exception as e:
        row["unreplayable"] = f"{type(e).__name__}: {e}"[:300]
        return row
    row["identifier"] = stored.identifier
    try:
        shadow, stripped = replay_holds._shadow(d, shadow_root, FRESH_KEYS)
        row["stripped"] = stripped
        # A key written as null (or an empty titles map) is no override.
        row["structure_override"] = any(stripped.get(k) is not None
                                        for k in ("set_breaks", "encore_after"))
        row["title_override"] = bool(stripped.get("titles"))
        fresh = _view(shadow, stored, prov, scratch, ARMS, capture_all=True)
        as_is = _view(ws, stored, prov, scratch, {"none": ARMS["none"]})
    finally:
        shutil.rmtree(shadow_root / d.name, ignore_errors=True)
        shutil.rmtree(scratch, ignore_errors=True)

    row["unreplayable"] = fresh["error"]
    row["unreplayable_as_is"] = as_is["error"]
    row["gate0"], row["gate0_diff"] = fresh["gate0"], fresh["gate0_diff"]
    row["gate0_as_is"], row["gate0_as_is_diff"] = as_is["gate0"], as_is["gate0_diff"]
    inp = fresh["inp"]
    if inp is not None:
        row["artist"] = fresh["artist"]
        row["family"] = jerrybase.is_family_artist(fresh["artist"])
        row["description"] = G._description(fresh["meta"])
        row["metadata_norms"] = sorted(inp.metadata_norms)
        row["desc"] = {"used": inp.desc.used.reader if inp.desc.used is not None else None,
                       "numbered": _desc_list(inp.desc.numbered),
                       "parse": _desc_list(inp.desc.parsed)}
        cb = inp.cb
        row["canonical"] = {"source": cb.source, "confidence": cb.setlist.confidence,
                            "needs_llm": cb.needs_llm,
                            "items": [{"title": it.title, "set": it.set, "segue": it.segue}
                                      for it in cb.setlist.items]}
    cap = fresh["cap"]
    if cap is not None:
        raw = {f["name"]: f.get("title") for f in (inp.kept if inp is not None else [])}
        row["today"] = [{"n": t.index, "title": t.title, "source": t.title_source,
                         "duration": t.duration_sec, "filename": t.filename,
                         "raw_tag": raw.get(t.filename)} for t in cap["tracks"]]
        row["today_op_notes"] = cap["op_notes"]
        row["today_struct_notes"] = cap["struct_notes"]
    if as_is["cap"] is not None:
        row["today_as_is"] = [{"title": t.title, "source": t.title_source}
                              for t in as_is["cap"]["tracks"]]
    legs = fresh["legs"]
    if legs is not None:
        row["today_flags"] = list(legs.flags)
        row["today_needs_llm"] = list(legs.needs_llm)
        row["today_outcome"] = list(classify(legs, row["state"]))
        row["today_notes"] = (list(legs.gather.notes)
                              + (list(legs.vet.notes) if legs.vet is not None else []))
    row["arms"] = fresh["arms"]
    row["arms_as_is"] = as_is["arms"]
    row.update(_alternatives(fresh))
    row["slfm_miss"] = _W["slfm"] is not None and len(_W["slfm"].misses) > misses
    return row


def _safe_one(d: str) -> dict:
    """`one`, never raising: one bad show cannot stop the run."""
    try:
        return one(d)
    except Exception as e:
        return {"slug": Path(d).name, "unreplayable": f"probe: {type(e).__name__}: {e}"[:300],
                "gate0": None, "gate0_as_is": None}


# --- dump -------------------------------------------------------------------------------------------

def dump(args: argparse.Namespace) -> int:
    replay_holds._check_identity()
    config_path = args.config or DEFAULT_ROOT / "config.toml"
    if args.config is not None and not args.config.exists():
        raise replay_holds.Refusal(f"no such config: {args.config}")
    cfg = load_config(config_path)
    root = cfg.root
    if replay_holds._overlaps(args.out, root):
        raise replay_holds.Refusal(f"refusing --out {args.out}: it overlaps the library root {root}")
    shows = root / "shows"
    if args.slugs:
        dirs = [str(shows / s) for s in replay_holds._read_slugs(args.slugs)]
    else:
        dirs = sorted(str(p) for p in shows.iterdir() if p.is_dir()) if shows.is_dir() else []
    meta = {"sha": code_identity(), "config_fingerprint": config_fingerprint(cfg),
            "setlistfm_configured": setlistfm_configured(cfg), "n": len(dirs),
            "align_coverage_threshold": cfg.structure.align_coverage_threshold}
    print(json.dumps(meta), file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)
    final = args.out / "dump.jsonl"
    tmp = args.out / f".dump.jsonl.{os.getpid()}.tmp"
    scratch_root = Path(tempfile.mkdtemp(prefix="th-probe-"))
    previous = logging.root.manager.disable
    try:
        with tmp.open("w") as fh:
            fh.write(json.dumps({"_meta": meta}) + "\n")
            if args.jobs <= 1:
                _init(str(config_path), str(scratch_root))
                try:
                    rows = map(_safe_one, dirs)
                    _write(fh, rows, len(dirs))
                finally:
                    _uninstall()
            else:
                with Pool(args.jobs, initializer=_init,
                          initargs=(str(config_path), str(scratch_root))) as pool:
                    _write(fh, pool.imap(_safe_one, dirs, chunksize=2), len(dirs))
        os.replace(tmp, final)
    finally:
        logging.disable(previous)
        tmp.unlink(missing_ok=True)
        shutil.rmtree(scratch_root, ignore_errors=True)
    return 0


def gate0_failures(row: dict) -> int:
    """Views of a row that fail gate 0: on a replayable view, anything but `True` (None is not
    passing)."""
    return ((row.get("unreplayable") is None and row.get("gate0") is not True)
            + (row.get("unreplayable_as_is") is None and row.get("gate0_as_is") is not True))


def _write(fh, rows, total: int) -> None:
    bad = 0
    for i, row in enumerate(rows, 1):
        fh.write(json.dumps(row, sort_keys=True) + "\n")
        bad += gate0_failures(row)
        if i % PROGRESS_EVERY == 0:
            print(f"dumped {i}/{total} (gate0 false so far: {bad})", file=sys.stderr, flush=True)
    print(f"dumped {total} show(s); gate0 false: {bad}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="the per-show gate dump (read-only)")
    d.add_argument("--config", type=Path, default=None)
    d.add_argument("--slugs", type=Path, default=None)
    d.add_argument("--jobs", type=int, default=1)
    d.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        return dump(args)
    except replay_holds.Refusal as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
