"""M2: the full-library no-op check for the setlist-gap rung.

Re-gathers every show in the on-disk library TWICE from cached archive.org
metadata -- once with `adopt_gap_titles` active, once with it monkeypatched to
a no-op -- and asserts that enabling the rung changes no track the unwired run
already resolved. The only legal difference is `unresolved` -> `setlist-gap`.

Why wired-vs-unwired and not "stored show.json vs new code": the stored shows
were produced by several older code versions (some by a released binary
predating `Track.matched`), so diffing against them would be dominated by
unrelated drift and could not attribute anything to THIS change.

Offline by construction: cached metadata only, fake LLM backend, and
setlistfm=None. That last one is the standing caveat -- shows whose real
canonical was setlist.fm-won are re-derived here from LMA descriptions alone,
so this is a bound on the change's blast radius, not a replica of production.

Task 7 (Phase C) generalises it to three ARMS, same harness, same rule --
turn ONE thing off, re-gather, and enumerate every track that moves:

  --arm gap       `structure.adopt_gap_titles` off  (the original M2 check)
  --arm sibling   `gather._sibling_transfer` off    (Phase C's new rung)
  --arm numeric   `titles.is_real_title`'s 4-digit clause off (the widening
                  that also opened `structure._hygienic`, the pipeline's
                  only silent adopter -- Task 7 Step 6)

Each arm names the ONE `title_source` transition it considers legal; every
other change is a regression. The arm is what makes the diff attributable:
comparing against the stored `show.json` would be dominated by unrelated
drift from older code versions.

Two plants, because an arm has two zeros to keep honest:
  --selftest          a deliberately wrong ADOPTER (gap arm) -- proves the
                      harness sees a legal change at all
  --selftest-regress  retitles an ALREADY-RESOLVED track -- proves the arm
                      can report a REGRESSION. Run it on every arm; without
                      it, "0 regressions" may be unfalsifiable rather than
                      true, which is exactly what `--arm numeric` was.

Usage:  python scripts/regather_diff.py [--arm gap|sibling|numeric]
                                        [--assert-no-regressions]
                                        [--selftest] [--selftest-regress]
"""
import json
import sys
import tempfile
from pathlib import Path

from herder import FakeProvider

from llama import titles as titles_mod
from llama.ia_client import IAError
from llama.models import Candidate
from llama.stages import gather as gather_mod
from llama.stages.gather import run_gather
from llama.workspace import ShowWorkspace

CACHE = Path.home() / ".llama/cache"
SHOWS = Path.home() / ".llama/shows"


class CachedIA:
    """Serves archive.org metadata from the local cache; anything uncached
    raises IAError, which gather already handles as a missing sibling."""

    def metadata(self, identifier):
        p = CACHE / f"md_{identifier}.json"
        if not p.exists():
            raise IAError(f"not cached: {identifier}")
        return json.loads(p.read_text())


def _selftest_adopt(tracks, *a, **k):
    """A deliberately wrong adopter: retitles every unresolved track. Used by
    --selftest to prove this harness can SEE a difference at all. Without it,
    "0 regressions, 0 newly resolved" is indistinguishable from a comparison
    that never engaged."""
    return [t.model_copy(update={"title": "SELFTEST-SENTINEL",
                                 "title_source": "setlist-gap"})
            if t.title_source == "unresolved" else t
            for t in tracks]


# arm -> the one legal title_source transition, `from` -> `to`.
#
# `from` is NEVER None: a change to a track that was ALREADY resolved is a
# regression in every arm, which is the whole point of the comparison. Only
# `to` may be None, meaning "any source", and only where the arm genuinely
# has more than one legal destination.
#
# `numeric` was ("numeric": (None, None)) in the first cut -- "any change is
# legal" -- which made its "0 regressions" UNFALSIFIABLE BY CONSTRUCTION: no
# code change of any kind could have produced a non-zero. That is not a
# measurement. Widening `is_real_title` can legitimately resolve a track
# that was `unresolved`, by any rung that consults the predicate (the tag
# rung, the sibling arm's hygiene check, `_hygienic`), so `from` is
# `unresolved` and `to` is open.
ARMS = {"gap": ("unresolved", "setlist-gap"),
        "sibling": ("unresolved", "sibling-align"),
        "numeric": ("unresolved", None)}


def _selftest_regress(tracks):
    """The ILLEGAL-transition plant: retitle a track that is ALREADY
    resolved. Every arm must report this as a REGRESSION, which is what
    makes each arm's "0 regressions" falsifiable. `--arm numeric`'s zero was
    not, until this ran."""
    out, done = [], False
    for t in tracks:
        if not done and t.title_source != "unresolved":
            out.append(t.model_copy(update={"title": "SELFTEST-REGRESSION"}))
            done = True
        else:
            out.append(t)
    return out


def _arm() -> str:
    if "--arm" in sys.argv:
        return sys.argv[sys.argv.index("--arm") + 1]
    return "gap"


def _no_four_digit(cleaned: str) -> bool:
    """`titles.is_real_title` WITHOUT its pure-4-digit clause -- the
    predicate as it stood before this phase widened it. Written out rather
    than monkeypatching the regex, so the comparison is against a stated
    function instead of a mutated constant whose other users would move
    too."""
    return len([c for c in cleaned if c.isascii() and c.isalpha()]) >= 3


def _gather(candidate, identifier, wired):
    arm = _arm()
    saved = (gather_mod.adopt_gap_titles, gather_mod._sibling_transfer,
             titles_mod.is_real_title)
    if not wired:
        if arm == "gap":
            gather_mod.adopt_gap_titles = lambda tracks, *a, **k: tracks
        elif arm == "sibling":
            gather_mod._sibling_transfer = lambda ia, c, i, w, t, n: (list(t), [])
        elif arm == "numeric":
            titles_mod.is_real_title = _no_four_digit
        else:
            raise SystemExit(f"unknown --arm {arm!r}")
    elif "--selftest" in sys.argv and arm == "gap":
        gather_mod.adopt_gap_titles = _selftest_adopt
    try:
        with tempfile.TemporaryDirectory() as td:
            return run_gather(ShowWorkspace(Path(td) / "s"), CachedIA(),
                              FakeProvider(), candidate, identifier,
                              setlistfm=None, jerrybase_enabled=True)
    finally:
        (gather_mod.adopt_gap_titles, gather_mod._sibling_transfer,
         titles_mod.is_real_title) = saved


def main() -> int:
    regressions, adopted, skipped, compared = [], [], 0, 0
    for d in sorted(SHOWS.iterdir()):
        show_f, prov_f = d / "show.json", d / "provenance.json"
        if not (show_f.exists() and prov_f.exists()):
            skipped += 1
            continue
        stored = json.loads(show_f.read_text())
        cand = Candidate(**json.loads(prov_f.read_text())["candidate"])
        ident = stored["identifier"]
        try:
            off = _gather(cand, ident, wired=False)
            on = _gather(cand, ident, wired=True)
            if "--selftest-regress" in sys.argv:
                on = on.model_copy(update={
                    "tracks": _selftest_regress(on.tracks)})
        except Exception as exc:
            skipped += 1
            print(f"  SKIP {d.name}: {type(exc).__name__}: {exc}")
            continue
        compared += 1
        if len(off.tracks) != len(on.tracks):
            regressions.append(f"{d.name}: track count changed")
            continue
        for a, b in zip(off.tracks, on.tracks):
            if a.title == b.title and a.title_source == b.title_source:
                continue
            legal_from, legal_to = ARMS[_arm()]
            if (a.title_source == legal_from
                    and (legal_to is None or b.title_source == legal_to)):
                adopted.append(f"{d.name} t{b.index}: {a.title_source}/"
                               f"{a.title!r} -> {b.title_source}/{b.title!r}")
            else:
                regressions.append(
                    f"{d.name} t{a.index}: {a.title_source}/{a.title!r} "
                    f"-> {b.title_source}/{b.title!r}")

    print(f"\narm={_arm()}: compared {compared} shows ({skipped} skipped)")
    print(f"{len(regressions)} regressions; {len(adopted)} newly resolved")
    for line in adopted:
        print(f"  ADOPTED  {line}")
    for line in regressions:
        print(f"  REGRESS  {line}")
    if "--selftest" in sys.argv:
        ok = bool(adopted or regressions)
        print(f"\nSELFTEST: harness {'CAN' if ok else 'CANNOT'} detect a "
              f"difference -> {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    if "--selftest-regress" in sys.argv:
        ok = bool(regressions)
        print(f"\nSELFTEST-REGRESS (arm={_arm()}): harness "
              f"{'CAN' if ok else 'CANNOT'} report a regression -> "
              f"{'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    if "--assert-no-regressions" in sys.argv and regressions:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
