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

Usage:  python scripts/regather_diff.py [--assert-no-regressions]
"""
import json
import sys
import tempfile
from pathlib import Path

from herder import FakeProvider

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


def _gather(candidate, identifier, wired):
    real = gather_mod.adopt_gap_titles
    if not wired:
        gather_mod.adopt_gap_titles = lambda tracks, *a, **k: tracks
    elif "--selftest" in sys.argv:
        gather_mod.adopt_gap_titles = _selftest_adopt
    try:
        with tempfile.TemporaryDirectory() as td:
            return run_gather(ShowWorkspace(Path(td) / "s"), CachedIA(),
                              FakeProvider(), candidate, identifier,
                              setlistfm=None, jerrybase_enabled=True)
    finally:
        gather_mod.adopt_gap_titles = real


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
            if a.title_source == "unresolved" and b.title_source == "setlist-gap":
                adopted.append(f"{d.name} t{b.index}: {b.title!r}")
            else:
                regressions.append(
                    f"{d.name} t{a.index}: {a.title_source}/{a.title!r} "
                    f"-> {b.title_source}/{b.title!r}")

    print(f"\ncompared {compared} shows ({skipped} skipped)")
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
    if "--assert-no-regressions" in sys.argv and regressions:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
