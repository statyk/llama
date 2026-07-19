# Research-Date Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vet adopts a well-evidenced research date over an archive.org
Jan-1 placeholder date (no hold), and every non-adopted date mismatch
gets one deduplicated, honestly-worded flag.

**Architecture:** `grounding_flags` in `src/llama/stages/vet_research.py`
becomes the single decision point: it returns `(flags, adopted_date)`;
`run_vet_research` applies the adoption to the `Show` it already
rewrites. Performance identity (slug, ledger key) is untouched — only
`Show.date` (presentation) changes, plus audit fields. The pipeline
re-reads show.json after vet (`pipeline.py:86`), so the correction
propagates to synthesize/package with no pipeline changes.
Spec: `docs/superpowers/specs/2026-07-19-date-adoption-design.md`.

**Tech Stack:** Python 3.11+, pydantic v2, pytest (offline). Run tests
with the venv active (`source .venv/bin/activate`).

## Global Constraints

- Adoption requires ALL of: `show.date` ends `-01-01` AND
  `show.date_source == "item"`; exactly ONE distinct normalized full
  research date; every parseable year-less (`--MM-DD`) assertion agrees
  with that date's month/day; same year as `show.date` and different
  from it; unknown-songs gate did NOT fire.
- On adoption: `show.date` ← research date, `item_date` ← old date,
  `date_source` ← `"research"`, NO wrong-date flag, NO hold,
  `VettingResult.adopted_date` set.
- New model fields must default (old artifacts must load):
  `Show.item_date: str | None = None`, `Show.date_source: str = "item"`,
  `VettingResult.adopted_date: str | None = None`.
- All vet flags keep the `research asserts ` prefix (`_VET_FLAG_PREFIX`)
  so re-vet flag scrubbing still works.
- Placeholder-flag wording (non-adopted, placeholder date):
  `research asserts <normalized>; item date <show.date> looks like a year-only placeholder`
- Non-placeholder mismatch wording unchanged
  (`research asserts wrong date: <first surface text>`), deduplicated by
  normalized value.
- Performance identity (performance_id, slug, ledger key) never changes.
- All tests offline (`pytest -q`); current baseline 482 passed, 7 deselected.
- Commit messages: conventional prefix, ending with the
  Co-Authored-By + Claude-Session trailer used in this repo.

---

### Task 1: Model fields + adoption/dedup logic in vet

**Files:**
- Modify: `src/llama/models.py` (Show ~line 148, VettingResult ~line 175)
- Modify: `src/llama/stages/vet_research.py`
- Test: `tests/test_stage_vet.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: existing `normalize_date`, `_known_song`, `_VET_FLAG_PREFIX`
  in `vet_research.py`.
- Produces: `grounding_flags(vetting, show) -> tuple[list[str], str | None]`
  (flags, adopted_date); `Show.item_date`/`Show.date_source`;
  `VettingResult.adopted_date`. Task 2 reads the Show fields for display.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_stage_vet.py` (helpers `setup`, `vet_json`,
`make_show`, `FakeProvider` already exist in the file):

```python
def placeholder_show():
    s = make_show()
    s.performance_id = "CountryJoe/1976-01-01"
    s.date = "1976-01-01"
    return s


def cj_dates():
    return ["1976-02-08", "Sunday, February 8, 1976", "Feb 8, 1976",
            "February, 8th 1976"]


def test_placeholder_date_adopted_from_research(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(asserted_dates=cj_dates())])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.flags == []
    assert result.adopted_date == "1976-02-08"
    s = json.loads(sws.show.read_text())
    assert s["date"] == "1976-02-08"
    assert s["item_date"] == "1976-01-01"
    assert s["date_source"] == "research"
    assert s["needs_review"] is False


def test_adopted_revet_is_idempotent(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(asserted_dates=cj_dates()),
                                   vet_json(asserted_dates=cj_dates())])
    run_vet_research(sws, fake, placeholder_show(), "r")
    corrected = read_model(sws.show, Show)
    sws.vetting.unlink()  # force the re-vet
    result = run_vet_research(sws, fake, corrected, "r")
    assert result.flags == []
    assert result.adopted_date is None  # nothing left to adopt
    s = json.loads(sws.show.read_text())
    assert s["date"] == "1976-02-08" and s["date_source"] == "research"


def test_no_adoption_on_non_placeholder_date_dedups_flags(tmp_path: Path):
    sws, show = setup(tmp_path)  # date 1973-06-10 - not a placeholder
    fake = FakeProvider(completes=[vet_json(
        asserted_dates=["1973-07-27", "July 27, 1973", "Jul 27, 1973"])])
    result = run_vet_research(sws, fake, show, "r")
    assert result.flags == ["research asserts wrong date: 1973-07-27"]
    assert result.adopted_date is None
    assert json.loads(sws.show.read_text())["date"] == "1973-06-10"


def test_no_adoption_on_conflicting_research_dates(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(
        asserted_dates=["1976-02-08", "1976-03-01"])])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date is None
    assert sorted(result.flags) == [
        "research asserts 1976-02-08; item date 1976-01-01 looks like a year-only placeholder",
        "research asserts 1976-03-01; item date 1976-01-01 looks like a year-only placeholder",
    ]
    assert json.loads(sws.show.read_text())["date"] == "1976-01-01"


def test_no_adoption_on_yearless_contradiction(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(
        asserted_dates=["1976-02-08", "December 2"])])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date is None
    assert ("research asserts 1976-02-08; item date 1976-01-01 looks like"
            " a year-only placeholder") in result.flags


def test_no_adoption_across_years(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(asserted_dates=["1977-02-08"])])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date is None
    assert result.flags == [
        "research asserts 1977-02-08; item date 1976-01-01 looks like a year-only placeholder",
    ]


def test_adoption_does_not_swallow_set_count_mismatch(tmp_path: Path):
    # Date adoption resolves the date; an independent structure contradiction
    # must still hold the show.
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(asserted_dates=cj_dates(),
                                            asserted_set_count=4)])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date == "1976-02-08"
    assert result.flags == ["research asserts 4 sets but structure has 2"]
    s = json.loads(sws.show.read_text())
    assert s["date"] == "1976-02-08" and s["needs_review"] is True


def test_no_adoption_when_songs_do_not_ground(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, placeholder_show())
    fake = FakeProvider(completes=[vet_json(
        asserted_songs=["Alien Song A", "Alien Song B", "Alien Song C"],
        asserted_dates=["1976-02-08"])])
    result = run_vet_research(sws, fake, placeholder_show(), "r")
    assert result.adopted_date is None
    assert ("research asserts 1976-02-08; item date 1976-01-01 looks like"
            " a year-only placeholder") in result.flags
    assert any("unknown song" in f for f in result.flags)
    assert json.loads(sws.show.read_text())["date"] == "1976-01-01"
```

Note the imports at the top of the file already include `Show`,
`ShowWorkspace`, `write_artifact`; add `read_model` to the
`llama.workspace` import line.

Append to `tests/test_models.py`:

```python
def test_show_date_fields_default_for_old_artifacts():
    from llama.models import Show, VettingResult, ResearchVetting
    s = Show(performance_id="p", identifier="i", artist="a", date="1976-01-01")
    assert s.item_date is None and s.date_source == "item"
    v = VettingResult(vetting=ResearchVetting())
    assert v.adopted_date is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stage_vet.py tests/test_models.py -q`
Expected: FAIL — `item_date`/`adopted_date` unknown fields /
`AttributeError: adopted_date` / flag-content mismatches

- [ ] **Step 3: Implement the model fields**

`src/llama/models.py` — `Show` gains, after `city`:

```python
    # Presentation date is correctable (vet may adopt a research date over an
    # archive year-only placeholder); performance identity never changes.
    item_date: str | None = None  # original archive date, set only when corrected
    date_source: str = "item"  # "item" | "research"
```

`VettingResult` gains:

```python
    adopted_date: str | None = None  # research date adopted over a placeholder
```

- [ ] **Step 4: Implement the vet logic**

`src/llama/stages/vet_research.py` — replace the date loop inside
`grounding_flags` and change its signature/return. Full new form:

```python
def grounding_flags(vetting: ResearchVetting, show: Show) -> tuple[list[str], str | None]:
    """Deterministic check: research contradicting this show flags for review.
    The gate exists to catch wrong-show research, so a couple of unmatched
    titles (tracklist gaps, odd variants) pass; a mostly-unmatched set, or a
    date that belongs to a different show, blocks. One exception: an archive
    year-only placeholder date (YYYY-01-01) contradicted by unanimous,
    well-grounded research is corrected, not flagged - returns the adopted
    date as the second element. Zero tokens."""
    flags: list[str] = []
    known = [normalize_song(t.title).split() for t in show.tracks]
    unknown = [s for s in vetting.asserted_songs if not _known_song(s, known)]
    songs_grounded = not (len(unknown) >= 2 and len(unknown) * 3 > len(vetting.asserted_songs))
    if not songs_grounded:
        flags += [f"{_VET_FLAG_PREFIX}unknown song: {s}" for s in unknown]

    full: dict[str, str] = {}      # normalized YYYY-MM-DD -> first surface text
    yearless: dict[str, str] = {}  # normalized --MM-DD -> first surface text
    for text in vetting.asserted_dates:
        norm = normalize_date(text)
        if norm is None:
            continue  # can't verify is not a contradiction; kept in vetting.json
        (yearless if norm.startswith("--") else full).setdefault(norm, text)

    mismatched = {n: t for n, t in full.items() if n != show.date}
    placeholder = show.date.endswith("-01-01") and show.date_source == "item"
    adopted: str | None = None
    if placeholder and songs_grounded and len(full) == 1 and len(mismatched) == 1:
        candidate = next(iter(mismatched))
        if candidate[:4] == show.date[:4] and all(
            candidate.endswith(y[1:]) for y in yearless
        ):
            adopted = candidate

    if adopted is None:
        for norm, text in mismatched.items():
            if placeholder:
                flags.append(
                    f"{_VET_FLAG_PREFIX}{norm}; item date {show.date}"
                    " looks like a year-only placeholder"
                )
            else:
                flags.append(f"{_VET_FLAG_PREFIX}wrong date: {text}")
        for norm, text in yearless.items():  # year-less: match on month and day
            if not show.date.endswith(norm[1:]):
                flags.append(f"{_VET_FLAG_PREFIX}wrong date: {text}")

    # Set-count check is independent of the date decision: an adoption must
    # not swallow a genuine structure contradiction.
    if vetting.asserted_set_count is not None and show.tracks:
        actual = len({t.set for t in show.tracks if t.set != "encore"})
        if vetting.asserted_set_count != actual:
            flags.append(
                f"{_VET_FLAG_PREFIX}{vetting.asserted_set_count} sets"
                f" but structure has {actual}"
            )
    return flags, adopted
```

(The unknown-songs block moves above the date logic because adoption
needs `songs_grounded`; the set-count block moves to the end unchanged.
Behavior of songs/set-count flags is identical to before.)

In `run_vet_research`, replace:

```python
    flags = grounding_flags(vetting, show)
```

with:

```python
    flags, adopted = grounding_flags(vetting, show)
```

and after `current = read_model(show_ws.show, Show)` add:

```python
    if adopted:
        current.item_date = current.date
        current.date = adopted
        current.date_source = "research"
```

and change the result construction to:

```python
    result = VettingResult(vetting=vetting, flags=flags, adopted_date=adopted)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_stage_vet.py tests/test_models.py -q`
Expected: PASS (all new tests plus the existing vet battery — the
existing single-date wrong-date tests still pass because dedup of one
date is that date, and wording for non-placeholder shows is unchanged)

- [ ] **Step 6: Run the full offline suite**

Run: `pytest -q`
Expected: 490+ passed, 7 deselected, no regressions

- [ ] **Step 7: Commit**

```bash
git add src/llama/models.py src/llama/stages/vet_research.py \
  tests/test_stage_vet.py tests/test_models.py
git commit -m "feat: adopt research date over archive year-only placeholder in vet"
```

---

### Task 2: Surface the correction in `llama show`

**Files:**
- Modify: `src/llama/cli.py` (~line 423, the show header line)
- Test: `tests/test_cli_commands.py`

**Interfaces:**
- Consumes: `Show.item_date` / `Show.date_source` (Task 1).
- Produces: display only; no new interfaces.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_commands.py` (mirrors the file's existing
`_flagged_show` / `test_show_prints_flags` pattern at lines ~194-214;
`ShowWorkspace`, `write_artifact`, `Show`, `runner`, `cli` are already
imported at the top of the file):

```python
def test_show_displays_corrected_date(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = ShowWorkspace(tmp_path / "shows" / "countryjoe-1976-01-01")
    write_artifact(sws.show, Show(
        performance_id="CountryJoe/1976-01-01", identifier="cjm76",
        artist="Country Joe McDonald", date="1976-02-08",
        item_date="1976-01-01", date_source="research", venue="WDR studio",
    ))
    result = runner.invoke(cli.app, ["show", str(sws.dir), "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "1976-02-08 (item date 1976-01-01, corrected via research)" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_commands.py -q -k corrected_date`
Expected: FAIL — header shows the bare date

- [ ] **Step 3: Implement**

In `src/llama/cli.py`, replace:

```python
    typer.echo(f"{s.artist}  {s.date}  {place}".rstrip())
```

with:

```python
    date_str = s.date
    if s.date_source == "research" and s.item_date:
        date_str = f"{s.date} (item date {s.item_date}, corrected via research)"
    typer.echo(f"{s.artist}  {date_str}  {place}".rstrip())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_commands.py -q`
Expected: PASS

- [ ] **Step 5: Run the full offline suite and commit**

Run: `pytest -q`
Expected: all passing, no regressions

```bash
git add src/llama/cli.py tests/test_cli_commands.py
git commit -m "feat: show corrected dates with provenance in llama show"
```
