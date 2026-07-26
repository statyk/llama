# Operate without hand-editing ~/.llama — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every remaining case where an operator must hand-edit a file under `~/.llama/`: view a show's tracks and exclude by number, override show metadata (venue/city/date/titles/set-breaks) via `overrides.json`, create/inspect presenters, and re-pin a profile's artist roster — all from the CLI.

**Architecture:** Extend the existing durable `overrides.json` (consumed by gather) with metadata fields; add view/edit flags to `llama show`; add a `presenter` sub-app wrapping the existing `save_presenter`; add `profile artists`. `show.json` stays derived; `overrides.json` is the authored input.

**Tech Stack:** Python 3, Typer 0.26 (bundled rich), Pydantic v2, pytest with the `fake` LLM backend, offline.

## Global Constraints

- No new third-party dependencies. No migration: every new `overrides.json` field is additive/optional; absent file behaves exactly as today.
- `overrides.json` is authored input; `show.json` stays derived (gather rewrites it). Overrides are consumed by gather, so metadata edits route to `llama redo <s> --from gather`.
- Out-of-range track numbers in `titles`/`set_breaks` are a loud gather-time `LlamaError`; a no-match `exclude` filename stays a tolerant warning (existing behavior).
- Metadata/exclude edits do NOT clear the hold directly — a clean re-gather self-clears the resolved flag (same model as `--exclude` today).
- `config.toml` is out of scope (ordinary config). `--set-breaks` is numbered-sets-only (no encore) in v1.
- Match house style: `typer.echo`, `log.warning` (logger `"llama"`), `write_artifact`, `read_model`/`read_overrides`, `LlamaError` for loud CLI-boundary failures.
- Tests offline/deterministic (`fake` backend + gd73 fixture).

---

### Task 1: Extend the `Overrides` model

**Files:**
- Modify: `src/llama/models.py` (the `Overrides` class, ~line 188)
- Test: `tests/test_workspace.py`

**Interfaces:**
- Produces: `Overrides(exclude: list[str]=[], narration: str="full", venue: str|None=None, city: str|None=None, date: str|None=None, titles: dict[int,str]={}, set_breaks: list[int]|None=None)`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_workspace.py`:

```python
def test_overrides_metadata_fields_round_trip(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(
        venue="X Hall", city="Austin, TX", date="2003-04-19",
        titles={4: "Bertha"}, set_breaks=[9, 17]))
    ov = read_overrides(ws)
    assert ov.venue == "X Hall" and ov.city == "Austin, TX" and ov.date == "2003-04-19"
    assert ov.titles == {4: "Bertha"}          # str JSON key coerced back to int
    assert ov.set_breaks == [9, 17]


def test_overrides_absent_metadata_defaults(tmp_path):
    ov = read_overrides(ShowWorkspace(tmp_path / "s"))
    assert ov.venue is None and ov.city is None and ov.date is None
    assert ov.titles == {} and ov.set_breaks is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workspace.py -k overrides_metadata -q`
Expected: FAIL — `Overrides` has no `venue`/`titles`/etc.

- [ ] **Step 3: Extend the model**

In `src/llama/models.py`, replace the `Overrides` body:

```python
class Overrides(BaseModel):
    """Hand-authored per-show operator input, durable across re-derivation.
    Read by gather (exclude, venue, city, date, titles, set_breaks) and
    synthesize (narration); never auto-written by a stage. Absent file == this
    default."""
    exclude: list[str] = Field(default_factory=list)   # source filenames to drop
    narration: str = "full"                            # "full" | "vague"
    venue: str | None = None
    city: str | None = None
    date: str | None = None                            # YYYY-MM-DD
    titles: dict[int, str] = Field(default_factory=dict)   # track number -> forced title
    set_breaks: list[int] | None = None                # track numbers a break falls after
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workspace.py -k overrides -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/models.py tests/test_workspace.py
git commit -m "feat: extend Overrides with venue/city/date/titles/set_breaks"
```

---

### Task 2: gather applies title / venue / city / date overrides

**Files:**
- Modify: `src/llama/stages/gather.py`
- Test: `tests/test_stage_gather.py`, `tests/test_stage_vet.py`

**Interfaces:**
- Consumes: `read_overrides` (already called in gather for `exclude`); reuse that `overrides` local.
- Behavior: `titles` force a track's title (`title_source="override"`) and clear the unresolved-titles flag when all gaps fill; `venue`/`city` win uncontested (drop venue-mismatch flag, `venue_source="override"`); `date` sets `date_source="override"`, `item_date=<original>`; out-of-range title number → `LlamaError`. `vet` already skips date-adoption unless `date_source=="item"` (no vet change — verified by test).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_stage_gather.py`:

```python
def test_gather_title_override_fills_and_clears_flag(tmp_path: Path):
    base = ShowWorkspace(tmp_path / "b")
    show0 = run_gather(base, StubIA(), FakeProvider(), make_candidate(), IDENT)
    # find an index and force a bogus title; assert it wins with source=override
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(titles={1: "Custom Opener"}))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert show.tracks[0].title == "Custom Opener"
    assert show.tracks[0].title_source == "override"


def test_gather_title_override_out_of_range_errors(tmp_path: Path):
    from llama.errors import LlamaError
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(titles={999: "Nope"}))
    with pytest.raises(LlamaError):
        run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)


def test_gather_venue_city_date_overrides(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(venue="My Hall", city="Nowhere, ZZ",
                                           date="1973-06-11"))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert show.venue == "My Hall" and show.venue_source == "override"
    assert show.city == "Nowhere, ZZ"
    assert show.date == "1973-06-11" and show.date_source == "override"
    assert show.item_date == "1973-06-10"   # original preserved
```

Add `import pytest` and `from llama.models import Overrides` / `from llama.workspace import write_artifact` if not already imported.

Add to `tests/test_stage_vet.py` a guard test:

```python
def test_vet_does_not_adopt_over_manual_date(tmp_path):
    # A show whose date was manually overridden must not be re-dated by vet's
    # placeholder-adoption, even if it looked like a placeholder.
    from llama.models import Show, Track
    from llama.stages.vet_research import run_vet_research
    from llama.llm.fake import FakeProvider
    from llama.workspace import ShowWorkspace, read_model
    ws = ShowWorkspace(tmp_path / "s")
    show = Show(performance_id="X/2003-01-01", identifier="x", artist="X",
                date="2003-01-01", date_source="override", item_date="2003-01-01",
                tracks=[Track(index=1, set="1", title="A", filename="a.mp3",
                              title_source="tags")])
    run_vet_research(ws, FakeProvider(), show, "research text", force=True)
    # vet writes vetting.json; show.date_source stays override (vet only adopts
    # when date_source == "item")
    assert show.date_source == "override"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_gather.py -k "title_override or venue_city_date" -q`
Expected: FAIL — overrides not applied.

- [ ] **Step 3: Add the LlamaError import to gather**

In `src/llama/stages/gather.py` top imports add:

```python
from llama.errors import LlamaError
```

- [ ] **Step 4: Apply title overrides after resolve_titles**

Immediately after `tracks = resolve_titles(kept, canonical, sibling_titles=siblings)` (~line 149) insert:

```python
    for n, forced in overrides.titles.items():
        if not (1 <= n <= len(tracks)):
            raise LlamaError(f"overrides.titles: no track {n} "
                             f"(show has {len(tracks)} tracks)")
        tracks[n - 1] = tracks[n - 1].model_copy(
            update={"title": forced, "title_source": "override"})
```

(`overrides` is the local already read for `exclude`. `resolve_titles` returns
a list of `Track`; reassigning an element is fine.)

- [ ] **Step 5: Apply venue/city overrides (drop mismatch flag)**

After the existing venue/city/venue_source computation block (the
`venue, city, venue_source = candidate.venue, ...` block, ~lines 225-233),
append:

```python
    if overrides.venue is not None:
        venue, venue_source = overrides.venue, "override"
        flags = [f for f in flags if not f.startswith("venue mismatch")]
    if overrides.city is not None:
        city = overrides.city
```

- [ ] **Step 6: Apply date override at Show construction**

Just before `show = Show(` (~line 263), compute date fields, and change the
`date=`/add `date_source=`/`item_date=` kwargs:

```python
    date, date_source, item_date = candidate.date, "item", None
    if overrides.date is not None:
        date, date_source, item_date = overrides.date, "override", candidate.date
```

Then in the `Show(...)` call set `date=date,` and add `date_source=date_source,
item_date=item_date,` (Show already has these fields defaulting to
`"item"`/`None`).

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_stage_gather.py tests/test_stage_vet.py -q`
Expected: PASS (new + existing).

- [ ] **Step 8: Commit**

```bash
git add src/llama/stages/gather.py tests/test_stage_gather.py tests/test_stage_vet.py
git commit -m "feat: gather applies title/venue/city/date overrides"
```

---

### Task 3: gather applies set_breaks override (numbered sets)

**Files:**
- Modify: `src/llama/stages/gather.py`
- Test: `tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `overrides.set_breaks`. When set, bypass the deterministic/LLM alignment: build numbered set labels from the break points, set `breaks`, `StructureInfo.source="override"`/`alignment="override"`, coverage `1.0`; out-of-range break → `LlamaError`.
- Produces: module helper `_sets_from_breaks(n_tracks: int, breaks: list[int]) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_stage_gather.py`:

```python
def test_gather_set_breaks_override_numbers_sets(tmp_path: Path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(set_breaks=[2, 4]))
    show = run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    # 6-track fixture -> sets: 1,1 | 2,2 | 3,3
    assert [t.set for t in show.tracks] == ["1", "1", "2", "2", "3", "3"]
    assert show.set_breaks == [2, 4]
    assert show.structure is not None and show.structure.alignment == "override"
    assert "low-confidence structure alignment" not in show.review_flags


def test_gather_set_breaks_out_of_range_errors(tmp_path: Path):
    from llama.errors import LlamaError
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(set_breaks=[99]))
    with pytest.raises(LlamaError):
        run_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_gather.py -k set_breaks -q`
Expected: FAIL.

- [ ] **Step 3: Add the helper**

In `src/llama/stages/gather.py` (module level, near the top after imports):

```python
def _sets_from_breaks(n_tracks: int, breaks: list[int]) -> list[str]:
    """Numbered set labels ("1","2",...) for each 1-based track, given the
    track numbers a break falls *after*. Break after track b closes a set."""
    bset = set(breaks)
    labels, cur = [], 1
    for i in range(1, n_tracks + 1):
        labels.append(str(cur))
        if i in bset:
            cur += 1
    return labels
```

- [ ] **Step 4: Bypass alignment when set_breaks is overridden**

Wrap the existing alignment region. The current code (~lines 164-194) computes
`result`, applies `result.sets`/`result.segues` to `tracks`, and sets
`breaks = set_breaks(tracks)`. Restructure to:

```python
    if overrides.set_breaks is not None:
        bad = [n for n in overrides.set_breaks if not (1 <= n < len(tracks))]
        if bad:
            raise LlamaError(f"overrides.set_breaks: track number(s) out of range "
                             f"{bad} (show has {len(tracks)} tracks)")
        labels = _sets_from_breaks(len(tracks), overrides.set_breaks)
        tracks = [t.model_copy(update={"set": s}) for t, s in zip(tracks, labels)]
        breaks = sorted(overrides.set_breaks)
        alignment = "override"
        coverage, conflicts = 1.0, []
    else:
        # ---- existing alignment block, unchanged ----
        result = align(tracks, canonical)
        alignment = "deterministic"
        # ... (the current lines 165-190, the coverage/anchor/LLM/flag logic) ...
        tracks = [t.model_copy(update={"set": s, "segue": g})
                  for t, s, g in zip(tracks, result.sets, result.segues)]
        breaks = set_breaks(tracks)
        coverage, conflicts = result.coverage, result.conflicts
```

Then update the `StructureInfo` construction (~line 256) to use `coverage`/
`conflicts` locals instead of `result.coverage`/`result.conflicts`, and treat
the override as a real source:

```python
    structure_info = None
    if overrides.set_breaks is not None:
        structure_info = StructureInfo(source="override", alignment="override",
                                       coverage=1.0, conflicts=[])
    elif best is not None or notes:
        source = best.source if best is not None else "none"
        structure_info = StructureInfo(source=source, alignment=alignment,
                                       coverage=coverage, conflicts=conflicts + notes)
```

(Keep `flags`, `structure_guard`, closer-tripwire, and multi-event handling as
they are — they run against the override `breaks`/`tracks` and no longer see an
alignment flag because the else-branch that appends
`"low-confidence structure alignment"` didn't run.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_stage_gather.py -q`
Expected: PASS (all gather tests, incl. the untouched alignment paths).

- [ ] **Step 6: Commit**

```bash
git add src/llama/stages/gather.py tests/test_stage_gather.py
git commit -m "feat: gather set_breaks override bypasses alignment (numbered sets)"
```

---

### Task 4: track formatter + `llama show --tracks`

**Files:**
- Modify: `src/llama/cli.py`
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Produces: `_format_tracks(show) -> list[str]` (shared by `--tracks` and the picker); `_fmt_dur(sec: float|None) -> str` (`"M:SS"` or `"?"`).
- `show` gains `--tracks` (bool); prints the listing during single-show inspection when `show.json` exists.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli_commands.py`:

```python
def test_show_tracks_lists_numbered_tracks(tmp_path: Path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--tracks", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert "tracks:" in r.output
    assert "1." in r.output and "Morning Dew" in r.output and "a.mp3" in r.output
```

(`test_catalog.build`'s `make_show` writes one track "Morning Dew"/`a.mp3`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_commands.py -k show_tracks -q`
Expected: FAIL — no `--tracks` option.

- [ ] **Step 3: Add the formatters**

In `src/llama/cli.py` (near `_print_show_entry`):

```python
def _fmt_dur(sec) -> str:
    if not sec:
        return "?"
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"


def _format_tracks(show) -> list[str]:
    lines = ["tracks:"]
    for t in show.tracks:
        title = t.title if t.title_source != "unresolved" else "(unknown)"
        lines.append(f"  {t.index:2d}. set {t.set:4.4s} {title:28.28s} "
                     f"{t.title_source:10.10s} {t.filename:24.24s} {_fmt_dur(t.duration_sec):>5s}")
    return lines
```

- [ ] **Step 4: Add `--tracks` to `show` and print during inspection**

Add the option to the `show` signature:

```python
    tracks: bool = typer.Option(False, "--tracks", help="List the show's tracks (numbered)"),
```

In `_print_show_entry`, after the needs-review block, the caller decides
whether to print tracks — pass a flag. Simplest: give `_print_show_entry(entry,
show_tracks: bool = False)` and, when true and `show.json` exists, append
`_format_tracks(read_model(sws.show, Show))`. Update the single-show
inspection call site to `_print_show_entry(entry, show_tracks=tracks)`.

```python
def _print_show_entry(entry, show_tracks: bool = False) -> None:
    ...
    # (after the needs-review block, before returning)
    if show_tracks:
        for line in _format_tracks(read_model(sws.show, Show)):
            typer.echo(line)
```

- [ ] **Step 5: Refactor `_pick_excludes` to use the shared formatter**

```python
def _pick_excludes(show) -> list[str]:
    for line in _format_tracks(show):
        typer.echo(line)
    picks = _parse_ranks(typer.prompt("exclude which track numbers? (comma-separated, empty = none)",
                                      default="", show_default=False))
    return [t.filename for t in show.tracks if t.index in picks]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -k "show_tracks or show" -q`
Expected: PASS (new + existing show tests).

- [ ] **Step 7: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: llama show --tracks + shared track formatter"
```

---

### Task 5: `--exclude` / `--include` accept track numbers

**Files:**
- Modify: `src/llama/cli.py`
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Produces: `_resolve_exclude_tokens(show_ws, tokens: list[str]) -> list[str]` — expands comma groups, maps all-digit tokens to that track's filename via `show.json` (error out of range / no show.json), passes filenames through.
- `show`'s `--exclude`/`--include` handling runs values through it before `_edit_overrides`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_commands.py`:

```python
def test_show_exclude_by_number_resolves_to_filename(tmp_path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"},
               needs_review=True)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--exclude", "1",
                                "--config", cfg])
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).exclude == ["a.mp3"]   # track 1's filename


def test_show_exclude_out_of_range_errors(tmp_path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"}, needs_review=True)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--exclude", "99", "--config", cfg])
    assert r.exit_code != 0
    assert "track 99" in r.output or "out of range" in r.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_commands.py -k "exclude_by_number or exclude_out_of_range" -q`
Expected: FAIL — `--exclude 1` stored verbatim as `"1"`.

- [ ] **Step 3: Add the resolver**

In `src/llama/cli.py`:

```python
def _resolve_exclude_tokens(show_ws, tokens) -> list[str]:
    """Expand comma groups and map all-digit tokens to that track's filename
    (via show.json). Non-numeric tokens pass through as filenames."""
    parts = [p.strip() for tok in tokens for p in str(tok).split(",") if p.strip()]
    if not any(p.isdigit() for p in parts):
        return parts
    if not show_ws.show.exists():
        raise LlamaError("--exclude by number needs show.json; reference the file by name")
    tracks = read_model(show_ws.show, Show).tracks
    by_index = {t.index: t.filename for t in tracks}
    out = []
    for p in parts:
        if p.isdigit():
            n = int(p)
            if n not in by_index:
                raise LlamaError(f"--exclude: no track {n} (show has {len(tracks)} tracks)")
            out.append(by_index[n])
        else:
            out.append(p)
    return out
```

- [ ] **Step 4: Use it in `show`**

Where the `show` command handles excludes (the `did_exclude` branch), replace
the raw lists with resolved ones:

```python
    if did_exclude:
        add = _resolve_exclude_tokens(sws, exclude or [])
        rm = _resolve_exclude_tokens(sws, include or [])
        ov = _edit_overrides(sws, add_exclude=add, rm_exclude=rm)
        typer.echo(f"{entry.slug}: overrides.exclude = {ov.exclude} "
                   "(the hold clears itself if a clean re-gather results)")
```

(Update `did_exclude = bool(exclude or include)` stays as-is.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -k "exclude" -q`
Expected: PASS (number, comma, filename-passthrough, out-of-range, existing).

- [ ] **Step 6: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: show --exclude/--include accept track numbers"
```

---

### Task 6: `show` metadata override flags

**Files:**
- Modify: `src/llama/cli.py`
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: extended `Overrides` (Task 1).
- Extends `_edit_overrides(show_ws, *, add_exclude=(), rm_exclude=(), narration=None, venue=None, city=None, date=None, set_titles=None, clear_titles=(), set_breaks=<sentinel>, clear_set_breaks=False) -> Overrides`.
- `show` gains `--set-venue`, `--set-city`, `--set-date`, `--title N=TITLE` (repeatable), `--clear-title N` (repeatable), `--set-breaks "9,17"`, `--clear-set-breaks`; all route to `redo --from gather`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_commands.py`:

```python
def test_show_set_venue_and_title_write_overrides_route_gather(tmp_path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"},
               needs_review=True)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--set-venue", "My Hall",
                                "--title", "1=Bertha", "--config", cfg])
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.venue == "My Hall" and ov.titles == {1: "Bertha"}
    assert "--from gather" in r.output


def test_show_set_breaks_and_clear(tmp_path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    runner.invoke(cli.app, ["show", "gratefuldead", "--set-breaks", "2,4", "--config", cfg])
    assert read_overrides(ws).set_breaks == [2, 4]
    runner.invoke(cli.app, ["show", "gratefuldead", "--clear-set-breaks", "--config", cfg])
    assert read_overrides(ws).set_breaks is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_commands.py -k "set_venue or set_breaks_and_clear" -q`
Expected: FAIL — unknown options.

- [ ] **Step 3: Extend `_edit_overrides`**

```python
_UNSET = object()

def _edit_overrides(show_ws, *, add_exclude=(), rm_exclude=(), narration=None,
                    venue=_UNSET, city=_UNSET, date=_UNSET, set_titles=None,
                    clear_titles=(), set_breaks=_UNSET, clear_set_breaks=False):
    from llama.workspace import read_overrides
    ov = read_overrides(show_ws)
    exclude = [f for f in ov.exclude if f not in set(rm_exclude)]
    for f in add_exclude:
        if f not in exclude:
            exclude.append(f)
    titles = dict(ov.titles)
    for n in clear_titles:
        titles.pop(int(n), None)
    for n, t in (set_titles or {}).items():
        titles[int(n)] = t
    data = ov.model_copy(update={
        "exclude": exclude,
        "narration": narration or ov.narration,
        "titles": titles,
    })
    if venue is not _UNSET:
        data = data.model_copy(update={"venue": venue})
    if city is not _UNSET:
        data = data.model_copy(update={"city": city})
    if date is not _UNSET:
        data = data.model_copy(update={"date": date})
    if clear_set_breaks:
        data = data.model_copy(update={"set_breaks": None})
    elif set_breaks is not _UNSET:
        data = data.model_copy(update={"set_breaks": set_breaks})
    write_artifact(show_ws.overrides, data)
    return data
```

(Existing callers pass only `add_exclude`/`rm_exclude`/`narration` and keep
working because the new params default to `_UNSET`/empty.)

- [ ] **Step 4: Add the flags + handling to `show`**

Add options:

```python
    set_venue: str = typer.Option(None, "--set-venue"),
    set_city: str = typer.Option(None, "--set-city"),
    set_date: str = typer.Option(None, "--set-date"),
    title: list[str] = typer.Option(None, "--title", help='Force a track title: --title N="Song"'),
    clear_title: list[str] = typer.Option(None, "--clear-title", help="Drop a title override by track number"),
    set_breaks: str = typer.Option(None, "--set-breaks", help='Set breaks by track number: "9,17"'),
    clear_set_breaks: bool = typer.Option(False, "--clear-set-breaks"),
```

Compute a `did_meta` flag and fold it into the resolution logic. Where the
action branch begins, extend:

```python
    parsed_titles = {}
    for spec in (title or []):
        if "=" not in spec:
            typer.echo(f"--title expects N=TITLE, got {spec!r}", err=True)
            raise typer.Exit(1)
        n, t = spec.split("=", 1)
        parsed_titles[int(n)] = t
    breaks_val = None
    if set_breaks:
        breaks_val = [int(x) for x in set_breaks.split(",") if x.strip()]

    did_meta = bool(set_venue or set_city or set_date or parsed_titles
                    or clear_title or set_breaks or clear_set_breaks)
    did_exclude = bool(exclude or include)
    did_narration = vague or full
    # ... pure-inspection early return unchanged (add did_meta to the guard) ...
```

Update the pure-inspection guard to include `did_meta`:
`if not (did_exclude or did_narration or clear or did_meta):`

In the action section, after the exclude/vague/full/clear handling, add:

```python
    if did_meta:
        _edit_overrides(sws,
            venue=set_venue if set_venue is not None else _UNSET,
            city=set_city if set_city is not None else _UNSET,
            date=set_date if set_date is not None else _UNSET,
            set_titles=parsed_titles or None,
            clear_titles=[int(n) for n in (clear_title or [])],
            set_breaks=breaks_val if set_breaks else _UNSET,
            clear_set_breaks=clear_set_breaks)
        typer.echo(f"{entry.slug}: metadata override updated")
```

And include metadata in the stage precedence (metadata ⇒ gather):

```python
    stage = "gather" if (did_exclude or did_meta) else ("synthesize" if did_narration else "package")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -k "show" -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: show --set-venue/--set-city/--set-date/--title/--set-breaks overrides"
```

---

### Task 7: `llama presenter` sub-app

**Files:**
- Modify: `src/llama/cli.py`
- Modify: `src/llama/presenters.py` (add a `list_presenters` helper)
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `Presenter`, `save_presenter`, `load_presenter`, `PresenterError` (`src/llama/presenters.py`).
- Produces: `list_presenters(root) -> list[tuple[str, Presenter|str]]` (id → Presenter, or an error string); `presenter` Typer sub-app with `add`/`list`/`show`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli_commands.py`:

```python
def test_presenter_add_and_show(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["presenter", "add", "casey", "--name", "Casey",
                                "--sex", "male", "--voice", "american-dj",
                                "--character", "Warm FM veteran.", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "presenters" / "casey.toml").exists()
    shown = runner.invoke(cli.app, ["presenter", "show", "casey", "--config", cfg])
    assert "Casey" in shown.output and "Warm FM veteran." in shown.output
    listed = runner.invoke(cli.app, ["presenter", "list", "--config", cfg])
    assert "casey" in listed.output


def test_presenter_add_refuses_overwrite_without_force(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    args = ["presenter", "add", "casey", "--name", "Casey", "--sex", "male",
            "--voice", "american-dj", "--character", "x", "--config", cfg]
    assert runner.invoke(cli.app, args).exit_code == 0
    again = runner.invoke(cli.app, args)
    assert again.exit_code != 0 and "exists" in again.output


def test_presenter_add_character_file_and_voice_xor(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    cf = tmp_path / "c.txt"; cf.write_text("Deep tape collector.\nDry humor.")
    r = runner.invoke(cli.app, ["presenter", "add", "deej", "--name", "DJ",
                                "--sex", "female", "--voice-clone", "/ref.wav",
                                "--character-file", str(cf), "--config", cfg])
    assert r.exit_code == 0, r.output
    # voice + voice-clone together must fail (model validator)
    bad = runner.invoke(cli.app, ["presenter", "add", "x", "--name", "X", "--sex",
                                  "male", "--voice", "a", "--voice-clone", "/r.wav",
                                  "--character", "y", "--config", cfg])
    assert bad.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_commands.py -k presenter -q`
Expected: FAIL — no `presenter` command.

- [ ] **Step 3: Add `list_presenters`**

In `src/llama/presenters.py`:

```python
def list_presenters(root: Path):
    """(id, Presenter | error-string) for each presenters/*.toml, sorted by id."""
    d = root / "presenters"
    out = []
    for p in sorted(d.glob("*.toml")) if d.is_dir() else []:
        try:
            out.append((p.stem, load_presenter(root, p.stem)))
        except PresenterError as exc:
            out.append((p.stem, str(exc)))
    return out
```

- [ ] **Step 4: Add the `presenter` sub-app**

In `src/llama/cli.py`, near the other sub-apps:

```python
presenter_app = typer.Typer(help="On-air hosts (presenters/<id>.toml)",
                            pretty_exceptions_enable=False)
app.add_typer(presenter_app, name="presenter", rich_help_panel="Discover & process")
```

Commands:

```python
@presenter_app.command("add")
def presenter_add(
    id: str = typer.Argument(...),
    name: str = typer.Option(..., "--name"),
    sex: str = typer.Option(..., "--sex"),
    voice: str = typer.Option(None, "--voice"),
    voice_clone: str = typer.Option(None, "--voice-clone"),
    character: str = typer.Option(None, "--character"),
    character_file: Path = typer.Option(None, "--character-file"),
    bed: str = typer.Option(None, "--bed"),
    force: bool = typer.Option(False, "--force"),
    config_path: Path = typer.Option(None, "--config"),
):
    """Create a presenter (on-air host)."""
    from llama.presenters import Presenter, save_presenter
    config, _, _ = _setup(config_path)
    if bool(character) == bool(character_file):
        typer.echo("give exactly one of --character / --character-file", err=True)
        raise typer.Exit(1)
    text = character if character else character_file.read_text().strip()
    dest = config.root / "presenters" / f"{id}.toml"
    if dest.exists() and not force:
        typer.echo(f"presenter {id!r} exists: {dest} (use --force to overwrite)", err=True)
        raise typer.Exit(1)
    try:
        p = Presenter(id=id, name=name, sex=sex, voice=voice,
                      voice_clone=voice_clone, character=text, bed=bed)
    except Exception as exc:
        typer.echo(f"invalid presenter: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"saved: {save_presenter(config.root, p)}")


@presenter_app.command("list")
def presenter_list(config_path: Path = typer.Option(None, "--config")):
    """List presenters."""
    from llama.presenters import list_presenters
    config, _, _ = _setup(config_path)
    rows = list_presenters(config.root)
    if not rows:
        typer.echo("no presenters")
        return
    for pid, p in rows:
        if isinstance(p, str):
            typer.echo(f"{pid:16.16s} (invalid: {p})")
        else:
            v = p.voice or f"clone:{p.voice_clone}"
            typer.echo(f"{pid:16.16s} {p.name:20.20s} {p.sex:8.8s} {v}")


@presenter_app.command("show")
def presenter_show(id: str = typer.Argument(...),
                   config_path: Path = typer.Option(None, "--config")):
    """Show one presenter's fields."""
    from llama.presenters import load_presenter
    config, _, _ = _setup(config_path)
    p = load_presenter(config.root, id)     # PresenterError -> main_cli boundary
    v = p.voice or f"clone:{p.voice_clone}"
    typer.echo(f"{p.name}  ({p.sex})  voice={v}" + (f"  bed={p.bed}" if p.bed else ""))
    typer.echo("character:")
    typer.echo(p.character)
```

(The `Exception` catch on construction is to convert the pydantic
ValidationError from the voice-XOR-clone validator into a clean exit.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -k presenter -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llama/cli.py src/llama/presenters.py tests/test_cli_commands.py
git commit -m "feat: llama presenter add/list/show"
```

---

### Task 8: `llama profile artists`

**Files:**
- Modify: `src/llama/cli.py`
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `load_profile`/`save_profile`, `resolve_artists`, `load_or_build`, `Criteria.artists`.
- Produces: `profile_app` command `artists`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli_commands.py`. Create a profile with the same
`interpret`-stub pattern as `test_profile_add_and_list`, then monkeypatch the
artist-resolution seam (`cli.resolve_artists`/`cli.load_or_build`, imported at
module scope in cli.py) so it's offline:

```python
def test_profile_artists_set_show_and_clear(tmp_path, monkeypatch):
    from llama.llm.fake import FakeProvider
    from llama.profiles import load_profile
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({
        "query": "q", "collection": "GratefulDead", "artist": "Grateful Dead",
        "date_from": None, "date_to": None, "setlist_constraints": [],
        "soft_preferences": None, "min_avg_rating": 4.0, "min_reviews": 3, "count": 1,
    })
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    assert runner.invoke(cli.app, ["profile", "add", "myprof", "q", "--config", cfg]).exit_code == 0

    # offline artist resolution: echo names as identifiers
    monkeypatch.setattr(cli, "load_or_build", lambda ia, cache: [])
    monkeypatch.setattr(cli, "resolve_artists",
                        lambda index, names: [{"identifier": n, "title": n} for n in names])

    r = runner.invoke(cli.app, ["profile", "artists", "myprof",
                                "--set", "Galactic, Lettuce", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert load_profile(tmp_path, "myprof").criteria.artists == ["Galactic", "Lettuce"]

    shown = runner.invoke(cli.app, ["profile", "artists", "myprof", "--config", cfg])
    assert "Galactic" in shown.output

    runner.invoke(cli.app, ["profile", "artists", "myprof", "--set", "", "--config", cfg])
    assert load_profile(tmp_path, "myprof").criteria.artists == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_commands.py -k profile_artists -q`
Expected: FAIL — no `artists` subcommand.

- [ ] **Step 3: Add the command**

```python
@profile_app.command("artists")
def profile_artists(
    name: str = typer.Argument(...),
    set_: str = typer.Option(None, "--set", help='Re-pin the roster (comma names); "" clears it'),
    config_path: Path = typer.Option(None, "--config"),
):
    """Show or re-pin a profile's pinned artist roster."""
    config, ia, _ = _setup(config_path)
    profile = load_profile(config.root, name)
    if set_ is None:
        roster = profile.criteria.artists
        typer.echo(", ".join(roster) if roster else "no pinned roster (uses the LLM matcher)")
        return
    names = [n.strip() for n in set_.split(",") if n.strip()]
    if not names:
        criteria = profile.criteria.model_copy(update={"artists": []})
        save_profile(config.root, profile.model_copy(update={"criteria": criteria}))
        typer.echo("cleared pinned roster (reverts to the LLM matcher)")
        return
    index = load_or_build(ia, config.root / "cache")
    resolved = resolve_artists(index, names)
    criteria = profile.criteria.model_copy(update={"artists": [a["identifier"] for a in resolved]})
    save_profile(config.root, profile.model_copy(update={"criteria": criteria}))
    typer.echo("pinned: " + ", ".join(f"{a['title']} ({a['identifier']})" for a in resolved))
```

(Imports `load_profile`, `save_profile`, `resolve_artists`, `load_or_build`
already exist at module scope in cli.py.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli_commands.py -k profile_artists -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: llama profile artists (view / re-pin roster)"
```

---

### Task 9: Documentation

**Files:**
- Modify: `README.md`, `docs/workflow.md`, `CLAUDE.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: workflow.md**

- Add the new `overrides.json` fields (venue/city/date/titles/set_breaks) to its callout and the on-disk tree note.
- In the `llama show` command reference: document `--tracks`, `--exclude/--include` by number, and the metadata flags (`--set-venue/--set-city/--set-date/--title N=…/--clear-title/--set-breaks/--clear-set-breaks`), all routing to `redo --from gather`, holds self-clearing.
- Add a `llama presenter` reference entry (add/list/show) and a `llama profile artists` entry.
- Add recipes: "junk announcement tracks" now `llama show <s> --tracks` then `--exclude 9,10 --apply`; "wrong venue/date/title/set breaks" via the metadata flags; "create a host without editing TOML" via `presenter add`; "re-pin a profile roster" via `profile artists --set`.

- [ ] **Step 2: README.md**

- In "## Use", add `llama show <s> --tracks`, exclude-by-number, the metadata override flags, `llama presenter add/list/show`, and `llama profile artists`.
- Where presenters are described (the Presenters section), note they can be created with `llama presenter add` (TOML editing still works).

- [ ] **Step 3: CLAUDE.md**

- Update the overrides bullet to list the metadata fields it now carries, and note `llama presenter`/`llama profile artists` exist so hosts and pinned rosters are app-managed. State the design line: `config.toml` remains the only file expected to be hand-edited.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/workflow.md CLAUDE.md
git commit -m "docs: track view, metadata overrides, presenter & profile-artists commands"
```

---

## Final verification

- [ ] `pytest -q` — all pass.
- [ ] `llama --help` shows the `presenter` group under "Discover & process"; `llama show --help` lists the new flags.

## Self-review notes (author)

- **Spec coverage:** Part A → Tasks 4, 5; Part B → Tasks 1, 2, 3, 6 (+ vet needs no change — its `date_source=="item"` guard already preserves an override, covered by a Task 2 test); Part C → Task 7; Part D → Task 8; docs → Task 9.
- **Deviation:** spec framed a vet change; implementation confirms vet already guards on `date_source=="item"`, so Part B's cross-stage requirement is met with only a gather change + a preservation test (documented in Task 2).
- **Type consistency:** `Overrides(...venue,city,date,titles:dict[int,str],set_breaks:list[int]|None)`, `_edit_overrides(...venue,city,date,set_titles,clear_titles,set_breaks,clear_set_breaks)` with `_UNSET` sentinel, `_resolve_exclude_tokens`, `_format_tracks`/`_fmt_dur`, `_sets_from_breaks`, `list_presenters` are used consistently across tasks.
