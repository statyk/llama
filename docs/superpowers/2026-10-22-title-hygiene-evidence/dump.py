#!/usr/bin/env python3
"""Piece 3 census, stage 1: per-show dump under CURRENT code (read-only).

For every show dir under ~/.llama/shows, replays gather (+vet, +brief reuse
decision) exactly as `llama.replay.compute_legs` does -- cache-only clients,
no LLM -- and captures, by wrapping gather's own module-level helpers
in-process (no repo edit), the intermediates the census needs:
  - resolve_titles' inputs (kept files with raw tags, the canonical setlist,
    format_titles, corroboration vocabulary)
  - build_canonical's result (source, needs_llm)
  - _recover_format_titles' basis, so the other-format bijection can be
    recomputed with titles.sibling_format_titles for class C
  - load_donor_tapes' donors (sibling tag titles) when gather fetched them
Writes one JSON line per show to dump.jsonl. Library is only read; each
show's scratch is under ~/.llama-harness/piece3/scratch/.

Run: /Users/shawn/projects/llama/.venv/bin/python dump.py [--jobs 6] [--slugs FILE]
"""
import argparse
import json
import logging
import os
import shutil
import sys
from multiprocessing import Pool
from pathlib import Path

import llama
from llama import jerrybase, replay
from llama.catalog import derive_state
from llama.config import DEFAULT_ROOT, load_config
from llama.junk import FORMAT_BY_AUDIO, LOSSLESS_TITLE_FORMATS, filter_files
from llama.ledger import Ledger
from llama.models import Show
from llama.replay import CacheOnlyIA, classify, compute_legs, setlistfm_client
from llama.setlist import parse_setlist
from llama.stages import gather as G
from llama.titles import clean_tag_title, clean_tag_titles, sibling_format_titles, title_fraction
from llama.util import length_seconds
from llama.workspace import ShowWorkspace, read_model, read_overrides

HERE = Path(__file__).resolve().parent
SCRATCH = Path.home() / ".llama-harness/piece3/scratch"
CFG = None
IA = None
SLFM = None
DELIVERED = None
DELIVERY = None
CAP: dict = {}


def _install_wrappers():
    orig_resolve = G.resolve_titles
    orig_build = G.build_canonical
    orig_recover = G._recover_format_titles
    orig_donors = G.load_donor_tapes

    def resolve_titles(kept_files, setlist, format_titles=None, gate_basis=None, **kw):
        out = orig_resolve(kept_files, setlist, format_titles=format_titles,
                           gate_basis=gate_basis, **kw)
        CAP["kept"] = [{"name": f["name"], "raw_title": f.get("title"),
                        "length": length_seconds(f.get("length"))} for f in kept_files]
        CAP["canonical"] = [{"title": i.title, "set": i.set} for i in setlist.items]
        CAP["canonical_conf"] = setlist.confidence
        CAP["format_recovered"] = format_titles is not None
        CAP["corroboration"] = sorted(kw.get("corroboration") or ())
        CAP["resolve_out"] = [{"title": t.title, "src": t.title_source} for t in out]
        return out

    def build_canonical(*a, **kw):
        cb = orig_build(*a, **kw)
        CAP["canonical_source"] = cb.source
        CAP["canonical_needs_llm"] = cb.needs_llm
        return cb

    def _recover(files, kept, ordering):
        res = orig_recover(files, kept, ordering)
        CAP["recover_basis"] = [f["name"] for f in kept]
        CAP["delivered_format"] = ordering.get("format")
        other = {}
        for fmt in LOSSLESS_TITLE_FORMATS:
            if fmt == ordering.get("format"):
                continue
            okept, _, _ = filter_files(files, want_format=fmt)
            if not okept:
                continue
            m = sibling_format_titles(kept, okept)
            raw = {f["name"]: f.get("title") for f in okept}
            other[fmt] = {"bijection": m is not None, "n": len(okept),
                          "titles": m,
                          "fraction": title_fraction(list(m.values())) if m else None,
                          "raw": raw}
        CAP["other_formats"] = other
        CAP["delivered_fraction"] = title_fraction(clean_tag_titles(kept))
        return res

    def load_donor_tapes(*a, **kw):
        donors, notes = orig_donors(*a, **kw)
        CAP["donors"] = [{"id": d.identifier, "titles": d.titles,
                          "durations": d.durations} for d in donors]
        return donors, notes

    G.resolve_titles = resolve_titles
    G.build_canonical = build_canonical
    G._recover_format_titles = _recover
    G.load_donor_tapes = load_donor_tapes


def _init():
    global CFG, IA, SLFM, DELIVERED, DELIVERY
    logging.disable(logging.CRITICAL)
    CFG = load_config(DEFAULT_ROOT / "config.toml")
    IA = CacheOnlyIA(CFG.root / "cache")
    SLFM = setlistfm_client(CFG)
    DELIVERED = {e.performance_id for e in Ledger(CFG.root / "ledger.jsonl").entries()
                 if e.status == "delivered"}
    DELIVERY = CFG.delivery_path
    _install_wrappers()


def _voiced(slug):
    if DELIVERY is None:
        return None
    try:
        m = json.loads((Path(DELIVERY) / slug / "manifest.json").read_text())
    except (OSError, ValueError):
        return False
    return isinstance(m, dict) and m.get("dj_audio") is not None


def _tracks(show: Show):
    return [{"n": t.index, "file": t.filename, "dur": t.duration_sec, "title": t.title,
             "src": t.title_source, "matched": t.matched, "set": t.set} for t in show.tracks]


def one(d: str) -> dict:
    d = Path(d)
    CAP.clear()
    ws = ShowWorkspace(d)
    row = {"slug": d.name}
    try:
        row["state"] = derive_state(ws, DELIVERED)[0]
    except Exception as e:
        row["state"] = f"error:{e}"
    row["voiced"] = _voiced(d.name) if row["state"] == "delivered" else False
    stored = None
    if ws.show.exists():
        try:
            stored = read_model(ws.show, Show)
            row["stored_tracks"] = _tracks(stored)
            row["stored_flags"] = list(stored.review_flags)
            row["identifier"] = stored.identifier
            row["artist"] = stored.artist
            row["date"] = stored.date
        except Exception as e:
            row["stored_error"] = str(e)[:200]
    try:
        ov = read_overrides(ws)
        row["override_titles"] = {str(k): v for k, v in ov.titles.items()}
        row["override_exclude"] = list(ov.exclude)
    except Exception:
        row["override_titles"] = None
    scratch = SCRATCH / f"w{os.getpid()}" / d.name
    shadow = SCRATCH / f"w{os.getpid()}" / ".shadow" / d.name
    # Pass 1: the show as the library has it (operator title overrides kept):
    # only flags/tracks are kept from this pass.
    try:
        legs0 = compute_legs(ws, config=CFG, ia=IA, slfm=SLFM, scratch=scratch)
        row["asis_flags"] = list(legs0.flags)
        row["asis_tracks"] = _tracks(legs0.replayed_show)
        row["asis_needs_llm"] = list(legs0.needs_llm)
    except Exception as e:
        row["asis_error"] = f"{type(e).__name__}: {e}"[:300]
    CAP.clear()
    # Pass 2 (primary): overrides.titles stripped, everything else kept, so
    # the census sees what a fresh `llama get` would ship under current code.
    try:
        shutil.rmtree(shadow, ignore_errors=True)
        shadow.mkdir(parents=True)
        for name in ("provenance.json", "show.json", "vetting.json", "briefing.json", "briefing.md"):
            if (d / name).is_file():
                shutil.copyfile(d / name, shadow / name)
        if ws.overrides.is_file():
            data = json.loads(ws.overrides.read_text())
            if isinstance(data, dict):
                data.pop("titles", None)
            (shadow / "overrides.json").write_text(json.dumps(data))
        legs = compute_legs(ShowWorkspace(shadow), config=CFG, ia=IA, slfm=SLFM, scratch=scratch)
        row["replayed"] = True
        row["needs_llm"] = list(legs.needs_llm)
        row["outcome"], row["would_be"] = classify(legs, row["state"])
        row["flags"] = list(legs.flags)
        row["gather_flags"] = list(legs.gather.show.review_flags)
        row["vet_flags"] = list(legs.vet.result.flags) if legs.vet else []
        row["brief_flags"] = list(legs.brief_flags)
        row["notes"] = list(legs.gather.notes) + (list(legs.vet.notes) if legs.vet else [])
        row["tracks"] = _tracks(legs.replayed_show)
        row["excluded_files"] = legs.gather.show.excluded_files
        try:
            from llama.models import VettingResult
            vr = read_model(ws.vetting, VettingResult)
            row["asserted_songs"] = list(vr.vetting.asserted_songs)
        except Exception:
            row["asserted_songs"] = None
    except Exception as e:
        row["replayed"] = False
        row["unreplayable"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(shadow, ignore_errors=True)
    row.update({k: v for k, v in CAP.items()})
    # selected item's own description and its own parse
    ident = row.get("identifier")
    if ident:
        try:
            md = IA.metadata(ident)
            meta = md.get("metadata", {})
            desc = G._description(meta)
            row["description"] = desc
            row["item_title"] = meta.get("title")
            p = parse_setlist(desc)
            row["own_parse"] = [i.title for i in p.items]
            row["own_parse_conf"] = p.confidence
            row["family"] = jerrybase.is_family_artist(row.get("artist") or "")
        except Exception as e:
            row["desc_error"] = str(e)[:200]
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--slugs", type=Path)
    ap.add_argument("--out", type=Path, default=HERE / "dump.jsonl")
    a = ap.parse_args()
    here = Path(llama.__file__).resolve()
    assert str(here).startswith("/Users/shawn/projects/llama/packages/llama/src"), here
    cfg = load_config(DEFAULT_ROOT / "config.toml")
    shows = cfg.root / "shows"
    if a.slugs:
        dirs = [str(shows / s.strip()) for s in a.slugs.read_text().split() if s.strip()]
    else:
        dirs = sorted(str(p) for p in shows.iterdir() if p.is_dir())
    meta = {"sha": replay.code_identity(), "config_fingerprint": replay.config_fingerprint(cfg),
            "setlistfm_configured": replay.setlistfm_configured(cfg), "n": len(dirs)}
    print(json.dumps(meta), file=sys.stderr)
    tmp = a.out.with_suffix(".tmp")
    with Pool(a.jobs, initializer=_init) as pool, tmp.open("w") as fh:
        fh.write(json.dumps({"_meta": meta}) + "\n")
        for i, row in enumerate(pool.imap_unordered(one, dirs, chunksize=4), 1):
            fh.write(json.dumps(row) + "\n")
            if i % 200 == 0:
                print(f"{i}/{len(dirs)}", file=sys.stderr, flush=True)
    os.replace(tmp, a.out)


if __name__ == "__main__":
    main()
