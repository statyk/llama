"""Task 7 Step 1/3: the named controls and the six-show table, through the
SHIPPED sibling-transfer code (`siblings.propose_rows` / `rate_alignment` /
`cplus_filter`), never the prototype.

Read-only: it opens `~/.llama/cache` and `~/.llama/shows` and writes nothing.

Every mode prints its EXPECTED value beside the measured one, because a
control that only prints what happened cannot fail.

Deliberately a SECOND driver, not a mode of `sibling_blind_arm.py`. The two
reach the same shipped functions by different routes -- this one from named
identifiers and the on-disk library, that one from a cache-wide sweep -- so a
mistake in one driver does not silently move the other's numbers. Where they
overlap (the localised-shift pair) the overlap is the check.

Usage:
  ./.venv/bin/python scripts/sibling_controls.py --baseline
  ./.venv/bin/python scripts/sibling_controls.py --deletions
  ./.venv/bin/python scripts/sibling_controls.py --rotation [--n 100]
  ./.venv/bin/python scripts/sibling_controls.py --localised-shift
  ./.venv/bin/python scripts/sibling_controls.py --wrong-performance
  ./.venv/bin/python scripts/sibling_controls.py --six-shows
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from llama.junk import FORMAT_BY_AUDIO, filter_files
from llama.models import Candidate, Track
from llama.siblings import (AUTO, FLOOR, DonorTape, cplus_filter,
                            propose_rows, rate_alignment)
from llama.structure import loosely_same_title
from llama.titles import clean_tag_titles, title_fraction
from llama.util import length_seconds

CACHE = Path.home() / ".llama" / "cache"
SHOWS = Path.home() / ".llama" / "shows"
WANT = FORMAT_BY_AUDIO["mp3"]

YMSB_TARGET = "ymsb2005-12-31.flac16.wav"
YMSB_DONOR = "ymsb2005-12-31.flac16"
SHIFT_TARGET = "gd1971-08-06.aud.wolfe.smith.114390.flac24"
SHIFT_DONOR = "gd1971-08-06.mtx.seamons.96668.sbeok.flac16"


# The hand-established ground truth for `ymsb2005-12-31.flac16.wav`, one
# entry per target track. SOURCE: Phase B's Section B hand-check
# (`docs/superpowers/2026-08-31-gap-fill-blind-test.md`), which established
# the two tapes' correspondence by cumulative-offset alignment across all
# three discs and BY HAND, independently of any DP. Transcribed here as the
# donor's own tag strings under that mapping, so a control can compare
# adopted STRINGS against it instead of against another run of the same code.
YMSB_TRUTH = [
    "Granny Woncha Smoke Some > Ride The Wild Turkey",
    "On The Run",
    "Postcard To My Son From Jail [tentative title]",
    "On The Run",
    "Steep Grade Sharp Curves",
    "Howard Hughes Blues",
    "Polly Put The Kettle On",
    "Jenny Run Away In the Mud & Rain",
    "Peace Of Mind > King Ebenezer Rap",
    "Peace Of Mind",
    "Intro",
    "Get Me Outta This City",
    "Midnight Blues",
    "Jack London",
    "Up On The Hill Where They Do The Boogie",
    "Countdown to Happy New Year - Auld Lang Syne",
    "Angel",
    "It's All Too Much",
    "Finally Saw The Light",
    "Ewe With The Crooked Horn",
    "If You're Ever In Oklahoma > Spanish Harlem Incident",
    "Crowd",
    "High Lonesome Sound",
    "Tear Down The Grand Ole Opry",
]


def _check_shapes() -> None:
    """Proof 1 of 3 for this instrument: the hand-transcribed ground truth
    has exactly one entry per target track, and every entry is non-empty. A
    transcription that silently lost or gained a line would shift every
    comparison below by one -- the exact failure this whole phase is about."""
    _n, durs, _t = load(YMSB_TARGET)
    assert len(YMSB_TRUTH) == len(durs), (
        f"YMSB_TRUTH has {len(YMSB_TRUTH)} entries for a {len(durs)}-track tape")
    assert all(t.strip() for t in YMSB_TRUTH), "YMSB_TRUTH has an empty entry"


def load(identifier: str):
    md = json.loads((CACHE / f"md_{identifier}.json").read_text())
    kept, _exc, _ord = filter_files(md.get("files", []), want_format=WANT)
    durs = [length_seconds(f.get("length")) for f in kept]
    return [f["name"] for f in kept], durs, clean_tag_titles(kept)


def donor_of(identifier: str, drop: int | None = None,
             rotate: int = 0) -> DonorTape:
    names, durs, titles = load(identifier)
    if drop is not None:
        names = names[:drop] + names[drop + 1:]
        durs = durs[:drop] + durs[drop + 1:]
        titles = titles[:drop] + titles[drop + 1:]
    if rotate:
        titles = titles[rotate:] + titles[:rotate]
    return DonorTape(identifier, names, durs, titles)


def tracks_of(names, durs, titles, hidden: set[int]) -> list[Track]:
    return [Track(index=i + 1, set="1",
                  title="" if (i in hidden or not t.strip()) else t,
                  filename=n, duration_sec=d,
                  title_source=("unresolved" if (i in hidden or not t.strip())
                                else "tags"))
            for i, (n, d, t) in enumerate(zip(names, durs, titles))]


def _table(rows, expect_titled: int, expect_declined: int) -> None:
    """`expect_titled` counts ADOPT VERDICTS, not rows carrying a string. A
    `weak evidence` decline deliberately keeps its `proposed` title so the
    operator surface can render what the DP thought, so counting non-empty
    strings would score that decline as an adoption -- the predicate has to
    be the verdict."""
    titled = [r for r in rows if r.verdict == "adopt"]
    declined = [r for r in rows if r.verdict != "adopt"]
    for r in rows:
        mark = " " if r.verdict == "adopt" else "X"
        print(f"  {mark} t{r.track:2d} span={str(r.donor_span):>9s} "
              f"resid={r.residual_sec:6.0f}s pen={r.penalty_sec:6.0f}s "
              f"{r.verdict:7s} {r.proposed!r} {r.reason}")
    ok = len(titled) == expect_titled and len(declined) == expect_declined
    print(f"  MEASURED adopt verdicts: {len(titled)} "
          f"(expected {expect_titled}); declines: {len(declined)} "
          f"(expected {expect_declined}) -> {'PASS' if ok else 'FAIL'}")


def baseline() -> int:
    """The probe baseline: ymsb2005's untagged tape against its fully tagged
    sibling. EXPECTED: 23 rows carry a proposed title, 1 does not (the donor
    has an `Intro` the target lacks), and the pair is `no-anchors` -- the
    tape is wholly untagged, so NOTHING is automatic."""
    names, durs, titles = load(YMSB_TARGET)
    donor = donor_of(YMSB_DONOR)
    print(f"BASELINE {YMSB_TARGET} <- {YMSB_DONOR} "
          f"(target n={len(durs)}, donor n={len(donor.durations)}, "
          f"target title_fraction={title_fraction(titles):.3f})")
    rows, diag = propose_rows(durs, donor, metadata_norms=set())
    tracks = tracks_of(names, durs, titles, hidden=set())
    res = rate_alignment(rows, tracks)
    _table(rows, expect_titled=23, expect_declined=1)
    adopted = [r for r in rows if r.verdict == "adopt"]
    right = sum(1 for r in adopted
                if loosely_same_title(YMSB_TRUTH[r.track - 1], r.proposed))
    print(f"  CONTENT: {right}/{len(adopted)} adopted titles match the "
          f"hand-established YMSB_TRUTH (expected 23/23) -> "
          f"{'PASS' if right == len(adopted) == 23 else 'FAIL'}")
    print(f"  band={res.band!r} (expected 'no-anchors'), "
          f"agreement={res.agreement}, anchors={res.n_anchors}")
    auto = [r for r in cplus_filter(rows, tracks) if r.verdict == "adopt"]
    print(f"  automatic titles: {len(auto)} (expected 0 -- untagged tape) -> "
          f"{'PASS' if not auto and res.band == 'no-anchors' else 'FAIL'}")
    return 0


def deletions() -> int:
    """A2/A3: delete a donor track and re-run. EXPECTED: the rows that lose
    their donor decline, and every SURVIVING adoption still matches the
    hand-established ground truth (`YMSB_TRUTH`), 0 wrong.

    Scored against the HAND-ESTABLISHED mapping, not against the baseline
    run: deleting the donor's `Intro` actually IMPROVES target track 1 (the
    baseline merges the Intro in and declines the row), so a
    same-as-baseline comparator would score a correction as a regression.
    Scoring by count alone cannot see a uniform shift either, which is the
    failure this control exists for -- so identity, by string."""
    names, durs, titles = load(YMSB_TARGET)
    ok = True
    for label, drop in (("baseline (no deletion)", None),
                        ("A2 (donor track 1, 'Intro', deleted)", 0),
                        ("A3 (donor track 18, mid-set-2 song, deleted)", 17)):
        rows, _ = propose_rows(durs, donor_of(YMSB_DONOR, drop=drop),
                               metadata_norms=set())
        adopted = [r for r in rows if r.verdict == "adopt"]
        right = [r for r in adopted
                 if loosely_same_title(YMSB_TRUTH[r.track - 1], r.proposed)]
        wrong = [r for r in adopted if r not in right]
        print(f"{label}: {len(adopted)} adopted, {len(right)} correct against "
              f"YMSB_TRUTH, {len(wrong)} wrong (expected 0), "
              f"{len(rows) - len(adopted)} declined")
        for r in wrong:
            print(f"    t{r.track}: truth={YMSB_TRUTH[r.track - 1]!r} "
                  f"proposed={r.proposed!r}")
        ok = ok and not wrong
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def rotation(cache_path: Path, n: int) -> int:
    """Guard honesty under a corrupted donor: rotate the donor's titles by
    one and re-run.

    TWO ARMS, because the obvious one is not a valid instrument on its own.

    (a) THE NAMED CONTROL (probe control A, spec Evidence table): ymsb2005's
        untagged tape with its donor's titles rotated. EXPECTED 0 automatic
        titles -- and the pair scores every row wrong against `YMSB_TRUTH`,
        which is what shows the scorer can see failure at all.

    (b) A CORPUS-WIDE EXTENSION over anchored pairs. **Rotation is not a
        guaranteed corruption**: where a donor carries one extra leading
        track (a banner, an intro, a `tuning`) its tag list is ALREADY
        displaced by one relative to the target's songs, so rotating it
        CORRECTS the correspondence instead of breaking it. Counting
        "titles shipped" there measures the corpus's donor shapes, not the
        guard. The property that is actually safety is therefore the one
        scored: zero WRONG automatic titles. Both counts are printed; only
        the wrong count gates."""
    names, durs, titles = load(YMSB_TARGET)
    rot_rows, _ = propose_rows(durs, donor_of(YMSB_DONOR, rotate=1),
                               metadata_norms=set())
    tracks = tracks_of(names, durs, titles, hidden=set())
    res = rate_alignment(rot_rows, tracks)
    auto = [r for r in cplus_filter(rot_rows, tracks) if r.verdict == "adopt"]
    scored_wrong = sum(1 for r in rot_rows if r.verdict == "adopt"
                       and not loosely_same_title(YMSB_TRUTH[r.track - 1],
                                                  r.proposed))
    n_adopt = sum(1 for r in rot_rows if r.verdict == "adopt")
    print(f"(a) NAMED CONTROL, ymsb2005 donor rotated +1: band={res.band!r}, "
          f"automatic titles={len(auto)} (expected 0); the scorer marks "
          f"{scored_wrong}/{n_adopt} of the rotated proposals WRONG against "
          f"YMSB_TRUTH (expected all of them) -> "
          f"{'PASS' if not auto and scored_wrong == n_adopt > 0 else 'FAIL'}")

    entries = [json.loads(l) for l in cache_path.read_text().splitlines()
               if l.strip()]
    rng = random.Random(5)
    sample = rng.sample(entries, min(n, len(entries)))
    honest = rotated = rotated_wrong = used = 0
    for e in sample:
        names, durs, titles = e["names"], e["durations"], e["titles"]
        keep = max(1, round(0.65 * len(titles)))
        hidden = set(rng.sample(range(len(titles)), len(titles) - keep))
        tracks = tracks_of(names, durs, titles, hidden)
        norms = set(e["norms"])
        for pair in e["pairs"][:1]:
            d_names, d_durs, d_titles = load(pair["donor"])
            for rot, bucket in ((0, "honest"), (1, "rotated")):
                donor = DonorTape(pair["donor"], d_names, d_durs,
                                  d_titles[rot:] + d_titles[:rot])
                rows, _ = propose_rows(durs, donor, metadata_norms=norms)
                if rows is None:
                    continue
                res = rate_alignment(rows, tracks)
                if res.band != "auto":
                    continue
                got = [r for r in cplus_filter(rows, tracks)
                       if r.verdict == "adopt" and (r.track - 1) in hidden
                       and titles[r.track - 1].strip()]
                if bucket == "honest":
                    honest += len(got)
                else:
                    rotated += len(got)
                    rotated_wrong += sum(
                        1 for r in got
                        if not loosely_same_title(titles[r.track - 1],
                                                  r.proposed))
            used += 1
    ok = honest > 0 and rotated_wrong == 0
    print(f"(b) CORPUS-WIDE over {used} pairs: honest donor ships {honest} "
          f"automatic titles (expected > 0); rotated donor ships {rotated}, "
          f"of which {rotated_wrong} are WRONG (expected 0) -> "
          f"{'PASS' if ok else 'FAIL'}"
          f"{'' if honest else '  (DEGENERATE: the honest arm shipped nothing)'}")
    return 0 if ok else 1


def localised_shift() -> int:
    """The named localised-shift pair. The sweep's cell that admitted it is
    not reproducible from the record, so this sweeps every stratum/rep this
    phase uses and reports the WORST cell: bare ratio vs C+."""
    names, durs, titles = load(SHIFT_TARGET)
    d_names, d_durs, d_titles = load(SHIFT_DONOR)
    donor = DonorTape(SHIFT_DONOR, d_names, d_durs, d_titles)
    rows, diag = propose_rows(durs, donor, metadata_norms=set())
    print(f"LOCALISED SHIFT {SHIFT_TARGET} <- {SHIFT_DONOR}: "
          f"target n={len(durs)}, donor n={len(d_durs)}, "
          f"cost={diag.get('cost')}, match={diag.get('match_fraction')}")
    worst = None
    rng = random.Random(3)
    for keep in (0.35, 0.65, 0.875):
        for rep in range(5):
            hidden = set(rng.sample(range(len(titles)),
                                    len(titles) - max(1, round(keep * len(titles)))))
            tracks = tracks_of(names, durs, titles, hidden)
            res = rate_alignment(rows, tracks)
            if res.band != "auto":
                continue
            bare = [r for r in rows if r.verdict == "adopt"
                    and (r.track - 1) in hidden and titles[r.track - 1].strip()]
            keptr = {r.track for r in cplus_filter(rows, tracks)
                     if r.verdict == "adopt"}
            bw = sum(1 for r in bare
                     if not loosely_same_title(titles[r.track - 1], r.proposed))
            cw = sum(1 for r in bare if r.track in keptr
                     and not loosely_same_title(titles[r.track - 1], r.proposed))
            cn = sum(1 for r in bare if r.track in keptr)
            cand = (bw, len(bare), cw, cn, keep, rep, res.agreement)
            if worst is None or cand > worst:
                worst = cand
    if worst is None:
        print("  the pair never reached the automatic band in any cell")
        return 0
    bw, bn, cw, cn, keep, rep, agr = worst
    print(f"  worst cell (keep={keep}, rep={rep}, agreement={agr:.3f}): "
          f"bare ratio adopts {bn} ({bw} wrong); C+ adopts {cn} ({cw} wrong)")
    print(f"  EXPECTED: C+ ships 0 of the bare ratio's wrong titles -> "
          f"{'PASS' if cw == 0 else 'FAIL'}")
    return 0 if cw == 0 else 1


def wrong_performance() -> int:
    """Control A5: a donor from a WHOLLY DIFFERENT performance. EXPECTED:
    agreement below FLOOR, so the pair is declined outright."""
    names, durs, titles = load(SHIFT_TARGET)
    results = []
    for other in ("gd1973-06-10.sbd.miller.89640.sbeok.flac16",
                  "gd1977-05-08.sbd.miller.97482.sbeok.flac16",
                  "ymsb2005-12-31.flac16"):
        p = CACHE / f"md_{other}.json"
        if not p.exists():
            continue
        d_names, d_durs, d_titles = load(other)
        rows, diag = propose_rows(durs, DonorTape(other, d_names, d_durs, d_titles),
                                  metadata_norms=set())
        tracks = tracks_of(names, durs, titles, hidden=set())
        if rows is None:
            results.append((other, None, "declined by propose_rows: "
                            + str(diag.get("decline"))))
            continue
        res = rate_alignment(rows, tracks)
        results.append((other, res.agreement, res.band))
    ok = True
    for other, agr, band in results:
        bad = agr is not None and agr >= FLOOR
        ok = ok and not bad
        print(f"  A5 donor {other}: agreement={agr}, band={band} "
              f"(expected < FLOOR={FLOOR})")
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def six_shows() -> int:
    """The library's six unresolved shows, through the shipped path, with the
    automatic band's yield asserted as the expected result."""
    from herder import FakeProvider
    from llama.ia_client import IAError
    from llama.stages.gather import best_donor, show_metadata_norms

    class CachedIA:
        def metadata(self, identifier):
            p = CACHE / f"md_{identifier}.json"
            if not p.exists():
                raise IAError(f"not cached: {identifier}")
            return json.loads(p.read_text())

    ia = CachedIA()
    total_auto = 0
    for d in sorted(SHOWS.iterdir()):
        show_f, prov_f = d / "show.json", d / "provenance.json"
        if not (show_f.exists() and prov_f.exists()):
            continue
        stored = json.loads(show_f.read_text())
        if not any(t["title_source"] == "unresolved" for t in stored["tracks"]):
            continue
        cand = Candidate(**json.loads(prov_f.read_text())["candidate"])
        ident = stored["identifier"]
        tracks = [Track(**t) for t in stored["tracks"]]
        try:
            meta = ia.metadata(ident).get("metadata", {})
        except IAError as err:
            print(f"{d.name}: NOT CACHED ({err})")
            continue
        norms = show_metadata_norms(str(meta.get("creator") or cand.collection),
                                    cand, meta, [])
        donor, rows, res, notes = best_donor(ia, cand, ident, WANT, tracks, norms)
        n_unres = sum(1 for t in tracks if t.title_source == "unresolved")
        if donor is None:
            print(f"{d.name}: {n_unres} unresolved, NO QUALIFYING DONOR "
                  f"({'; '.join(notes) or 'none'})")
            continue
        auto = 0
        if res.band == "auto":
            auto = sum(1 for r in cplus_filter(rows, tracks)
                       if r.verdict == "adopt"
                       and tracks[r.track - 1].title_source == "unresolved")
        proposals = sum(1 for r in rows if r.proposed
                        and tracks[r.track - 1].title_source == "unresolved")
        total_auto += auto
        print(f"{d.name}: {n_unres} unresolved; donor={donor.identifier}; "
              f"agreement={res.agreement}; anchors={res.n_anchors}; "
              f"band={res.band}; proposals-on-unresolved={proposals}; "
              f"AUTOMATIC={auto}")
        for dis in res.disagreements:
            print(f"    disagreement t{dis.track}: tape={dis.tape_title!r} "
                  f"sibling={dis.proposed!r}")
    print(f"\nAUTOMATIC BAND'S LIBRARY YIELD: {total_auto} tracks "
          f"(EXPECTED 0, asserted as the design's stated result) -> "
          f"{'PASS' if total_auto == 0 else 'REVIEW'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--deletions", action="store_true")
    ap.add_argument("--rotation", type=Path, metavar="ALIGN_JSONL")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--localised-shift", action="store_true")
    ap.add_argument("--wrong-performance", action="store_true")
    ap.add_argument("--six-shows", action="store_true")
    a = ap.parse_args()
    _check_shapes()
    print(f"SHAPE CHECK: YMSB_TRUTH is {len(YMSB_TRUTH)} entries for a "
          f"{len(YMSB_TRUTH)}-track tape -> PASS")
    if a.baseline:
        return baseline()
    if a.deletions:
        return deletions()
    if a.rotation:
        return rotation(a.rotation, a.n)
    if a.localised_shift:
        return localised_shift()
    if a.wrong_performance:
        return wrong_performance()
    if a.six_shows:
        return six_shows()
    ap.error("pick a mode")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
