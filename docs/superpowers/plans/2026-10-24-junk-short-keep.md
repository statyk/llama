# Keep short files that belong to the show (held-backlog piece 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the short files the junk filter's duration arm drops today when they belong to the show (spoken band material, segue pieces, reprises, short songs), drop the junk ones by tag, keep spam out with a tripwire, and re-key the three positional overrides by filename so an inserted track can never move an operator's title, break or encore onto another file.

**Architecture:** The rule lives in `junk._keep_and_exclude` (pure functions ported verbatim from the spec, plus the interior test), so every `filter_files` caller gets it; `filter_files` reports what it kept as `ordering["short_kept"]`, `resolve_titles` stamps `Track.short_kept`, and `structure._songish_coverage` leaves those tracks out. The positional overrides keep their key names with filename values: a new `llama/override_keys.py` owns the legacy-value test, the raw re-key mapping and the one resolver `compute_gather` calls (through `title_inputs`), and every writer translates the track numbers the operator saw in `show.json` into filenames. Section 5's pieces this branch owns are a reworked `replay.briefing_reusable`, a new `llama/audio_reuse.py` that re-uses already-downloaded audio inside every re-packaging unit, and the `deliver` safety changes. The one-off migration is `scripts/rekey_overrides.py` (dry run, `--snapshot`, `--apply`, `--restore`).

**Gate ordering.** Tasks 1-2 make the rule live and wire `short_kept` and coverage. Tasks 3-5 re-key the overrides (model, resolver, writers). Tasks 6-8 are harness and probe code only. Task 9 measures (CHECKPOINT A). Tasks 11-14 are section 5's library side; Task 15 is CHECKPOINT B, before Task 16 touches `deliver`. Tasks 17-20 are the migration. Tasks 21-23 close (CHECKPOINT C). No task touches `~/.llama` or the station except read-only probes that say so.

**Tech Stack:** Python 3.11+, pydantic v2, pytest, typer; offline tests (`herder.FakeProvider`, captured fixtures, `test_stage_gather`'s `StubIA`, `fixture_library.library_show`, `helpers.build_ready`).

**Spec:** `docs/superpowers/specs/2026-10-23-junk-short-keep-design.md` (review mode Opus). Every implementer reads the spec sections their task names, this task, Global Constraints and Review Focus. Evidence: `docs/superpowers/2026-10-23-junk-short-keep-evidence/` (`decisions-r1/r2/r3.md`, `r-INSTRUCTIONS.md`, `voiced-severe-final.json`, `voiced-minor-final.json`). Reference harness (read-only): `~/.llama-harness/piece45/spec/r1/` (`arm_base.jsonl`, `arm_r1.jsonl`, `r1_files.jsonl`, `r1_sibs.json`, `m3_cmp.py`, `m6_final.py`, `reuse_r1.py`, `dump_r1.py`, `rprime2.py`).

## Global Constraints

- **Untouched, byte-identical:** `junk.SHORT_FRACTION_OF_MEDIAN`, `MIN_MEDIAN_SAMPLE`, `MIN_PLAUSIBLE_SEC`, `_stem`, `_track_number`, the two-pass floor, the convention/provenance/`missing duration` arms, `_dedupe_duplicate_listings`, `filter_files`' format choice and the position of `readmit`; `junk.FORMAT_BY_AUDIO`, `LOSSLESS_TITLE_FORMATS`; `structure.is_filler`/`_FILLER`, `TAUTOLOGICAL_TITLE_SOURCES`; `titles.clean_tag_title`, `is_real_title`, `_TRACK_NUM_PREFIX`; every piece-3 fixed constant (CLAUDE.md "Title hygiene"); `package.DURATION_TOLERANCE_S = 5.0`; `catalog.purge_package_audio`'s verification. Every code-quality review greps the diff for these names.
- **Normative code.** Spec 2.3's regexes (`LEAD`, `TIME_PAREN`, `SPLIT`, `EDGE`, `JUNK_PART`, `NONPERF`, `SPAM`, `SPAM_STEM`, `SPAM_TAG`) and functions (`parts`, `short_tag_is_junk`, `short_is_spam`) are ported into `junk.py` character for character. `basename_without_extension(name)` is `re.sub(r"\.[A-Za-z0-9]+$", "", name.rsplit("/", 1)[-1])` (as measured, `rprime2.stem`).
- **Fixed strings:**
  - tripwire drop reason: `spam-shaped name or tag`;
  - junk note (notes.json): `short-kept track <n> '<title>': its final title is wholly junk`;
  - legacy refusal: `<slug>: overrides.json uses track-number keys; run the migration`;
  - mixed refusal: `<slug>: overrides.json mixes track-number and filename keys (filename-valued: <key> <file>, ...); undo the hand edit`;
  - dangling refusal (one message): `<slug>: overrides name files not in the track list: <key> <file>, ...; clear them with llama fix <slug> --clear-title <file> / --clear-set-breaks / --clear-encore`, where `<key>` is `titles`, `set_breaks` or `encore_after`;
  - staleness refusal: `<slug>: show.json's track list is not what gather keeps now; re-gather under the new rule first (llama redo <slug> --from gather)`;
  - exclusion refusal: `<slug>: <file> carries overrides.<key>; clear it first with llama fix <slug> <flag>`, `<flag>` being `--clear-title <file>`, `--clear-set-breaks` or `--clear-encore`;
  - deliver selector refusal: `--replace-voiced takes one named show, never a selector`;
  - unreadable destination: `refusing to deliver <slug>: cannot read <out>/manifest.json (<error>); check the station copy by hand`.
- **New fields, all defaulted, permissive:** `Track.short_kept: bool = False` (show.json only; never in `ManifestTrack`); `ordering["short_kept"]: list[str]` (always present, `[]` with `short_keep=False`); `TitleInputs.positions: Positions`; `ShowReplay.filenames`, `short_kept`, `flags` (Task 6). `Overrides` changes types only (Task 3).
- **Lock order** run ⊃ show ⊃ ledger is unchanged; `process_show` stays lock-free. The migration lock `<root>/.rekey.lock` is outermost and is taken only by `scripts/rekey_overrides.py`.
- **Tests** run from the worktree root as `./.venv/bin/python -m pytest …` (CLAUDE.md: never a bare `pytest`, never `.venv/bin/*` from a copy). Each task ends with the full suite green: `./.venv/bin/python -m pytest -q`. Baseline: the line Task 0 records.
- Every behavioural change gets a test that fails on today's code; a pin is marked **(pin)**. A task whose change moves existing expectations does the **dry run** first: list every test whose expectation changes, each tied to a spec clause, report it before editing, and treat an unexplained change as BLOCKED (never resolved by editing a fixture).
- **Never write to `~/.llama` or `/Volumes/media/lma-radio/delivered/`.** Harness and probe output goes under `~/.llama-harness/piece4/`. No task runs `reapply`, `deliver`, `rm`, `fix`, `redo`, `emcee` or the migration's `--snapshot`/`--apply`/`--restore` on the live library. The migration's dry run is read-only and may run against it (Task 22). Merge, push, tag, release, migration, bulk apply and deliveries are the operator's (Appendix).
- One commit per task, ending with the attribution trailer the orchestrating session specifies. Status reports to the parent list every dispatch since the last report with its model.

## Review Focus

1. **A derivative whose own `title` is empty but whose original's is set** (42 files in the library). Expected: the tag is the original's, cleaned; spam reads both. Test: Task 1 `test_tag_falls_back_to_the_original_title`.
2. **A short candidate that is also a duplicate listing.** Expected: dedupe still drops the second copy and it is not in `ordering["short_kept"]`. Test: Task 1 `test_short_kept_names_survive_dedupe_only`.
3. **`fix --exclude 3 --set-title 3=X` in one invocation.** Expected: refused up front (the title would name an excluded file), nothing written. Test: Task 4 `test_exclude_and_title_on_the_same_file_refuses`.
4. **A filename value with a directory prefix or spaces** (`<identifier>/gd74 d1t02.mp3`, `GD_022474_D3_T02.mp3`). Expected: `rekey_raw` and the resolver round-trip it exactly. Test: Task 3 `test_filename_keys_with_dir_prefix_and_spaces_round_trip`.
5. **Two tracks with the same title at different indexes, and a station manifest of the right length with one retitled index.** Expected: the pairing is by index, so the first copy pairs correctly; the retitled copy is not reused at all. Test: Task 12 `test_pairing_is_by_index_and_any_title_mismatch_drops_the_copy`.

---

### Task 0: Worktree venv and baselines (orchestrator, once)

**Files:** none in the repo.

- [ ] **Step 1:** `W=/Users/shawn/projects/llama/.claude/worktrees/junk-filter; cd "$W" && python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`.
- [ ] **Step 2:** `./.venv/bin/python -c "import llama; print(llama.__file__)"` prints a path under `$W/`.
- [ ] **Step 3:** `./.venv/bin/python -m pytest -q` passes; record the exact summary line in the SDD ledger as the baseline.
- [ ] **Step 4:** `mkdir -p ~/.llama-harness/piece4`. The base tree is made in Task 9 Step 1.

---

### Task 1: The filter rule

**Spec:** 1, 2.1-2.5 (except `Track.short_kept` and the junk note, Task 2), strict surface (c). **Implementer: Opus** (strict surface; the dry run across gather fixtures needs judgment).

**Files:** Modify `packages/llama/src/llama/junk.py`; Create `packages/llama/tests/fixtures/short_keep_corpus.jsonl`, `packages/llama/tests/fixtures/junk_v2_17_0.py`; Test `packages/llama/tests/test_junk.py`, `packages/llama/tests/test_short_keep_rule.py` (new).

**Interfaces:**
- Produces (in `junk.py`):

```python
SPAM_REASON = "spam-shaped name or tag"
def parts(t: str) -> list[str]
def short_tag_is_junk(tag: str | None) -> bool
def short_is_spam(filename: str, own_title: str | None, original_title: str | None) -> bool
def short_filename_is_junk(filename: str) -> bool
    # short_tag_is_junk(re.sub(r"^[\d\s._-]+", "", basename_without_extension(filename)))
def short_verdict(filename: str, own_title: str | None, original_title: str | None,
                  *, interior: bool) -> str
    # "spam" | "junk" | "keep" | "filename" | "edge", decided in that order:
    # spam (tripwire) -> tagged: "junk" if short_tag_is_junk(tag) else "keep"
    # -> untagged: "filename" if short_filename_is_junk else ("keep" if interior else "edge")
def filter_files(files, want_format="VBR MP3", *, readmit=frozenset(),
                 short_keep: bool = True) -> tuple[list[dict], list[dict], dict]
```
- `ordering["short_kept"]`: sorted names the rule kept that are in the returned `kept` (after dedupe and readmit).

- [ ] **Step 1: Build the corpus fixture.** One read-only one-liner over `~/.llama-harness/piece45/spec/r1/r1_files.jsonl` writing `{"slug", "name", "tag", "pos", "r1_dec"}` per row (3,547 rows) to `short_keep_corpus.jsonl`. Record its row count and sha256 in the commit message.
- [ ] **Step 2: Write the failing tests** (`test_short_keep_rule.py`):
  - `test_deny_vocabulary_corpus` (strict): for every corpus row, `short_verdict(name, tag, None, interior=(pos == "interior"))` is `"keep"` exactly when `r1_dec` starts with `keep`; `drop-junk` and `drop-nonperf` rows give `"junk"`; `drop-filename` gives `"filename"`; `drop-edge` gives `"edge"` or `"filename"`. Assert the totals: 2,822 keep, 685 junk, 3 filename, 37 edge-or-filename.
  - `test_junk_test_examples`: kept (not junk): `intro/tuning`, `tuning/banter`, `Take A Step Back/Tuning`, `Mexican Hat Dance Tuning`, `crowd/tuning jam`, `Bob Weir comment to crowd`, `Stage Announcements`, `Banter Promote CD`, `banter - promoting the new CD`, `Stage Banter: Consummation Station`, `Mohammed's Radio`, `Radio Blues`, `Jesus on the Radio`, `Radio Free Europe`, `DJ Logic / Jam`; junk: `crowd/tuning`, `Crowd & Tuning`, `2: crowd/tuning ->`, `Radio Outro`, `radio ID`, `tuning`, `Tunning`; `short_tag_is_junk("")` and `short_tag_is_junk("--")` are False (empty cleaning is not junk).
  - `test_tripwire_examples`: spam: a stem with `http://`, `www.x`, `foo.com`, `@bypikeno`, `follow`, `download`, `subscribe`; a tag `Follow me on X`, `follow us`; not spam: tag `John follows his fingers`, `I'll Follow the Sun`, `Follow You Down`, stem `bwww1996-12-31t01`, album/artist strings never read (the function has no parameter for them).
  - `test_tripwire_drop_records_its_own_reason`: a short file named `follow-me-now.mp3` in an otherwise clean item is excluded with `reasons == ["spam-shaped name or tag"]`; an untagged edge file keeps `["implausibly short"]`.
  - `test_untagged_interior_kept_edge_dropped`: in a 7-file item, an untagged short file between two kept files is kept; untagged short first and last files drop with `implausibly short`.
  - `test_interior_uses_track_tag_order_only_when_complete_and_unique`: filenames out of track-tag order; with unique tags over the kept, tagged-kept and untagged candidates the interior test follows the tags; with one duplicate tag it follows filename order.
  - `test_filename_junk_drops_untagged_only`: untagged interior `10 Crowd.mp3` and `0201tuning.mp3` drop; a tagged `10.tuningup.mp3` whose tag is `tmp` is kept (spec 2.2: placeholders count as tagged).
  - `test_tag_falls_back_to_the_original_title` (Review Focus 1): a derivative with no `title` whose original's title is `Drums` is kept; one whose original's is `tuning` drops.
  - `test_short_kept_names_survive_dedupe_only` (Review Focus 2).
  - `test_other_reasons_untouched` **(pin)**: a short file that also fails the convention arm keeps both reasons and stays excluded; `FOLLOW-ME @BYPIKENO.mp3` in the gd73 fixture is still excluded with its convention reason.
  - `test_short_keep_false_reproduces_today` **(pin)**: over every fixture under `tests/fixtures/*.json` that has `files`, for `mp3` and `flac`, `filter_files(..., short_keep=False)` returns exactly what e37f670's `filter_files` returns (vendored as `tests/fixtures/junk_v2_17_0.py`, the file verbatim with a header naming the commit), apart from the added `ordering["short_kept"] == []`.
  - `test_floor_unchanged_by_kept_short_files` **(pin)**: a kept short file does not change the floor (the reported `duration_sec`s and the excluded set of a second, still-short file are identical with and without the first file's tag).
- [ ] **Step 3:** Run `./.venv/bin/python -m pytest packages/llama/tests/test_short_keep_rule.py -q` → FAIL (`ImportError`).
- [ ] **Step 4: Implement.** In `_keep_and_exclude(files, audio, *, short_keep)`: after the reasons loop, when `short_keep`, take every entry whose reasons are exactly `["implausibly short"]`; tag = `f["title"]`, else the original's `title` (`f["original"]` looked up among `files`); spam → reasons become `[SPAM_REASON]`; tagged non-junk → kept; untagged non-filename-junk → candidate. Play order for the interior test is over kept ∪ tagged-kept ∪ untagged candidates (spam and filename-junk files are not in it): by `_track_number` when every one is non-None and unique, else by name. An untagged candidate is kept when some kept or tagged-kept file is before it and another after it. Kept files rejoin `kept` (sorted by name, as today); `filter_files` threads `short_keep` and builds `ordering["short_kept"]` from the names the rule kept that are in the final `kept`.
- [ ] **Step 5: Dry run before editing any existing test.** Run the full suite and list every failing test with its spec clause. Expected: tests built on `dso2003-01-25.json` (`Announcements` kept), `furthur2012-07-15.json` (`10.tuningup.mp3`, tag `tmp`, kept and 2b-demoted), `gd1970-02-14_spans_metadata.json` and `gd74_miller_metadata.json` (`Introduction` kept), `gd74_windsor_metadata.json` (`Weather Report Suite Part I >` kept), `rre2013-11-30.json` (two `Banter` files kept); `test_junk.py` tests asserting a short drop; any test asserting the exact `ordering` dict (the new key). `gd73_metadata.json` has no short-only drop and its tests must not change. Then update each listed test with a comment naming its clause.
- [ ] **Step 6:** Run the full suite → PASS.
- [ ] **Step 7:** Commit `feat(junk): keep short files that belong to the show (piece 4 rule)`.

---

### Task 2: `Track.short_kept`, coverage and the junk note

**Spec:** 2.5 (`Track.short_kept`, the junk note), 3. **Implementer: Sonnet.** Touches `structure.py`, `titles.py`, `gather.py`.

**Files:** Modify `packages/llama/src/llama/models.py` (`Track`), `titles.py` (`resolve_titles`), `structure.py` (`_songish_coverage`), `stages/gather.py` (the cascade call and the note); Test `test_stage_gather.py`, `test_structure.py`, `test_titles.py`.

**Interfaces:**
- Consumes: `ordering["short_kept"]`, `junk.short_tag_is_junk` (Task 1).
- Produces: `Track.short_kept: bool = False` (after `included`); `resolve_titles(..., short_kept: frozenset[str] = frozenset())` stamps `short_kept=f["name"] in short_kept`; `title_cascade` passes `frozenset(inp.ordering.get("short_kept", ()))`; `_songish_coverage`'s comprehension gains `and not t.short_kept` (no other filter).

- [ ] **Step 1: Write the failing tests:**
  - `test_resolve_titles_stamps_short_kept` (test_titles.py).
  - `test_songish_coverage_ignores_short_kept` (test_structure.py): two matched songs plus one unmatched `short_kept` `Jam >` → 1.0; the same track not short-kept → 0.667.
  - `test_unmatched_short_kept_track_does_not_lower_coverage` (test_stage_gather.py, the spec's gather-level test): a fixture tape whose kept short file (a tagged `Murph` absent from the canonical) is unmatched; `structure.coverage` equals the coverage of the same show with that file excluded, and no `low-confidence structure alignment` flag.
  - `test_short_kept_survives_to_show_json`: through `align()`, the structure-override path (`set_breaks` given) and taper ownership, the final `show.json` track carries `short_kept=True`; `ManifestTrack` has no such field **(pin)**.
  - `test_wholly_junk_final_title_notes`: a short-kept untagged interior file that setlist-gap names `(crowd)` produces the fixed junk note in `notes.json`; the same title on a non-short-kept track produces none.
  - `test_old_show_json_reads_short_kept_false` **(pin)**.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.** Grep every `Track(` construction in `packages/llama/src` (today `titles.py` and `title_hygiene.py`'s neighbour list, which is internal and never shipped) and confirm every later rung copies tracks with `model_copy`, so the stamp survives. The note is appended to `op_notes` right after slice 5's `strip_notes`, once per short-kept track whose final title `short_tag_is_junk` judges junk.
- [ ] **Step 4:** Dry run as in Task 1 Step 5 (expected: only tests whose coverage or flags move because a short-kept track is now excluded from coverage). Then full suite → PASS.
- [ ] **Step 5:** Commit `feat(gather): short_kept tracks, coverage clause, wholly-junk note`.

---

### Task 3: Filename-valued overrides: model, keys module, resolver, writer translation

**Spec:** 4.1 (all of it), 4.2 "Writers take track numbers" (translation only). Strict surface (a). **Implementer: Opus.** Touches `gather.py`.

**Files:**
- Create: `packages/llama/src/llama/override_keys.py`; `packages/llama/tests/fixtures/overrides_v2_17_0.py` (e37f670's `Overrides` class verbatim, renamed `OverridesV2170`, with a header naming the commit).
- Modify: `models.py` (`Overrides` types), `stages/gather.py` (`title_inputs` gains `slug`, builds `positions`; `title_cascade` and `compute_gather` read `inp.positions`), `cli.py` (`_edit_overrides` only), `scripts/title_hygiene_probe.py` (passes `slug=`).
- Test: `packages/llama/tests/test_override_keys.py` (new), `test_stage_gather.py`, `test_fix.py`, `test_catalog.py`, and every existing test that writes a positional `overrides.json` (converted to filename values).

**Interfaces:**
- Produces:

```python
# models.Overrides
titles: dict[str, str] = Field(default_factory=dict)       # filename -> forced title (legacy: track number)
set_breaks: list[int | str] | None = None                  # filenames a break falls after (legacy: numbers)
encore_after: int | str | None = None                      # filename the encore follows (legacy: number)

# llama/override_keys.py
POSITIONAL_KEYS = ("titles", "set_breaks", "encore_after")
def legacy_int(v: object) -> int | None
    # v2.17.0's own rule: TypeAdapter(int).validate_json(json.dumps(v)) (lax, JSON mode, as
    # read_model reads), else None. A titles key is judged as the JSON string it is.
def classify(data: Mapping[str, object]) -> str        # "none" | "legacy" | "filename" | "mixed"
    # over titles keys, set_breaks items, encore_after; `set_breaks: []`/None and a missing
    # or None encore contribute nothing. Takes json.loads output or Overrides.model_dump().
def filename_values(data: Mapping[str, object]) -> list[tuple[str, str]]   # (key, filename)
def rekey_raw(raw: dict, filenames: Sequence[str]) -> dict
    # the migration's mapping: a copy of `raw` with each legacy value N replaced by
    # filenames[N - 1]; only the three keys change, key order and every other key kept;
    # IndexError on N outside 1..len(filenames) (callers check first)
@dataclass(frozen=True)
class Positions:
    titles: dict[int, str]
    set_breaks: list[int] | None
    encore_after: int | None
def resolve_positions(ov: Overrides, kept_names: Sequence[str], *, slug: str) -> Positions
    # raises LlamaError: mixed (first), legacy, dangling (every key in one message)
```
- `title_inputs(..., slug: str)` computes `positions = resolve_positions(overrides, [f["name"] for f in kept], slug=slug)` after the exclusion; `TitleInputs.positions: Positions`. Every `overrides.titles`/`overrides.set_breaks`/`overrides.encore_after` read in `gather.py` becomes `inp.positions.*`; `_validate_structure_override` and `_sets_from_breaks` run unchanged on the positional values.
- `_edit_overrides` keeps its number-taking signature; it raises `LlamaError` (the legacy refusal) when the file holds a legacy value, and translates every number through `show.json` (`tracks[n - 1].filename`; `LlamaError("no track N (show has M tracks)")` out of range; `LlamaError` naming `llama redo <slug> --from gather` when `show.json` is absent and a number needs translating). `clear_titles` items that are not all digits are filenames, removed as given.

- [ ] **Step 1: Write the failing tests** (`test_override_keys.py` unless named):
  - `test_legacy_agrees_with_the_v2_17_0_model` (strict): for each of `"7"`, `" 7"`, `"07"`, `7`, `2.0`, `"2.0"`, `2.5`, `True`, `"gd73-06-10d1t01.mp3"`, `"Track 7"`, `""`: `legacy_int(v) is not None` exactly when `OverridesV2170.model_validate_json(json.dumps({"set_breaks": [v]}))` succeeds; the same for a `titles` key (where `v` is a string).
  - `test_old_model_rejects_a_migrated_file` (strict): `OverridesV2170.model_validate_json` raises `ValidationError` on `{"titles": {"gd73-06-10d1t03.mp3": "X"}}`, on `{"set_breaks": ["gd73-06-10d1t03.mp3"]}` and on `{"encore_after": "gd73-06-10d1t05.mp3"}`.
  - `test_classify`: none (`{}`, `{"set_breaks": []}`, `{"set_breaks": null}`), legacy, filename, mixed (a legacy title plus a filename break).
  - `test_rekey_raw_maps_only_positional_keys_and_keeps_the_rest`: an unknown key `{"zz": [1, 2]}`, `exclude`, `narration` unchanged; `set_breaks: []` unchanged; key order unchanged.
  - `test_filename_keys_with_dir_prefix_and_spaces_round_trip` (Review Focus 4).
  - `test_resolver_refusals`: legacy → the legacy message; mixed → the mixed message naming each filename-valued key; two dangling keys (a title and the encore) → ONE `LlamaError` naming both and the three `--clear-*` routes.
  - `test_iter_shows_lists_legacy_migrated_and_mixed` (test_catalog.py): a library with one of each lists all three without raising.
  - `test_delmccoury_shape_through_gather` (test_stage_gather.py): 18 filename titles plus `set_breaks: []` → alignment `override`, `set_breaks == []`, each title on its file.
  - `test_gather_refuses_a_legacy_overrides_file` (test_stage_gather.py): `compute_gather` raises the legacy `LlamaError`.
  - `test_filename_title_follows_its_file_across_an_insertion` (test_stage_gather.py): a title keyed by file 5's filename stays on that file when Task 1's rule inserts a short file before it.
  - `test_set_title_writes_the_show_json_filename` (test_fix.py): `fix --set-title 3=X --no-run` writes `{"<show.json track 3 filename>": "X"}`; `--set-breaks 2,4` and `--set-encore 5` write filenames.
  - `test_edit_overrides_refuses_a_legacy_file` (test_fix.py): `_edit_overrides` raises the legacy message and leaves the file byte-identical.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4: Dry run.** List every existing test that fails, with its clause; expected: tests writing `overrides.json` with track-number keys and then gathering (convert their fixtures to the filename form, never to a refusal test unless that is the point), tests asserting stored `titles`/`set_breaks`/`encore_after` values (now filenames), `scripts/test_title_hygiene_probe.py` (the `slug=` argument). Then update them.
- [ ] **Step 5:** `grep -rn "\.titles\b\|\.set_breaks\b\|\.encore_after\b" packages/llama/src scripts` and list, in the commit message, every remaining reader of an `Overrides` positional field with why it is safe (spec 8 premise 5: no other positional key; `Show.set_breaks` and manifest `set_breaks` are play-order indexes, not overrides). `grep -rn "overrides" packages/emcee/src packages/transmitter/src` finds no reader.
- [ ] **Step 6:** Full suite → PASS.
- [ ] **Step 7:** Commit `feat(overrides): filename-valued positional overrides, one resolver`.

---

### Task 4: The shared kept-list helper and `fix`'s writer rules

**Spec:** 4.1 "Writers refuse legacy", 4.2 (writers, staleness, behaviour change, no `show.json`, exclusion refusal, dangling-key repair). **Implementer: Opus** (strict surface; `cli.py` control flow).

**Files:** Modify `stages/gather.py` (`final_kept`, used by `title_inputs`), `cli.py` (`fix`, `_propose_titles_for_show`, helpers); Test `test_fix.py`, `test_stage_gather.py`.

**Interfaces:**
- Produces:

```python
# stages/gather.py
@dataclass(frozen=True)
class FinalKept:
    unexcluded: list[dict]     # filter + include, before overrides.exclude (recovery_basis's input)
    kept: list[dict]           # gather's final kept list, in play order
    excluded: list[dict]
    ordering: dict
def final_kept(files: list[dict], overrides: Overrides, want: Sequence[str], *,
               short_keep: bool = True) -> FinalKept
    # title_inputs' filter / include / exclude block moved here verbatim (warnings included)

# cli.py
def _refuse_legacy(sws, slug: str) -> None                         # typer.Exit(1) with the legacy message
def _stale(ia, config, sws, slug: str) -> str | None               # the staleness message, or None
def _keyed_files(sws, extra: Mapping[str, str] = {}) -> dict[str, str]
    # filename -> "titles" | "set_breaks" | "encore_after", stored keys plus this invocation's
```
- `fix`: `_refuse_legacy` runs first, before any flag parsing, prompt or lock, for every invocation. The positional flags (`--set-title`, `--set-breaks`, `--set-encore`, `--suggest-titles`, `--untitled`, and a numeric `--clear-title`) refuse without `show.json` (existing `refuse_no_show_json` text); all but the numeric `--clear-title` then run `_stale` before any prompt. `--clear-title <filename>`, `--clear-set-breaks` and `--clear-encore` skip `_stale` and work without `show.json`. Before the unit, `--exclude` targets (numbers through `show.json`, filenames as given) are checked against `_keyed_files(sws, this invocation's new title/break/encore files)`; a hit refuses with the exclusion message, with or without `--no-run`. `_propose_titles_for_show` computes its `kept` with `final_kept` (its C1 decline stays as a second line of defence).

- [ ] **Step 1: Write the failing tests** (test_fix.py unless named):
  - `test_title_inputs_unchanged_by_final_kept` **(pin)** (test_stage_gather.py): `title_inputs` on the gd73 fixture with include and exclude gives the same `kept`, `excluded`, `ordering`, `recovery_basis` as before the refactor (literal expectations).
  - `test_every_fix_flag_refuses_a_legacy_file`: parametrised over `--set-venue X`, `--exclude 1`, `--include x1`, `--narration vague`, `--set-title 1=X --no-run`, `--suggest-titles`, `--untitled`, `--overrule`: exit 1, the legacy message, `overrides.json` byte-identical, no prompt shown (`input=""`).
  - `test_positional_edit_refuses_when_stale`: a show whose `show.json` lacks a short file the rule now keeps → `--set-title 2=X` exits 1 with the staleness message, nothing written; `--clear-set-breaks` on the same show succeeds.
  - `test_exclude_then_title_numbers_are_show_json_numbers` (the spec's behaviour change): `fix --exclude 3 --set-title 7=X --no-run` → `titles == {<show.json track 7 filename>: "X"}`.
  - `test_exclude_and_title_on_the_same_file_refuses` (Review Focus 3).
  - `test_exclusion_refuses_a_keyed_file`: parametrised over `--exclude 4` and `--exclude <filename>`, each with and without `--no-run`, on a file carrying a title, a break and the encore in turn: exit 1, the exclusion message with the right `--clear-*` flag, nothing written.
  - `test_clear_flags_work_without_show_json`: no `show.json`, a dangling filename title, break and encore → `--clear-title <filename>`, `--clear-set-breaks`, `--clear-encore` each remove their key; `--set-title 1=X` refuses naming `llama redo`.
  - `test_suggest_titles_kept_list_comes_from_final_kept`: patch `gather.final_kept` to record its call; `--suggest-titles` calls it once with the stored overrides.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Dry run (expected: `test_fix.py` tests that ran positional edits on shows whose `show.json` the fixture never re-gathered under the new rule; fix the fixture by gathering, never by skipping the check). Full suite → PASS.
- [ ] **Step 5:** Commit `feat(fix): writers translate show.json numbers, refuse legacy and stale positional edits`.

---

### Task 5: Triage's writer rules and the readers' display

**Spec:** 4.1 "Writers refuse legacy" (triage), 4.2 "Exclusion refuses up front", "Readers" (`llama show`, triage's current-values line). **Implementer: Sonnet.**

**Files:** Modify `cli.py` (`_interactive_resolve`, `_metadata_editor`, `_pick_excludes`' caller); Test `test_triage.py`, `test_show_cmd.py`.

**Interfaces:**
- Consumes: `_refuse_legacy`'s check (reuse its predicate, not its `Exit`), `_stale`, `_keyed_files` (Task 4).
- Produces: `_interactive_resolve` prints `error: <legacy message>` and returns before the resolve prompt on a legacy file. `[m]`, `[t]` and `[u]` run `_stale` before their own prompts (`error: …`, back to the prompt). `[e]` checks the picked files with `_keyed_files` (`error: <exclusion message>`, back to the prompt). `_metadata_editor`'s `title overrides` default renders `N=Title` with `N` the `show.json` index of each filename key; `cur_breaks` likewise.

- [ ] **Step 1: Write the failing tests:**
  - `test_triage_skips_a_legacy_show_before_any_prompt` (test_triage.py): two held shows, the first legacy → its error line, then the second show's prompt; the legacy file is byte-identical.
  - `test_triage_metadata_line_shows_today_numbers`: filename titles on tracks 2 and 5 render `2=A, 5=B`; accepting the default writes the same filenames back unchanged.
  - `test_triage_positional_choice_refuses_when_stale` (`[m]`, `[t]`, `[u]` each).
  - `test_triage_exclusion_refuses_a_keyed_file`.
  - `test_show_prints_the_stored_mapping` **(pin)** (test_show_cmd.py): `llama show` and `llama show --json` print the filename-keyed `titles`, `set_breaks`, `encore_after` as stored.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Full suite → PASS.
- [ ] **Step 5:** Commit `feat(triage): legacy, staleness and keyed-exclusion refusals; numbers in the metadata line`.

---

### Task 6: Replay record fields and the harness re-key

**Spec:** 4.2 "The harness re-key", "Readers" (the strip options and probes), 6(a). **Implementer: Sonnet.** Scripts plus `replay.py`'s record only.

**Files:** Modify `packages/llama/src/llama/replay.py` (`ShowReplay`, `replay_show`), `scripts/replay_holds.py` (`run --rekey-overrides`, `_shadow`, `compare`), `scripts/taper_probe.py`, `scripts/title_hygiene_probe.py`; Test `test_replay.py`, `scripts/test_replay_holds.py`, `scripts/test_taper_probe.py`, `scripts/test_title_hygiene_probe.py`.

**Interfaces:**
- Consumes: `override_keys.classify`, `rekey_raw` (Task 3).
- Produces:
  - `ShowReplay.filenames: list[str]`, `short_kept: list[bool]` (per track of `gathered.show`), `flags: list[str]` (`legs.flags`); base rows (e37f670) lack them and readers treat them as absent.
  - `replay_holds.py run --rekey-overrides` (combinable with both strip options): every show is replayed through `_shadow`; when the source `overrides.json` classifies `legacy`, the shadow's file is `rekey_raw(raw, [t["filename"] for t in show.json tracks])`, re-key first, then strip. Any re-key failure copies the file unchanged and records `row["rekey_error"]`. Row key `rekeyed: bool`; arm header `overrides_rekeyed: true`. It never touches `compute_legs`.
  - `compare` accepts a rekeyed candidate against a base arm without the flag, and writes no apply lists when either arm is rekeyed (their digests predate the migration; spec 4.3 step 8).
  - `taper_probe.py` and `title_hygiene_probe.py` translate a filename-valued `set_breaks`/`encore_after`/`titles` key to its 1-based position through the row's `filenames` (or the shadow's `show.json`) before comparing; an int value is used as is (base arms).

- [ ] **Step 1: Write the failing tests:** `test_record_carries_filenames_short_kept_and_flags` (test_replay.py); `test_rekey_shadow_maps_legacy_and_leaves_the_library_alone` (the live file's hash unchanged, the shadow's titles keyed by filename, `rekeyed` true); `test_rekey_then_strip`; `test_rekey_failure_is_recorded_not_raised` (a title key beyond the track count); `test_compare_accepts_rekeyed_candidate_and_writes_no_apply_lists`; `test_taper_probe_translates_filename_breaks`; `test_title_hygiene_probe_reads_filename_titles`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Full suite → PASS.
- [ ] **Step 5:** Commit `feat(harness): --rekey-overrides and the piece-4 record fields`.

---

### Task 7: Probe, arm reports

**Spec:** 6(a), 6(b), 6(d), 6(e), 4.3 "Harness and apply lists" (the repro check), 8 premise 1. **Implementer: Sonnet.**

**Files:** Create `scripts/short_keep_probe.py`, `scripts/test_short_keep_probe.py`.

**Interfaces:**
- `short_keep_probe.py arms --base BASE.json --cand CAND.json --ref-dir ~/.llama-harness/piece45/spec/r1 --out DIR` writes `arms.md` and `arms.json`:
  - **base consistency:** per show, the replay base row's `titles` and `gather_flags + vet_flags + brief_flags` against `arm_base.jsonl`'s track titles and `flags`; mismatches listed (a mismatch means the library moved since the reference ran; the operator reads them at Checkpoint A).
  - **reference reproduction:** per show, the candidate's `filenames`, `titles`, `title_sources`, `sets`, segues (from `segue_changes` applied to the stored show, as `replay_holds._arm_titles` does for titles) and `flags` against `arm_r1.jsonl`'s tracks (`file`, `title`, `src`, `set`, `segue`) and `flags`; every difference listed by show.
  - **tallies**, ported from `m3_cmp.py` with the candidate in place of `arm_r1.jsonl` and `arm_base.jsonl` as the base: unchanged, changed, files added, cleared, added, flags-changed, unreplayable; cleared and added by state; override tracks on a different file (6(d), expected 0); positional fills lost and gained (6(e), sources `desc-position` and `setlist`).
  - **added-hold classes** (6(b)), first match wins: `override shift`, `positional rung lost`, `new unresolved track`, `low confidence remains` (the only new flag is `low-confidence structure alignment`), `long single-set show` (a new flag starting `single-set structure for a long show`), `jerrybase closer not at a break` (starting `jerrybase set closer`), `other`. Expected counts `{new unresolved track: 18, long single-set show: 6, positional rung lost: 4, low confidence remains: 3, jerrybase closer not at a break: 2, other: 1}`; a class outside these, `override shift` non-zero, or a count above 1.25x expected prints `BLOCKS MERGE: <class> <n> (expected <m>)`.
  - every cleared show listed for the operator.
- `short_keep_probe.py repro --pre PRE.json --post POST.json --out DIR`: per show, `outcome` and `titles` equal; writes `repro.md`, exit 1 on any difference (the post-migration check, Appendix step 8).

- [ ] **Step 1: Write the failing tests** on small fake arms and a fake ref dir: `test_base_consistency_lists_mismatches`, `test_reference_reproduction_per_show`, `test_tallies_match_m3_definitions` (a hand-computed three-show case), `test_added_hold_classes_and_the_25_percent_rule`, `test_override_shift_blocks`, `test_repro_exit_codes`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (read-only; refuses an `--out` overlapping the config's library root, as `replay_holds._overlaps`). **Step 4:** Full suite → PASS.
- [ ] **Step 5:** Commit `feat(scripts): short-keep probe arm reports`.

---

### Task 8: Probe, hand-check packets and the vocabulary look

**Spec:** 6(c), 8 premises 2 and 3. **Implementer: Sonnet.**

**Files:** Modify `scripts/short_keep_probe.py`, `scripts/test_short_keep_probe.py`.

**Interfaces:**
- `packets --cand CAND.json --ref-dir R1 --out DIR [--seed 47]` writes `DIR/packet.jsonl` and `DIR/INSTRUCTIONS.md`. Rows are drawn from `r1_files.jsonl` joined to the candidate: kept = the file is in the candidate show's `filenames` with `short_kept`; dropped = not in it. Strata and sizes (spec 6(c)): kept `music` 10, `music-fragment` 5, `spoken` 10, `mixed-with-tuning` 6, untagged interior 8 (`r1_dec == "keep-untagged"`), placeholder-tagged 3 (`tagged` false and `rp_tagged` true in the row); dropped `drop-junk` 8, `drop-nonperf` 5, `drop-edge` 3, `drop-filename` 2. Each row has the `r_packets.py` item fields (neighbours in play order from the cached metadata through `CacheOnlyIA`, the description up to 3,000 characters), with `rule_would` in place of `rule_R_would`. The instructions are `r-INSTRUCTIONS.md`'s, with the rulings written into the direction: stage banter and band talk are kept; crowd-only and tuning-only drop; a broadcast DJ, interview, commercial, promo or station ID drops; an untagged file is kept only between two kept tracks; a placeholder tag (`Track 9`, `tmp`) counts as tagged.
- `score --packet DIR/packet.jsonl --answers ANSWERS.jsonl --out DIR` writes `score.md`: rows right / wrong, the bar (zero kept `spoken-broadcast` or `non-performance`, zero dropped `song`/`segue-or-continuation`/`fragment`, at least 90% `rule_right`), every wrong row, and `first10.md` (rows 1-10 for the operator, premise 2).
- `sibvocab --ref-dir R1 --out DIR` writes `sibvocab.txt`: every kept sibling short tag in `r1_sibs.json` (`tagged` true, `jc` null) matching `(?i)tun|crowd|applau|radio|\bdj\b|silen|noise|fade|commercial|promo|interview|station|static|hiss`, with its item id (premise 3).

- [ ] **Step 1: Write the failing tests:** `test_packet_strata_sizes_and_fields`, `test_packet_is_deterministic_for_a_seed`, `test_score_bar_and_wrong_rows`, `test_sibvocab_filters_kept_tags`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Full suite → PASS.
- [ ] **Step 5:** Commit `feat(scripts): short-keep hand-check packets and vocabulary look`.

---

### Task 9: Measurement (CHECKPOINT A)

**Spec:** 6(a)-(e), 8 premises 1-3. **Orchestrator**, with Sonnet hand-checkers and an Opus pre-screen. Writes only under `~/.llama-harness/piece4/` and `docs/superpowers/2026-10-23-junk-short-keep-evidence/acceptance.md`.

- [ ] **Step 1: Base tree.** `git worktree add --detach .claude/worktrees/junk-filter-base e37f670`; its own `.venv` as in Task 0 Step 1; `llama.__file__` resolves inside it; `git diff e37f670 HEAD -- packages scripts` there is empty.
- [ ] **Step 2: Arms, before any migration, on the legacy library.** Base: `<base>/.venv/bin/python <base>/scripts/replay_holds.py run --all --out ~/.llama-harness/piece4/base.json`. Candidate: `./.venv/bin/python scripts/replay_holds.py run --all --rekey-overrides --out ~/.llama-harness/piece4/cand.json`. Record both shas.
- [ ] **Step 3:** `replay_holds.py compare base.json cand.json --out ~/.llama-harness/piece4/compare` passes its gates (exit 0); `short_keep_probe.py arms …` and `sibvocab …`.
- [ ] **Step 4: Verify** (spec 6(a), (b), (d), (e)): the reference reproduction has no unexplained difference (each one written up, with cause); 1,537 changed, 2,649 files added, 20 cleared, 34 added, or each difference explained; no `BLOCKS MERGE` line; 0 override shifts; the positional-fill losses and gains match 6(e). A rule or wiring defect goes back to its task and Steps 2-4 re-run.
- [ ] **Step 5: Hand check (6(c)).** `packets …` under `~/.llama-harness/piece4/hc/`; run the `usage-pacing` fleet check, then two Sonnet checkers on halves of the packet (rows 1-30, 31-60) with `INSTRUCTIONS.md` as the brief; then one Opus pre-screen of every wrong row and of `sibvocab.txt` (premise 3). `score …`.
- [ ] **Step 6:** Write `acceptance.md` (arm shas, gate results, the tallies, the class table, the reproduction differences, the hand-check score with sha256 of the answers file, the sibvocab verdict).
- [ ] **Step 7: CHECKPOINT A (orchestrator → operator, then stop).** Report: the numbers against the spec's; every reproduction difference; the class table; `first10.md` for the operator to check first (premise 2); the score and every wrong row with the pre-screen's class (accepted class in spec 7, or a fix); the sibvocab verdict. The operator rules on each blocking item.

---

### Task 10: Apply the Checkpoint A rulings (conditional)

**Spec:** the operator's Checkpoint A rulings. **Implementer: Sonnet** for a vocabulary or reading change; **Opus** if a ruling changes the rule's structure. Skip when nothing is ruled.

- [ ] **Step 1:** For each ruling, the failing test first, then the change, then the corpus test updated only for rows the ruling names (each listed in the commit message).
- [ ] **Step 2:** Re-run Task 9 Steps 2-4 for the affected arm; full suite → PASS.
- [ ] **Step 3:** Commit `fix: apply Checkpoint A rulings (<summary>)`.

---

### Task 11: Briefing reuse ignores short-kept tracks

**Spec:** 5.3. **Implementer: Sonnet.**

**Files:** Modify `packages/llama/src/llama/replay.py` (`briefing_reusable`); Test `test_replay.py`, `test_reapply.py`.

**Interfaces:**
- `briefing_reusable(stored_show, new_show, briefing, narration) -> str | None` (signature unchanged). `short = {t.filename for t in new_show.tracks if t.short_kept}`. On both shows, drop tracks whose filename is in `short`. Then, in order (first failure returned): `tracks differ` when the remaining filename lists differ; `broadcast fields changed: titles/sets/segues` when the per-track `(title, set, segue)` lists differ; `broadcast fields changed: set_breaks` when the break keys differ, a break `i` keyed by the filename of the last remaining track at or before track `i` (`None` when there is none), compared as sorted lists; `broadcast fields changed: date/venue/city`; then today's narration and `briefing_guard` checks unchanged. This is `reuse_r1.new_rule` with today's messages.

- [ ] **Step 1: Write the failing tests:** `test_reuse_ignores_an_inserted_short_kept_track`; `test_reuse_ignores_an_already_included_short_file_on_both_sides` (the 173 case: the file is in both shows, `short_kept` on the new one); `test_a_real_track_title_change_still_forces_a_brief` **(pin)**; `test_banter_sliding_across_a_set_boundary_keeps_the_brief` (a short-kept banter file directly after a break); `test_a_moved_real_break_forces_a_brief`; `test_guard_still_runs_on_reuse` **(pin)**; `test_reapply_reuses_the_briefing_of_a_held_show_that_gained_a_short_file` (test_reapply.py).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Dry run (expected: none outside these tests), full suite → PASS.
- [ ] **Step 5:** Commit `feat(replay): briefing reuse leaves out short-kept tracks`.

---

### Task 12: Re-use existing audio: the module, `build_package` and the unit

**Spec:** 5.4 (all of it). **Implementer: Opus** (moves and restores audio across a failure).

**Files:** Create `packages/llama/src/llama/audio_reuse.py`; Modify `stages/package.py` (`build_package`), `show_unit.py`; Test `packages/llama/tests/test_audio_reuse.py` (new), `test_stage_package.py`, `test_show_unit.py`.

**Interfaces:**
- Produces:

```python
ASIDE_DIR = ".audio-aside"     # <show>/.audio-aside/: outside package/, skipped by show_unit

@dataclass(frozen=True)
class ReusePlan:
    old_filenames: tuple[str, ...]        # the current show.json's source filenames, in order
    library: dict[str, str]               # source filename -> packaged name (library manifest paired)
    station: dict[str, Path]              # source filename -> <station>/audio/<packaged name>

def plan_reuse(show_ws: ShowWorkspace, station_dir: Path | None) -> ReusePlan | None
    # None without a readable show.json. A copy whose manifest is missing or unreadable, or
    # whose tracks differ from show.json's in length or in title at any index, contributes {}.
def set_aside(show_ws: ShowWorkspace) -> None        # os.replace every file in package/audio/ into ASIDE_DIR
def reuse_into(dest: Path, source: str, expected_sec: float | None, plan: ReusePlan,
               show_ws: ShowWorkspace, *, tolerance: float) -> str | None
    # tries ASIDE_DIR/<library name> then the station path: exists, read_duration not None,
    # expected_sec not None, within tolerance -> shutil.copyfile to dest; "library" | "station" | None
def put_back(show_ws: ShowWorkspace) -> None        # os.replace each aside file into package/audio/
def discard_aside(show_ws: ShowWorkspace) -> None
```
- `build_package(show_ws, ia, show, force=False, profile=None, *, reuse: ReusePlan | None = None)`: when `reuse` is given and `[t.filename for t in show.tracks] != list(reuse.old_filenames)`, `set_aside` once before the loop; for a track whose `dest` is missing, `reuse_into(dest, t.filename, <cached metadata length of t.filename>, reuse, show_ws, tolerance=DURATION_TOLERANCE_S)` runs before the download, which happens exactly as today when it returns None. Tagging and the duration flag run as today on every file.
- `show_unit`: `_tracked_files` also skips the top-level `ASIDE_DIR`; entry deletes a leftover `ASIDE_DIR` together with a leftover `.txn/` (documented limitation 5: a SIGKILL'd unit's aside audio is lost; `llama redo <show> --from package` re-downloads it); on failure `put_back` runs after `restore_snapshot`; on success `discard_aside` runs before `discard_snapshot`.

- [ ] **Step 1: Write the failing tests** (test_audio_reuse.py unless named):
  - `test_plan_pairs_library_and_station_by_index`;
  - `test_pairing_is_by_index_and_any_title_mismatch_drops_the_copy` (Review Focus 5);
  - `test_plan_without_show_json_is_none`; `test_unreadable_station_manifest_contributes_nothing`;
  - `test_changed_list_sets_old_audio_aside_and_reuses_it_under_the_new_name` (test_stage_package.py; a short file inserted before track 3: old `03 X.mp3` reused as `04 X.mp3` with no download, the new track downloads, no old-numbered file left in `package/audio/`);
  - `test_same_title_renumbered_never_inherits_the_wrong_audio` (old track 4 and new track 4 share a title; the new track 4 is a different source file → its own reused copy or a download, never old track 4's audio);
  - `test_unchanged_list_behaves_as_today` **(pin)** (no aside dir, no copy);
  - `test_duration_mismatch_or_unreadable_falls_back_to_download`; `test_station_copy_used_when_the_library_was_purged`;
  - `test_failed_unit_puts_aside_audio_back_under_old_names` (test_show_unit.py: an exception after `build_package` → `package/audio/` holds exactly the old names and bytes, no aside dir);
  - `test_successful_unit_deletes_the_aside` (test_show_unit.py); `test_leftover_aside_is_deleted_at_unit_entry` (test_show_unit.py).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Full suite → PASS.
- [ ] **Step 5:** Commit `feat(package): re-use existing audio when a show's track list changes`.

---

### Task 13: Thread the reuse plan through every re-packaging unit

**Spec:** 5.4 "Where it runs", "Mapping" (before the re-gather). **Implementer: Sonnet.**

**Files:** Modify `pipeline.py` (`process_show(..., audio_reuse: ReusePlan | None = None)` → `run_package(..., reuse=)`), `stages/package.py` (`run_package`), `cli.py` (`_redo_show_locked`), `reapply.py` (`reapply_show`); Test `test_redo_cmd.py`, `test_fix.py`, `test_reapply.py`.

**Interfaces:**
- Consumes: Task 12.
- `_redo_show_locked` computes `plan_reuse(show_ws, config.delivery_path / show_ws.dir.name if config.delivery_path else None)` before `drop_stage_artifacts`, and passes it to `process_show`. `fix` and triage edits reach it through their unit; `redo` single and batch through `_redo_show`.
- `reapply_show` computes the plan right after the still-held check (the stored `show.json` is still in place) and passes it to `build_package`. From the plan to the commit marker it runs `try: … except BaseException: put_back(ws); raise`, then `discard_aside(ws)` after the commit marker; a leftover aside is deleted at its entry, as in `show_unit`.

- [ ] **Step 1: Write the failing tests:** `test_redo_from_gather_reuses_library_audio_after_an_insertion` (test_redo_cmd.py; count `download_file` calls: only the new track); `test_fix_auto_redo_of_a_delivered_show_reuses_the_station_copy` (test_fix.py; a `--dest`-style `delivery_path` in the test config holding the delivered copy, library audio purged); `test_reapply_reuses_audio_and_puts_it_back_on_failure` (test_reapply.py; a failure injected in the commit-marker write leaves the old audio under its old names).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Full suite → PASS.
- [ ] **Step 5:** Commit `feat: redo, fix, triage and reapply re-use existing audio`.

---

### Task 14: Probe, the reuse check over delivered shows (read-only)

**Spec:** 8 premises 6-8. **Implementer: Sonnet.**

**Files:** Modify `scripts/short_keep_probe.py`, `scripts/test_short_keep_probe.py`.

**Interfaces:**
- `reuse-check --cand CAND.json [--sample 20 --seed 47] --out DIR`: over a seeded sample of delivered, unvoiced shows the candidate changes, calls `audio_reuse.plan_reuse` with the config's `delivery_path` and, for each paired station file, `read_duration` against the cached metadata length (no copy, no write); writes `reuse_check.md`: per show the pairing result, pass / fallback per file with the reason, wall time per show (premises 7-8); and, over every changed delivered unvoiced show, the summed metadata `size` of the files the reuse cannot cover (the new short-kept files plus every file of a show whose station copy does not pair), premise 6. Refuses an `--out` overlapping the library root or `delivery_path`.

- [ ] **Step 1: Write the failing tests** with a fake station dir: `test_reuse_check_counts_fallbacks_and_times`, `test_reuse_check_never_writes` (tree hashes of the fake library and station unchanged), `test_uncovered_bytes_sum`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Full suite → PASS.
- [ ] **Step 5:** Commit `feat(scripts): read-only reuse check over delivered shows`.

---

### Task 15: CHECKPOINT B (before the deliver path)

**Orchestrator**, with one Opus reader. Writes only under `~/.llama-harness/piece4/` and `acceptance.md`.

- [ ] **Step 1:** Re-run the candidate arm (Task 9 Step 2) at the current HEAD; `arms` against the Checkpoint A candidate shows no change in files, titles or flags; count `briefing == "reuse"` over the changed shows that have a briefing (spec 5.3: 1,017 of 1,415).
- [ ] **Step 2:** `reuse-check` over 20 delivered shows (reads the station share; writes nothing there).
- [ ] **Step 3:** Premise 4: one Opus reader reads 10 of the 37 `voiced-severe-final.json` briefings beside the candidate's restored files and reports any claim that a restored piece is absent.
- [ ] **Step 4: CHECKPOINT B (orchestrator → operator, then stop).** Report the reuse count, the reuse check (fallbacks, time per show over SMB, uncovered bytes), the briefing read, and the deliver changes Task 16 will make. Task 16 starts only on the operator's go.

---

### Task 16: `deliver` safety and the voiced pre-check

**Spec:** 5.5 (all owned bullets), strict surface (b). **Implementer: Opus.**

**Files:** Modify `cli.py` (`deliver`, `_deliver_batch`, `_deliver_one`, `_destination_is_voiced`, `reapply`'s two `re-deliver with` hints), `scripts/short_keep_probe.py` (`voiced-precheck`); Test `test_deliver_cmd.py`, `test_reapply.py`, `scripts/test_short_keep_probe.py`.

**Interfaces:**
- `deliver`: `--replace-voiced` with any selector (`other_selector`, already computed) exits 1 with the selector refusal before `_setup()`; single-name `--replace-voiced` is unchanged.
- `_destination_is_voiced(out) -> bool`: `FileNotFoundError` (manifest or directory missing) → False; any other `OSError`, invalid JSON, or a non-object → `raise LlamaError(<unreadable destination message>)`. `_deliver_one` lets it propagate (single name: exit 1, nothing copied). `_deliver_batch`'s preflight catches it per show, marks that row `  (refused: destination manifest unreadable)`, leaves it out of the shows it delivers, and continues.
- `_deliver_one`: when the destination is unvoiced and its manifest is readable and its track `filename` list (in order) differs from the package's, copy through `_replace_destination` instead of the merging `copytree` (plan reading of "track list changed": any change of packaged names, so no stale file survives a retitle either). A missing destination manifest keeps today's merge.
- `reapply`: the `re-deliver with` hint is printed only when the destination is not voiced (`_destination_is_voiced` False; an unreadable one prints the unreadable message instead).
- `short_keep_probe.py voiced-precheck --list voiced-severe-final.json <slug>` (read-only): exit 0 only when the slug is in the list, the station destination is voiced, the library `show.json` has every listed source file with `short_kept` true, and `package/manifest.json` exists with as many tracks as `show.json`; else exit 1 naming each failed check.

- [ ] **Step 1: Write the failing tests** (test_deliver_cmd.py unless named):
  - `test_replace_voiced_with_any_selector_refuses`: parametrised over `--held`, `--packaged`, `--state packaged`, `--artist X`, `--run R`, `--profile P`; exit 1, the selector message, the station tree byte-identical (`helpers.tree_bytes`).
  - `test_replace_voiced_single_name_still_replaces` **(pin)**.
  - `test_unreadable_destination_manifest_refuses_the_show` (replaces `test_unparseable_destination_manifest_is_not_voiced`: invalid JSON, a JSON list, a permission error each refuse; nothing copied).
  - `test_batch_preflight_marks_an_unreadable_destination_and_continues`.
  - `test_missing_destination_manifest_is_unvoiced` **(pin)**.
  - `test_changed_track_list_replaces_an_unvoiced_destination` (an old-numbered file in the station copy is gone afterwards; the swap is atomic: a failure in `_replace_destination` leaves the old destination, as the existing replace tests check).
  - `test_unchanged_track_list_still_overlays` **(pin)** (today's `test_unvoiced_existing_destination_still_overlays`).
  - `test_voiced_destination_still_refuses_without_the_flag` **(pin)**.
  - `test_reapply_hint_suppressed_for_a_voiced_destination` (test_reapply.py).
  - `test_voiced_precheck_passes_and_names_each_failure` (scripts/test_short_keep_probe.py).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4: Dry run.** Expected: `test_unparseable_destination_manifest_is_not_voiced` (reversed by spec 5.5), `test_batch_replace_voiced_marks_only_voiced_and_replaces_it` (a batch with `--replace-voiced` is now refused; rewrite it as the refusal plus a single-name replace). Anything else is BLOCKED. Full suite → PASS.
- [ ] **Step 5:** Commit `feat(deliver): --replace-voiced takes one name; unreadable destinations refuse; changed track lists replace`.

---

<!-- MIGRATION-TASKS: Tasks 17-20 (spec 4.3) are written after the final review of spec section 4. -->

### Tasks 17-20: The migration (spec 4.3)

Pending: written after the final strict review of spec section 4 reports.

---

### Task 21: Mutation run (scratch copy only)

**Implementer: Sonnet.** **Files:** commit only `docs/superpowers/2026-10-24-junk-short-keep-sdd/mutation.md`.

- [ ] **Step 1:** Scratch copy via `git archive HEAD | tar -x -C <scratch>`; run `<worktree>/.venv/bin/python -m pytest` with `PYTHONPATH=<scratch>/packages/llama/src:<scratch>/packages/herder/src:<scratch>/scripts`, after a planted sentinel proves shadowing; `PYTHONPYCACHEPREFIX` per mutant (memory: mutation scoring needs a prediction).
- [ ] **Step 2:** For each mutant, name the predicted red test before flipping it:
  - (a) `short_tag_is_junk` uses `any(...)` for `all(...)` (per-part anchoring, spec 6(f)) → `test_junk_test_examples` and `test_deny_vocabulary_corpus`;
  - (b) `legacy_int` accepts only `str.isdigit()` strings (legacy-value test, spec 6(f)) → `test_legacy_agrees_with_the_v2_17_0_model`;
  - (c) the snapshot skips its hash verification (spec 6(f)) → the Task 18 snapshot verification test;
  - (d) `SPAM_STEM` applied to tags → `test_tripwire_examples` (`I'll Follow the Sun`);
  - (e) the interior test counts untagged candidates as neighbours → `test_untagged_interior_kept_edge_dropped`;
  - (f) `_songish_coverage` without `not t.short_kept` → `test_songish_coverage_ignores_short_kept`;
  - (g) the resolver accepts legacy values → `test_gather_refuses_a_legacy_overrides_file`;
  - (h) `_stale` skipped for `--set-title` → `test_positional_edit_refuses_when_stale`;
  - (i) `set_aside` skipped → `test_same_title_renumbered_never_inherits_the_wrong_audio`;
  - (j) `_destination_is_voiced` returns False on any error → `test_unreadable_destination_manifest_refuses_the_show`;
  - (k) the selector check removed → `test_replace_voiced_with_any_selector_refuses`;
  - plus one mutant per migration gate (Tasks 17-20 name them).
- [ ] **Step 3:** Record mutant, predicted test, observed result. Every mutant is caught by its predicted test; a survivor or a surprise catch goes back to the owning task.
- [ ] **Step 4:** Commit `docs: piece 4 mutation record`.

---

### Task 22: Final acceptance (CHECKPOINT C)

**Orchestrator.** Writes only under `~/.llama-harness/piece4/` and `acceptance.md`.

- [ ] **Step 1:** Candidate arm at HEAD (Task 9 Step 2), `compare` and `arms` against the Checkpoint A base; differences from Checkpoint A's candidate are only those Tasks 10-16 explain.
- [ ] **Step 2:** The migration's dry run against the real library (read-only, no lock): `./.venv/bin/python scripts/rekey_overrides.py`; expected `606` would-rekey lines, `0` refused, and the totals `3,203 titles, 427 breaks, 365 encore keys` (spec 4.3 "Measured today"), or each difference explained.
- [ ] **Step 3:** Full suite green from the worktree venv; record the line.
- [ ] **Step 4:** Update `acceptance.md`.
- [ ] **Step 5: CHECKPOINT C (orchestrator → operator, then stop).** Report the acceptance numbers, the dry-run result, the mutation record, and the open gaps (below). The final branch review is the spec's Opus seat. Merge, push, release and the Appendix are the operator's.

---

### Task 23: CLAUDE.md and the SDD record

**Implementer: Sonnet.** **Files:** Modify `CLAUDE.md`; Create `docs/superpowers/2026-10-24-junk-short-keep-sdd/` (ledger and verdicts).

- [ ] **Step 1:** In CLAUDE.md: replace the "Plausible duration is RELATIVE" gotcha's last sentences with the rule (the floor unchanged; a short-only drop is kept unless the tripwire or a wholly junk tag drops it; untagged interior kept, edge and filename-junk drop; `spam-shaped name or tag`; `short_kept`, coverage; the operator's 239 includes); one Architecture bullet for piece 4 (the rule, the filename-valued overrides and the one resolver, the writers' rules, briefing reuse, audio reuse and `.audio-aside/`, the deliver changes, the migration script and its runbook, accepted limitations from spec 7, spec/plan/evidence/SDD paths); under Commands, `short_keep_probe.py arms|repro|packets|score|sibvocab|reuse-check|voiced-precheck`, `replay_holds.py run --rekey-overrides`, `scripts/rekey_overrides.py`; amend the `overrides.json` bullet (filename values under the legacy key names; numbers in `fix`/triage mean `show.json`'s numbering) and the `deliver` bullet (selector refusal, unreadable destinations, changed track lists replace).
- [ ] **Step 2:** Copy the SDD ledger and verdicts into the SDD dir (`.superpowers/` is gitignored; copy before any worktree is removed).
- [ ] **Step 3:** Commit `docs: piece 4 in CLAUDE.md; SDD record`.

---

## Open gaps (named, not closed by this plan)

- **The bulk apply of pieces 1-5** is planned separately. It needs: the migration done (Appendix steps 1-7); a post-migration candidate re-run whose per-show outcome and titles reproduce the pre-migration candidate (`short_keep_probe.py repro`); apply lists from that re-run, so their `input_digests` match the migrated files. Still open: **reapply's path extended to packaged and delivered shows** (spec 5.2: gather from the cache, the stored vet extraction, the stored briefing when reusable), which this branch does not build; the 28 voiced-minor shows stay out until the re-voice-later decision.
- **The piece-4 release version** the migration gates on is assumed `2.18.0` (Tasks 17-20); confirm before tagging.

## Appendix: operator runbook (after merge; not plan tasks)

Filled in with Tasks 17-20. Order (spec 4.3): stop the sweep loop and confirm `pgrep -x llama` prints nothing; dry run with v2.17.0 installed; repair refusals with v2.17.0; `--snapshot`; install the release (`llama --version`); `--apply`; restart the sweep loop; re-run the harness (`repro`, apply lists); bulk apply; triage held shows after it; re-deliver unvoiced shows (never `--replace-voiced`; outside the playout horizon first); for each of the 37 `voiced-severe-final.json` slugs, `short_keep_probe.py voiced-precheck`, then `llama deliver <slug> --replace-voiced`, then `emcee voice <slug>`.
