# Taper's Section allowlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let llama find, select and package recordings from archive.org's Taper's Section (`collection:taperssection`) for an operator-curated allowlist of artists, without changing behaviour for any existing LMA artist.

**Architecture:** A new `llama/taperssection.py` holds the allowlist model, the synthetic artist key and exact creator matching. Pure helper modules hold lineage classification, the date cross-check, the age-adjusted download measure and title venue parsing. An `Allowlist` object built from config is threaded explicitly, as a keyword argument defaulting to empty, into the artist index, interpret, search, winnow, select, gather and replay. With an empty allowlist every one of those paths takes today's branch.

**Tech Stack:** Python 3, pydantic v2, pytest (offline, fake LLM backend), archive.org scrape/metadata APIs via `IAClient`.

**Spec:** `docs/superpowers/specs/2026-11-09-taperssection-allowlist-design.md`. Read it before any task. Every task's requirements include the spec section it names.

## Global Constraints

- **Guarded surface (spec "Stakes"):**
  - With an empty allowlist, LMA behaviour and every LLM prompt's rendered text are identical to today.
  - With a populated allowlist, each LMA artist's search query, grouping, winnow scorer prompt and payload for an LMA batch, and recording selection are unchanged.
  - New artifact keys may be null-valued, and that is noise, not a regression.
- **Workspace and tests:**
  - Work in the worktree `/Users/shawn/projects/llama/.claude/worktrees/taperssection` with its OWN venv. Run tests as `./.venv/bin/python -m pytest -q` from the worktree root (root `CLAUDE.md`).
  - Check `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree.
  - The suite stays offline and deterministic. Live archive.org calls belong only in `scripts/` probes or `pytest -m live` tests.
- **Imports:** `emcee`, `transmitter` and `llama` never import each other.
- **Constants:**
  - Synthetic key prefix: `ts-`. A key is `ts-` + `slugify(name)`, e.g. `ts-phish`, `ts-jerry-garcia`; performance id `ts-phish/1997-11-22`, show slug `ts-phish-1997-11-22`.
  - No-evidence age: 75 days (`NO_EVIDENCE_AGE_DAYS = 75`).
  - Lineage classes are `aud`, `sbd`, `matrix`, `fm`, `webcast`, `unknown`. An entry's `lineages` may name any of the first five.
- **Config:** `config.toml` key `[[taperssection.artists]]`. The model is strict (`_StrictModel`, unknown key is an error). The build never writes `~/.llama/config.toml`.
- **File names:** no file whose name starts REPORT/SUMMARY/FINDINGS/ANALYSIS (subagent write guard). Evidence goes in `docs/superpowers/2026-11-09-taperssection-evidence/`.

## Review Focus

1. **A creator string that differs from an entry's spelling only by case, a leading "The" or punctuation** ("phish", "The Allman Brothers Band"). Expected: it matches. Pinned in Task 1 (`test_norm_creator_folds_case_the_punct`).
2. **An LMA query or pinned roster naming an LMA collection that merely contains an allowlisted name** (`JazzIsPhish`, `DeadPhishOrchestra`). Expected: today's etree path, untouched. Pinned in Tasks 3 and 6.
3. **A taperssection candidate whose every recording is filtered**: forbidden lineage, `exclude`, active bounds, date cross-check. Expected: dropped in search, with no shortlist slot and no `ValueError` anywhere. Pinned in Tasks 5 and 9.
4. **An allowlist edit between runs**: entry renamed, entry removed, `jerrybase` added. Expected:
   - a pinned old key fails with `LlamaError` naming it;
   - the index rebuilds the taperssection part on the next run;
   - the replay fingerprint changes.

   Pinned in Tasks 1, 4 and 10.
5. **A show whose only evidence-bearing recordings are under 75 days old.** Expected: the scorer gets no percentile and a below-floor baseline, and it never ships because of a zero download count. Pinned in Tasks 7 and 8.

---

## Checkpoints

- **Checkpoint A** follows Task 2. The operator rules lineage rule (a) or (b) from coverage, precision and date-drop numbers. Tasks 3+ may proceed, but Task 2b implements the ruling before Task 5 merges.
- **Checkpoint B** follows Task 8. The ~20-show Phish scorer measurement (live LLM, operator approves the spend) is reviewed before Task 12's acceptance.

---

### Task 0: Premise probes and fixtures (no product code)

**Files:**
- Create: `scripts/taperssection_probe.py` (read-only; subcommands below)
- Create: `docs/superpowers/2026-11-09-taperssection-evidence/premises.md`
- Create (fixtures): `packages/llama/tests/fixtures/` entries for one Phish and one Garcia item, via `python scripts/capture_fixture.py <identifier>`

**Interfaces:**
- Produces: fixture identifiers recorded in `premises.md`, used by Tasks 2, 5, 9 and 12.

- [ ] **Step 1:** Read `scripts/CLAUDE.md` and `scripts/capture_fixture.py`. Pick one Phish item with a `Source:` description line (e.g. a `ph2017-07-30...flac2496` item) and one Garcia JGB item dated before 1995-08-09. Capture both.
- [ ] **Step 2:** Write `taperssection_probe.py fields`. One `IAClient.scrape('collection:taperssection AND creator:"Phish"', ["identifier","creator","addeddate","source","lineage","downloads","date","title","description"], count=100)` call, then report the fraction of docs carrying each field. Record whether `lineage` is served at all. If it is not, Tasks 2 and 5 read it only from item metadata at select time, and `premises.md` says so.
- [ ] **Step 3:** Record in `premises.md`. For each item, give the answer and the command that produced it.
  - (a) Does setlist.fm list a 1976 JGB date under "Jerry Garcia" or "Jerry Garcia Band"? One search for each name.
  - (b) What does emcee's `[assign.artists]` matcher (`packages/emcee/src/emcee/artists.py`) do with "Phish" and "Jerry Garcia" against the operator's emcee config? Read-only.
  - (c) Run `filter_files` and `FORMAT_BY_AUDIO` on both fixtures: which audio files are kept, and which format wins?
  - (d) Run `setlist.parse_setlist` on the Phish fixture's description: are `<div>`/`<p>` handled?
  - (e) On the Garcia scrape: how many dates have a JGB jerrybase row while the title or description names another act (Legion of Mary, acoustic, Garcia/Grisman)? These could raise false jerrybase holds.
  - (f) Run the `date_disagrees` comparison (Task 2) per survey artist after Task 2 lands, and record the rates.
  - (g) Run `parse_title_venue` (Task 7) over 100 sampled Phish titles after Task 7 lands, and record wrong parses (precision).
- [ ] **Step 4:** Commit: `git add scripts/taperssection_probe.py docs/superpowers/2026-11-09-taperssection-evidence packages/llama/tests/fixtures && git commit -m "taperssection: premise probes and fixtures"`

---

### Task 1: Allowlist model, synthetic key, exact matching

**Files:**
- Create: `packages/llama/src/llama/taperssection.py`
- Modify: `packages/llama/src/llama/config.py` (add `taperssection: TaperssectionConfig` to `Config`; add a commented example to the `config init` template)
- Test: `packages/llama/tests/test_taperssection.py`

**Interfaces:**
- Produces:
  - `KEY_PREFIX = "ts-"`
  - `class TaperssectionArtist(_StrictModel)`, with fields:
    - `name: str`
    - `creators: list[str]` (min 1)
    - `lineages: list[Literal["aud","sbd","matrix","fm","webcast"]]` (min 1)
    - `exclude: list[str] = []`
    - `note: str = ""`
    - `jerrybase: str | None = None`
    - `active_from: str | None = None` (YYYY-MM-DD)
    - `active_until: str | None = None`
    - `setlistfm: str | None = None` (only if Task 0's step 3a showed setlist.fm needs a different name; otherwise omit the field)
  - `class TaperssectionConfig(_StrictModel): artists: list[TaperssectionArtist] = []`
  - `norm_creator(s: str) -> str`: lowercase, strip a leading "the ", collapse non-alphanumerics to single spaces, strip.
  - `artist_key(name: str) -> str`: returns `KEY_PREFIX + slugify(name)`.
  - `class Allowlist`:
    - `Allowlist.from_config(cfg: TaperssectionConfig) -> Allowlist`
    - `Allowlist.empty() -> Allowlist`
    - `.entries: list[TaperssectionArtist]`
    - `__bool__` (true when non-empty)
    - `.key(entry) -> str`
    - `.by_key(key: str) -> TaperssectionArtist | None`
    - `.require(key: str) -> TaperssectionArtist`: raises `LlamaError(f"unknown taperssection artist key {key!r}; is it still in [[taperssection.artists]]?")` when `key.startswith(KEY_PREFIX)` and no entry matches.
    - `.match_creator(creator: str | list | None, entry) -> bool`: exact `norm_creator` equality against the entry's creators.
    - `.resolve_name(name: str | None) -> TaperssectionArtist | None`: exact `norm_creator` match on `name` or any creator; also accepts a CamelCase collection guess (compare `norm_creator` of the guess against each spelling with spaces removed).
    - `.matching_names(entry) -> list[str]`: name plus creators.
    - `.fingerprint() -> str | None`: `None` when empty, else sha256 of the canonical JSON of entries.
  - `is_synthetic(key: str) -> bool`

- [ ] **Step 1: Write failing tests**

```python
def test_norm_creator_folds_case_the_punct():
    assert norm_creator("The Allman Brothers Band") == norm_creator("allman brothers band")
    assert norm_creator("Gov't Mule") == "gov t mule"

def test_key_is_prefixed_slug():
    assert artist_key("Jerry Garcia") == "ts-jerry-garcia"

def test_match_creator_is_exact_not_substring():
    al = Allowlist.from_config(TaperssectionConfig(artists=[TaperssectionArtist(name="Pearl Jam", creators=["Pearl Jam"], lineages=["aud"])]))
    e = al.entries[0]
    assert al.match_creator("pearl jam", e)
    assert not al.match_creator("Vitalogy: Pearl Jam Tribute", e)
    assert not al.match_creator("Even Flow (The Ultimate Pearl Jam Tribute Band)", e)

def test_resolve_name_exact_and_camelcase():
    al = ...  # Phish entry
    assert al.resolve_name("Phish") is not None
    assert al.resolve_name("Phish").name == "Phish"
    assert al.resolve_name("JazzIsPhish") is None
    assert al.resolve_name("Jazz Is Phish") is None

def test_require_unknown_prefixed_key_raises():
    with pytest.raises(LlamaError, match="ts-old-name"):
        Allowlist.empty().require("ts-old-name")

def test_unknown_key_in_config_is_error():
    with pytest.raises(ValidationError):
        TaperssectionArtist(name="X", creators=["X"], lineages=["aud"], bogus=1)

def test_empty_fingerprint_is_none():
    assert Allowlist.empty().fingerprint() is None
```

- [ ] **Step 2:** Run `./.venv/bin/python -m pytest packages/llama/tests/test_taperssection.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement the interfaces above. Add `taperssection: TaperssectionConfig = Field(default_factory=TaperssectionConfig)` to `Config`.
- [ ] **Step 4:** Run the new tests plus `packages/llama/tests/test_config.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): allowlist model, synthetic key, exact creator matching`

---

### Task 2: Lineage classifier, exclude matching, date cross-check (pure)

**Files:**
- Create: `packages/llama/src/llama/ts_rules.py`
- Test: `packages/llama/tests/test_ts_rules.py`

**Interfaces:**
- Consumes: `TaperssectionArtist` (Task 1)
- Produces:
  - `source_lines(description: str | None) -> list[str]`: lines (after HTML `<br>`/`<p>`/`<div>` → newline and tag strip) whose stripped text starts, case-insensitively, with `source`, `src`, `lineage` or `transfer`.
  - `classify(rec: RecordingSummary) -> Literal["aud","sbd","matrix","fm","webcast","unknown"]`: reads `rec.identifier`, `rec.title`, `rec.source`, `rec.lineage`, `source_lines(rec.description)`. The rule is spec "Lineage classification" verbatim:
    - a marker beats gear;
    - "aud matrix"/"audience matrix" with no other marker reads `aud`;
    - a mic model or position word reads `aud`;
    - deck gear never reads `aud`.
  - `MIC_WORDS: frozenset[str]`, `POSITION_WORDS: frozenset[str]`, `DECK_WORDS: frozenset[str]`: lexicons with a comment giving their rationale.
  - `excluded(rec: RecordingSummary, entry) -> bool`: case-insensitive term match over identifier, title, `source` and source lines only.
  - `dates_claimed(identifier: str, title: str) -> set[str]`: ISO dates parsed from `YYYY-MM-DD`, `YYYY.MM.DD`, `YYMMDD`-after-artist-prefix (`ph1997...`, `phish1997-...`) and `M-D-YYYY` forms.
  - `date_disagrees(rec) -> bool`: true when `dates_claimed` is non-empty and does not contain `rec.date`.
  - `in_active_window(date: str, entry) -> bool`
  - `allowed(rec, entry, *, rule: Literal["a","b"]) -> Literal["allowed","forbidden","unknown"]`:
    - class in `entry.lineages` → allowed;
    - known class not in it → forbidden;
    - `unknown` → `"unknown"` under rule a; under rule b, `"allowed"` if `"aud" in entry.lineages`, else `"unknown"`.
  - `RULE: Literal["a","b"]`: module constant, set after Checkpoint A (start with `"a"`).
- Also modify `packages/llama/src/llama/models.py` `RecordingSummary`: add `creator: str | None = None`, `addeddate: str | None = None`, `source: str | None = None`, `lineage: str | None = None`.

- [ ] **Step 1: Write failing tests.** The spec's nine acceptance cases are table-driven. Each case builds a `RecordingSummary(identifier="x", description=<case text>)` and asserts `classify(...)`:

```python
CASES = [
    ("Source: Schoeps CMC6/MK4 > 744T", "aud"),
    ("Source: SBD > DAT", "sbd"),
    ("Source: FM->DAT->CD", "fm"),
    ("Location: OTS (right of SBD)\nSource: DPA 4061 > R-09", "aud"),
    ("Source: AKG 480 AUD Matrix", "aud"),
    ("Source: SBD/AUD matrix (Schoeps)", "matrix"),
    ("This show was webcast live\nSource: Neumann AK43 > LC3", "aud"),
    ("Transfer: DAT (patch master)", "sbd"),
    ("Source: DAT master", "unknown"),
]
```

  Plus:
  - `test_exclude_ignores_prose`: description "available as a download from LivePhish" with `exclude=["livephish"]` → `excluded` is False. The same term in the title → True.
  - `test_date_disagrees`:
    - `2024-08-30-phish-fob`, date `2024-08-01` → True;
    - a matching date → False;
    - no parseable date → False;
    - `Phish2027-07-27`, date `2025-07-27` → True.
  - `test_allowed_rules` covers rules a and b for an `["aud"]` entry and for an all-classes entry.
  - `test_lma_lineage_class_unchanged`: `scoring.lineage_class` returns today's values for three LMA-style identifiers (`gd77-05-08.sbd.hicks...`, an `.aud.` one, an unknown one).
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. `scoring.lineage_class` is not touched.
- [ ] **Step 4:** Run `test_ts_rules.py test_scoring.py test_models.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): lineage rule, anchored exclude, date cross-check`

---

### Checkpoint A: lineage coverage and precision (operator rules)

- [ ] **Step 1:** Add `taperssection_probe.py lineage`. It scrapes every `creator:"Phish"` taperssection item (exact-creator filtered) and builds `RecordingSummary` with the new fields. It writes to `docs/superpowers/2026-11-09-taperssection-evidence/lineage.md`:
  - (i) per date, the classes under today's `lineage_class` and under `classify`;
  - (ii) coverage: unknown-under-today dates that `classify` places, as a count and share;
  - (iii) a seeded random sample of 50 dates, listing for each the identifier, the classes and the source lines, with blank `label:` columns for hand-labelling;
  - (iv) the `date_disagrees` drop count, and how many dates it empties.
- [ ] **Step 2:** The orchestrator hand-labels the 50 (or delegates on Opus, never Sonnet) and fills in false-aud and false-non-aud counts.
- [ ] **Step 3: STOP.** Send the operator coverage, precision and drop count, and ask for rule (a) or (b). Record the ruling verbatim in `lineage.md`.

### Task 2b: Apply the Checkpoint A ruling

**Files:** Modify `ts_rules.py` (`RULE`). If precision showed systematic errors, also the lexicons, with each change named in `lineage.md`. Test: `test_ts_rules.py`.

- [ ] **Step 1:** Set `RULE` to the ruling. Add `test_rule_is_operator_ruling` asserting the value, with the ruling's date in a comment.
- [ ] **Step 2:** Any lexicon fix gets an acceptance case taken from the hand-labelled sample. Run `test_ts_rules.py`. Expected: PASS.
- [ ] **Step 3:** Commit: `taperssection: lineage rule per Checkpoint A ruling`

---

### Task 3: Interpret maps named allowlisted artists (exact)

**Files:**
- Modify: `packages/llama/src/llama/stages/interpret.py`. `run_interpret(ws, provider, query, force=False, *, allowlist: Allowlist | None = None)`: after the LLM result, if `allowlist and (e := allowlist.resolve_name(criteria.artist) or allowlist.resolve_name(criteria.collection))`, set `criteria.collection = allowlist.key(e)` and `criteria.artist = e.name`. Otherwise leave criteria unchanged.
- Modify: `packages/llama/src/llama/cli.py`, the three `run_interpret` call sites (`_get_query`, `run resume`'s re-interpret branch, `profile add`): pass `allowlist=Allowlist.from_config(config.taperssection)`.
- Test: `packages/llama/tests/test_taperssection_interpret.py`

- [ ] **Step 1: Failing tests:**
  - `test_phish_query_maps_to_key`: fake provider returns `collection: "Phish"`, `artist: "Phish"` → `criteria.collection == "ts-phish"`.
  - `test_jazz_is_phish_untouched`: `JazzIsPhish` stays.
  - `test_empty_allowlist_untouched`.
  - `test_lma_name_wins_never_arises`: an entry whose name equals an LMA collection title still maps, because interpret has no index; record this decision in a comment. Spec: "builder decides which wins and pin it"; decided: the allowlist wins only on an exact match, which the research round prevents for LMA names.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run `test_taperssection_interpret.py test_cli.py test_profiles.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): exact interpret mapping at all call sites`

---

### Task 4: Artist index pass, separate cache, discovery floor bypass

**Files:**
- Modify: `packages/llama/src/llama/artist_index.py`
- Modify: `packages/llama/src/llama/stages/discover.py`
- Modify: `packages/llama/src/llama/prompts/find_artists.md`
- Test: `packages/llama/tests/test_taperssection_index.py`

**Interfaces:**
- Produces:
  - `TS_INDEX_FILENAME = "taperssection_index.json"`
  - `build_ts_index(ia, allowlist) -> dict`: returns `{"allowlist": fingerprint, "built_at", "artists": [index rows], "items": {key: {date: [{"identifier","downloads","addeddate"}...]}}}`.
    - Index rows have the same shape as LMA rows (`identifier`=key, `title`=name, `recordings`, `year_min`, `year_max`, `downloads`) plus `"allowlisted": True`.
    - It scrapes `collection:taperssection AND mediatype:audio AND creator:(...)` per entry with fields `identifier, creator, date, year, downloads, addeddate` and keeps exact-creator matches only.
  - `load_ts_index(ia, cache_dir, allowlist, *, refresh=False) -> dict`: rebuilds when missing, when the stored `allowlist` fingerprint differs, or on refresh. Empty allowlist → `{"artists": [], "items": {}}` with no IO.
  - `load_or_build(..., allowlist: Allowlist | None = None)`: appends `load_ts_index(...)["artists"]` when non-empty, after a collision check that raises `LlamaError` if any LMA identifier `slugify`s to a string starting with `ts-`.
  - `filter_artists`: rows with `allowlisted` bypass the floor.
  - `ts_items(cache_dir, key) -> dict[str, list[dict]]`: per-date item store for Task 7.
- The `find_artists` prompt: when any allowlisted row is in the inventory, render one extra sentence stating that the inventory includes Taper's Section artists with no LMA collection, and that they are eligible. Otherwise render exactly today's text.

- [ ] **Step 1: Failing tests (fake `ia.scrape`):**
  - `test_ts_index_keeps_exact_creators_only`: docs include "Vitalogy: Pearl Jam Tribute" → excluded from counts and items.
  - `test_ts_index_rebuilds_on_allowlist_change`: fingerprint changes → scrape is called again; unchanged → not called.
  - `test_empty_allowlist_no_io_and_lma_index_identical`: `load_or_build` result equals today's for an empty allowlist.
  - `test_allowlisted_bypass_floor`: a 5-item row survives `filter_artists(…, 25, 50000)`.
  - `test_prefix_collision_raises`.
  - `test_find_artists_prompt_unchanged_without_allowlisted_rows`: rendered text equality against today's template render.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. Pass `allowlist` from `cli` to `run_discover`/`load_or_build` and to `llama artists`. **Step 4:** Run `test_taperssection_index.py test_artist_index.py test_artists_cmd.py test_prompts.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): index pass, separate cache, floor bypass`

---

### Task 5: Search for synthetic keys: query, exact creators, filters

**Files:**
- Modify: `packages/llama/src/llama/stages/search.py`
- Modify: `packages/llama/src/llama/cli.py`: `_execute` resolves pinned rosters with `allowlist.require(key)` for prefixed keys before search, and passes `allowlist`.
- Test: `packages/llama/tests/test_taperssection_search.py`

**Interfaces:**
- Consumes: Task 1's `Allowlist`; Task 2's `classify`, `allowed`, `excluded`, `date_disagrees`, `in_active_window`.
- Produces:
  - `TS_EXTRA_FIELDS = ["creator", "addeddate", "source", "lineage"]` (drop `lineage` if Task 0 showed the scrape doesn't serve it).
  - `build_query(criteria, allowlist: Allowlist | None = None) -> str`: for a synthetic `criteria.collection`, returns `collection:taperssection AND mediatype:audio AND creator:("A" OR "B")` plus today's date clause. Every other input returns today's string exactly.
  - `ts_filter_docs(docs, entry, *, rule) -> list[dict]`: keeps a doc only when
    - its creator matches exactly,
    - its date is in the active window,
    - `date_disagrees` is false (each drop is logged at INFO with the identifier and both dates),
    - it is not `excluded`,
    - and `allowed(...) != "forbidden"`.
  - `run_search(..., allowlist=None)`: for synthetic keys, scrape with `SEARCH_FIELDS + TS_EXTRA_FIELDS`, apply `ts_filter_docs`, then `group_candidates` as today. The new `RecordingSummary` fields are populated from the doc. A grouped candidate with no recordings left is dropped.

- [ ] **Step 1: Failing tests:**
  - `test_build_query_lma_unchanged`: three LMA criteria shapes (collection; artist only; dates) equal today's strings, with and without a populated allowlist.
  - `test_build_query_synthetic`.
  - `test_filter_drops_tributes_dates_forbidden_excluded`: one doc per drop reason, plus one survivor.
  - `test_all_filtered_candidate_dropped`: no exception.
  - `test_unknown_pinned_key_raises`: `_execute` with `criteria.artists=["ts-gone"]` → `LlamaError` naming it, before any scrape.
  - `test_ts_recording_fields_populated`.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run `test_taperssection_search.py test_grouping.py test_get_cmd.py test_pipeline.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): search, exact creators, policy pre-filter`

---

### Task 6: jerrybase routing helper and gather's artist names

**Files:**
- Modify: `packages/llama/src/llama/jerrybase.py`: add `resolve_artist(name_or_key: str, allowlist: Allowlist | None) -> str`, which returns `entry.jerrybase` when `name_or_key` is an allowlisted key, name or creator and the entry sets `jerrybase`. Otherwise it returns its input unchanged.
- Modify the five call sites to route through it: `grouping.py:131`, `stages/winnow.py:41`, `stages/gather.py:1866` and `:1399`, `cli.py:3637`, `adjudicator/bundle.py:228`. Each gains an `allowlist` keyword, defaulting to `None`, threaded from its caller.
- Modify `stages/gather.py` `compute_gather`/`run_gather`: add `allowlist: Allowlist | None = None`. For a synthetic `candidate.collection`:
  - `Show.artist` is `entry.name`;
  - the setlist.fm lookup uses `entry.setlistfm or entry.name`;
  - every artist-matching use (title cleaning, `_drop_artist_items`, banner drop, `cosmetic_strip`, `show_metadata_norms`) receives `allowlist.matching_names(entry)` plus the item creator.

  Where a callee takes one artist string today, give it a `names: Sequence[str]` variant and leave the single-string behaviour for LMA.
- Test: `packages/llama/tests/test_taperssection_gather.py`

- [ ] **Step 1: Failing tests** (Garcia fixture from Task 0; entry `jerrybase="Jerry Garcia Band"`):
  - `test_resolve_artist_maps_and_passes_through`: LMA names come back unchanged.
  - `test_garcia_e1_candidate_gets_event_in_gather`: a two-event JGB date from the vendored CSV, with a synthetic candidate `ts-jerry-garcia/<date>/e1` → the gather result's event is not None.
  - `test_show_artist_is_display_name`.
  - `test_jgb_banner_title_cleaned`: `"Jerry Garcia Band - Sugaree"` → `"Sugaree"`.
  - `test_family_vocabulary_for_garcia`: `is_family_artist(resolve_artist("ts-jerry-garcia", al))` is True.
  - `test_lma_gather_unchanged`: `gd73-06-10` gather output with `allowlist=None` equals the populated-allowlist output.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run the new tests, then the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): jerrybase routing helper, display vs matching artist`

---

### Task 7: Download measure and title venue (pure)

**Files:**
- Create: `packages/llama/src/llama/ts_measure.py`
- Test: `packages/llama/tests/test_ts_measure.py`

**Interfaces:**
- Produces:
  - `NO_EVIDENCE_AGE_DAYS = 75`
  - `rate(downloads: int, addeddate: str | None, today: date) -> float | None`: returns `None` when `addeddate` is missing or the item is younger than 75 days; else `downloads / age_days`.
  - `show_rate(items: list[dict], today) -> float | None`: the max over the items' non-None rates.
  - `percentile(value: float, population: list[float]) -> float`: 0-100 share of the population at or below the value.
  - `catalogue_rates(items_by_date: dict[str, list[dict]], today) -> list[float]`: per-date `show_rate`, Nones dropped.
  - `parse_title_venue(title: str) -> tuple[str | None, str | None]`: `(venue, city)` from `"<artist> - <date> - <venue> - <city>"`, `"... Live at <venue> on ..."`, `"... @ <venue>, <city>"`. Returns `(None, None)` otherwise. The patterns must not fire on a bare date or artist title.

- [ ] **Step 1: Failing tests:**
  - `test_rate_none_under_75_days`.
  - `test_rate_steady`.
  - `test_show_rate_takes_best`.
  - `test_percentile_bounds` (min → >0, max → 100).
  - `test_parse_title_venue_three_forms` (the spec's three examples).
  - `test_parse_title_venue_rejects`: `"Phish 1997-11-22"` → `(None, None)`.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): age-adjusted download measure, title venue parser`

---

### Task 8: Winnow for allowlisted shows

**Files:**
- Modify: `packages/llama/src/llama/stages/winnow.py`
- Modify: `packages/llama/src/llama/prompts/score_reviews.md`
- Modify: `packages/llama/src/llama/models.py`: `QualityAssessment` gains `attribution: Literal["ok","suspect"] | None = None` and `attribution_reason: str | None = None`.
- Modify: `packages/llama/src/llama/stages/search.py` or `winnow.py`: the candidate-level venue fallback via `parse_title_venue`, applied when a synthetic candidate's `venue` is empty, using the most common parse over its recordings' titles. It is written to `Candidate.venue`/`city` only, never to a recording.
- Test: `packages/llama/tests/test_taperssection_winnow.py`

**Interfaces:**
- Consumes: Task 4's `ts_items`; Task 7's `show_rate`, `catalogue_rates`, `percentile`.
- Produces:
  - `run_winnow(..., allowlist: Allowlist | None = None, today: date | None = None)`.
  - `_is_ts(c) -> bool`
  - `_ts_evidence(c, rates) -> tuple`: `(sum reviews, show_rate or -1)`.
  - `split_sample(lma: list, ts: list, budget: int) -> tuple[list, list]`: proportional to counts, at least 1 each when both are non-empty and budget ≥ 2.
  - Payload for a ts show adds `download_percentile: float | None` and `recordings: [{identifier, creator, title, description[:600]}]`.

Rules (spec "Winnow"):

- (1) `_passes_mechanical` skips the review/rating floor for ts candidates. LMA is unchanged.
- (2) The sample: `split_sample`, LMA sorted by today's `_evidence`, ts by `_ts_evidence`, then `cap_across_artists` as today.
- (3) Batches are partitioned: LMA payloads batch exactly as today. ts payloads batch separately and render the extra prompt block (percentile baseline: `percentile/10`, with no percentile → baseline 4, below `min_quality_score` 6.0; plus the attribution question) via a template variable that is empty for LMA batches.
- (4) The single-date skip: when `criteria.date_from == criteria.date_to` and the candidate is ts, `min_quality_score` is not applied. The scorer still runs.
- (5) The light research artist for a ts candidate is `entry.name`.

- [ ] **Step 1: Failing tests (fake providers):**
  - `test_lma_batch_prompt_and_payload_identical_with_allowlist`: capture the rendered prompt for an LMA-only batch with `allowlist=None` and with a populated allowlist; they are equal.
  - `test_ts_skips_review_floor`.
  - `test_mixed_pool_samples_both_sources`: 50 LMA + 50 ts survivors, budget 40 → both present.
  - `test_ts_sorted_by_rate_not_date`: higher-rate later dates are sampled first.
  - `test_no_evidence_show_gets_null_percentile`.
  - `test_single_date_skips_quality_floor_ts_only`: ts scored 3.0 survives a single-date query; LMA does not.
  - `test_attribution_suspect_recorded_on_assessment`.
  - `test_venue_fallback_candidate_level_only`.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement; pass `allowlist` from `cli`. **Step 4:** Run `test_taperssection_winnow.py test_pipeline.py test_prompts.py` and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): winnow by age-adjusted downloads, separate ts batches`

### Checkpoint B: scorer measurement (live LLM; operator approves the spend)

- [ ] Add `taperssection_probe.py score`: score 20 Phish shows (a seeded sample across eras) through the real `score_reviews` provider, twice, in two different batch orders. Write to `docs/superpowers/2026-11-09-taperssection-evidence/scorer.md`:
  - each show's percentile and its two scores;
  - the share at or above 6.0;
  - the largest per-show score difference between orders.
- [ ] **STOP:** report to the operator. If the scores ignore the baseline (for example, everything lands below 6), the operator rules on a prompt change before Task 12.

---

### Task 9: Select: policy filter, unknown handling, pins, rate tiebreak

**Files:**
- Modify: `packages/llama/src/llama/stages/select_recording.py`
- Modify: `packages/llama/src/llama/pipeline.py` (pass `allowlist`)
- Test: `packages/llama/tests/test_taperssection_select.py`

**Interfaces:**
- `run_select_recording(..., allowlist: Allowlist | None = None, today: date | None = None) -> str`. For a ts candidate:
  - recordings with `allowed == "forbidden"` or `excluded` are removed before scoring;
  - `unknown` ones are removed when any `allowed` recording remains;
  - `downloads_norm` uses `ts_measure.rate` (None → 0), normalised as today;
  - filtered recordings never appear in `scores`;
  - an empty remaining set raises `LlamaError(f"{pid}: no recording allowed by the taperssection policy")`;
  - a pin (`overrides.recording`) naming a removed forbidden or excluded recording raises `LlamaError(f"{pid}: pinned recording {ident} is forbidden by the taperssection policy")`;
  - a pin to an `unknown` recording is honoured (the hold comes from gather, Task 10).
- `selection.json` gains `"ts_lineage": {ident: class}` for ts candidates only.

- [ ] **Step 1: Failing tests:**
  - `test_forbidden_never_in_scores`.
  - `test_unknown_excluded_when_allowed_sibling`.
  - `test_unknown_competes_when_alone`.
  - `test_empty_set_raises_llamaerror_not_valueerror`.
  - `test_pin_to_forbidden_raises`.
  - `test_adjudicator_switch_to_forbidden_raises`: apply a `switch_recording` verdict through `adjudicator/apply.py` onto a ts show whose target is sbd under an aud-only entry → the show is restored and the error surfaced.
  - `test_rate_tiebreak`.
  - `test_lma_selection_unchanged`: the gd73-06-10 selection.json scores are equal with and without an allowlist.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run `test_taperssection_select.py test_cli_select.py test_adjudicator_apply.py` and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): select policy filter, pins, rate tiebreak`

---

### Task 10: Holds, overrule kinds, adjudicator bars, replay

**Files:**
- Modify: `stages/gather.py` (`compute_gather`/`run_gather`: new keyword `assessment: QualityAssessment | None = None`)
- Modify: `pipeline.py` (pass `entry.assessment`)
- Modify: `replay.py` (`compute_legs` passes `prov.assessment` and the allowlist; `config_fingerprint` folds `allowlist.fingerprint()` only when it is not None; `_FAMILIES` entries)
- Modify: `overrules.py` (`_PATTERNS`), `adjudicator/gate.py` (`OVERRULE_BAR`)
- Test: `packages/llama/tests/test_taperssection_holds.py`

**Decisions.** This narrows the spec's carrier wording; same effect, fewer stored fields:

- The unknown-lineage verdict is **recomputed in gather** from `candidate.recordings` (which carry the classification fields, and come from `provenance.json`), the selected identifier and the allowlist. Gather therefore needs no new stored field, and replay reproduces it from provenance automatically.
- The misattribution verdict comes from `assessment.attribution`, passed explicitly.
- Flag strings:
  - `f"unclassified lineage for {name} (allowed: {', '.join(lineages)}): {identifier}"`, kind `lineage-unknown`, subject mode `raw` (the identifier);
  - `f"possible misattribution: {reason}"`, kind `misattribution`, subject mode `none`.
- `OVERRULE_BAR`: `"lineage-unknown": "never"`, `"misattribution": "medium"`.
- `_FAMILIES`: `("taperssection", lambda f: f.startswith(("unclassified lineage for", "possible misattribution:")))`.

- [ ] **Step 1: Failing tests:**
  - `test_gather_flags_selected_unknown`.
  - `test_gather_flags_misattribution`.
  - `test_overrule_clears_each`: a `fix --overrule` record matches via `flag_key`.
  - `test_replay_keeps_both_flags`: build a held ts show dir from fixtures, run `replay.compute_legs`, and the flags are present.
  - `test_fingerprint_unchanged_when_empty`.
  - `test_fingerprint_changes_on_allowlist_edit`.
  - `test_adjudicator_bar_lineage_never`.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run `test_taperssection_holds.py test_replay.py test_reapply.py test_overrules.py test_adjudicator_gate.py` and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): hold flags, overrule kinds, replay carriers`

---

### Task 11: Display-name sites and docs

**Files:**
- Modify:
  - `cli.py:189`: the shortlist column prints `entry.name` for ts candidates;
  - `catalog.py:309`, `:395`: the artist fallback uses `entry.name`;
  - `llama show`/`status`, wherever `collection` is shown as the artist.
- Modify docs:
  - `packages/llama/CLAUDE.md`: a new "Taper's Section allowlist" bullet covering the config shape, the `ts-` key, the rename caveat, the rules, holds and bars, the known limitations (per-set items; an artist later gaining an LMA collection; unclassified source lines; the newest tour deferred by the 75-day rule; discovery reaching `jam`/`dead-family`) and the evidence-doc paths;
  - the root `CLAUDE.md` table, only if a new script is added (`scripts/CLAUDE.md` entry for `taperssection_probe.py`).
- Test: extend `test_cli.py`/`test_catalog.py` with one assertion each that a ts candidate displays its name.

- [ ] **Step 1:** Write the failing display tests. **Step 2:** Run. Expected: FAIL. **Step 3:** Implement and update the docs. **Step 4:** Run the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `taperssection: display names, docs`

---

### Task 12: Acceptance

**Files:**
- Test: `packages/llama/tests/test_taperssection_e2e.py`
- Evidence: `docs/superpowers/2026-11-09-taperssection-evidence/acceptance.md`

- [ ] **Step 1: Offline end-to-end** (fake LLM, fixtures from Task 0):
  - a Phish aud fixture goes through search → package with a populated allowlist, giving a packaged show with `artist == "Phish"`, the `ts-phish-...` slug and no review flags;
  - the Garcia fixture packages with jerrybase evidence.
- [ ] **Step 2: Empty-allowlist regression:**
  - the full suite passes;
  - then, per `scripts/CLAUDE.md`, run the replay harness read-only over the operator library with an empty allowlist and record that no show's computed outcome changed. Digest-only churn from null keys is expected and listed separately.
- [ ] **Step 3: Live smoke (operator approves):**
  - `llama get "Phish 1997-11-22" --plan` resolves to `ts-phish` and lists candidates;
  - an `llama artists "blues rock"`-style query lists Warren Haynes when allowlisted.

  Record the output in `acceptance.md`.
- [ ] **Step 4: Per-set items:** find a Phish date whose only allowed recordings carry a `set2`/`partial` token. Run it offline. Does an existing hold (structure, research-sets) catch it? Record yes or no. If no, record it as a known limitation in `packages/llama/CLAUDE.md`, with no new mechanism.
- [ ] **Step 5:** Commit: `taperssection: acceptance evidence`

---

## Not in this plan

- **The research round.** It is separate from the build (spec "The research round"): Sonnet research workers per artist, Opus synthesis, a committed record named e.g. `docs/superpowers/2026-11-09-taperssection-evidence/artist-policies.md`, plus suggested `[[taperssection.artists]]` entries. The operator pastes in the approved entries. Run it after Task 12, or in parallel with the build.
- **The `phish` and `garcia` profiles.** Operator work after the build, first runs with `human_gate = true`.
