# Broadcast-ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a derived "broadcast-ready" property to shows (packaged + all audio on disk + DJ script + DJ audio + broadcast.m3u + not held) and surface it as a tag/filter on `status`, `show`, `deliver`, and `redo`.

**Architecture:** Broadcast-ready is derived on demand, never stored — mirroring the existing `voiced`/`state` derivations in `src/llama/catalog.py`. A single `broadcast_readiness(ws)` helper returns `(ready, reasons)`; `CatalogEntry` gains a `broadcast_ready` bool populated in `iter_shows`; `select_shows` gains a `broadcast_ready` filter. The four CLI commands thread one new keyword through their existing selector idioms.

**Tech Stack:** Python 3, Typer CLI, Pydantic models, pytest (offline, `fake` LLM backend). `typer.testing.CliRunner` for CLI tests.

## Global Constraints

- No new dependencies.
- No schema change, no persisted state, no migration — broadcast-ready stays derived.
- Positive-only filter: `--broadcast-ready` selects ready shows on every surface; there is deliberately **no** `--not-broadcast-ready`.
- Held shows (`show.needs_review is True`) are never broadcast-ready, regardless of files present.
- Strict on-disk audio check: verify every `manifest.tracks[].filename` exists under `package/audio/`, not merely that the show reached the `packaged` state.
- Offline, deterministic tests only. Match existing test idioms (`tests/test_catalog.py` builders, `tests/test_cli_commands.py` CliRunner usage).
- Spec: `docs/superpowers/specs/2026-07-26-broadcast-ready-design.md`.

---

### Task 1: Core predicate + catalog wiring

**Files:**
- Modify: `src/llama/catalog.py` (add `broadcast_readiness`; add `CatalogEntry.broadcast_ready`; populate it in `iter_shows`; add `broadcast_ready` param to `select_shows`)
- Create: `tests/test_broadcast_ready.py` (shared fixture + core tests)

**Interfaces:**
- Produces:
  - `broadcast_readiness(ws: ShowWorkspace) -> tuple[bool, list[str]]` — `ready` is true iff `reasons` is empty.
  - `CatalogEntry.broadcast_ready: bool` (default `False`).
  - `select_shows(entries, *, states=None, voiced=None, artist=None, run=None, broadcast_ready: bool = False)` — when `broadcast_ready` is true, keep only entries whose `broadcast_ready is True`.
- Consumes (existing, already imported in `catalog.py`): `read_json`, `read_model`, `ShowWorkspace` from `llama.workspace`; `Show` from `llama.models`.

**Reason strings (exact):** `"not packaged"`, `"held for review"`, `"no DJ script"`, `"no DJ audio (unvoiced)"`, `"no broadcast.m3u"`, `"{n} of {m} audio files missing"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_broadcast_ready.py`. It reuses the `build`/`make_show` helpers from `tests/test_catalog.py` for non-ready cases and defines a `build_ready` helper for the fully-airable case.

```python
import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.catalog import (CatalogEntry, broadcast_readiness, iter_shows,
                           select_shows)
from llama.ledger import Ledger
from llama.models import Show, Track
from llama.workspace import ShowWorkspace, write_artifact

runner = CliRunner()


def build_ready(root: Path, slug: str = "gratefuldead-1973-06-10", *,
                needs_review: bool = False, voiced: bool = True,
                broadcast_m3u: bool = True, drop_audio: bool = False,
                script: bool = True) -> ShowWorkspace:
    """A fully broadcast-ready show, with knobs to break one condition at a time."""
    ws = ShowWorkspace(root / "shows" / slug)
    write_artifact(ws.show, Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10",
        tracks=[Track(index=1, set="1", title="Morning Dew", filename="a.mp3",
                      title_source="tags")],
        needs_review=needs_review,
        review_flags=["held for a reason"] if needs_review else []))
    if script:
        write_artifact(ws.dj_notes_json, {"set_intros": {"1": "a"}, "outro": "o"})
    manifest = {"schema_version": 2,
                "tracks": [{"index": 1, "set": "1", "title": "Morning Dew",
                            "filename": "01 - Morning Dew.mp3"}]}
    if voiced:
        manifest["dj_audio"] = {"set_intros": {"1": "dj-audio/set1-intro.mp3"},
                                "outro": "dj-audio/99-outro.mp3"}
    write_artifact(ws.package_dir / "manifest.json", manifest)
    if not drop_audio:
        write_artifact(ws.package_dir / "audio" / "01 - Morning Dew.mp3", "x")
    if broadcast_m3u:
        write_artifact(ws.package_dir / "broadcast.m3u", "#EXTM3U\n")
    return ws


def test_fully_ready_show(tmp_path: Path):
    ws = build_ready(tmp_path)
    assert broadcast_readiness(ws) == (True, [])


def test_not_packaged(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "shows" / "bare")
    write_artifact(ws.selection, {})            # a show dir with no manifest
    assert broadcast_readiness(ws) == (False, ["not packaged"])


def test_each_condition_breaks_readiness(tmp_path: Path):
    cases = [
        ("held", dict(needs_review=True), "held for review"),
        ("noscript", dict(script=False), "no DJ script"),
        ("unvoiced", dict(voiced=False), "no DJ audio (unvoiced)"),
        ("nom3u", dict(broadcast_m3u=False), "no broadcast.m3u"),
        ("noaudio", dict(drop_audio=True), "1 of 1 audio files missing"),
    ]
    for slug, kw, reason in cases:
        ws = build_ready(tmp_path / slug, "gratefuldead-1973-06-10", **kw)
        ready, reasons = broadcast_readiness(ws)
        assert ready is False, slug
        assert reasons == [reason], (slug, reasons)


def test_iter_shows_populates_broadcast_ready(tmp_path: Path):
    build_ready(tmp_path, "ready-show")
    build_ready(tmp_path, "silent-show", voiced=False)   # unvoiced -> not ready
    entries = {e.slug: e for e in iter_shows(tmp_path, Ledger(tmp_path / "l.jsonl"))}
    assert entries["ready-show"].broadcast_ready is True
    assert entries["silent-show"].broadcast_ready is False


def test_select_shows_broadcast_ready_filter():
    def e(slug, ready):
        return CatalogEntry(slug=slug, ws=ShowWorkspace(Path("/x")),
                            state="packaged", broadcast_ready=ready)
    es = [e("a", True), e("b", False)]
    assert {x.slug for x in select_shows(es, broadcast_ready=True)} == {"a"}
    assert {x.slug for x in select_shows(es)} == {"a", "b"}   # default: no filter
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_broadcast_ready.py -q`
Expected: FAIL — `ImportError: cannot import name 'broadcast_readiness'` (and `CatalogEntry` has no `broadcast_ready`).

- [ ] **Step 3: Add `broadcast_readiness` and the `broadcast_ready` field**

In `src/llama/catalog.py`, add the `broadcast_ready` field to `CatalogEntry` (after the `voiced` field, around line 36):

```python
    voiced: bool | None = None
    broadcast_ready: bool = False
    overrides: Overrides = field(default_factory=Overrides)
```

Add the helper immediately after `derive_voiced` (after line 85):

```python
def broadcast_readiness(ws: ShowWorkspace) -> tuple[bool, list[str]]:
    """(ready, reasons). A show is broadcast-ready iff it is packaged with
    every manifest track's audio file on disk, has a DJ script, has DJ audio,
    has a broadcast.m3u, and is not held for review. `reasons` names each
    failed condition (empty when ready); it is recomputed on demand for the
    single-show detail view. Never raises."""
    manifest_path = ws.package_dir / "manifest.json"
    if not manifest_path.exists():
        return False, ["not packaged"]
    manifest = read_json(manifest_path)
    reasons: list[str] = []
    if ws.show.exists() and read_model(ws.show, Show).needs_review:
        reasons.append("held for review")
    if not ws.dj_notes_json.exists():
        reasons.append("no DJ script")
    if manifest.get("dj_audio") is None:
        reasons.append("no DJ audio (unvoiced)")
    if not (ws.package_dir / "broadcast.m3u").exists():
        reasons.append("no broadcast.m3u")
    tracks = manifest.get("tracks", [])
    missing = [t for t in tracks
               if not (ws.package_dir / "audio" / t["filename"]).exists()]
    if missing:
        reasons.append(f"{len(missing)} of {len(tracks)} audio files missing")
    return (not reasons), reasons
```

- [ ] **Step 4: Populate the field in `iter_shows` and add the `select_shows` filter**

In `iter_shows` (around line 104), add `broadcast_ready` to the `CatalogEntry(...)` construction:

```python
        entries.append(CatalogEntry(slug=d.name, ws=ws, state=state, flags=flags,
                                    provenance=prov, artist=artist, date=date,
                                    voiced=derive_voiced(ws),
                                    broadcast_ready=broadcast_readiness(ws)[0],
                                    overrides=read_overrides(ws)))
```

In `select_shows` (line 111), add the parameter and filter:

```python
def select_shows(entries: list[CatalogEntry], *, states: set[str] | None = None,
                 voiced: bool | None = None, artist: str | None = None,
                 run: str | None = None,
                 broadcast_ready: bool = False) -> list[CatalogEntry]:
    out = list(entries)
    if states:
        out = [e for e in out if e.state in states]
    if voiced is not None:
        out = [e for e in out if e.voiced is voiced]
    if artist:
        out = [e for e in out if artist.lower() in e.artist.lower()]
    if run:
        out = [e for e in out if e.provenance and e.provenance.run == run]
    if broadcast_ready:
        out = [e for e in out if e.broadcast_ready]
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_broadcast_ready.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `pytest -q`
Expected: PASS (existing count + 5).

- [ ] **Step 7: Commit**

```bash
git add src/llama/catalog.py tests/test_broadcast_ready.py
git commit -m "feat: derive broadcast-ready property in catalog

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GwvWaJJL6ZMK9Jpo2pLfE4"
```

---

### Task 2: `llama status` surface (mark, filter, JSON)

**Files:**
- Modify: `src/llama/cli.py` (the `status` command, around lines 1044-1108)
- Test: `tests/test_broadcast_ready.py` (append)

**Interfaces:**
- Consumes: `select_shows(..., broadcast_ready=...)` and `CatalogEntry.broadcast_ready` from Task 1.
- Produces: `--broadcast-ready` flag on `status`; a `"broadcast-ready"` entry in the per-show `marks` list; a `broadcast_ready` key in each `--json` object.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_broadcast_ready.py`:

```python
def _cfg(tmp_path: Path) -> str:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return str(tmp_path / "config.toml")


def test_status_marks_broadcast_ready(tmp_path: Path):
    build_ready(tmp_path, "gratefuldead-1973-06-10")
    r = runner.invoke(cli.app, ["status", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "broadcast-ready" in r.output


def test_status_broadcast_ready_filter_excludes_unready(tmp_path: Path):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)   # unvoiced -> not ready
    r = runner.invoke(cli.app, ["status", "--broadcast-ready", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "ready-1973-06-10" in r.output
    assert "silent-1973-06-11" not in r.output


def test_status_json_includes_broadcast_ready(tmp_path: Path):
    build_ready(tmp_path, "gratefuldead-1973-06-10")
    r = runner.invoke(cli.app, ["status", "--json", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    obj = next(o for o in json.loads(r.output) if o["slug"] == "gratefuldead-1973-06-10")
    assert obj["broadcast_ready"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_broadcast_ready.py -k status -q`
Expected: FAIL — `--broadcast-ready` is not a known option; `broadcast_ready` key absent; mark absent.

- [ ] **Step 3: Add the flag, filter, mark, and JSON key**

In `src/llama/cli.py` `status` signature (after the `state` option, ~line 1050), add:

```python
    broadcast_ready: bool = typer.Option(False, "--broadcast-ready",
                                         help="Only broadcast-ready shows"),
```

Update the `select_shows` call and `filtering` flag (~lines 1071-1074):

```python
    voiced_filter = True if voiced else (False if unvoiced else None)
    entries = select_shows(entries, states=states or None, voiced=voiced_filter,
                           artist=artist, run=run, broadcast_ready=broadcast_ready)
    filtering = bool(states or voiced_filter is not None or run or artist
                     or broadcast_ready)
```

Add the JSON key (in the `--json` dict, ~line 1091, next to `"voiced": e.voiced,`):

```python
            "voiced": e.voiced,
            "broadcast_ready": e.broadcast_ready,
```

Add the mark (in the `marks` block, ~line 1101, before the `voiced` mark so the airable tag leads):

```python
        marks = []
        if e.broadcast_ready:
            marks.append("broadcast-ready")
        if e.voiced:
            marks.append("voiced")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_broadcast_ready.py -k status -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llama/cli.py tests/test_broadcast_ready.py
git commit -m "feat: broadcast-ready mark, filter, and JSON on llama status

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GwvWaJJL6ZMK9Jpo2pLfE4"
```

---

### Task 3: `llama show` surface (list filter + detail line)

**Files:**
- Modify: `src/llama/cli.py` (`_print_show_entry` ~lines 628-683; the `show` command list form ~lines 719-729 and its signature ~lines 699-705)
- Test: `tests/test_broadcast_ready.py` (append)

**Interfaces:**
- Consumes: `broadcast_readiness` and `select_shows(..., broadcast_ready=...)` from Task 1.
- Produces: `--broadcast-ready` list-form selector on `show`; a `broadcast-ready: yes|no` line (with reasons on `no`) in the single-show detail view.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_broadcast_ready.py`:

```python
def test_show_detail_ready_line(tmp_path: Path):
    build_ready(tmp_path, "gratefuldead-1973-06-10")
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "broadcast-ready: yes" in r.output


def test_show_detail_not_ready_lists_reasons(tmp_path: Path):
    build_ready(tmp_path, "silent-1973-06-11", voiced=False, broadcast_m3u=False)
    r = runner.invoke(cli.app, ["show", "silent", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "broadcast-ready: no" in r.output
    assert "no DJ audio (unvoiced)" in r.output
    assert "no broadcast.m3u" in r.output


def test_show_list_broadcast_ready_selector(tmp_path: Path):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)
    r = runner.invoke(cli.app, ["show", "--broadcast-ready", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "ready-1973-06-10" in r.output
    assert "silent-1973-06-11" not in r.output
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_broadcast_ready.py -k show -q`
Expected: FAIL — no `broadcast-ready:` line; `--broadcast-ready` unknown to `show`.

- [ ] **Step 3: Add the detail line to `_print_show_entry`**

In `src/llama/cli.py`, at the top of `_print_show_entry` add the import next to the existing local import, or use a module-level one. Insert the readiness line **after** the needs-review block and **before** the `if show_tracks:` block (after line 680):

```python
    from llama.catalog import broadcast_readiness
    ready, reasons = broadcast_readiness(sws)
    if ready:
        typer.echo("broadcast-ready: yes")
    else:
        typer.echo("broadcast-ready: no")
        for r in reasons:
            typer.echo(f"  - {r}")
    if show_tracks:
        for line in _format_tracks(s):
            typer.echo(line)
```

(Note: `sws = entry.ws` is already bound at the top of `_print_show_entry`; `s` is the loaded `Show`.)

- [ ] **Step 4: Add the list-form selector to the `show` command**

In the `show` signature, next to the other set-form options (~line 703), add:

```python
    broadcast_ready: bool = typer.Option(False, "--broadcast-ready",
                                         help="Set form: only broadcast-ready shows"),
```

In the list-form block (`name is None`), update the default-held guard and the `select_shows` call (~lines 725-729):

```python
        if not states and not (voiced or unvoiced or artist or run or broadcast_ready):
            states = {"held"}   # set form defaults to held
        vf = True if voiced else (False if unvoiced else None)
        entries = select_shows(iter_shows(config.root, ledger),
                               states=states or None, voiced=vf, artist=artist,
                               run=run, broadcast_ready=broadcast_ready)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_broadcast_ready.py -k show -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/llama/cli.py tests/test_broadcast_ready.py
git commit -m "feat: broadcast-ready line and selector on llama show

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GwvWaJJL6ZMK9Jpo2pLfE4"
```

---

### Task 4: `llama deliver` and `llama redo` selectors

**Files:**
- Modify: `src/llama/cli.py` (`_batch_select` ~lines 825-836; `_has_selector` ~lines 839-840; `deliver` command ~lines 885-911; `redo` command ~lines 991-1016)
- Test: `tests/test_broadcast_ready.py` (append)

**Interfaces:**
- Consumes: `select_shows(..., broadcast_ready=...)` from Task 1.
- Produces: `--broadcast-ready` selector on `deliver` and `redo`, both routed through the shared `_batch_select` / `_has_selector`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_broadcast_ready.py`. Each test monkeypatches the side-effecting per-show function so no files are copied and no pipeline runs; we assert only the *selected* set.

```python
def test_batch_select_broadcast_ready_filters(tmp_path: Path):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)
    _cfg(tmp_path)   # writes config.toml; _setup needs a Path, not the str
    config, _, ledger = cli._setup(tmp_path / "config.toml")
    entries = cli._batch_select(config, ledger, broadcast_ready=True)
    assert {e.slug for e in entries} == {"ready-1973-06-10"}


def test_deliver_broadcast_ready_selector(tmp_path: Path, monkeypatch):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)
    picked = []
    monkeypatch.setattr(cli, "_deliver_one",
                        lambda config, ledger, e, dest, force: picked.append(e.slug))
    r = runner.invoke(cli.app, ["deliver", "--broadcast-ready", "--yes",
                                "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert picked == ["ready-1973-06-10"]


def test_redo_broadcast_ready_selector(tmp_path: Path, monkeypatch):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "silent-1973-06-11", voiced=False)
    picked = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda config, ia, ledger, e, stage: picked.append(e.slug))
    r = runner.invoke(cli.app, ["redo", "--from", "package", "--broadcast-ready",
                                "--yes", "--config", _cfg(tmp_path)])
    assert r.exit_code == 0, r.output
    assert picked == ["ready-1973-06-10"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_broadcast_ready.py -k "batch_select or deliver or redo" -q`
Expected: FAIL — `_batch_select` has no `broadcast_ready` kwarg; `--broadcast-ready` unknown to `deliver`/`redo`.

- [ ] **Step 3: Thread `broadcast_ready` through `_batch_select` and `_has_selector`**

In `src/llama/cli.py`, update `_batch_select` (lines 825-836):

```python
def _batch_select(config, ledger, *, held=False, packaged=False, voiced=False,
                  unvoiced=False, state=None, artist=None, run=None,
                  broadcast_ready=False):
    from llama.catalog import iter_shows, select_shows
    states = {s for s, on in [("held", held), ("packaged", packaged)] if on}
    if state:
        states.add(state)
    vf = True if voiced else (False if unvoiced else None)
    entries = select_shows(iter_shows(config.root, ledger),
                           states=states or None, voiced=vf, artist=artist,
                           run=run, broadcast_ready=broadcast_ready)
    if not held:                         # never act on held shows implicitly
        entries = [e for e in entries if e.state != "held"]
    return entries
```

Update `_has_selector` (lines 839-840):

```python
def _has_selector(held, packaged, voiced, unvoiced, state, artist, run,
                  broadcast_ready) -> bool:
    return any([held, packaged, voiced, unvoiced, state, artist, run,
                broadcast_ready])
```

- [ ] **Step 4: Add the flag and wire it in `deliver`**

In the `deliver` signature (after the `run` option, ~line 896), add:

```python
    broadcast_ready: bool = typer.Option(False, "--broadcast-ready",
                                         help="Selector: broadcast-ready shows"),
```

Update the two `_has_selector(...)` calls and the `_batch_select(...)` call in `deliver` (lines 901, 905, 909-911) to pass `broadcast_ready`:

```python
    if name is not None and _has_selector(held, packaged, voiced, unvoiced, state,
                                          artist, run, broadcast_ready):
        typer.echo("give a show OR selectors, not both", err=True)
        raise typer.Exit(1)
    if name is None:
        if not _has_selector(held, packaged, voiced, unvoiced, state, artist, run,
                             broadcast_ready):
            typer.echo("give a show or a selector (e.g. --packaged)", err=True)
            raise typer.Exit(1)
        config, _, ledger = _setup(config_path)
        entries = _batch_select(config, ledger, held=held, packaged=packaged,
                                voiced=voiced, unvoiced=unvoiced, state=state,
                                artist=artist, run=run,
                                broadcast_ready=broadcast_ready)
```

- [ ] **Step 5: Add the flag and wire it in `redo`**

In the `redo` signature (after the `run` option, ~line 997), add the identical option:

```python
    broadcast_ready: bool = typer.Option(False, "--broadcast-ready",
                                         help="Selector: broadcast-ready shows"),
```

Update the two `_has_selector(...)` calls and the `_batch_select(...)` call in `redo` (lines 1006, 1010, 1014-1016) to pass `broadcast_ready` (same edits as Step 4).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_broadcast_ready.py -k "batch_select or deliver or redo" -q`
Expected: PASS (3 tests).

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/llama/cli.py tests/test_broadcast_ready.py
git commit -m "feat: broadcast-ready selector on llama deliver and redo

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GwvWaJJL6ZMK9Jpo2pLfE4"
```

---

## Docs (fold into the final task's commit or a trailing task)

- [ ] Update `CLAUDE.md` "Commands" list and the `llama show`/`status` descriptions to mention the `--broadcast-ready` selector and the broadcast-ready tag. Update `README.md`/`docs/` where `status`/`show`/`deliver`/`redo` selectors are documented, matching the existing style. Keep it to the surfaces added here; no new concepts beyond the spec.

---

## Self-review notes

- **Spec coverage:** predicate (Task 1); status mark/filter/JSON (Task 2); show detail line + reasons + list filter (Task 3); deliver + redo selectors (Task 4); held-excluded, strict audio check, positive-only filter all enforced in Task 1's helper and tests. Docs task covers the doc surfaces.
- **Reason strings** are defined once (Task 1) and asserted verbatim in tests; later tasks reference them through the helper, never re-implement.
- **Type consistency:** `broadcast_readiness(ws) -> (bool, list[str])`, `CatalogEntry.broadcast_ready: bool`, and `select_shows(..., broadcast_ready=False)` names/signatures are identical everywhere they appear.
