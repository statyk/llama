# Taper's Section allowlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let llama find, select and package recordings from archive.org's Taper's Section (`collection:taperssection`) for an operator-curated allowlist of artists, without changing behaviour for any existing LMA artist.

**Architecture:** `config.py` holds the allowlist config models. A new `llama/taperssection.py` holds the `Allowlist` object, the synthetic artist key and exact creator matching. Pure helper modules hold lineage classification, the date cross-check, the age-adjusted download measure and title venue parsing. An `Allowlist` built from config is threaded explicitly into the artist index, interpret, search, winnow, select, gather and replay. It is a keyword argument defaulting to `None`, except on `process_show`, where it is required. Every ts-aware function resolves its candidate through `Allowlist.for_candidate`, which raises for a `ts-` key when no populated allowlist was passed. So a missed call site fails loudly instead of running a ts show as LMA. With an empty allowlist every one of those paths takes today's branch.

**Tech Stack:** Python 3, pydantic v2, pytest (offline, fake LLM backend), archive.org scrape/metadata APIs via `IAClient`.

**Spec:** `docs/superpowers/specs/2026-11-09-taperssection-allowlist-design.md`. Read it before any task. Every task's requirements include the spec section it names.

## Global Constraints

- **Guarded surface (spec "Stakes"):**
  - With an empty allowlist, LMA behaviour and every LLM prompt's rendered text are identical to today.
  - With a populated allowlist, each LMA artist's search query, grouping, winnow scorer prompt and payload for an LMA batch, and recording selection are unchanged.
  - New artifact keys may be null-valued, and that is noise, not a regression.
- **Fail closed on a missing allowlist.** Every ts-aware function (search, winnow, select, gather's `compute_gather`, `replay.compute_legs`, the jerrybase routing) gets its entry from `Allowlist.for_candidate(allowlist, collection)` (Task 1). For a `ts-` key it raises `LlamaError` when `allowlist` is None or empty, or when the key is unknown. It never falls back to the LMA branch.
- **Workspace and tests:**
  - Work in the worktree `/Users/shawn/projects/llama/.claude/worktrees/taperssection` with its OWN venv (Task 0 Step 0). Run tests as `./.venv/bin/python -m pytest -q` from the worktree root (root `CLAUDE.md`).
  - Check `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree.
  - The suite stays offline and deterministic. Live archive.org calls belong only in `scripts/` probes or `pytest -m live` tests.
- **Imports:** `emcee`, `transmitter` and `llama` never import each other. Within llama, `taperssection.py` imports from `config.py`, never the reverse.
- **Constants:**
  - Synthetic key prefix: `ts-`. A key is `ts-` + `slugify(name)`, e.g. `ts-phish`, `ts-jerry-garcia`; performance id `ts-phish/1997-11-22`, show slug `ts-phish-1997-11-22`.
  - No-evidence age: 75 days (`NO_EVIDENCE_AGE_DAYS = 75`).
  - Download store TTL: 7 days (`TS_INDEX_TTL_DAYS = 7`).
  - Lineage classes are `aud`, `sbd`, `matrix`, `fm`, `webcast`, `unknown`. An entry's `lineages` may name any of the first five.
- **Config:** `config.toml` key `[[taperssection.artists]]`. The model is strict (`_StrictModel`, unknown key is an error). The build never writes `~/.llama/config.toml`.
- **File names:** no file whose name starts REPORT/SUMMARY/FINDINGS/ANALYSIS (subagent write guard). Evidence goes in `docs/superpowers/2026-11-09-taperssection-evidence/`.

## Review Focus

1. **A creator string that differs from an entry's spelling only by case, a leading "The" or punctuation** ("phish", "The Allman Brothers Band"). Expected: it matches. Pinned in Task 1 (`test_norm_creator_folds_case_the_punct`).
2. **An LMA query or pinned roster naming an LMA collection that merely contains an allowlisted name** (`JazzIsPhish`, `DeadPhishOrchestra`), or an LMA item whose creator is exactly an allowlisted name. Expected: today's etree path, untouched. Pinned in Tasks 3, 4 and 6a.
3. **A taperssection candidate whose every recording is filtered**: forbidden lineage, `exclude`, active bounds, date cross-check. Expected: dropped in search, with no shortlist slot and no `ValueError` anywhere. Pinned in Tasks 5 and 9.
4. **An allowlist edit between runs**: entry renamed, entry removed, `jerrybase` added. Expected:
   - a pinned old key (in `criteria.artists` or `criteria.collection`) fails with `LlamaError` naming it;
   - the index rebuilds the taperssection part on the next run;
   - the replay fingerprint changes (a `note`-only edit does not).

   Pinned in Tasks 1, 4, 5 and 10.
5. **A show whose only evidence-bearing recordings are under 75 days old.** Expected: the scorer gets no percentile and a below-floor baseline, and it never ships because of a zero download count. Pinned in Tasks 7 and 8.
6. **A ts-aware call site reached without an allowlist.** Expected: `LlamaError`, never an LMA run of a ts show. Pinned in Tasks 1, 6b and 9.

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
- Produces: fixture identifiers recorded in `premises.md`, used by Tasks 2, 5, 6a, 9 and 12.

- [ ] **Step 0:** Create the worktree venv with the root `CLAUDE.md` setup command: `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`. Then run `./.venv/bin/python -c "import llama; print(llama.__file__)"` and confirm it resolves inside the worktree.
- [ ] **Step 1:** Read `scripts/CLAUDE.md` and `scripts/capture_fixture.py`. Pick one Phish item with a `Source:` description line (e.g. a `ph2017-07-30...flac2496` item) and one Garcia JGB item dated before 1995-08-09, on a date that has two JGB events in the vendored jerrybase CSV (Task 6a's `/e1` test needs it). Capture both.
- [ ] **Step 2:** Write `taperssection_probe.py fields`. One `IAClient.scrape('collection:taperssection AND creator:"Phish"', ["identifier","creator","addeddate","source","lineage","downloads","date","title","description"], count=100)` call, then report the fraction of docs carrying each field. Record whether `lineage` is served at all. If it is not, `premises.md` says so, and Task 5 fills `RecordingSummary.lineage` from cached per-item metadata.
- [ ] **Step 3:** Record in `premises.md`. For each item, give the answer and the command that produced it.
  - (a) Does setlist.fm list a 1976 JGB date under "Jerry Garcia" or "Jerry Garcia Band"? One search for each name.
  - (b) What does emcee's `[assign.artists]` matcher (`packages/emcee/src/emcee/artists.py`) do with "Phish" and "Jerry Garcia" against the operator's emcee config? Read-only.
  - (c) Run `filter_files` and `FORMAT_BY_AUDIO` on both fixtures: which audio files are kept, and which format wins?
  - (d) Run `setlist.parse_setlist` on the Phish fixture's description: are `<div>`/`<p>` handled?
  - (e) On the Garcia scrape: how many dates have a JGB jerrybase row while the title or description names another act (Legion of Mary, acoustic, Garcia/Grisman)? These could raise false jerrybase holds.
  - (h) What do transmitter's artist separation (`packages/transmitter/src/transmitter/rules.py`) and rotation do with the artist names "Phish" and "Jerry Garcia"? Read-only.
- [ ] **Step 4:** Commit: `git add scripts/taperssection_probe.py docs/superpowers/2026-11-09-taperssection-evidence packages/llama/tests/fixtures && git commit -m "taperssection: premise probes and fixtures"`

---

### Task 1: Allowlist model, synthetic key, exact matching

**Files:**
- Modify: `packages/llama/src/llama/config.py`: define `TaperssectionArtist` and `TaperssectionConfig`; add `taperssection: TaperssectionConfig` to `Config`; add a commented example to the `config init` template.
- Create: `packages/llama/src/llama/taperssection.py` (`Allowlist`, the key and the matching functions; imports the models from `config`)
- Test: `packages/llama/tests/test_taperssection.py`

**Interfaces:**
- Produces, in `config.py`:
  - `class TaperssectionArtist(_StrictModel)`, with fields:
    - `name: str`
    - `creators: list[str]` (min 1)
    - `lineages: list[Literal["aud","sbd","matrix","fm","webcast"]]` (min 1)
    - `exclude: list[str] = []`
    - `note: str = ""`
    - `jerrybase: str | None = None`
    - `active_from: str | None = None` (YYYY-MM-DD)
    - `active_until: str | None = None`
    - `setlistfm: str | None = None` (always present; Task 0's step 3a only informs whether entries set it)
  - `class TaperssectionConfig(_StrictModel): artists: list[TaperssectionArtist] = []`
- Produces, in `taperssection.py`:
  - `KEY_PREFIX = "ts-"`
  - `norm_creator(s: str) -> str`: lowercase, strip a leading "the ", collapse non-alphanumerics to single spaces, strip.
  - `artist_key(name: str) -> str`: returns `KEY_PREFIX + slugify(name)`.
  - `is_synthetic(key: str) -> bool`
  - `class Allowlist`:
    - `Allowlist.from_config(cfg: TaperssectionConfig) -> Allowlist`: raises `LlamaError` when two entries' names give the same key, or when one `norm_creator`-normalized creator appears in two entries.
    - `Allowlist.empty() -> Allowlist`
    - `Allowlist.for_candidate(allowlist: Allowlist | None, collection: str) -> TaperssectionArtist | None` (static): returns None for a non-prefixed `collection`; for a prefixed one, raises `LlamaError` when `allowlist` is None or empty, else returns `allowlist.require(collection)`.
    - `.entries: list[TaperssectionArtist]`
    - `__bool__` (true when non-empty)
    - `.key(entry) -> str`
    - `.by_key(key: str) -> TaperssectionArtist | None`
    - `.require(key: str) -> TaperssectionArtist`: raises `LlamaError(f"unknown taperssection artist key {key!r}; is it still in [[taperssection.artists]]?")` when `key.startswith(KEY_PREFIX)` and no entry matches.
    - `.match_creator(creator: str | list | None, entry) -> bool`: exact `norm_creator` equality against the entry's creators.
    - `.resolve_name(name: str | None) -> TaperssectionArtist | None`: exact `norm_creator` match on `name` or any creator; also accepts a CamelCase collection guess (compare `norm_creator` of the guess against each spelling with spaces removed).
    - `.matching_names(entry) -> tuple[str, ...]`: name plus creators.
    - `.fingerprint() -> str | None`: `None` when empty, else sha256 of the canonical JSON of entries with `note` excluded.

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

def test_for_candidate_fails_closed():
    assert Allowlist.for_candidate(None, "GratefulDead") is None
    with pytest.raises(LlamaError):
        Allowlist.for_candidate(None, "ts-phish")
    with pytest.raises(LlamaError):
        Allowlist.for_candidate(Allowlist.empty(), "ts-phish")
    with pytest.raises(LlamaError, match="ts-gone"):
        Allowlist.for_candidate(al, "ts-gone")   # al: Phish entry
    assert Allowlist.for_candidate(al, "ts-phish").name == "Phish"

def test_duplicate_key_rejected():
    # names "Phish" and "phish" both give ts-phish
    with pytest.raises(LlamaError): Allowlist.from_config(...)

def test_shared_creator_rejected():
    # "The Phish" in one entry's creators, "phish" in another's
    with pytest.raises(LlamaError): Allowlist.from_config(...)

def test_unknown_key_in_config_is_error():
    with pytest.raises(ValidationError):
        TaperssectionArtist(name="X", creators=["X"], lineages=["aud"], bogus=1)

def test_empty_fingerprint_is_none():
    assert Allowlist.empty().fingerprint() is None

def test_fingerprint_ignores_note():
    # same entry with note="" and note="changed" -> equal fingerprints
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
  - `classify(rec: RecordingSummary) -> Literal["aud","sbd","matrix","fm","webcast","unknown"]`: reads `rec.identifier`, `rec.title`, `rec.source`, `rec.lineage`, `source_lines(rec.description)`. It is the one classification input for select (Task 9) and gather (Task 10). The rule is spec "Lineage classification" verbatim:
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
    - an entry whose `lineages` cover all five classes → `"allowed"` for every class, `unknown` included, under both rules;
    - class in `entry.lineages` → allowed;
    - known class not in it → forbidden;
    - `unknown` under rule a → `"unknown"`;
    - `unknown` under rule b is classified `aud` and judged as such: `"allowed"` if `"aud" in entry.lineages`, else `"forbidden"`.
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
  - `test_allowed_rules`:
    - `["aud"]` entry: aud → allowed, sbd → forbidden; unknown → `"unknown"` under a, `"allowed"` under b;
    - `["sbd"]` entry: unknown → `"unknown"` under a, `"forbidden"` under b;
    - all-five-classes entry: unknown → `"allowed"` under both a and b.
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
- [ ] **Step 2:** Run the `date_disagrees` comparison per survey artist (premise 3(f), moved here from Task 0) and record the rates in `premises.md`.
- [ ] **Step 3:** The orchestrator hand-labels the 50 (or delegates on Opus, never Sonnet) and fills in false-aud and false-non-aud counts.
- [ ] **Step 4: STOP.** Send the operator coverage, precision and drop count, and ask for rule (a) or (b). Record the ruling verbatim in `lineage.md`.

### Task 2b: Apply the Checkpoint A ruling

**Files:** Modify `ts_rules.py` (`RULE`). If precision showed systematic errors, also the lexicons, with each change named in `lineage.md`. Test: `test_ts_rules.py`.

- [ ] **Step 1:** Set `RULE` to the ruling. Add `test_rule_is_operator_ruling` asserting the value, with the ruling's date in a comment.
- [ ] **Step 2:** Any lexicon fix gets an acceptance case taken from the hand-labelled sample. Run `test_ts_rules.py`. Expected: PASS.
- [ ] **Step 3:** Commit: `taperssection: lineage rule per Checkpoint A ruling`

---

### Task 3: Interpret maps named allowlisted artists (exact)

**Files:**
- Modify: `packages/llama/src/llama/stages/interpret.py`. `run_interpret(ws, provider, query, force=False, *, allowlist: Allowlist | None = None)`: after the LLM result, if `allowlist and (e := allowlist.resolve_name(criteria.artist) or allowlist.resolve_name(criteria.collection))`, set `criteria.collection = allowlist.key(e)` and `criteria.artist = e.name`. Otherwise leave criteria unchanged.
- Modify: `packages/llama/src/llama/cli.py`, the two `run_interpret` call sites: `_interpret_and_stamp` (`cli.py:815`, serving `_get_query` and `run resume`) and `profile add` (`cli.py:5388`). Each passes `allowlist=Allowlist.from_config(config.taperssection)`.
- Test: `packages/llama/tests/test_taperssection_interpret.py`

- [ ] **Step 1: Failing tests:**
  - `test_phish_query_maps_to_key`: fake provider returns `collection: "Phish"`, `artist: "Phish"` → `criteria.collection == "ts-phish"`.
  - `test_jazz_is_phish_untouched`: `JazzIsPhish` stays.
  - `test_empty_allowlist_untouched`.
  - `test_allowlist_wins_on_exact_match`: an entry whose name equals an LMA collection title still maps, because interpret has no index; record this decision in a comment. Spec: "builder decides which wins and pin it"; decided: the allowlist wins only on an exact match, which the research round prevents for LMA names.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run `test_taperssection_interpret.py test_cli.py test_profiles.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): exact interpret mapping at both call sites`

---

### Task 4: Artist index pass, download store, discovery floor bypass, pinned rosters

**Files:**
- Modify: `packages/llama/src/llama/artist_index.py`
- Modify: `packages/llama/src/llama/stages/discover.py`
- Modify: `packages/llama/src/llama/prompts/find_artists.md`
- Modify: `packages/llama/src/llama/cli.py`: `profile add --artists` (`cli.py:5398`) and `profile artists --set` (`cli.py:5427`) pass `allowlist` to `resolve_artists`.
- Create (golden): `packages/llama/tests/fixtures/golden/find_artists_pre_ts.txt`
- Test: `packages/llama/tests/test_taperssection_index.py`

**Interfaces:**
- Produces:
  - `TS_INDEX_FILENAME = "taperssection_index.json"`
  - `TS_INDEX_TTL_DAYS = 7`
  - `build_ts_index(ia, allowlist) -> dict`: returns `{"allowlist": fingerprint, "built_at", "artists": [index rows], "items": {key: {date: [{"identifier","downloads","addeddate"}...]}}}`.
    - Index rows have the same shape as LMA rows (`identifier`=key, `title`=name, `recordings`, `year_min`, `year_max`, `downloads`) plus `"allowlisted": True`.
    - It scrapes `collection:taperssection AND mediatype:audio AND creator:(...)` per entry with fields `identifier, creator, date, year, downloads, addeddate` and keeps exact-creator matches only.
  - `load_ts_index(ia, cache_dir, allowlist, *, refresh=False) -> dict`: rebuilds when missing, when the stored `allowlist` fingerprint differs, when `built_at` is older than `TS_INDEX_TTL_DAYS`, or on refresh. Empty allowlist → `{"artists": [], "items": {}}` with no IO.
  - `load_or_build(..., allowlist: Allowlist | None = None)`: appends `load_ts_index(...)["artists"]` when non-empty, after a collision check that raises `LlamaError` if any LMA identifier `slugify`s to a string starting with `ts-`.
  - `filter_artists`: rows with `allowlisted` bypass the floor.
  - `ts_items(ts_index: dict, key: str) -> dict[str, list[dict]]`: the per-date item store for one key, read from a `load_ts_index` result (Task 8).
  - `resolve_artists(index, names, allowlist: Allowlist | None = None)`:
    - an exact `allowlist.resolve_name(name)` match is tried FIRST and wins, resolving to that entry's ts index row;
    - then today's exact rung;
    - the unique-substring rung matches LMA rows only (ts rows are excluded from it), so no LMA substring pin changes.
- The `find_artists` prompt: when any allowlisted row is in the inventory, render one extra sentence stating that the inventory includes Taper's Section artists with no LMA collection, and that they are eligible. Otherwise render exactly today's text.

- [ ] **Step 1:** Before editing `find_artists.md`, render today's template for a fixed LMA-only inventory and save it as `tests/fixtures/golden/find_artists_pre_ts.txt`.
- [ ] **Step 2: Failing tests (fake `ia.scrape`):**
  - `test_ts_index_keeps_exact_creators_only`: docs include "Vitalogy: Pearl Jam Tribute" → excluded from counts and items.
  - `test_ts_index_rebuilds_on_allowlist_change`: fingerprint changes → scrape is called again; unchanged → not called.
  - `test_ts_index_rebuilds_after_ttl`: `built_at` 8 days old → scrape is called again.
  - `test_empty_allowlist_no_io_and_lma_index_identical`: `load_or_build` result equals today's for an empty allowlist.
  - `test_allowlisted_bypass_floor`: a 5-item row survives `filter_artists(…, 25, 50000)`.
  - `test_prefix_collision_raises`.
  - `test_find_artists_prompt_unchanged_without_allowlisted_rows`: rendered text equals the golden file from Step 1.
  - `test_pin_jerry_garcia_resolves_to_ts_key`: `resolve_artists(index, ["Jerry Garcia"], allowlist)` → `ts-jerry-garcia` (today it pins `CatsUnderTheStarsTributeToJerryGarcia`).
  - `test_lma_substring_pin_unchanged_with_allowlist`: an existing LMA substring pin resolves identically with a populated allowlist.
- [ ] **Step 3:** Run. Expected: FAIL.
- [ ] **Step 4:** Implement. Pass `allowlist` from `cli` to `run_discover`/`load_or_build`, to `llama artists`, and to the two `resolve_artists` sites.
- [ ] **Step 5:** Run `test_taperssection_index.py test_artist_index.py test_artists_cmd.py test_prompts.py test_profiles.py`. Expected: PASS.
- [ ] **Step 6:** Commit: `feat(taperssection): index pass, download store, floor bypass, pinned rosters`

---

### Task 5: Search for synthetic keys: query, exact creators, filters

**Files:**
- Modify: `packages/llama/src/llama/stages/search.py`
- Modify: `packages/llama/src/llama/grouping.py`: `_summary` fills the new `RecordingSummary` fields.
- Modify: `packages/llama/src/llama/cli.py`: before search, `_execute` calls `allowlist.require(...)` on a prefixed `criteria.collection` and on each prefixed `criteria.artists` entry, and passes `allowlist`.
- Test: `packages/llama/tests/test_taperssection_search.py`

**Interfaces:**
- Consumes: Task 1's `Allowlist`; Task 2's `classify`, `allowed`, `excluded`, `date_disagrees`, `in_active_window`.
- Produces:
  - `TS_EXTRA_FIELDS = ["creator", "addeddate", "source", "lineage"]` (drop `lineage` if Task 0 showed the scrape doesn't serve it).
  - `build_query(criteria, allowlist: Allowlist | None = None) -> str`: for a synthetic `criteria.collection`, gets the entry via `Allowlist.for_candidate` and returns `collection:taperssection AND mediatype:audio AND creator:("A" OR "B")` plus today's date clause. Every other input returns today's string exactly.
  - `ts_filter_docs(docs, entry, *, rule) -> list[dict]`: keeps a doc only when
    - its creator matches exactly,
    - its date is in the active window,
    - `date_disagrees` is false (each drop is logged at INFO with the identifier and both dates),
    - it is not `excluded`,
    - and `allowed(...) != "forbidden"`.
  - `run_search(..., allowlist=None)`: for synthetic keys, scrape with `SEARCH_FIELDS + TS_EXTRA_FIELDS`, apply `ts_filter_docs`, then `group_candidates` as today. The new `RecordingSummary` fields are populated from the doc. If Task 0 showed the scrape lacks `lineage`, `RecordingSummary.lineage` is filled from cached `ia.metadata` per ts item, so the candidate stored in provenance carries it. A grouped candidate with no recordings left is dropped.

- [ ] **Step 1: Failing tests:**
  - `test_build_query_lma_unchanged`: three LMA criteria shapes (collection; artist only; dates) equal today's strings, with and without a populated allowlist.
  - `test_build_query_synthetic`.
  - `test_filter_drops_tributes_dates_forbidden_excluded`: one doc per drop reason, plus one survivor.
  - `test_all_filtered_candidate_dropped`: no exception.
  - `test_unknown_pinned_key_raises`: `_execute` with `criteria.artists=["ts-gone"]` → `LlamaError` naming it, before any scrape.
  - `test_unknown_collection_key_raises`: stored criteria with `collection="ts-gone"` → `LlamaError` naming it, before any scrape.
  - `test_ts_recording_fields_populated` (including `lineage`, from the doc or from metadata per Task 0).
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run `test_taperssection_search.py test_grouping.py test_get_cmd.py test_pipeline.py`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): search, exact creators, policy pre-filter`

---

### Task 6a: jerrybase routing by candidate key

**Files:**
- Modify: `packages/llama/src/llama/jerrybase.py`: add `jerrybase_artist(collection: str, fallback_artist: str, allowlist: Allowlist | None) -> str`. It gets the entry via `Allowlist.for_candidate(allowlist, collection)`. For a prefixed `collection` it returns `entry.jerrybase`, or `fallback_artist` when the entry sets none. For anything else it returns `fallback_artist` unchanged. It never keys on names.
- Modify the call sites to route through it, each passing the candidate's `collection` and gaining an `allowlist` keyword (default `None`) threaded from its caller: `grouping.py:131`, `stages/winnow.py:41`, `stages/gather.py:1866` and `:1399`, `cli.py:3637`, `adjudicator/bundle.py:228`.
- Test: `packages/llama/tests/test_taperssection_jerrybase.py`

- [ ] **Step 1: Failing tests** (Garcia fixture from Task 0; entry `jerrybase="Jerry Garcia Band"`):
  - `test_jerrybase_artist_maps_key_and_passes_through`: `jerrybase_artist("ts-jerry-garcia", "Jerry Garcia", al) == "Jerry Garcia Band"`; an LMA collection returns `fallback_artist`.
  - `test_lma_creator_named_jerry_garcia_unchanged`: an LMA item whose creator is exactly "Jerry Garcia" gets `fallback_artist` back unchanged.
  - `test_ts_key_without_allowlist_raises`: `jerrybase_artist("ts-jerry-garcia", "x", None)` → `LlamaError`.
  - `test_garcia_e1_candidate_gets_event_in_gather`: the fixture's two-event JGB date, with a synthetic candidate `ts-jerry-garcia/<date>/e1` → the gather result's event is not None.
  - `test_family_vocabulary_for_garcia`: `is_family_artist(jerrybase_artist("ts-jerry-garcia", "Jerry Garcia", al))` is True.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run the new tests, then the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): jerrybase routing by candidate key`

---

### Task 6b: gather naming and title venue

**Files:**
- Modify `stages/gather.py` `compute_gather`/`run_gather`: add `allowlist: Allowlist | None = None`; the entry comes from `Allowlist.for_candidate(allowlist, candidate.collection)`. For a synthetic `candidate.collection`:
  - `Show.artist` is `entry.name`;
  - the setlist.fm lookup uses `entry.setlistfm or entry.name`;
  - every artist-matching use (title cleaning, `_drop_artist_items`, banner drop, `cosmetic_strip`, `show_metadata_norms`) receives `allowlist.matching_names(entry)` plus the item creator.

  Where a callee takes one artist string today, give it a `names: tuple[str, ...]` variant; LMA passes `(creator,)`, keeping today's behaviour.
- Modify `adjudicator/bundle.py` (~:222): for a ts show, the setlist.fm cache key uses the same name as gather, `entry.setlistfm or entry.name`.
- Modify `models.py` `Candidate`: add `ts_title_venue: tuple[str | None, str | None] | None = None`.
- Modify `stages/search.py`: for a ts candidate, set `ts_title_venue` from `parse_title_venue` (Task 7), as the most common parse over its recordings' titles.
- Modify `stages/gather.py`: gather uses `candidate.ts_title_venue` only AFTER the vote/jerrybase/city chain has left the venue empty. It never feeds the venue-mismatch or city holds.
- Test: `packages/llama/tests/test_taperssection_gather.py`

- [ ] **Step 1: Failing tests:**
  - `test_show_artist_is_display_name`.
  - `test_jgb_banner_title_cleaned`: `"Jerry Garcia Band - Sugaree"` → `"Sugaree"`.
  - `test_compute_gather_ts_without_allowlist_raises`: `compute_gather` on a `ts-` candidate with `allowlist=None` → `LlamaError`.
  - `test_bundle_setlistfm_key_matches_gather`.
  - `test_jerrybase_venue_beats_title_venue`: a Garcia show with a jerrybase event keeps jerrybase's venue, and a differing title venue raises no hold.
  - `test_title_venue_fills_empty_venue`: no vote, no jerrybase event → the venue comes from `ts_title_venue`.
  - `test_lma_gather_unchanged`: `gd73-06-10` gather output with `allowlist=None` equals the populated-allowlist output.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run the new tests, then the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): display vs matching artist, title venue fallback`

**Order:** Task 6b's title-venue work consumes Task 7's `parse_title_venue`, so run Task 6b after Task 7.

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
  - `percentile(value: float, population: list[float]) -> float | None`: 0-100 share of the population at or below the value; `None` when the population is empty.
  - `catalogue_rates(items_by_date: dict[str, list[dict]], today) -> list[float]`: per-date `show_rate`, Nones dropped.
  - `parse_title_venue(title: str) -> tuple[str | None, str | None]`: `(venue, city)` from `"<artist> - <date> - <venue> - <city>"`, `"... Live at <venue> on ..."`, `"... @ <venue>, <city>"`. Returns `(None, None)` otherwise. The patterns must not fire on a bare date or artist title.

- [ ] **Step 1: Failing tests:**
  - `test_rate_none_under_75_days`.
  - `test_rate_steady`.
  - `test_show_rate_takes_best`.
  - `test_percentile_bounds` (min → >0, max → 100).
  - `test_percentile_empty_population_is_none`.
  - `test_parse_title_venue_three_forms` (the spec's three examples).
  - `test_parse_title_venue_rejects`: `"Phish 1997-11-22"` → `(None, None)`.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Run `parse_title_venue` over 100 sampled Phish titles (premise 3(g), moved here from Task 0) via a `taperssection_probe.py venue` subcommand, and record wrong parses (precision) in `premises.md`.
- [ ] **Step 6:** Commit: `feat(taperssection): age-adjusted download measure, title venue parser`

---

### Task 8: Winnow for allowlisted shows

**Files:**
- Modify: `packages/llama/src/llama/stages/winnow.py`
- Modify: `packages/llama/src/llama/prompts/score_reviews.md`
- Modify: `packages/llama/src/llama/models.py`: `QualityAssessment` gains `attribution: Literal["ok","suspect"] | None = None` and `attribution_reason: str | None = None`.
- Create (golden): `packages/llama/tests/fixtures/golden/score_reviews_pre_ts.txt`
- Test: `packages/llama/tests/test_taperssection_winnow.py`

**Interfaces:**
- Consumes: Task 4's `load_ts_index`, `ts_items`; Task 7's `show_rate`, `catalogue_rates`, `percentile`.
- Produces:
  - `run_winnow(..., cache_dir: Path, allowlist: Allowlist | None = None, today: date | None = None)`. When ts candidates are present, it calls `load_ts_index(ia, cache_dir, allowlist)` itself and reads each key's dates with `ts_items`.
  - `_is_ts(c) -> bool`
  - `_ts_evidence(c, rates) -> tuple`: `(sum reviews, show_rate or -1)`.
  - `split_sample(lma: list, ts: list, budget: int) -> tuple[list, list]`: proportional to counts, at least 1 each when both are non-empty and budget ≥ 2.
  - Payload for a ts show adds `download_percentile: float | None` and `recordings: [{identifier, creator, title, description[:600]}]`. An empty population (no evidence-bearing dates) gives every show `download_percentile=None`, never a division by zero.

Rules (spec "Winnow"):

- (1) `_passes_mechanical` skips the review/rating floor for ts candidates. LMA is unchanged.
- (2) The sample: `split_sample`, LMA sorted by today's `_evidence`, ts by `_ts_evidence`, then `cap_across_artists` as today.
- (3) Batches are partitioned: LMA payloads batch exactly as today. ts payloads batch separately and render the extra prompt block (percentile baseline: `percentile/10`, with no percentile → baseline 4, below `min_quality_score` 6.0; plus the attribution question) via a template variable that is empty for LMA batches.
- (4) The single-date skip: when `criteria.date_from is not None and criteria.date_from == criteria.date_to` and the candidate is ts, `min_quality_score` is not applied. The scorer still runs.
- (5) The light research artist for a ts candidate is `entry.name`.
- (6) The scorer may omit `attribution`; the assessment then stores `None`, and gather treats it as suspect for a ts show (Task 10).

- [ ] **Step 1:** Before editing `score_reviews.md`, render today's template for a fixed LMA-only batch and save it as `tests/fixtures/golden/score_reviews_pre_ts.txt`.
- [ ] **Step 2: Failing tests (fake providers):**
  - `test_lma_batch_prompt_and_payload_identical_with_allowlist`: the rendered prompt for an LMA-only batch, with `allowlist=None` and with a populated allowlist, equals the golden file from Step 1; the payloads are equal.
  - `test_ts_skips_review_floor`.
  - `test_mixed_pool_samples_both_sources`: 50 LMA + 50 ts survivors, budget 40 → both present.
  - `test_ts_sorted_by_rate_not_date`: higher-rate later dates are sampled first.
  - `test_no_evidence_show_gets_null_percentile`.
  - `test_empty_population_all_null_percentile`: no evidence-bearing dates → every ts show gets `download_percentile=None`, no exception.
  - `test_pinned_roster_builds_store_when_missing`: a pinned-roster ts run with no `taperssection_index.json` in `cache_dir` builds it.
  - `test_single_date_skips_quality_floor_ts_only`: ts scored 3.0 survives a single-date query; LMA does not.
  - `test_undated_ts_run_keeps_floor`: `date_from` and `date_to` both None → ts scored 3.0 is dropped.
  - `test_attribution_suspect_recorded_on_assessment`.
- [ ] **Step 3:** Run. Expected: FAIL.
- [ ] **Step 4:** Implement; pass `allowlist` and `cache_dir` from `cli`.
- [ ] **Step 5:** Run `test_taperssection_winnow.py test_pipeline.py test_prompts.py` and the full suite. Expected: PASS.
- [ ] **Step 6:** Commit: `feat(taperssection): winnow by age-adjusted downloads, separate ts batches`

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
- Modify: `packages/llama/src/llama/pipeline.py`: `process_show` gains a required keyword `allowlist: Allowlist` and passes it to select and gather.
- Modify: `packages/llama/src/llama/cli.py`: the `process_show` callers pass `Allowlist.from_config(config.taperssection)`:
  - `cli.py:592` `_process`;
  - `cli.py:3288` `_redo_show`, which serves `redo`, `fix`, triage and the adjudicator's `_redo_show_locked`.
- Test: `packages/llama/tests/test_taperssection_select.py`

**Interfaces:**
- `run_select_recording(..., allowlist: Allowlist | None = None, today: date | None = None) -> str`. The entry comes from `Allowlist.for_candidate`. For a ts candidate:
  - each recording is classified with `ts_rules.classify` over the candidate's `RecordingSummary`, and `score_recording`'s lineage for ts tapes is that class;
  - recordings with `allowed == "forbidden"` or `excluded` are removed before scoring;
  - `unknown` ones are removed when any `allowed` recording remains, except a pinned one;
  - `downloads_norm` uses `ts_measure.rate` (None → 0), normalised as today;
  - removed recordings never appear in `scores`;
  - an empty remaining set raises `LlamaError(f"{pid}: no recording allowed by the taperssection policy")`;
  - a pin (`overrides.recording`) naming a removed forbidden or excluded recording raises `LlamaError(f"{pid}: pinned recording {ident} is forbidden by the taperssection policy")`;
  - a pin to an `unknown` recording keeps it in the scored set: it appears in `scores` and is selected, and gather holds it (Task 10).
- `selection.json` gains `"ts_lineage": {ident: class}` for ts candidates only.

- [ ] **Step 1: Failing tests:**
  - `test_forbidden_never_in_scores`.
  - `test_unknown_excluded_when_allowed_sibling`.
  - `test_unknown_competes_when_alone`.
  - `test_empty_set_raises_llamaerror_not_valueerror`.
  - `test_pin_to_forbidden_raises`.
  - `test_pin_to_unknown_selected`: a pin to an unknown recording with an allowed sibling present → it is in `scores` and selected, no error.
  - `test_adjudicator_switch_to_forbidden_raises`: apply a `switch_recording` verdict through `adjudicator/apply.py` onto a ts show whose target is sbd under an aud-only entry, driving the real `_redo_show_locked` → `process_show` path → the show is restored and the error surfaced.
  - `test_process_show_requires_allowlist`: calling `process_show` without `allowlist` is a `TypeError`.
  - `test_rate_tiebreak`.
  - `test_lma_selection_unchanged`: the gd73-06-10 selection.json scores are equal with and without an allowlist.
- [ ] **Step 2:** Run. Expected: FAIL. **Step 3:** Implement. **Step 4:** Run `test_taperssection_select.py test_cli_select.py test_adjudicator_apply.py` and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(taperssection): select policy filter, pins, rate tiebreak`

---

### Task 10: Holds, overrule kinds, adjudicator bars, replay

**Files:**
- Modify: `stages/gather.py` (`compute_gather`/`run_gather`: new keyword `assessment: QualityAssessment | None = None`)
- Modify: `pipeline.py` (pass `entry.assessment`)
- Modify: `replay.py` (`compute_legs` passes `prov.assessment` and the allowlist to `compute_gather`; `config_fingerprint` folds `allowlist.fingerprint()` only when it is not None; `_FAMILIES` entries)
- Modify: `reapply.py`: pass `Allowlist.from_config(config.taperssection)` to `compute_legs`.
- Modify: `overrules.py` (`_PATTERNS`), `adjudicator/gate.py` (`OVERRULE_BAR`)
- Test: `packages/llama/tests/test_taperssection_holds.py`

**Decisions.** This narrows the spec's carrier wording; same effect, fewer stored fields:

- The unknown-lineage verdict is **recomputed in gather** with `ts_rules.classify` over `candidate.recordings` (which carry the classification fields, and come from `provenance.json`), the selected identifier and the allowlist. It uses the same classification input as select (Task 9). Gather therefore needs no new stored field, and replay reproduces it from provenance automatically.
- The misattribution verdict comes from `assessment.attribution`, passed explicitly. For a ts show, `attribution is None` counts as suspect, with reason `"scorer gave no attribution verdict"`.
- Flag strings:
  - `f"unclassified lineage for {name} (allowed: {', '.join(lineages)}): {identifier}"`, kind `lineage-unknown`, subject mode `raw` (the identifier);
  - `f"possible misattribution: {reason}"`, kind `misattribution`, subject mode `none`.
- `OVERRULE_BAR`: `"lineage-unknown": "never"`, `"misattribution": "medium"`.
- `_FAMILIES`, one entry per flag:
  - `("lineage-unknown", lambda f: f.startswith("unclassified lineage for"))`;
  - `("misattribution", lambda f: f.startswith("possible misattribution:"))`.

- [ ] **Step 1: Failing tests:**
  - `test_gather_flags_selected_unknown`.
  - `test_gather_flags_misattribution`.
  - `test_gather_flags_missing_attribution`: the fake scorer omits the field → gather flags `possible misattribution: scorer gave no attribution verdict`.
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
  - `cli._print_shortlist` (`cli.py:~189`): the shortlist column prints `entry.name` for ts candidates. Its caller builds an `Allowlist` from config and passes it down;
  - `catalog.py:309`, `:395`: the artist fallback uses `entry.name`;
  - `llama show`/`status`: grep `cli.py` for `.collection` used as an artist label; each such site prints the display name, and the commit message lists each site.
- Modify docs:
  - `packages/llama/CLAUDE.md`: a new "Taper's Section allowlist" bullet covering the config shape, the `ts-` key, the rename caveat, the rules, holds and bars, the known limitations (per-set items; an artist later gaining an LMA collection; unclassified source lines; the newest tour deferred by the 75-day rule; discovery reaching `jam`/`dead-family`) and the evidence-doc paths;
  - the root `CLAUDE.md` table, only if a new script is added (`scripts/CLAUDE.md` entry for `taperssection_probe.py`).
- Test: extend `test_cli.py`/`test_catalog.py` with one assertion each that a ts candidate displays its name.

- [ ] **Step 1:** Write the failing display tests. **Step 2:** Run. Expected: FAIL. **Step 3:** Implement and update the docs. **Step 4:** Run the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `taperssection: display names, docs`, with the grepped `show`/`status` sites listed in the body.

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
  - then run the two-arm replay per `scripts/CLAUDE.md`, read-only over the operator library, with output under `~/.llama-harness/taperssection/`:
    - baseline arm from `main` at the merge base, with its own interpreter;
    - branch arm with an empty allowlist.
  - Expected: `compare` shows no outcome change. List and explain each digest/fingerprint difference (null-key churn is expected). `compare` exits 2 on any digest difference, so read its output rather than its exit code.
- [ ] **Step 3: Live smoke (operator approves):** use a scratch config, `llama --config <scratchpad>/ts-config.toml`, holding a Phish and a Warren Haynes entry. Never touch `~/.llama/config.toml`.
  - `llama get "Phish 1997-11-22" --plan` resolves to `ts-phish` and lists candidates;
  - an `llama artists "blues rock"`-style query lists Warren Haynes.

  Record the output in `acceptance.md`.
- [ ] **Step 4: Per-set items:** find a Phish date whose only allowed recordings carry a `set2`/`partial` token. Run it offline. Does an existing hold (structure, research-sets) catch it? Record yes or no. If no, record it as a known limitation in `packages/llama/CLAUDE.md`, with no new mechanism.
- [ ] **Step 5:** In `acceptance.md`, mark spec Success #1 (profile runs that deliver) as operator follow-up after the research round.
- [ ] **Step 6:** Commit: `taperssection: acceptance evidence`

---

## Not in this plan

- **The research round.** It is separate from the build (spec "The research round"): Sonnet research workers per artist, Opus synthesis, a committed record named e.g. `docs/superpowers/2026-11-09-taperssection-evidence/artist-policies.md`, plus suggested `[[taperssection.artists]]` entries. The operator pastes in the approved entries. Run it after Task 12, or in parallel with the build.
- **The `phish` and `garcia` profiles.** Operator work after the build, first runs with `human_gate = true`. Spec Success #1 (profile runs that deliver) is verified here, not in Task 12.
