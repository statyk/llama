"""M3: the full-library abort-set check for the canonical footnote-marker strip.

Re-gathers every show in the on-disk library TWICE from cached archive.org
metadata -- once with `gather._strip_footnote_markers` active, once with it
monkeypatched to a no-op -- and checks that turning the strip ON moves
NOTHING except track `title` text on tracks whose canonical item genuinely
carried a trailing marker.

The abort set was registered in advance, before this script existed, in
`docs/superpowers/2026-08-31-footnote-strip-prediction.md`: `matched`, `set`,
`title_source`, set breaks, coverage, alignment output. If any of them moves
on any show, this script exits 2 (ABORT) rather than 1 -- the markers would
then be load-bearing in matching, which is a materially different change than
the one authorized, and is escalated rather than ruled on locally.

WHY NOT `regather_diff.py`: that harness is a differential over
`adopt_gap_titles` wired vs no-op. A cleaning-pass change moves BOTH of its
arms identically, so it reports a clean no-op while the canonical shifts
underneath it. A cleaning-pass change needs its own arm; that blindness is
the whole reason this file exists.

WHY `--selftest` IS MANDATORY AND RUNS FIRST: the registered prediction says
the abort set comes back EMPTY. A genuinely-empty result and a harness that
never engaged the changed code produce byte-identical output, and cannot be
told apart after the fact. `--selftest` replaces the strip with a cleaner
that RENAMES every canonical item outright -- a canonical mutation matching
cannot possibly ignore -- and demands the differential go red. Same shape as
`regather_diff.py --selftest`, different question.

Offline by construction: cached metadata only, fake LLM backend, and
setlistfm=None. That last one is the standing caveat -- shows whose real
canonical was setlist.fm-won are re-derived here from LMA descriptions alone,
so this is a BOUND on the change's blast radius, not a replica of production.

Usage:  python scripts/footnote_strip_diff.py [--selftest] [--out DIR]
Exit:   0 clean, 1 selftest failed to detect, 2 ABORT SET MOVED
"""
import json
import re
import sys
import tempfile
from pathlib import Path

from herder import FakeProvider

from llama.ia_client import IAError
from llama.models import Candidate, ParsedSetlist, SetlistItem
from llama.songs import normalize_song
from llama.stages import gather as gather_mod
from llama.stages.gather import _strip_footnote_markers, run_gather
from llama.workspace import ShowWorkspace

CACHE = Path.home() / ".llama/cache"
SHOWS = Path.home() / ".llama/shows"

# The comparison is a WHOLE-MODEL diff of the two `Show`s, not a field
# allowlist. An allowlist answers "did the fields I thought of move?", and the
# registered prediction is a claim about everything -- a field nobody listed
# moving is exactly the silent false negative this measurement exists to
# prevent. `_deep_diff` walks both dumps and reports every differing path;
# only the paths below are classified as anything other than an abort.
_TITLE_PATH = re.compile(r"^tracks\[\d+\]\.title$")
_CONFLICT_PATH = re.compile(r"^structure\.conflicts\[\d+\]$")


class CachedIA:
    """Serves archive.org metadata from the local cache; anything uncached
    raises IAError, which gather already handles as a missing sibling."""

    def metadata(self, identifier):
        p = CACHE / f"md_{identifier}.json"
        if not p.exists():
            raise IAError(f"not cached: {identifier}")
        return json.loads(p.read_text())


def _selftest_clean(parsed: ParsedSetlist) -> ParsedSetlist:
    """A deliberately wrong cleaner: renames every canonical item outright.

    NOT a marker change. The point is a canonical mutation that matching
    cannot ignore -- these names match no track, so `matched`/coverage/`set`
    must all move. If the differential stays green against THIS, it is not
    looking at the canonical setlist at all and its verdict on the real strip
    is worthless.
    """
    return parsed.model_copy(update={
        "items": [it.model_copy(update={"title": f"SELFTEST-RENAMED-{n}"})
                  for n, it in enumerate(parsed.items)]})


def _gather(candidate, identifier, on: bool):
    real = gather_mod._strip_footnote_markers
    if not on:
        gather_mod._strip_footnote_markers = lambda parsed: parsed
    elif "--selftest" in sys.argv:
        gather_mod._strip_footnote_markers = _selftest_clean
    try:
        with tempfile.TemporaryDirectory() as td:
            return run_gather(ShowWorkspace(Path(td) / "s"), CachedIA(),
                              FakeProvider(), candidate, identifier,
                              setlistfm=None, jerrybase_enabled=True)
    finally:
        gather_mod._strip_footnote_markers = real


def _marker_explains(before: str, after: str) -> bool:
    """True only if `after` is exactly what the shipped strip makes of
    `before`. Calls the real function rather than re-expressing its pattern:
    a second copy of the regex here could bless a title change the shipped
    rule never actually produces."""
    probe = ParsedSetlist(items=[SetlistItem(title=before,
                                             normalized=normalize_song(before),
                                             set="1")])
    return _strip_footnote_markers(probe).items[0].title == after


def _deep_diff(a, b, path: str = "") -> list[tuple[str, object, object]]:
    """Every differing leaf path between two `Show.model_dump()`s.

    A length change on a list is reported as one diff at the list's own path
    rather than as a flood of positional ones -- a shifted list is a single
    fact, and rendering it as N mismatches would bury it."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            sub = f"{path}.{k}" if path else str(k)
            if k not in a or k not in b:
                out.append((sub, a.get(k), b.get(k)))
            else:
                out += _deep_diff(a[k], b[k], sub)
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [(path, f"<{len(a)} items>", f"<{len(b)} items>")]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += _deep_diff(x, y, f"{path}[{i}]")
        return out
    return [] if a == b else [(path, a, b)]


def main() -> int:
    selftest = "--selftest" in sys.argv
    outdir = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
    aborts, titles_changed, conflicts_moved = [], [], []
    skipped, compared = 0, 0
    for d in sorted(SHOWS.iterdir()):
        show_f, prov_f = d / "show.json", d / "provenance.json"
        if not (show_f.exists() and prov_f.exists()):
            skipped += 1
            continue
        stored = json.loads(show_f.read_text())
        cand = Candidate(**json.loads(prov_f.read_text())["candidate"])
        ident = stored["identifier"]
        try:
            off = _gather(cand, ident, on=False)
            on = _gather(cand, ident, on=True)
        except Exception as exc:
            skipped += 1
            print(f"  SKIP {d.name}: {type(exc).__name__}: {exc}", flush=True)
            continue
        compared += 1
        if compared % 10 == 0:
            print(f"  ... {compared} shows compared", flush=True)
        for path, x, y in _deep_diff(off.model_dump(), on.model_dump()):
            explained = (isinstance(x, str) and isinstance(y, str)
                         and _marker_explains(x, y))
            if _TITLE_PATH.match(path) and explained:
                titles_changed.append(f"{d.name} {path}: {x!r} -> {y!r}")
            elif _CONFLICT_PATH.match(path) and explained:
                # STILL AN ABORT: `structure.conflicts` is alignment output,
                # which the pre-registration named. Kept as its own bucket so
                # the escalation can say precisely what moved rather than
                # "something in structure".
                conflicts_moved.append(f"{d.name} {path}: {x!r} -> {y!r}")
            else:
                aborts.append(f"{d.name} {path}: {x!r} -> {y!r}")

    print(f"\ncompared {compared} shows ({skipped} skipped)")
    print(f"{len(titles_changed)} track titles stripped; "
          f"{len(conflicts_moved)} structure.conflicts entries stripped; "
          f"{len(aborts)} other abort-set moves")
    for line in titles_changed:
        print(f"  TITLE     {line}")
    for line in conflicts_moved:
        print(f"  CONFLICT  {line}")
    for line in aborts:
        print(f"  ABORT     {line}")
    if outdir:
        name = "selftest" if selftest else "real"
        (outdir / f"{name}-titles.txt").write_text("\n".join(titles_changed) + "\n")
        (outdir / f"{name}-conflicts.txt").write_text("\n".join(conflicts_moved) + "\n")
        (outdir / f"{name}-aborts.txt").write_text("\n".join(aborts) + "\n")
    if selftest:
        ok = bool(aborts or conflicts_moved)
        print(f"\nSELFTEST: harness {'CAN' if ok else 'CANNOT'} see a canonical "
              f"mutation -> {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    return 2 if (aborts or conflicts_moved) else 0


if __name__ == "__main__":
    raise SystemExit(main())
