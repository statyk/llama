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

`dump` measures a PRE-WIRING tree: one whose `compute_gather` does not call the cascade
(e.g. commit 89fd787, where gate 0 held on 3983/3983 shows on both views at Checkpoint A).
On a wired tree (plan Task 16 on) `compute_gather` IS the cascade with every enabled slice,
so the `today` capture is the all-slices gather at 2a, and its sibling notes are not
captured (gather reaches sibling-align through `_sibling_transfer_full`); gate 0 then
measures nothing and is expected to fail.

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
import collections
import dataclasses
import json
import logging
import os
import re
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

    # R16: a numbering restart after an `Encore` header. Since the R16 clarification the taper's
    # encore-header grammar is the DEFAULT, so `default` is the shipped reader; the alternative
    # is the narrow lone-line grammar (`encore_header=False`), the pre-clarification reader.
    # "admits_new" therefore means: admitted by the default but not by the narrow reader. On a
    # tree before the clarification both are identical and nothing is reported.
    desc = G._description(v["meta"])
    default = read_numbered(desc)
    narrow = read_numbered(desc, encore_header=False)
    alt["alt_encore_restart"] = {
        "default": "admitted" if isinstance(default, DescList) else default,
        "encore_header": "admitted" if isinstance(default, DescList) else default,
        "narrow": "admitted" if isinstance(narrow, DescList) else narrow,
        "admits_new": isinstance(default, DescList) and not isinstance(narrow, DescList),
        "count_matched": isinstance(default, DescList) and len(default.raws) == n}

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


# --- the gate table (plan Task 14) ---------------------------------------------------------------
#
# `gate` tabulates `dump.jsonl` against the hand-check rows. It computes NO alternative of its own:
# rows R4 and R14-R17 and the notes section read the dump's `alt_*` fields (or its records).

GOOD_VERDICTS = frozenset({"all-right", "fix-helps", "strip-fixes-it"})
BAD_VERDICTS = frozenset({"shifted", "some-wrong-not-shift", "fix-hurts", "mixed",
                          "strip-would-damage", "strip-not-enough"})
NEUTRAL_VERDICTS = frozenset({"fix-neutral"})
GROUPS = ("good", "bad", "neutral", "cant-tell", "unchecked")
SLICES = ("slice1", "slice2", "slice3", "slice4", "slice5")
SLICE_CLASSES = {"slice1": frozenset({"S"}), "slice2": frozenset({"D", "U"}),
                 "slice3": frozenset({"C"}), "slice4": frozenset({"A_rev"}),
                 "slice5": frozenset({"A"})}
PATHS = ("S", "D", "C1", "C2", "4", "5")
PATH_SLICE = {"S": "slice1", "D": "slice2", "C1": "slice3", "C2": "slice3", "4": "slice4",
              "5": "slice5"}
UNRES_FLAG = "unresolved track titles"
LOWC_FLAG = "low-confidence structure alignment"
N_EXAMPLES = 10
EVIDENCE = Path(__file__).resolve().parents[1] / "docs" / "superpowers" / \
    "2026-10-22-title-hygiene-evidence"
DEFAULT_CENSUS = Path.home() / ".llama-harness" / "piece3" / "census" / "dump.jsonl"


def verdict_group(v: str | None) -> str:
    """A hand-check show verdict as good / bad / neutral / cant-tell (anything else reads as
    cant-tell; the groups are reported in their own columns, never pooled)."""
    if v in GOOD_VERDICTS:
        return "good"
    if v in BAD_VERDICTS:
        return "bad"
    if v in NEUTRAL_VERDICTS:
        return "neutral"
    return "cant-tell"


def tally_groups(groups) -> dict[str, int]:
    t = dict.fromkeys(GROUPS, 0)
    for g in groups:
        t[g if g else "unchecked"] += 1
    return t


def _key(title: str) -> str:
    return fuzzy_norm_title(clean_one(title or "").text)


class HandCheck:
    """The hand-check rows of every class directory, indexed by (slug, track number)."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.by_slug: dict[str, list[dict]] = {}
        self.tracks: dict[tuple[str, int], list[tuple[str, dict]]] = {}
        for r in rows:
            self.by_slug.setdefault(r["slug"], []).append(r)
            for t in r.get("tracks", []):
                self.tracks.setdefault((r["slug"], t["n"]), []).append((r["class"], t))

    @classmethod
    def load(cls, directory) -> "HandCheck":
        rows = []
        for f in sorted(Path(directory).glob("*/rows.jsonl")):
            fallback = re.sub(r"\d+$", "", f.parent.name)
            for ln in f.read_text().splitlines():
                if ln.strip():
                    r = json.loads(ln)
                    r["class"] = r.get("class") or fallback
                    rows.append(r)
        return cls(rows)

    def judge(self, slug: str, n: int, title: str, classes=None) -> tuple[str, str | None]:
        """("judged", right|wrong|cant-tell) when some row's candidate equals `title` (by
        fuzzy_norm_title after clean_one; wrong beats right beats cant-tell); else
        ("inferred", right|wrong) from a non-null correct_title via `agrees`; else
        ("unjudged", None)."""
        cands = [t for c, t in self.tracks.get((slug, n), ())
                 if classes is None or c in classes]
        key = _key(title)
        hits = [t for t in cands if key and _key(t["candidate"]) == key]
        if hits:
            vs = {{"right": "right", "right-partial": "right", "wrong": "wrong"}
                  .get(t["verdict"], "cant-tell") for t in hits}
            return "judged", "wrong" if "wrong" in vs else "right" if "right" in vs else "cant-tell"
        cts = [t["correct_title"] for t in cands if t.get("correct_title")]
        if cts:
            return "inferred", ("right" if any(title_hygiene.agrees(title, ct) for ct in cts)
                                else "wrong")
        return "unjudged", None

    def show_group(self, slug: str, classes=None) -> str | None:
        """The show's verdict group over rows of `classes` (bad beats good beats neutral beats
        cant-tell); None when the show has no row there."""
        groups = {verdict_group(r["show_verdict"]) for r in self.by_slug.get(slug, ())
                  if classes is None or r["class"] in classes}
        for g in ("bad", "good", "neutral", "cant-tell"):
            if g in groups:
                return g
        return None


# -- per-row readers (tolerant of missing fields) -------------------------------------------------

def _arm(row: dict, name: str) -> dict | None:
    return (row.get("arms") or {}).get(name)


def _rec(row: dict) -> dict:
    a = _arm(row, "all")
    return (a or {}).get("record") or {}


def _tok(path: str) -> list[str]:
    return ["S" if t == "S-deferred" else t for t in (path or "").split("+") if t]


def _titles(row: dict, arm: str):
    if arm == "today":
        return [(t["title"], t["source"]) for t in row.get("today") or []]
    a = _arm(row, arm)
    return [(t["title"], t["source"]) for t in a["tracks"]] if a else None


def changed_positions(row: dict, a: str, b: str) -> list[int]:
    x, y = _titles(row, a), _titles(row, b)
    if x is None or y is None or len(x) != len(y):
        return []
    return [i for i, (p, q) in enumerate(zip(x, y)) if p != q]


def _path(row: dict, i: int) -> str:
    paths = (_arm(row, "all") or {}).get("paths") or []
    return paths[i] if i < len(paths) else ""


def held_today(row: dict) -> bool:
    return bool(row.get("today_flags"))


def held_arm(row: dict, arm: str, thr: float) -> bool:
    """The approximate held predicate: today's fresh-view flags minus `unresolved track titles`,
    minus `low-confidence structure alignment` when the arm is self-filled or its coverage
    reaches the threshold, plus `unresolved track titles` when any track is unresolved."""
    a = _arm(row, arm)
    if a is None:
        return held_today(row)
    flags = [f for f in row.get("today_flags") or [] if f not in (UNRES_FLAG, LOWC_FLAG)]
    if LOWC_FLAG in (row.get("today_flags") or []) and not (
            a.get("self_filled") or (a.get("coverage") or 0.0) >= thr):
        flags.append(LOWC_FLAG)
    if any(t["source"] == "unresolved" for t in a["tracks"]):
        flags.append(UNRES_FLAG)
    return bool(flags)


def canon_group(row: dict) -> str:
    src = (row.get("canonical") or {}).get("source")
    if src is None:
        return "none"
    if src in ("setlist.fm", "chosen"):
        return src
    return "sibling item" if str(src).startswith("lma:") else "other"


def _plan(row: dict) -> dict:
    return _rec(row).get("s_plan") or {}


def is_q1_decline(row: dict) -> bool:
    """Q1: plan mode `untagged` WITH a non-empty declined list (a wholly untagged tape
    with no S position takes the mode and declines nothing)."""
    p = _plan(row)
    return p.get("mode") == "untagged" and bool(p.get("declined"))


def _d(row: dict) -> dict | None:
    return _rec(row).get("d")


def _d_fills(row: dict) -> dict:
    return (_d(row) or {}).get("fills") or {}


def _d_failed(row: dict) -> list:
    return (_d(row) or {}).get("failed") or []


def _used_list(row: dict) -> dict | None:
    desc = row.get("desc") or {}
    used = desc.get("used")
    return desc.get(used) if used else None


def _n_tracks(row: dict) -> int:
    a = _arm(row, "all")
    return len(a["tracks"]) if a else 0


def _count_matched(row: dict) -> bool:
    u = _used_list(row)
    return bool(u) and u.get("n") == _n_tracks(row) and _n_tracks(row) > 0


# -- table plumbing -------------------------------------------------------------------------------

def md_table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "n/a"


def examples(items, k: int = N_EXAMPLES) -> str:
    items = list(items)
    s = ", ".join(str(i) for i in items[:k])
    return s + (f" (+{len(items) - k} more)" if len(items) > k else "") if items else "none"


class Gate:
    def __init__(self, rows: list[dict], meta: dict, hc: HandCheck, census: dict | None):
        self.rows = [r for r in rows if _arm(r, "all") is not None]
        self.all_rows = rows
        self.meta = meta
        self.hc = hc
        self.census = census
        self.thr = float(meta.get("align_coverage_threshold", 0.8))
        self.sections: list[tuple[str, str, list[str], dict]] = []
        self.samples: dict[str, list[str]] = {}
        self.unchecked: list[str] = []

    def add(self, key: str, title: str, lines: list[str], data: dict) -> None:
        self.sections.append((key, title, lines, data))

    def sample(self, name: str, lines) -> None:
        self.samples[name] = [str(x) for x in lines]

    def group(self, row: dict, classes=None) -> str:
        return self.hc.show_group(row["slug"], classes) or "unchecked"

    def tally(self, rows, classes=None) -> dict[str, int]:
        return tally_groups(self.hc.show_group(r["slug"], classes) for r in rows)

    def held(self, row: dict, arm: str = "all") -> bool:
        return held_arm(row, arm, self.thr)

    # -- scoring ----------------------------------------------------------------------------------
    def score(self, items, classes_of) -> dict:
        """items: (slug, n, title) -> counts. `classes_of(item)` picks the hand-check classes."""
        c = dict(tracks=0, judged_right=0, judged_wrong=0, judged_cant_tell=0,
                 inferred_right=0, inferred_wrong=0, unjudged=0)
        for it in items:
            c["tracks"] += 1
            kind, v = self.hc.judge(it[0], it[1], it[2], classes_of(it))
            if kind == "judged":
                c["judged_" + v.replace("-", "_")] += 1
            elif kind == "inferred":
                c["inferred_" + v] += 1
            else:
                c["unjudged"] += 1
        return c

    @staticmethod
    def score_cells(c: dict) -> list:
        jw, jr = c["judged_wrong"], c["judged_right"]
        return [c["tracks"], jr, jw, c["judged_cant_tell"], c["inferred_right"],
                c["inferred_wrong"], c["unjudged"], pct(jw, jr + jw)]

    SCORE_HEAD = ["tracks", "judged right", "judged wrong", "judged cant-tell", "inferred right",
                  "inferred wrong", "unjudged", "wrong / judged (R+W)"]

    def attributed(self, r: dict, ref: str, arm: str = "all", changed_only: bool = False):
        """(i, kind, tokens) for every position where `arm` differs from `ref` or carries a path
        token. kind `fill`: the arm ships a title there; `removed`: the arm leaves a position
        `unresolved` that `ref` had filled (tokens: `S removed` when `ref` was today's S rung).
        `changed_only` keeps only positions where the title or source differs."""
        x, y = _titles(r, ref), _titles(r, arm)
        if x is None or y is None or len(x) != len(y):
            return []
        out = []
        for i, (p, q) in enumerate(zip(x, y)):
            toks = _tok(_path(r, i)) if arm == "all" else []
            if p == q and (changed_only or not toks):
                continue
            if q[1] == "unresolved" and p[1] != "unresolved":
                out.append((i, "removed", ["S removed" if p[1] == "setlist" else "removed"]))
            elif q[1] == "unresolved":
                continue
            else:
                out.append((i, "fill", toks or ["other"]))
        return out

    def score_removed(self, items, classes_of) -> dict:
        """items: (slug, n, old_title): was the title that the arm no longer ships right?"""
        c = dict(removed=0, judged_right=0, judged_wrong=0, judged_cant_tell=0,
                 inferred_right=0, inferred_wrong=0, unjudged=0)
        for it in items:
            c["removed"] += 1
            kind, v = self.hc.judge(it[0], it[1], it[2], classes_of(it))
            if v is None:
                c["unjudged"] += 1
            else:
                c[f"{kind}_{v.replace('-', '_')}"] += 1
        return c

    REMOVED_HEAD = ["fills removed", "was right: judged (cost)", "was wrong: judged (benefit)",
                    "judged cant-tell", "was right: inferred", "was wrong: inferred", "unjudged"]


# -- R0 ------------------------------------------------------------------------------------------

def r0(g: Gate) -> None:
    rows = g.all_rows

    def view(key, unrep):
        rep = [r for r in rows if r.get(unrep) is None]
        bad = [r["slug"] for r in rep if r.get(key) is not True]
        return {"pass": len(rep) - len(bad), "total": len(rep)}, bad, len(rows) - len(rep)
    fresh, bad_f, unrep_f = view("gate0", "unreplayable")
    asis, bad_a, unrep_a = view("gate0_as_is", "unreplayable_as_is")
    data = {"fresh": fresh, "as_is": asis, "unreplayable_fresh": unrep_f,
            "unreplayable_as_is": unrep_a, "failing_fresh": bad_f[:N_EXAMPLES],
            "failing_as_is": bad_a[:N_EXAMPLES]}
    lines = md_table(["view", "gate0 true / replayable rows", "unreplayable", "failing"],
                     [["fresh-get", f"{fresh['pass']} / {fresh['total']}", unrep_f,
                       examples(bad_f)],
                      ["as-is", f"{asis['pass']} / {asis['total']}", unrep_a, examples(bad_a)]])
    lines.append("")
    lines.append("`gate0 is not True` on a replayable row counts as failing (None is not passing).")
    # The held approximation applied to arm `none`, against today's flags.
    mism = [r["slug"] for r in g.rows if g.held(r, "none") != held_today(r)]
    data["held_approx_none_vs_today_mismatch"] = len(mism)
    lines.append(f"Held approximation on arm `none` disagrees with today's flags on "
                 f"{len(mism)} show(s) (e.g. {examples(mism, 5)}).")
    # Census cross-check.
    if g.census is None:
        data["census"] = None
        lines.append("Census cross-check: no census dump available.")
    else:
        comp, eq, diffs = 0, 0, []
        for r in g.rows:
            if r.get("structure_override") or r["slug"] not in g.census:
                continue
            comp += 1
            ours = [(t["title"], t["source"]) for t in r.get("today") or []]
            theirs = [(t.get("title"), t.get("src")) for t in g.census[r["slug"]].get("tracks") or []]
            if ours == theirs:
                eq += 1
            else:
                diffs.append(r["slug"])
        data["census"] = {"compared": comp, "equal": eq, "diff": len(diffs)}
        lines.append(f"Census cross-check (today vs census `tracks`, shows with no structure "
                     f"override): {eq} / {comp} equal; differing: {examples(diffs)}.")
        g.sample("r0_census_diffs", diffs)
    g.add("R0", "Gate 0 and the census cross-check", lines, data)


# -- R1 ------------------------------------------------------------------------------------------

def _slice_of(tok: str) -> str | None:
    return PATH_SLICE.get(tok, "slice1" if tok == "S removed" else None)


def r1(g: Gate) -> None:
    lines = ["Path view: tracks the `all` arm fills by a path (fills identical to today's, such as "
             "S, included) or ships differently from today. A `+5` suffix counts under both "
             "paths. Each slice is scored on its own hand-check classes; a track now `unresolved` "
             "is a removed fill, scored below by the title it removed."]
    data: dict = {"paths": {}, "removed": {}, "ablation": {}, "pooled": None}
    fills: dict[str, list] = {}
    removed: dict[str, list] = {}
    for r in g.rows:
        a = _arm(r, "all")
        for i, kind, toks in g.attributed(r, "today"):
            for t in toks:
                if kind == "fill":
                    fills.setdefault(t, []).append((r["slug"], i + 1, a["tracks"][i]["title"]))
                else:
                    removed.setdefault(t, []).append((r["slug"], i + 1, r["today"][i]["title"]))
    rows = []
    for p in (*PATHS, "other"):
        classes = SLICE_CLASSES.get(PATH_SLICE.get(p, ""), None)
        c = g.score(fills.get(p, []), lambda it, classes=classes: classes)
        data["paths"][p] = c
        rows.append([p, *g.score_cells(c)])
    uniq = {(it[0], it[1]): (it, {t for t, v in fills.items() if it in v}) for v in fills.values()
            for it in v}

    def cls_of(it):
        cs: set = set()
        for t in uniq[(it[0], it[1])][1]:
            cs |= SLICE_CLASSES.get(PATH_SLICE.get(t, ""), frozenset())
        return cs or None
    pooled = g.score([v[0] for v in uniq.values()], cls_of)
    data["pooled"] = pooled
    rows.append(["pooled (unique tracks)", *g.score_cells(pooled)])
    lines += md_table(["path", *Gate.SCORE_HEAD], rows)
    lines += ["", "The S row is S's residual (fills identical to today's included): what it still "
                  "ships, not damage slice 1 adds."]
    lines += ["", "Fills removed (today's title now `unresolved`), scored on the removed title:"]
    rrows = []
    for t, its in sorted(removed.items()):
        cl = SLICE_CLASSES.get(_slice_of(t) or "", None)
        c = g.score_removed(its, lambda it, cl=cl: cl)
        data["removed"][t] = c
        rrows.append([t, *c.values()])
    lines += md_table(["removed by", *Gate.REMOVED_HEAD], rrows)
    lines += ["", "Ablation view and newly held shows, per slice (`all` vs `all-<slice>`; held is "
                  "the labelled approximation)."]
    arows, rrows2 = [], []
    for s in SLICES:
        classes = SLICE_CLASSES[s]
        fl, rm = [], []
        for r in g.rows:
            a = _arm(r, "all")
            for i, kind, _ in g.attributed(r, f"all-{s}", "all", changed_only=True):
                if kind == "fill":
                    fl.append((r["slug"], i + 1, a["tracks"][i]["title"]))
                else:
                    rm.append((r["slug"], i + 1, _arm(r, f"all-{s}")["tracks"][i]["title"]))
        c = g.score(fl, lambda it, classes=classes: classes)
        cr = g.score_removed(rm, lambda it, classes=classes: classes)
        nh_abl = [r for r in g.rows if _arm(r, f"all-{s}") is not None
                  and g.held(r) and not g.held(r, f"all-{s}")]
        touched = {}
        for r in g.rows:
            for i, kind, toks in g.attributed(r, "today", changed_only=True):
                if any(_slice_of(t) == s for t in toks):
                    touched[r["slug"]] = r
        nh_path = [r for r in touched.values() if g.held(r) and not held_today(r)]
        ta, tp = g.tally(nh_abl, classes), g.tally(nh_path, classes)
        data["ablation"][s] = {"score": c, "removed": cr, "newly_held_ablation": ta,
                               "newly_held_path": tp, "path_shows": len(touched)}
        arows.append([s, *g.score_cells(c)])
        rrows2.append([s, *cr.values(), *[f"{k} {v}" for k, v in ta.items()],
                       f"{len(touched)} shows: " + ", ".join(f"{k} {v}" for k, v in tp.items())])
    lines += md_table(["slice (fills)", *Gate.SCORE_HEAD], arows)
    lines += ["", "Removed fills and newly held shows, per slice:"]
    lines += md_table(["slice", *Gate.REMOVED_HEAD, *[f"newly held (ablation) {k}" for k in GROUPS],
                       "newly held vs today (path)"], rrows2)
    g.add("R1", "Per-slice yield: tracks, hand-check verdicts, newly held shows", lines, data)


# -- R2 / R2b / R3 / R4 / R5 ---------------------------------------------------------------------

def _s_shipped(row: dict, n: int, candidate: str) -> bool:
    a = _arm(row, "all")
    if a is None or n < 1 or n > len(a["tracks"]):
        return False
    t = a["tracks"][n - 1]
    return t["source"] != "unresolved" and title_hygiene.agrees(t["title"], candidate)


def r2(g: Gate) -> None:
    cells: dict[tuple, dict] = {}
    for r in g.rows:
        sp = _rec(r).get("s_positions") or []
        if not sp:
            continue
        k = (canon_group(r), _plan(r).get("mode"))
        c = cells.setdefault(k, {"shows": 0, "s_positions": 0, "today_s": 0, "all_s": 0})
        c["shows"] += 1
        c["s_positions"] += len(sp)
        c["today_s"] += sum(1 for t in r.get("today") or [] if t["source"] == "setlist")
        c["all_s"] += sum(1 for i in range(_n_tracks(r)) if "S" in _tok(_path(r, i)))
    lines = md_table(["canonical", "S plan mode", "shows", "S positions", "today S tracks",
                      "all-arm S tracks"],
                     [[*k, *c.values()] for k, c in sorted(cells.items(), key=str)])
    s_rows = {r["slug"]: r for r in g.rows}
    hc_s = [h for h in g.hc.rows if h["class"] == "S"]
    byk: dict[tuple, dict] = {}
    caught, uncaught, lost_q1, lost_other, bar = [], [], [], [], []
    for h in hc_s:
        r = s_rows.get(h["slug"])
        if r is None:
            continue
        grp = verdict_group(h["show_verdict"])
        k = (canon_group(r), _plan(r).get("mode"))
        byk.setdefault(k, dict.fromkeys(("good", "bad", "neutral", "cant-tell"), 0))[grp] += 1
        wrong = [t for t in h["tracks"] if t["verdict"] == "wrong"]
        persists = [t["n"] for t in wrong if _s_shipped(r, t["n"], t["candidate"])]
        if grp == "bad":
            (uncaught if persists else caught).append(h["slug"])
        if grp == "good":
            drop = [t["n"] for t in h["tracks"] if t["verdict"] in ("right", "right-partial")
                    and not _s_shipped(r, t["n"], t["candidate"])]
            if drop:
                nh = g.held(r) and not held_today(r)
                (lost_q1 if is_q1_decline(r) else lost_other).append(
                    f"{h['slug']} (newly held: {nh})")
                if nh and not is_q1_decline(r):
                    bar.append(h["slug"])
    lines += ["", "Hand-checked S shows (the 128 S rows) by canonical source and plan mode:"]
    lines += md_table(["canonical", "S plan mode", "good", "bad", "neutral", "cant-tell"],
                      [[*k, *c.values()] for k, c in sorted(byk.items(), key=str)])
    lines += ["", f"After Q1 and the split: bad shows caught {len(caught)}, uncaught "
                  f"{len(uncaught)}.",
              f"Slice-1 bar (holds no more than 2 hand-checked-good S shows, excluding Q1 "
              f"declines): newly held, non-Q1, good S shows = {len(bar)} ({examples(bar)}).",
              f"Separately, good shows that lose S fills (held or not): Q1 declines "
              f"{len(lost_q1)} (reported separately), other {len(lost_other)}.",
              f"- uncaught bad: {examples(uncaught)}",
              f"- good shows losing fills, other than Q1: {examples(lost_other)}",
              f"- good shows losing fills, Q1: {examples(lost_q1)}"]
    g.sample("r2_s_uncaught_bad", uncaught)
    g.sample("r2_s_good_lost", lost_other + ["-- Q1 --"] + lost_q1)
    g.add("R2", "S re-count by canonical source and plan mode; caught and uncaught", lines,
          {"cells": {f"{k[0]}|{k[1]}": c for k, c in cells.items()},
           "hand_checked": {f"{k[0]}|{k[1]}": c for k, c in byk.items()},
           "caught": len(caught), "uncaught": len(uncaught), "good_lost_other": len(lost_other),
           "good_lost_q1": len(lost_q1),
           "bar_newly_held_non_q1_good": len(bar)})


def r2b(g: Gate) -> None:
    reasons: dict[str, list[str]] = {}
    total = 0
    for r in g.rows:
        if canon_group(r) != "chosen":
            continue
        a = _arm(r, "all")
        d, mode = _d(r), _plan(r).get("mode")
        for i, t in enumerate(r.get("today") or []):
            if t["source"] != "setlist" or i >= len(a["tracks"]):
                continue
            total += 1
            nt = a["tracks"][i]
            if nt["source"] == "desc-position" and title_hygiene.agrees(nt["title"], t["title"]):
                why = "reproduced by D"
            elif nt["source"] == "setlist" and title_hygiene.agrees(nt["title"], t["title"]):
                why = "kept by S (gated)"
            elif mode in ("gated", "untagged", "none"):
                why = f"no admissible list (mode {mode} declined the fill)"
            elif d is None:
                why = "D did not run"
            elif str(i) in (d.get("track_declines") or {}):
                why = f"D declined: track {d['track_declines'][str(i)]}"
            elif not d.get("fills") and d.get("failed"):
                why = f"D declined: {d['failed'][0][0]}"
            else:
                why = "other"
            reasons.setdefault(why, []).append(f"{r['slug']} track {i + 1}")
    lines = md_table(["reason", "tracks", "shows"],
                     [[k, len(v), len({x.rsplit(' track ', 1)[0] for x in v})]
                      for k, v in sorted(reasons.items())])
    lines.append("")
    lines.append(f"{total} chosen-canonical S fills today.")
    lines.append("- " + "; ".join(f"{k}: {examples(v, 3)}" for k, v in sorted(reasons.items())))
    g.sample("r2b_chosen_s_fills", [f"{k}\t{x}" for k, v in sorted(reasons.items()) for x in v])
    g.add("R2b", "Chosen-canonical S fills today that D does not reproduce", lines,
          {"total": total, "reasons": {k: len(v) for k, v in reasons.items()}})


def r3(g: Gate) -> None:
    withdrawn, gap = [], []
    for r in g.rows:
        p, d = _plan(r), _d(r)
        if p.get("mode") == "deferred" and p.get("deferred") and d is not None \
                and d.get("shift"):
            first = next((c for c, _ in d.get("failed", []) if c in title_hygiene.SHIFT_CHECKS),
                         "?")
            withdrawn.append((r, first))
        if canon_group(r) == "chosen" and _rec(r).get("gap_filled") and d is not None \
                and not d.get("fills"):
            gap.append(r)
    lines = [f"Deferred S withdrawn because D declined on a shift: {len(withdrawn)} show(s) "
             f"(verdicts on S rows: {g.tally([r for r, _ in withdrawn], {'S'})}).",
             "- by D's first shift check: " + str(dict(collections.Counter(c for _, c in withdrawn))),
             f"- {examples(r['slug'] for r, _ in withdrawn)}",
             f"setlist-gap fills on chosen-canonical tapes where D then declined (attributed to "
             f"setlist-gap): {len(gap)} show(s), "
             f"{sum(len(_rec(r)['gap_filled']) for r in gap)} track(s).",
             f"- {examples(r['slug'] for r in gap)}"]
    g.sample("r3_withdrawn", [f"{r['slug']}\t{c}" for r, c in withdrawn])
    g.sample("r3_gap_after_d_decline", [r["slug"] for r in gap])
    g.add("R3", "S withdrawn with D; setlist-gap fills after a D decline", lines,
          {"withdrawn": len(withdrawn), "gap_shows": len(gap),
           "gap_tracks": sum(len(_rec(r)["gap_filled"]) for r in gap)})


def r4(g: Gate) -> None:
    hc_s = {h["slug"]: h for h in g.hc.rows if h["class"] == "S"}
    variants = {"gap_span": ("dropped", "the gap_span-literal reading (leading-edge branch kept)"),
                "both_sides": ("dropped_both_sides",
                               "the both-sides reading (an independent anchor on BOTH sides)")}
    data, lines = {}, ["The stricter non-chosen S alternative, read from `alt_bracketed_s`: "
                       "reported, not adopted."]
    for name, (field, label) in variants.items():
        shows, dropped, added, bad_stopped, good_lost = [], 0, 0, [], []
        groups = []
        for r in g.rows:
            alt = r.get("alt_bracketed_s") or {}
            drop = alt.get(field) or []
            if not alt.get("applies") or not drop:
                continue
            shows.append(r["slug"])
            dropped += len(drop)
            if not g.held(r):
                added += 1
            grp = g.hc.show_group(r["slug"], {"S"})
            groups.append(grp)
            h = hc_s.get(r["slug"])
            if h and grp == "bad":
                wrong = [t["n"] - 1 for t in h["tracks"] if t["verdict"] == "wrong"]
                if all(p in drop for p in wrong):
                    bad_stopped.append(r["slug"])
            if grp == "good" and not g.held(r):
                good_lost.append(r["slug"])
        data[name] = {"shows_with_drops": len(shows), "dropped": dropped, "added_holds": added,
                      "by_group": tally_groups(groups), "bad_stopped": len(bad_stopped),
                      "good_lost": len(good_lost)}
        lines += [f"**{label}**: {len(shows)} show(s) with S fills dropped ({dropped} track(s)); "
                  f"holds added (not already held, approx.): {added}; hand-check groups "
                  f"{tally_groups(groups)}; bad shows it would stop: {len(bad_stopped)} "
                  f"({examples(bad_stopped)}); good shows it would hold: {len(good_lost)} "
                  f"({examples(good_lost)})."]
        g.sample(f"r4_{name}", shows)
    g.add("R4", "The stricter non-chosen S alternative (gap_span-bracketed runs only)", lines,
          data)


def r5(g: Gate) -> None:
    q1 = [r for r in g.rows if is_q1_decline(r)]
    groups = [g.group(r, {"S"}) for r in q1]
    nh = [r for r in q1 if g.held(r) and not held_today(r)]
    silent_bad = [r for r in q1 if g.group(r, {"S"}) == "bad" and not held_today(r)]
    q1d = {"shows": len(q1), "tracks": sum(len(_plan(r).get("declined") or []) for r in q1),
           "verdicts": tally_groups(groups), "held_now": sum(1 for r in q1 if g.held(r)),
           "unheld_today": sum(1 for r in q1 if not held_today(r)),
           "newly_held": len(nh), "newly_held_verdicts": g.tally(nh, {"S"}),
           "silent_bad_today": len(silent_bad),
           "silent_bad_stopped": sum(1 for r in silent_bad if g.held(r))}
    lines = [f"Q1 on the fresh-get view (plan mode `untagged` with a non-empty decline): "
             f"{q1d['shows']} show(s), {q1d['tracks']} declined track(s); verdicts "
             f"{q1d['verdicts']}; held now (approx.) {q1d['held_now']}; newly held "
             f"{q1d['newly_held']} {q1d['newly_held_verdicts']}; bad shows unheld today "
             f"(silent) {q1d['silent_bad_today']}, of which now held {q1d['silent_bad_stopped']}."]
    ship = {}
    rows = []
    for s in SLICES:
        classes = SLICE_CLASSES[s]
        sh = [r for r in g.rows if any(_slice_of(t) == s
                                       for _, _, toks in g.attributed(r, "today", changed_only=True)
                                       for t in toks)]
        un = [r for r in sh if not held_today(r)]
        ship[s] = {"changed_shows": len(sh), "unheld_today": len(un), "verdicts": g.tally(un, classes)}
        rows.append([s, len(sh), len(un), *g.tally(un, classes).values()])
    lines += ["", "Per slice, changed shows unheld today (ships silently):"]
    lines += md_table(["slice", "changed shows", "unheld today", *GROUPS], rows)
    g.sample("r5_q1_shows", [r["slug"] for r in q1])
    g.add("R5", "Q1's trade and the ships-silently counts (fresh-get view)", lines,
          {"q1": q1d, "ships_silently": ship})


NOTE_RE = re.compile(r"^positional fill declined: (\S+) track (\d+) (.+?) '(.*)'$")


def _notes_of(g: Gate, check: str):
    out = []
    for r in g.rows:
        for n in (_arm(r, "all") or {}).get("op_notes") or []:
            m = NOTE_RE.match(n)
            if m and m.group(3) == check:
                out.append((r["slug"], m.group(1), int(m.group(2)), m.group(4)))
    return out


def r6(g: Gate) -> None:
    hits = _notes_of(g, "metadata")
    lines = [f"`metadata` per-track declines (self-titled songs): {len(hits)} track(s) on "
             f"{len({h[0] for h in hits})} show(s).",
             "- " + "; ".join(f"{s} {rung} track {n} '{t}'" for s, rung, n, t in hits[:N_EXAMPLES])]
    g.sample("r6_metadata", [f"{s}\t{r}\t{n}\t{t}" for s, r, n, t in hits])
    g.add("R6", "`metadata` per-track declines", lines, {"tracks": len(hits),
                                                         "shows": len({h[0] for h in hits})})


def r7(g: Gate) -> None:
    hits = _notes_of(g, "filler entry")
    d_pos = sum(1 for r in g.rows for c in ((_d(r) or {}).get("track_declines") or {}).values()
                if c == "filler entry")
    lines = [f"Positions left unresolved by `Filler:` entries: {len(hits)} noted track(s) on "
             f"{len({h[0] for h in hits})} show(s) ({d_pos} in D's track declines).",
             "- " + "; ".join(f"{s} {rung} track {n} '{t}'" for s, rung, n, t in hits[:N_EXAMPLES])]
    g.sample("r7_filler", [f"{s}\t{r}\t{n}\t{t}" for s, r, n, t in hits])
    g.add("R7", "Positions left unresolved by `Filler:`", lines,
          {"tracks": len(hits), "shows": len({h[0] for h in hits}), "d_track_declines": d_pos})


def r8(g: Gate) -> None:
    pairs = []
    for r in g.rows:
        for c in (r.get("alt_check2_cleaned") or {}).get("calls") or []:
            if c.get("built"):
                pos, cand, other = c["built"]
                pairs.append((r["slug"], c["rung"], pos + 1, cand, other))
    noted = len(_notes_of_adj(g))
    lines = [f"`adjacent duplicate` declines: {len(pairs)} call(s) on "
             f"{len({p[0] for p in pairs})} show(s) ({noted} noted); each with its pair:"]
    lines += [f"- {s} {rung} track {n}: '{a}' ~ '{b}'" for s, rung, n, a, b in pairs]
    g.sample("r8_adjacent_duplicates", [f"{s}\t{r}\t{n}\t{a}\t{b}" for s, r, n, a, b in pairs])
    g.add("R8", "`adjacent duplicate` declines and their pairs", lines,
          {"calls": len(pairs), "shows": len({p[0] for p in pairs}), "noted": noted})


def _notes_of_adj(g: Gate):
    out = []
    for r in g.rows:
        for n in (_arm(r, "all") or {}).get("op_notes") or []:
            if "adjacent duplicate" in n:
                out.append(r["slug"])
    return out


def _shows_failing(g: Gate, check: str):
    return [r for r in g.rows if any(c == check for c, _ in _d_failed(r))]


def r9(g: Gate) -> None:
    fl = _shows_failing(g, "agreement")
    good = [r for r in fl if g.group(r, {"D", "U"}) == "good"]
    lines = [f"`agreement` declines: {len(fl)} show(s); verdicts (D/U classes) "
             f"{g.tally(fl, {'D', 'U'})}.",
             f"On hand-checked-right shows: {len(good)} ({examples(r['slug'] for r in good)}).",
             f"- all: {examples(r['slug'] for r in fl)}"]
    g.sample("r9_agreement", [r["slug"] for r in fl])
    g.add("R9", "`agreement` declines", lines,
          {"shows": len(fl), "on_right_shows": len(good), "verdicts": g.tally(fl, {"D", "U"})})


def r10(g: Gate) -> None:
    fl = _shows_failing(g, "block size")
    good = [r for r in fl if g.group(r, {"D", "U"}) == "good"]
    diff = [r for r in g.rows if (r.get("alt_encore_fold") or {}).get("differs")]
    lines = [f"`block size` declines library-wide: {len(fl)} show(s); on hand-checked-right "
             f"shows: {len(good)} ({examples(r['slug'] for r in good)}).",
             f"Shows whose outcome the encore fold changes: {len(diff)}"
             + "".join(f"; {r['slug']}: fold {r['alt_encore_fold'].get('fold')!r}, "
                       f"no fold {r['alt_encore_fold'].get('no_fold')!r}" for r in diff[:5])]
    g.sample("r10_block_size", [r["slug"] for r in fl])
    g.sample("r10_encore_fold_differs", [r["slug"] for r in diff])
    g.add("R10", "`block size` declines; the encore fold", lines,
          {"shows": len(fl), "on_right_shows": len(good), "fold_differs": len(diff)})


def _indep_denominator(r: dict) -> int:
    return sum(1 for t in _arm(r, "all")["tracks"]
               if t["source"] in INDEPENDENT_SOURCES and not is_filler(t["title"]))


def r11(g: Gate) -> None:
    new = []
    for r in g.rows:
        a = _arm(r, "all")
        if LOWC_FLAG in (r.get("today_flags") or []) and (
                a.get("self_filled") or (a.get("coverage") or 0.0) >= g.thr):
            new.append(r)
    with_d = [r for r in new if _d_fills(r)]
    buckets: dict[str, list[dict]] = {}
    for r in with_d:
        n = _indep_denominator(r)
        buckets.setdefault("0" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3+",
                           []).append(r)
    rows = [[k, len(v), sum(1 for r in v if _arm(r, "all").get("self_filled")),
             *g.tally(v, {"D", "U"}).values()] for k, v in sorted(buckets.items())]
    suppress = [r for r in g.rows
                if any(str(n).startswith("unknown-song flags suppressed")
                       for n in r.get("today_notes") or []) and _d_fills(r)]
    lines = [f"Shows newly above the coverage threshold (low-confidence flag today, self-filled "
             f"or covered now): {len(new)}, of which {len(with_d)} have a D fill and "
             f"{len(new) - len(with_d)} do not (their coverage rose through C, slice 4 or "
             f"slice 5). The D shows, by independent-denominator size:"]
    lines += md_table(["denominator", "shows", "of which self-filled", *GROUPS], rows)
    lines += ["", f"Shows with a 4a suppression note today and a D fill now (upper bound on "
                  f"consequence (2)): {len(suppress)} ({examples(r['slug'] for r in suppress)})."]
    g.sample("r11_newly_above", [f"{r['slug']}\t{_indep_denominator(r)}" for r in new])
    g.sample("r11_4a_and_d", [r["slug"] for r in suppress])
    g.add("R11", "Coverage consequences of D-filled tracks", lines,
          {"newly_above": len(new), "with_d": len(with_d), "by_denominator": {k: len(v) for k, v in buckets.items()},
           "suppress_and_d": len(suppress)})


def r12(g: Gate, tagged_siblings: dict[str, int]) -> None:
    res = []
    for r in g.rows:
        if not (_rec(r).get("wholly_untagged") and _d_fills(r)):
            continue
        u = _used_list(r) or {}
        no_blocks = not (u.get("boundaries") or [])
        no_dur = not any(e.get("durations") for e in u.get("entries") or [])
        if no_blocks and no_dur:
            res.append(r)
    by = collections.Counter("unknown" if r["slug"] not in tagged_siblings
                             else ("tagged sibling" if tagged_siblings[r["slug"]] else "no sibling")
                             for r in res)
    lines = [f"D's residual: wholly untagged D-filled shows whose list has no block boundary "
             f"(block-size check inert) and no written durations: {len(res)}; tagged sibling "
             f"(from untagged-index.json): {dict(by)}. Verdicts (D/U): "
             f"{g.tally(res, {'D', 'U'})}.",
             "Approximation: filename disc structure and sibling durations are not in the dump, "
             "so `no block boundary` stands in for the block-size check being inert.",
             f"- {examples(r['slug'] for r in res)}"]
    g.sample("r12_residual", [r["slug"] for r in res])
    g.add("R12", "D's residual on untagged tapes", lines,
          {"shows": len(res), "siblings": dict(by), "verdicts": g.tally(res, {"D", "U"})})


def r13(g: Gate) -> None:
    pop = [r for r in g.rows if _rec(r).get("wholly_untagged") and _count_matched(r)]
    in_u = {h["slug"] for h in g.hc.rows if h["class"] == "U"}
    unchecked = sorted(r["slug"] for r in pop if r["slug"] not in in_u)
    g.unchecked = unchecked
    lines = [f"Wholly untagged shows with a count-matched admissible list (Definitions "
             f"predicate): {len(pop)}; in U0-U3: {len([r for r in pop if r['slug'] in in_u])}; "
             f"not checked: {len(unchecked)} (written to untagged_unchecked.txt).",
             f"Verdicts of the checked ones (U): {g.tally(pop, {'U'})}.",
             f"- not checked: {examples(unchecked)}"]
    g.sample("r13_population", [r["slug"] for r in pop])
    g.add("R13", "The wholly untagged count-matched population", lines,
          {"total": len(pop), "checked": len(pop) - len(unchecked), "unchecked": len(unchecked),
           "verdicts": g.tally(pop, {"U"})})


def r14(g: Gate) -> None:
    hits = [r for r in g.rows if r.get("alt_bare_number")]
    s_slugs = {h["slug"] for h in g.hc.rows if h["class"] == "S"}
    in_s = [r for r in hits if r["slug"] in s_slugs]
    cands = [(r["slug"], b) for r in hits for b in r["alt_bare_number"]]
    decided = sum(1 for _, b in cands if b.get("exemption_decided"))
    lines = [f"Bare-number S candidates: {len(cands)} track(s) on {len(hits)} show(s); the "
             f"own-tag-core exemption decides {decided}. Over the hand-checked S rows "
             f"({len(s_slugs)} shows): {len(in_s)} show(s), declines by verdict "
             f"{g.tally(in_s, {'S'})}.",
             "- " + examples(s + ":" + repr(b.get("text")) for s, b in cands)]
    g.sample("r14_bare_number", [f"{s}\t{b.get('pos')}\t{b.get('text')}\t{b.get('judge')}"
                                 for s, b in cands])
    g.add("R14", "The bare-number rule over the S rows", lines,
          {"shows": len(hits), "tracks": len(cands), "exemption_decided": decided,
           "in_s_rows": g.tally(in_s, {"S"})})


def r15(g: Gate) -> None:
    ex = [(r, r["alt_hygiene_all_entries"]) for r in g.rows
          if (r.get("alt_hygiene_all_entries") or {}).get("extra")]
    by = collections.Counter(f["check"] for _, a in ex for f in a["extra"])
    lines = [f"Extra show-level hygiene declines if every entry were judged (plan reading): "
             f"{len(ex)} show(s) beyond the candidates; by check {dict(by)}; verdicts (D/U) "
             f"{g.tally([r for r, _ in ex], {'D', 'U'})}.",
             "- " + "; ".join(f"{r['slug']} pos {f['pos'] + 1} {f['check']} '{f['text']}'"
                              for r, a in ex[:N_EXAMPLES] for f in a["extra"][:1])]
    g.sample("r15_extra_hygiene", [f"{r['slug']}\t{f['pos'] + 1}\t{f['check']}\t{f['text']}"
                                   for r, a in ex for f in a["extra"]])
    g.add("R15", "Extra hygiene declines if every entry were judged", lines,
          {"shows_with_extra": len(ex), "by_check": dict(by)})


def r16(g: Gate) -> None:
    new = [r for r in g.rows if (r.get("alt_encore_restart") or {}).get("admits_new")]
    cm = [r for r in new if r["alt_encore_restart"].get("count_matched")]
    lines = [f"Lists inadmissible only because a numbering restart follows an `Encore` header: "
             f"{len(new)} show(s), {len(cm)} count-matched; verdicts (D/U) "
             f"{g.tally(cm, {'D', 'U'})}.",
             f"- {examples(r['slug'] for r in new)}"]
    g.sample("r16_encore_restart", [f"{r['slug']}\t{r['alt_encore_restart'].get('default')}\t"
                                    f"{r['alt_encore_restart'].get('count_matched')}" for r in new])
    g.add("R16", "Lists blocked only by an Encore-header restart", lines,
          {"admits_new": len(new), "count_matched": len(cm)})


C1_NOT_APPLICABLE = ("out of scope", "no lossless format")


def r17(g: Gate) -> None:
    dec = [r for r in g.rows if (r.get("alt_c1") or {}).get("declined")
           and r["alt_c1"]["declined"] not in C1_NOT_APPLICABLE and r["alt_c1"].get("targets")]
    targets = sum(len(r["alt_c1"]["targets"]) for r in dec)
    alone = sum(r["alt_c1"].get("would_pass_alone", 0) for r in dec)
    via = [r for r in g.rows if (r.get("alt_c1") or {}).get("via_c_where_ab_disagreed")]
    via_tracks = [(r["slug"], p + 1) for r in via for p in r["alt_c1"]["via_c_where_ab_disagreed"]]
    judged: collections.Counter = collections.Counter()
    for r in via:
        tr = _arm(r, "all")["tracks"]
        for p in r["alt_c1"]["via_c_where_ab_disagreed"]:
            title = tr[p]["title"] if p < len(tr) else ""
            judged[g.hc.judge(r["slug"], p + 1, title, {"C"})[1] or "unjudged"] += 1
    lines = [f"C1 show-level declines (with C1 targets): {len(dec)} show(s), {targets} target(s), "
             f"{alone} would pass on their own (the per-stem alternative; plan reading); by "
             f"reason {dict(collections.Counter(r['alt_c1']['declined'] for r in dec))}.",
             f"C1 adoptions made via (c) where (a) or (b) disagreed: {len(via_tracks)} track(s) "
             f"on {len(via)} show(s); judged {dict(judged)}.",
             f"- declines: {examples(r['slug'] for r in dec)}", f"- via (c): {examples(via_tracks)}"]
    g.sample("r17_c1_declines", [f"{r['slug']}\t{r['alt_c1']['declined']}\t{len(r['alt_c1']['targets'])}\t"
                                 f"{r['alt_c1'].get('would_pass_alone')}" for r in dec])
    g.sample("r17_c1_via_c", [f"{s}\t{n}" for s, n in via_tracks])
    g.add("R17", "C1 declines and the per-stem alternative; adoptions via (c)", lines,
          {"declined_shows": len(dec), "targets": targets, "would_pass_alone": alone,
           "via_c_shows": len(via), "via_c_tracks": len(via_tracks)})


def r18(g: Gate) -> None:
    out = {}
    lines = []
    for check in ("agreement", "written durations"):
        fl = _shows_failing(g, check)
        good = [r for r in fl if g.group(r, {"D", "U"}) == "good"]
        out[check] = {"shows": len(fl), "on_right_shows": len(good)}
        lines.append(f"`{check}`: {len(fl)} firing(s) library-wide; on hand-checked-right shows "
                     f"(D/U): {len(good)} ({examples(r['slug'] for r in good)}).")
        g.sample("r18_" + check.replace(" ", "_"), [f"{r['slug']}\t{g.group(r, {'D', 'U'})}"
                                                    for r in fl])
    g.add("R18", "Agreement and written-duration firings on right shows", lines, out)


def r19(g: Gate) -> None:
    rows, filled, declined = [], collections.Counter(), collections.Counter()
    for r in g.rows:
        u = _used_list(r) or {}
        d_fill = _d_fills(r)
        cands = (r.get("alt_hygiene_all_entries") or {}).get("candidates")
        for i, e in enumerate(u.get("entries") or []):
            if e.get("trailing_time_stripped") and _d(r) is not None \
                    and (cands is None or i in cands):
                rows.append((r["slug"], "D", i + 1, e.get("raw"), e.get("text"),
                             str(i) in d_fill))
        a = _arm(r, "all")
        for c in r.get("s_candidates") or []:
            if c.get("trailing_time_stripped"):
                p = c["pos"]
                is_f = p < len(a["tracks"]) and "S" in _tok(_path(r, p))
                rows.append((r["slug"], "S", p + 1, c.get("raw"), c.get("text"), is_f))
    for slug, rung, n, raw, text, is_f in rows:
        row = next(x for x in g.rows if x["slug"] == slug)
        title = _arm(row, "all")["tracks"][n - 1]["title"]
        v = g.hc.judge(slug, n, title)[1] if is_f else None
        (filled if is_f else declined)[(rung, v or ("unjudged" if is_f else "-"))] += 1
    lines = [f"Candidates a trailing `m:ss` strip changed: {len(rows)} (filled "
             f"{sum(1 for x in rows if x[5])}, declined {sum(1 for x in rows if not x[5])}).",
             f"- filled by rung and verdict: {dict(filled)}", f"- declined: {dict(declined)}"]
    lines += [f"- {s} {rung} track {n}: '{raw}' -> '{text}' ({'filled' if f else 'declined'})"
              for s, rung, n, raw, text, f in rows[:N_EXAMPLES]]
    g.sample("r19_trailing_time", [f"{s}\t{rung}\t{n}\t{raw}\t{text}\t{'filled' if f else 'declined'}"
                                   for s, rung, n, raw, text, f in rows])
    g.add("R19", "Trailing `m:ss` strips", lines,
          {"candidates": len(rows), "filled": sum(1 for x in rows if x[5]),
           "declined": sum(1 for x in rows if not x[5])})


# -- Notes for Checkpoint A ------------------------------------------------------------------------

QONLY_RE = re.compile(r"^[^A-Za-z]*\?[^A-Za-z]*$")
LEAD_NUM_RE = re.compile(r"^\d{1,3}\s*[-._)]\s*\S")
TRAIL_MARK_RE = re.compile(r"(?:=>|->|>|\*+|@+)\s*$")
DEBRIS_RE = re.compile(r"\(\s*\)|\[\s*\]|[_.]\s*$|^\s*[-_.]")


def _reason_key(reason: str) -> str:
    return re.sub(r"\d+", "N", reason.split(":")[0]).strip()


def notes(g: Gate) -> None:
    n: dict = {}
    lines: list[str] = []

    def put(key, title, items, label=None):
        """items: list of (slug, text). Counts shows and tracks, up to 10 examples; the full
        list goes to samples/notes_<key>.txt."""
        items = list(items)
        n[key] = {"shows": len({s for s, _ in items}), "items": len(items)}
        lines.append(f"**{title}**: {n[key]['shows']} show(s), {len(items)} item(s). "
                     + "; ".join(f"{s}: {t}" for s, t in items[:N_EXAMPLES]))
        g.sample("notes_" + key, [f"{s}\t{t}" for s, t in items])

    # (1) reader rejections by reason
    for key, field, label in (("reader_i_reasons", "numbered", "reader (i)"),
                              ("reader_ii_reasons", "parse", "reader (ii)")):
        cnt: dict[str, list[str]] = {}
        for r in g.rows:
            reason = ((r.get("desc") or {}).get(field) or {}).get("reason")
            if reason:
                cnt.setdefault(_reason_key(reason), []).append(r["slug"])
        n[key] = {k: len(v) for k, v in sorted(cnt.items())}
        lines.append(f"**(1) {label} rejections by reason**: "
                     + "; ".join(f"{k}: {len(v)} (e.g. {examples(v, 3)})"
                                 for k, v in sorted(cnt.items(), key=lambda kv: -len(kv[1]))))
        g.sample("notes_" + key, [f"{k}\t{s}" for k, v in sorted(cnt.items()) for s in v])
    # (2) used reader (ii) while reader (i) is non-contiguous
    nc = [(r["slug"], (r["desc"]["numbered"] or {}).get("reason")) for r in g.rows
          if (r.get("desc") or {}).get("used") == "parse"
          and ((r["desc"].get("numbered") or {}).get("reason") or "").startswith("non-contiguous")]
    put("parse_with_noncontiguous_numbered", "(2) used list is reader (ii) while reader (i) is "
        "non-contiguous", nc)
    # (3) lone `?`-ish passes; declines containing `opened`
    qpass, opened = [], []
    for r in g.rows:
        u = _used_list(r) or {}
        alt = r.get("alt_hygiene_all_entries") or {}
        fails = {f["pos"] for f in alt.get("failures") or []}
        for i in alt.get("candidates") or []:
            ents = u.get("entries") or []
            if i < len(ents) and QONLY_RE.match(ents[i].get("text") or "") and i not in fails:
                qpass.append((r["slug"], f"track {i + 1} raw {ents[i].get('raw')!r}"))
        for f in alt.get("failures") or []:
            if re.search(r"\bopened\b", f.get("text") or "", re.I):
                opened.append((r["slug"], f"{f['check']} '{f['text']}'"))
        for nt in (_arm(r, "all") or {}).get("op_notes") or []:
            if re.search(r"\bopened\b", nt, re.I):
                opened.append((r["slug"], nt))
    put("lone_question_passes", "(3a) check-1 passes of a lone `?`-ish text", qpass)
    put("opened_declines", "(3b) declines whose text contains `opened`",
        sorted(set(opened)))
    # (4) D fills still starting with a track number
    lead = []
    for r in g.rows:
        for pos, t in sorted(_d_fills(r).items(), key=lambda kv: int(kv[0])):
            if LEAD_NUM_RE.match(t):
                lead.append((r["slug"], f"track {int(pos) + 1} '{t}'"))
    put("d_leading_track_number", "(4) D fills whose shipped text starts with a track number (the regex also "
        "catches dates such as `12.28.99`)",
        lead)
    # (5) would-decline by rung with cleaned neighbours
    by_rung: dict[str, list] = {}
    for r in g.rows:
        for rung, fills in ((r.get("alt_check2_cleaned") or {}).get("would_decline") or {}).items():
            if fills:
                by_rung.setdefault(rung, []).append((r["slug"], f"{len(fills)} fill(s)"))
    n["check2_cleaned"] = {k: len(v) for k, v in by_rung.items()}
    lines.append("**(5) `alt_check2_cleaned` would-declines by rung**: "
                 + ("; ".join(f"{k}: {len(v)} show(s) (e.g. {examples([s for s, _ in v], 3)})"
                              for k, v in sorted(by_rung.items())) or "none"))
    g.sample("notes_check2_cleaned", [f"{k}\t{s}\t{t}" for k, v in by_rung.items() for s, t in v])
    # (6) containment-only C2
    cont = [(r["slug"], f"track {c['pos'] + 1} '{c['lossless']}' vs '{c['ref']}' "
                        f"({c['reference']}, ratio {c['ratio']})")
            for r in g.rows for c in ((r.get("alt_c2_containment") or {}).get("c2") or [])
            if c.get("containment_only")]
    put("c2_containment_only", "(6) containment-only C2 replacements", cont)
    # (7) C1 via (c); C1 fills ending in a taper marker
    via = [(r["slug"], f"track {p + 1}") for r in g.rows
           for p in (r.get("alt_c1") or {}).get("via_c_where_ab_disagreed") or []]
    put("c1_via_c_disagreed", "(7a) C1 adoptions via (c) where (a)/(b) disagreed", via)
    marks = []
    for r in g.rows:
        ll = _rec(r).get("lossless") or {}
        for p, c in (ll.get("changed") or {}).items():
            if c == "C1":
                t = ll["titles"][int(p)]
                if TRAIL_MARK_RE.search(t):
                    marks.append((r["slug"], f"track {int(p) + 1} '{t}'"))
    put("c1_trailing_marker", "(7b) C1 fills ending in a taper marker", marks)
    # (8) slice-4 confirmations from `Filler:` entries
    fil = [(r["slug"], f"position(s) {[p + 1 for p in r['alt_filler_confirm']]}")
           for r in g.rows if r.get("alt_filler_confirm")]
    put("filler_confirm", "(8) slice-4 confirmations from `Filler:` entries", fil)
    # (9) slice-5 strips that leave debris
    deb = []
    for r in g.rows:
        a, b = _arm(r, "all"), _arm(r, "all-slice5")
        for i in range(len((a or {}).get("tracks") or [])):
            if "5" in _tok(_path(r, i)):
                new = a["tracks"][i]["title"]
                if DEBRIS_RE.search(new):
                    old = b["tracks"][i]["title"] if b and i < len(b["tracks"]) else "?"
                    deb.append((r["slug"], f"track {i + 1} '{old}' -> '{new}'"))
    put("slice5_debris", "(9) slice-5 strips that leave debris", deb)
    g.add("NOTES", "Notes for Checkpoint A", [f"- {ln}" for ln in lines], n)


# -- the driver ------------------------------------------------------------------------------------

def load_dump(path: Path) -> tuple[dict, list[dict]]:
    with path.open() as fh:
        meta = json.loads(fh.readline())["_meta"]
        rows = [json.loads(ln) for ln in fh if ln.strip()]
    return meta, rows


def load_census(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open() as fh:
        fh.readline()
        out = {}
        for ln in fh:
            if ln.strip():
                r = json.loads(ln)
                out[r["slug"]] = {"tracks": r.get("tracks")}
    return out


def build_gate(dump: Path, handcheck: Path, census: Path, out: Path) -> Gate:
    meta, rows = load_dump(dump)
    g = Gate(rows, meta, HandCheck.load(handcheck), load_census(census))
    sibs: dict[str, int] = {}
    idx = EVIDENCE / "untagged-index.json"
    if idx.exists():
        sibs = {e["slug"]: e.get("tagged_siblings", 0) for e in json.loads(idx.read_text())}
    r0(g), r1(g), r2(g), r2b(g), r3(g), r4(g), r5(g), r6(g), r7(g), r8(g), r9(g), r10(g)
    r11(g), r12(g, sibs), r13(g), r14(g), r15(g), r16(g), r17(g), r18(g), r19(g), notes(g)
    out.mkdir(parents=True, exist_ok=True)
    (out / "samples").mkdir(exist_ok=True)
    md = [f"# Title hygiene gate table (Checkpoint A)", "",
          f"dump: `{dump}` sha `{meta.get('sha')}`; shows {len(rows)}; hand-check rows "
          f"{len(g.hc.rows)}; held is the labelled approximation (today's flags minus "
          f"`{UNRES_FLAG}`, minus `{LOWC_FLAG}` when self-filled or covered, plus "
          f"`{UNRES_FLAG}` when any track is unresolved).", ""]
    for key, title, lines, _ in g.sections:
        head = title if key == "NOTES" else f"{key}. {title}"
        md += [f"## {head}", "", *lines, ""]
    (out / "gate_table.md").write_text("\n".join(md))
    with (out / "gate_rows.jsonl").open("w") as fh:
        for key, title, _, data in g.sections:
            fh.write(json.dumps({"row": key, "title": title, "data": data}, sort_keys=True,
                                default=str) + "\n")
    (out / "untagged_unchecked.txt").write_text("".join(s + "\n" for s in g.unchecked))
    for name, ls in g.samples.items():
        (out / "samples" / f"{name}.txt").write_text("".join(x + "\n" for x in ls))
    return g


def gate(args: argparse.Namespace) -> int:
    build_gate(args.dump, args.handcheck, args.census, args.out)
    print(f"wrote {args.out / 'gate_table.md'}", file=sys.stderr)
    return 0


# --- Task 19: acceptance reports over a wired arm (parity, hand-check packets) ------------------

NONE = "  (none)"
PACKET_SEED = 20261023
PACKET_SAMPLE = 60
STRATA = ("wholly_untagged_d3", "newly_cleared_sample", "delivered_changes", "slice4")
_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


def parity(args: argparse.Namespace) -> int:
    """Per show, the wired fresh-get arm's titles and sources against the gate dump's `all`
    arm (`dump` measured the cascade unwired; this proves the wiring is the same code path).
    Exit 1 when any compared show differs. Writes `<out>/parity.txt` (sorted, deterministic)."""
    try:
        arm = json.loads(args.arm.read_text())
        shows = arm["shows"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise replay_holds.Refusal(f"cannot read arm {args.arm}: {err}")
    if arm.get("root") and replay_holds._overlaps(args.out, Path(arm["root"])):
        raise replay_holds.Refusal(f"refusing --out {args.out}: it overlaps the library root {arm['root']}")
    meta, rows = load_dump(args.dump)
    by = {r["slug"]: r for r in rows}
    head = [f"parity of {args.arm.name} against the `all` arm of {args.dump}",
            f"dump sha {meta.get('sha')}; arm disabled_slices {json.dumps(arm.get('disabled_slices') or [])}"]
    if not (arm.get("title_overrides_stripped") and arm.get("structure_overrides_stripped")):
        head.append("WARNING: arm is not a fresh-get arm (run with --strip-title-overrides "
                    "--strip-structure-overrides); its titles are not the dump's view")
    if arm.get("disabled_slices"):
        head.append("WARNING: the arm has disabled slices; the dump's `all` arm has none")
    compared, bad, skipped = 0, [], []
    for slug in sorted(set(shows) & set(by)):
        r, d = shows[slug], by[slug]
        a = ((d.get("arms") or {}).get("all") or {}).get("tracks")
        if d.get("unreplayable") or a is None:
            skipped.append(f"  {slug}  skipped: dump row unreplayable or without an `all` arm")
            continue
        if r.get("outcome") == "unreplayable" or "titles" not in r:
            skipped.append(f"  {slug}  skipped: arm row "
                           + ("unreplayable" if r.get("outcome") == "unreplayable" else "has no titles"))
            continue
        compared += 1
        want = [(t["title"], t["source"]) for t in a]
        got = list(zip(r["titles"], r.get("title_sources") or [None] * len(r["titles"])))
        if len(want) != len(got):
            bad.append(f"  {slug}  track count: dump {len(want)} vs arm {len(got)}")
            continue
        bad += [f"  {slug}  #{i + 1}: dump {w!r} vs arm {g!r}"
                for i, (w, g) in enumerate(zip(want, got)) if w != g]
    only_arm = sorted(set(shows) - set(by))
    n_bad = len({ln.split()[0] for ln in bad})
    out = [*head, f"compared {compared}, matching {compared - n_bad}, mismatching {n_bad}; "
           f"skipped {len(skipped)}; arm only {len(only_arm)}; dump only {len(set(by) - set(shows))}",
           "", "== mismatches", *(bad or [NONE]), "", "== skipped", *(skipped or [NONE]), "",
           "== in the arm but not the dump", *([f"  {s}" for s in only_arm] or [NONE])]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "parity.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"parity: {compared} compared, {n_bad} mismatching ({args.out / 'parity.txt'})", file=sys.stderr)
    return 1 if n_bad else 0


def _sec(v) -> str:
    try:
        if v and ":" in str(v):
            s = 0.0
            for x in str(v).split(":"):
                s = s * 60 + float(x)
            return f"{s:.0f}s"
        return f"{float(v):.0f}s" if v else "?"
    except ValueError:
        return str(v)


def _read(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def stratified_sample(keys: dict[str, str], k: int, seed: int) -> list[str]:
    """`k` slugs of `keys` (slug -> stratum key), round-robin over the keys in sorted order,
    each key's members shuffled once by `random.Random(seed)` from a sorted list: reproducible,
    every key represented before any is repeated."""
    import random
    rng = random.Random(seed)
    groups: dict[str, list[str]] = {}
    for s in sorted(keys):
        groups.setdefault(keys[s], []).append(s)
    for g in sorted(groups):
        rng.shuffle(groups[g])
    picked: list[str] = []
    while len(picked) < k and any(groups.values()):
        for g in sorted(groups):
            if groups[g] and len(picked) < k:
                picked.append(groups[g].pop())
    return sorted(picked)


def _changed(trow: dict | None, drow: dict | None) -> list[tuple[int, str]]:
    """(1-based position, path) of the positions the candidate changed: the compare's own
    list where it has one, else today's titles against the dump's `all` arm."""
    if trow is not None:
        return sorted((c["index"], c.get("path") or "") for c in trow.get("changes") or [])
    if drow is not None:
        return [(i + 1, _path(drow, i)) for i in changed_positions(drow, "today", "all")]
    return []


def _packet(slug: str, stratum: str, trow: dict | None, drow: dict | None, root: Path,
            view: str = "unknown view") -> str:
    md = [f"# {slug}  (stratum {stratum})", ""]
    wired = bool(trow and trow.get("titles"))
    md += ["candidate title source: " + (
        f"the compare arm's wired titles (title_rows.json); view: {view}" if wired else
        "the dump's PRE-WIRING `all` arm, fresh-get view (this show is not in title_rows.json)"), ""]
    if trow is not None:
        md.append(f"state {trow.get('state')}; base {trow.get('base_outcome')} -> cand "
                  f"{trow.get('cand_outcome')}; self-filled {trow.get('self_filled')}; "
                  f"D fills {trow.get('d_fills')}")
    changed = _changed(trow, drow)
    md += ["changed: " + ("; ".join(f"#{n} {p or '(unattributed)'}" for n, p in changed) or "(none)"), ""]
    if drow is None:
        md += ["(this show is not in the dump: no description, per-file data or siblings)", ""]
        return "\n".join(md) + "\n"
    today = drow.get("today") or []
    allarm = (drow.get("arms") or {}).get("all") or {}
    titles = (trow or {}).get("titles") or [t["title"] for t in allarm.get("tracks") or []]
    srcs = (trow or {}).get("title_sources") or [t["source"] for t in allarm.get("tracks") or []]
    paths = (trow or {}).get("title_paths") or allarm.get("paths") or []
    mark = {n for n, _ in changed}
    md += ["## Tracks (candidate = see the source line above; `*` = changed against today)", "",
           "| # | file | dur | today (pre-wiring dump) | candidate | source | path | raw tag |", "|---|---|---|---|---|---|---|---|"]
    esc = lambda x: str(x if x is not None else "").replace("|", "/")      # noqa: E731
    for i in range(max(len(today), len(titles))):
        t = today[i] if i < len(today) else {}
        md.append(f"| {i + 1}{'*' if i + 1 in mark else ''} | {esc(t.get('filename'))} | "
                  f"{_sec(t.get('duration'))} | {esc(t.get('title'))} ({esc(t.get('source'))}) | "
                  f"{esc(titles[i] if i < len(titles) else '')} | {esc(srcs[i] if i < len(srcs) else '')} | "
                  f"{esc(paths[i] if i < len(paths) else '')} | {esc(t.get('raw_tag'))} |")
    canon = drow.get("canonical") or {}
    md += ["", f"## Canonical setlist (source {canon.get('source')})", "",
           ", ".join(f"[{c.get('set')}] {c.get('title')}" for c in canon.get("items") or []) or "(empty)",
           "", "## Tagged sibling recordings of the same performance (titles and durations from archive.org metadata)"]
    scores = (_read(root / "shows" / slug / "selection.json") or {}).get("scores") or {}
    sibs = sorted(((i, s) for i, s in scores.items()
                   if i != drow.get("identifier") and (s.get("title_fraction") or 0) >= 0.9),
                  key=lambda kv: (-(kv[1].get("score") or 0), kv[0]))
    if not sibs:
        md.append("\n(none with title_fraction >= 0.9)")
    for ident, s in sibs[:3]:
        md.append(f"\n### {ident} (https://archive.org/details/{ident}; kept_tracks "
                  f"{s.get('kept_tracks')}, lineage {s.get('lineage')})\n")
        meta = _read(root / "cache" / f"md_{ident}.json")
        if meta is None:
            md.append("(metadata not cached)")
            continue
        files = [f for f in meta.get("files", []) if str(f.get("name", "")).lower().endswith(
            (".mp3", ".flac", ".shn"))]
        mp3 = [f for f in files if f["name"].lower().endswith(".mp3")]
        md += ["| # | file | dur | title |", "|---|---|---|---|"]
        md += [f"| {i} | {f['name']} | {_sec(f.get('length'))} | {esc(f.get('title'))} |"
               for i, f in enumerate(sorted(mp3 or files, key=lambda f: f["name"]), 1)]
    md += ["", "## Selected item description (verbatim)", "", drow.get("description") or "(none)"]
    return "\n".join(md) + "\n"


def _extra_strata(specs: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for spec in specs or []:
        name, eq, file = spec.partition("=")
        if not eq or not _NAME.match(name) or name in STRATA or name in out:
            raise replay_holds.Refusal(
                f"bad --extra {spec!r}: want NAME=FILE with a new NAME of letters, digits, _ . - "
                f"(not one of {', '.join(STRATA)})")
        try:
            lines = Path(file).read_text().splitlines()
        except OSError as err:
            raise replay_holds.Refusal(f"cannot read --extra file {file}: {err}")
        out[name] = sorted({ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")})
    return out


def packets(args: argparse.Namespace) -> int:
    """Hand-check packets for Acceptance 3, from `compare`'s `title_rows.json` and the gate
    dump. Strata (a directory each under --out): `wholly_untagged_d3` (newly cleared, wholly
    untagged, D filled 3+ tracks or self-filled), `newly_cleared_sample` (a stratified 60 of
    the other newly cleared, seed 20261023, round-robin over the path signature),
    `delivered_changes` (every show with a changed title TEXT on a delivered or voiced show),
    `slice4` (any title path starting 4), and each `--extra NAME=FILE` (no sampling).
    Also `strata_index.txt` / `.json`: slug, stratum, changed positions and their paths."""
    extras = _extra_strata(args.extra)
    tr = _read(args.cmp / "title_rows.json")
    if not isinstance(tr, dict) or not isinstance(tr.get("shows"), dict):
        raise replay_holds.Refusal(f"no usable title_rows.json in {args.cmp} (run compare first)")
    trows = tr["shows"]
    if not args.root and not tr.get("root"):
        raise replay_holds.Refusal("no library root is recorded in title_rows.json; pass --root")
    root = args.root or Path(tr["root"])
    if replay_holds._overlaps(args.out, root):
        raise replay_holds.Refusal(f"refusing --out {args.out}: it overlaps the library root {root}")
    _, drows = load_dump(args.dump)
    dby = {r["slug"]: r for r in drows}
    wholly = lambda s: bool(_rec(dby[s]).get("wholly_untagged")) if s in dby else False   # noqa: E731
    cleared = sorted(s for s, r in trows.items() if r.get("newly_cleared"))
    strata: dict[str, list[str]] = {}
    strata["wholly_untagged_d3"] = [s for s in cleared if wholly(s) and (
        trows[s].get("d_fills", 0) >= 3 or trows[s].get("self_filled"))]
    rest = [s for s in cleared if s not in set(strata["wholly_untagged_d3"])]
    key = lambda s: "+".join(sorted({p.split("+")[0] for p in trows[s].get("title_paths") or [] if p})) or "(none)"  # noqa: E731
    strata["newly_cleared_sample"] = stratified_sample({s: key(s) for s in rest}, PACKET_SAMPLE, PACKET_SEED)
    strata["delivered_changes"] = sorted(
        s for s, r in trows.items() if r.get("state") in ("delivered", "voiced")
        and any(c.get("kind") == "text" for c in r.get("changes") or []))
    strata["slice4"] = sorted(s for s, r in trows.items() if r.get("slice4"))
    strata.update(extras)
    index, lines = [], []
    for stratum, slugs in strata.items():
        d = args.out / stratum
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.md"):
            old.unlink()
        for s in slugs:
            (d / f"{s}.md").write_text(_packet(s, stratum, trows.get(s), dby.get(s), root, tr.get("view") or "unknown view"), encoding="utf-8")
            ch = _changed(trows.get(s), dby.get(s))
            index.append({"slug": s, "stratum": stratum, "changed": [{"index": n, "path": p} for n, p in ch]})
            lines.append(f"{s}\t{stratum}\t" + ("; ".join(f"#{n} {p}".rstrip() for n, p in ch) or "(none)"))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "strata_index.txt").write_text("".join(x + "\n" for x in lines), encoding="utf-8")
    (args.out / "strata_index.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n")
    print("packets: " + ", ".join(f"{k} {len(v)}" for k, v in strata.items()), file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="the per-show gate dump (read-only)")
    d.add_argument("--config", type=Path, default=None)
    d.add_argument("--slugs", type=Path, default=None)
    d.add_argument("--jobs", type=int, default=1)
    d.add_argument("--out", type=Path, required=True)
    g = sub.add_parser("gate", help="tabulate dump.jsonl into the Checkpoint A gate table")
    g.add_argument("--dump", type=Path, required=True)
    g.add_argument("--handcheck", type=Path, default=EVIDENCE / "handcheck")
    g.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    g.add_argument("--out", type=Path, required=True)
    pa = sub.add_parser("parity", help="a wired fresh-get arm's titles against the dump's `all` arm")
    pa.add_argument("--arm", type=Path, required=True)
    pa.add_argument("--dump", type=Path, required=True)
    pa.add_argument("--out", type=Path, required=True)
    pk = sub.add_parser("packets", help="Acceptance 3 hand-check packets from a compare directory")
    pk.add_argument("--cmp", type=Path, required=True, help="a `replay_holds.py compare` output directory")
    pk.add_argument("--dump", type=Path, required=True)
    pk.add_argument("--out", type=Path, required=True)
    pk.add_argument("--root", type=Path, default=None, help="library root (default: the one compare recorded)")
    pk.add_argument("--extra", action="append", default=[], metavar="NAME=FILE",
                    help="an extra stratum: FILE is a newline list of slugs (repeatable, no sampling)")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "gate":
            return gate(args)
        if args.cmd == "parity":
            return parity(args)
        if args.cmd == "packets":
            return packets(args)
        return dump(args)
    except replay_holds.Refusal as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
