"""A fixture library for the replay harness (spec slice 0): shows produced by
the real `run_gather` against the gd73 fixture, so a replay reproduces them.

Plain module, like `helpers.py`: `packages/llama/tests` test files import it
by name (pytest puts `tests/` on `sys.path`), and `scripts/test_replay_holds.py`
adds this directory to `sys.path` itself.
"""
import json
from pathlib import Path

from herder import FakeProvider
from llama.config import Config
from llama.models import (Briefing, Candidate, Provenance, RecordingSummary, ResearchVetting,
                          VettingResult)
from llama.stages.gather import run_gather
from llama.stages.vet_research import apply_vet
from llama.workspace import ShowWorkspace, write_artifact

FIXTURES = Path(__file__).parent / "fixtures"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"


def replay_config(root: Path) -> Config:
    """Jerrybase OFF: the vendored CSV has GD 1973-06-10 with three numbered
    sets, and the trimmed gd73 fixture has two, so an enabled dataset would
    hold the fixture show. The stored show and the replay use this same config."""
    return Config(root=root, jerrybase={"enabled": False})


def library_show(root: Path, *, held: bool, date="1973-06-10",
                 held_flags=("unresolved track titles",), asserted_dates=None,
                 with_vetting=True, with_briefing=False, alignment=None, description=None,
                 vetted=False):
    """A gathered gd73 show `gratefuldead-<date>` in <root>/shows/, produced by
    the real run_gather against the fixture under `replay_config(root)` (so the
    replay reproduces it), with the knobs the tests need. `held` appends
    `held_flags` to the stored flags; the default flag is one the replay does
    not raise (a synthetic hold: the replay clears it). `asserted_dates`
    defaults to `[date]`, so the vetting matches the show's own date.
    `vetted=True` stores the show as the vet stage leaves it (apply_vet over
    the stored vetting, e.g. a placeholder date adopted), as production does."""
    md = json.loads((FIXTURES / "gd73_metadata.json").read_text())
    if description is not None:
        md["metadata"]["description"] = description
    (root / "cache").mkdir(parents=True, exist_ok=True)
    (root / "cache" / f"md_{IDENT}.json").write_text(json.dumps(md))
    ws = ShowWorkspace(root / "shows" / f"gratefuldead-{date}")
    cand = Candidate(performance_id=f"GratefulDead/{date}", collection="GratefulDead",
                     date=date, venue="RFK Stadium", city="Washington, DC",
                     recordings=[RecordingSummary(identifier=IDENT)])
    write_artifact(ws.provenance, Provenance(performance_id=cand.performance_id, run="r1",
                                             dossier="d", candidate=cand,
                                             processed_at="2026-10-19T00:00:00+00:00"))

    class _IA:
        def metadata(self, i): return md
    cfg = replay_config(root)
    show = run_gather(ws, _IA(), FakeProvider(), cand, IDENT, structure_cfg=cfg.structure,
                      jerrybase_enabled=cfg.jerrybase.enabled)
    vetting = ResearchVetting(
        asserted_songs=["Morning Dew", "Dark Star"],
        asserted_dates=list(asserted_dates) if asserted_dates is not None else [date])
    if vetted:
        show = apply_vet(vetting, show).show
    if alignment:
        show.structure = show.structure.model_copy(update={"alignment": alignment})
    if held:
        show.review_flags = show.review_flags + list(held_flags)
        show.needs_review = True
    write_artifact(ws.show, show)
    if with_vetting:
        write_artifact(ws.vetting, VettingResult(vetting=vetting))
    if with_briefing:
        write_artifact(ws.briefing_json, Briefing(context="c", significance="s",
                                                  per_set={"1": ["a"], "2": ["b"], "encore": ["c"]}))
    return ws, show


HELD = "gratefuldead-1973-06-10"
CLEAN = "gratefuldead-1973-06-11"


def build_library(root: Path, *, held_for_real: bool = False) -> dict[str, ShowWorkspace]:
    """A two-show library at `root` with its own `config.toml` (`root` set,
    jerrybase off, as `replay_config`).

    - `gratefuldead-1973-06-10`: held, with a vetting.json and a reusable
      briefing.json. Default: a synthetic hold (`unresolved track titles`
      appended) that the replay clears, the shape of a hold a Tier 1 rule
      removes. `held_for_real=True`: the vetting asserts a wrong date, so the
      replay raises the stored flag and the show stays held.
    - `gratefuldead-1973-06-11`: clean and packaged (a `package/manifest.json`);
      its vetting asserts its own date.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.toml").write_text(f'root = "{root}"\n\n[jerrybase]\nenabled = false\n')
    if held_for_real:
        held, _ = library_show(root, held=True, with_briefing=True,
                               asserted_dates=["1973-06-10", "1974-01-01"],
                               held_flags=("research asserts wrong date: 1974-01-01",))
    else:
        held, _ = library_show(root, held=True, with_briefing=True)
    clean, _ = library_show(root, held=False, date="1973-06-11", with_briefing=True)
    write_artifact(clean.package_dir / "manifest.json",
                   {"schema_version": 3, "source": {"performance_id": "GratefulDead/1973-06-11"},
                    "tracks": []})
    return {HELD: held, CLEAN: clean}
