# Preflight: held-backlog Tier 1 plan vs spec and the current tree

Reviewer: read-only pre-flight. No code changed, no commits.
Plan: `docs/superpowers/plans/2026-10-19-held-backlog-tier1.md` (3315 lines). Spec: `docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md`.
Method: read the spec and plan in full; grepped the tree for every referenced symbol; ran in-memory, read-only probes with the worktree's own interpreter (`PYTHONDONTWRITEBYTECODE=1`). The probes ran `parse_setlist`/`rank_parses`, `_closer_candidates`, `is_real_title`, `clean_tag_titles`, `normalize_song`, the jerrybase CSV rows and the six `~/.llama/cache` items the fixtures are cut from. I also re-implemented the plan's specified regexes and predicates and ran them against each task's own test tables (Tasks 8, 10, 12, 14). Nothing was written outside `$D/preflight/`.

## Findings, sorted by severity

### BLOCKERs (following the text literally fails or contradicts spec/contract)

**B1. Task 1: the extract_setlist test's description is parseable. The test cannot pass.** Plan lines 244-249.
`"a lovely tape, no setlist here, just prose about the night"` parses to 3 items, `[('a lovely tape','1'),('no setlist here','1'),('just prose about the night','1')]`, at confidence `low`. `rank_parses` returns that parse whenever any candidate has items (`structure.py:344-385`), so `best` is not None and the `extract_setlist` branch is never reached. The 3-item canonical then gives coverage 0 against the tags, so gather reaches `align_structure`. Result: `res.needs_llm == ("align_structure",)`, not `("extract_setlist",)`.
*Ruling:* use the description the existing fallback test uses, `"An amazing night of music, seeded with love."` (`test_stage_gather.py:126`). It parses to 0 items (probed). With that, the canonical is empty, `align_structure` is unreachable and the verdict is exactly `("extract_setlist",)`.

**B2. Task 12: the plan has no race-track fold, so its own test row `("Meramec Race Track", "Merramec Racetrack")` fails.** Plan lines 1756 (`_PLACE_FOLD`), 1759, 1796. Spec line 418.
Spec 1b names a fold for "race track/racetrack". The plan relies on the joined-string test for that, but the joined strings `meramecracetrack` and `merramecracetrack` differ by the typo. The token subset fails on `racetrack` against `race`/`track`. I emulated the plan's `venues_equivalent` exactly: every other true and false row passes, and only this one fails.
*Ruling:* add the spec's fold before tokenising, e.g. `re.sub(r"\brace\s+track\b", "racetrack", s)` in `_place_tokens`, alongside the amphitheatre/pavillion folds.

**B3. Task 13 turns an existing test red, while its Step 4 says the gd73 tests "must still pass unchanged".** Plan lines 1876, 2046.
`test_stage_gather.py:1032 test_gather_venue_equivalent_passes_no_mismatch` builds its event with `_jb_event(..., venue="Robert F. Kennedy Stadium", city="Washington")`. The helper hard-codes `state="ST"` (`test_stage_gather.py:981-986`). Under spec step 1 (vote equivalent **and cities compatible**), `cities_compatible("Washington, DC", "Washington, ST")` is False: both regions are non-empty and differ. The step falls through, no swap or 1c applies (the selected recording has no venue), and today's `venue mismatch` flag fires. The test asserts no mismatch and `needs_review is False`.
I checked the other `_jb_event` users: only this test asserts the absence of a venue flag (the `test_gather_event_suffix_selects_right_event` enrichment path is unaffected).
*Ruling:* the spec mandates the city check, so fix the fixture, not the rule. Add a `state` keyword to `_jb_event` and pass `state="DC"` in this test, and say so in Task 13's Files and Step 4.

**B4. Task 17: redefining `_tracks` in `test_structure.py` breaks about 30 existing tests.** Plan lines 2466-2468.
`test_structure.py:194` already defines `def _tracks(n, dur=300.0)`, with 36 call sites. Appending `def _tracks(*titles)` at module end rebinds the global. Every earlier `_tracks(8, dur=300.0)` call then builds `Track(title=8)` and fails, or raises on the `dur` keyword. `_items` is free.
*Ruling:* rename the new helpers, for example `_titled(*titles)` and `_canon(*pairs)`.

**B5. Task 18: the tape title "JBG" already matches the closer "Johnny B. Goode", so the declining case is never set up.** Plan lines 2582-2592.
Probe: `_closer_candidates(["Bertha","Deal","Playin","Sugar Magnolia","JBG"], "Johnny B. Goode") == [4]` under today's fuzzy tier. The encore row's closer therefore has a candidate. By the plan's own rule ("every encore row's closer has none"), `anchor_numbered_sets` returns None, so `labels, note = anchor_numbered_sets(...)` raises `TypeError`. The `two_encores` sub-case uses `JBG` too, but it declines anyway because `Bertha` matches.
*Ruling:* use a title that matches nothing, e.g. `"Casey Jones"` (probed: `[]`), as the first 5c.2 test already does.

**B6. Task 19: three "writes nothing" snapshot tests fail because `file_lock` creates `<show>/.lock`.** Plan lines 2826-2829, 2836-2840, 2919-2922.
`locks.file_lock` does `os.open(path, O_CREAT|O_RDWR)` and never unlinks the file. The fixture library's show dir has no `.lock` beforehand (nothing in `run_gather` locks). After `reapply_show`, the dir contains `.lock: b""`, so `{p.name: p.read_bytes()} == before` fails in:
- `test_reapply_writes_nothing_on_a_needs_llm_show`
- `test_reapply_writes_nothing_on_a_refusal_mid_show`
- `test_dry_run_predicts_and_writes_nothing`

*Ruling:* touch `entry.ws.lock` before taking `before`, or exclude `.lock` from both snapshots. The lock file is not an artifact.

### MAJORs (likely confusion or rework)

**M1. Task 18: the 5c.3 fold changes `anchor_breaks` on shows that already anchor, which contradicts spec and makes Checkpoint F contradict itself.** Plan lines 2529, 2601-2614, 2663-2664. Spec lines 798-803 and 814-817.
The spec says "No other anchoring rule or constant changes" and requires "Zero anchoring changes on shows that already anchored… by construction because 5c.2 runs only when today's anchoring declines". 5c.3 folds inside `_closer_candidates`, which `anchor_breaks` uses. A fold can therefore add a second candidate on an already-anchored show and move a break through `_resolve_positions`' latest-candidate rule. The plan rewrites the existing guard test into `[0, 1]` to accept exactly that.
Checkpoint F then says both "any already-jerrybase show with a set_breaks diff fails the checkpoint" (item 2) and "on such a show anchor_breaks resolves to the latest candidate, so a break can move one track" (item 3).
*Ruling:* make the leading-parenthetical fold a **fallback tier** in `_closer_candidates`, consulted only when the unfolded exact and fuzzy tiers find nothing. Every already-anchored show then has unchanged candidates by construction, the spec's `(I Can't Get No) Satisfaction` example still matches, and the existing `test_closer_matching_preserves_a_leading_parenthetical` (`== [0]`) stays as is. Drop the REWRITE and Checkpoint F item 3's "can move" sentence.

**M2. Task 5: the identity check does not catch the worktree trap when the worktree is nested inside the main repo.** Plan line 800.
The rule is "`llama.__file__` under `Path(__file__).parents[1]`". This setup puts worktrees at `<repo>/.claude/worktrees/<name>`, inside the main checkout's tree. Running the main checkout's `scripts/replay_holds.py` with an interpreter that imports the worktree's llama therefore passes the check. That is the exact wrong-tree case the check exists to enforce (the reverse direction is caught).
*Ruling:* require `Path(llama.__file__).resolve()` to be under `Path(__file__).resolve().parents[1] / "packages" / "llama" / "src"`. The existing refusal test still passes.

**M3. Task 5 (and Task 20): enumerating shows with `catalog.iter_shows` would crash the whole run on one bad `overrides.json`.** Plan lines 793-803, 894-903, 2973.
`iter_shows` calls `read_overrides(ws)` for every show (`catalog.py:293`), so the Review Focus 2 input (`"[1, 2"`) raises out of the enumeration. The required result is a per-show `unreplayable`, and `test_unreadable_overrides_marks_the_show_unreplayable_and_continues` would fail. Task 5 does not say how `run` enumerates; `iter_shows` is the natural choice. Task 20 explicitly builds `entries` with `iter_shows`, so one malformed file anywhere in a 3,467-show library aborts a batch.
*Ruling:* in `run`, enumerate `sorted((root/"shows").iterdir())` and call `derive_state` per show inside the per-show try. In Task 20, resolve each row's slug to its `ShowWorkspace` directly (and `derive_state`), not through `iter_shows`.

**M4. Task 11: the near-miss test is vacuous and asserts nothing about the lookahead.** Plan lines 1697-1700.
`["01Pig In A Pen","02Midnight Moonlight","03Old And In The Way","3AM","M80","7-Up","01ABBA"]` has 3 glued of 7 voters (0.43 < 0.8). The vote fails and nothing is stripped, so `out[3:]` is unchanged whatever `_GLUED_NUM_PREFIX` says. Dropping the `(?=[A-Z][a-z])` lookahead would leave the test green.
*Ruling:* make the vote pass, e.g. 8 glued real titles plus `"3AM"` and `"01ABBA"` (8/10 = 0.8). Assert the two near misses unchanged and a glued one stripped. Optionally also unit-test `_GLUED_NUM_PREFIX.match` on `3AM`, `M80`, `7-Up`, `01ABBA`.

**M5. Task 20: `test_batch_stops_after_three_consecutive_llm_failures` really sleeps about 30 s.** Plan lines 3044-3046.
Each `HerderError` goes through `herder.tasks._with_transport_retry`: 3 attempts with `_sleep(2.0)` and `_sleep(8.0)`. No autouse fixture patches `herder.tasks._sleep` (grep). That is about 10 s per show times 3 shows. The test passes (12 queued errors cover 9 calls), but it is slow.
*Ruling:* `monkeypatch.setattr("herder.tasks._sleep", lambda s: None)` in that test.

**M6. Task 1 (and Task 8): existing tests unpack `build_canonical` as a 3-tuple.** Plan line 331.
`test_stage_gather.py:2020`, `:2072`, `:2112` and `:2121` do `canonical, notes, source = build_canonical(...)`. Adding `needs_llm` (Task 1) and `corroboration` (Task 8) to the NamedTuple raises `ValueError: too many values to unpack`. Task 1 Step 3 only points at `cli.py`.
*Ruling:* name these four test sites in Task 1 Step 3 and switch them to attribute access. `cli.py:2585` already uses `.setlist`.

**M7. Contracts and Task 4: `date` is a shipped field that the arm cannot report, and the diff baseline is unspecified.** Plan lines 91, 101, 593, 977.
Contracts list `date` among the shipped fields, and `shipped_diff` returns a `date` key. `ShowReplay` ("`to_dict()` gives exactly these keys") has no `date`, and `packaged_exposure.txt` omits it. A `clean-changed` outcome caused by a date change (vet's placeholder adoption runs in the replay) would therefore show no field. Task 4's test also diffs against `legs.gather.show`, while the vet leg can change `date`.
*Ruling:* add `date {old,new}|null` to `ShowReplay` and to the packaged-exposure fields. State that `shipped_diff` compares the stored show with the **vetted** replayed show (`legs.vet.show` when present).

**M8. Plan replaces several spec-mandated full hand checks with an Opus pre-screen plus a 20-row sample.** Plan line 187.
Spec sources: ruling 1, line 242 ("a hand check of every cleared show when there are at most ~150"); 2a acceptance, line 539; 2b, line 599 ("hand-checked in full"); slice 3, line 679 ("Every briefing that will ship by reuse is read whole by hand"); 4a/4b, lines 760-765.
The plan says "the operator confirms this at plan approval". If that confirmation is not already recorded with the approval at `f1744ad`, this is an open spec contradiction on the strict surface.
*Ruling:* confirm it was ratified; otherwise restore full reads for the strict lists (reused briefings, 4a at ≤150, 2b demotions).

**M9. Task 9: 2b emits demotion notes for tracks an override later titles.** Plan line 1423. Spec lines 576-577.
Notes are computed from `placeholder_positions` over the tag layer, before the `overrides.titles` loop. A track the operator forced (including slice 7's `Untitled (track N)` on `eotoband-2007-10-09`) still gets "placeholder tag title: … demoted to unresolved". The spec says an override "never is" judged, and these notes inflate Checkpoint B's ≈650-row demotion list.
*Ruling:* emit the 2b note only for positions `n` not in `overrides.titles`.

### MINORs

**Missing test imports** (an implementer hits NameError or a collection error and fixes it):

| Task | File | Missing names | Plan lines |
|---|---|---|---|
| 10 | `test_stage_gather.py` | `Track` | 1622 |
| 14 | `test_stage_brief.py` | `pytest`, `normalize_song`, `read_model` | 2120, 2125-2142 |
| 15 | `test_stage_vet.py` | `pytest` | 2261 |
| 19 | `test_stage_brief.py` | `generate_briefing` | 2709 |

**Patch-by-name requirements left implicit.** Task 19's tests patch `reapply_mod.compute_legs` and `reapply_mod.build_package` (lines 2768, 2860, 2891), so `reapply.py` must import both **by name**. State that in Interfaces (2683-2689).

**Task 2:**
- `config_fingerprint`'s dict literal has `{"audio_format", ...}`, a typo for `"audio_format": config.audio_format` (line 366).
- The `test_setlistfm.py` builder is `make(tmp_path, handler)`, not `_client(tmp_path)` (line 458; the plan does say "adapt").

**Task 3:**
- No existing `grounding_flags` unpacks exist in `test_stage_vet.py`, so the "update every existing… unpack" instruction is a no-op (line 531).
- `apply_vet(vetting, read_model(show_ws.show))` grounds against the disk show, while today grounds against the `show` parameter (`vet_research.py:166`). This is equivalent on every current call path, but worth a sentence (line 527).

**Task 4:**
- The "brief leg only when `flags` so far are empty" rule counts carried package flags, as the test at 705-711 requires. Say so in Interfaces (line 591).
- The "`no vetting.json` alone with gather flags → still-held" exception departs from spec (lines 322-323 and 839-840: no `vetting.json` means needs-LLM). Under the names form, `reapply` then writes `notes.json` and `show.json` for a show the spec says is "untouched". Either align with spec or record the deviation (line 592).

**Task 5:**
- `logging.disable(CRITICAL)` must be undone (`logging.disable(logging.NOTSET)` in `finally`). Otherwise any `caplog` test that runs after it in the same session goes silent; today that is hidden only by testpaths order (line 801).
- "imported … as `test_purge_delivered_audio.py` does" is inaccurate: that file only adds `scripts/` to `sys.path`. The plan's own snippet is correct (line 786).

**Task 6:**
- `structure_changed.txt`, `closest_calls` 4b and 5a need `identifier`, `asserted_dates` and durations, which the arm does not carry. Say "read from `<root>/shows/<slug>/` (show.json, vetting.json)", as Task 7 does (lines 979, 985-986).
- `flags.txt`'s line format is fixed only by the test string (`"research-date: removed 1, added 0"`). Put it in Interfaces (line 975).

**Task 9 / Contracts:**
- The note `format sibling tagged: …` is not in the Contracts note table, although Global Constraints say every note text comes from there (lines 34, 69-79, 1423).
- The File Structure table omits gather.py for T9 and T11, and replay.py for T14 (lines 129, 132).

**Task 10 / 14 / 9:** expected mutation survivors, worth pre-empting with a test row:

| Task | Mutant | Plan line | Row that would catch it |
|---|---|---|---|
| 10 | (c) any segue component corroborated | 1659 | none has an uncorroborated multi-component core; add one |
| 14 | (a) any component known | 2219 | add `("Drums > Nope", ["Drums"], False)` |
| 9 | (d) residue arm without the `is_real_title` gate | 1527 | add a non-real residue tag such as `"d1t02"` |

**Task 11:**
- Files omits `gather.py`, but the Interfaces require gather to emit the 2c note (lines 1670, 1675).
- `clean_tag_titles` returns early when the `_TRACK_NUM_PREFIX` vote fails (`titles.py:196-197`), so the glued vote must run on both paths. Say so (line 1675).

**Task 13:**
- 1a placement is ambiguous: is it terminal, and does step 1 run after it?
- For blank vote and blank jerrybase venue, the plan never flags even when cities are incompatible. Spec line 413 says 1a holds "when the cities are compatible" (plan lines 1873-1875).
- Checkpoint C item 4 says string changes "carry a swap, 1c or 1d note", but 1d is a **flag**, not a note (line 2065).

**Task 14:** `briefings.txt` section (4) re-implements "the same fields `briefing_guard` joins" in the script. Extract a `brief._guard_prose(b)` helper so the two cannot drift (line 2094).

**Task 16:**
- `info["resolved"]` is asserted as an int (line 2404), while Interfaces use `resolved` as a list (line 2331). State that the dict carries counts.
- If Checkpoint E moves the constant, `test_constants_are_the_spec_values` must change in the same commit.

**Task 18:** the 5c.2 path appends "set breaks anchored from jerrybase" to the local `notes`, which become `structure.conflicts` and reach the briefing LLM (line 2534). The string is existing provenance, but Global Constraints line 29 says "Nothing new is appended to `StructureInfo.conflicts`". Add an explicit exception or route it elsewhere.

**Task 21:**
- The spec's end-state acceptance ("on a fixture whose gather and vet raise flags", spec lines 958-963) is met only with `_redo_show` stubbed (lines 3197-3214).
- `--clear-set-breaks`, `--clear-encore` and `--clear-title` are not refused alongside `--untitled` (line 3139). `--no-run` is a sensible addition beyond spec.

**Finish:** "whole-branch review on Opus" (line 3315) conflicts with the spec Kickoff's "Review mode: Fable", which picks the final branch reviewer (spec lines 16-17; user CLAUDE.md "Spec review").

**Spec inconsistencies the plan inherits:**
- The spec header still says "draft for review, not approved" (spec line 3).
- 2b says "the 6 shows and 15 tracks" (spec line 588), while Evidence lists 5 shows and 14 tracks (spec line 174). The plan uses the 5 (line 1736), which is right.

**Spec Testing fixture list:** it says `dso2003-01-25` "with its Pageant sibling" (spec line 1031). The plan uses a synthetic `RecordingSummary` served the Barrymore metadata through `StubIA` (lines 1898-1904). This is acceptable for venue logic; note the deviation.

## Table 1: task pairs that share a file or an interface

| Pair | Producer → consumer (what is shared) | Finding |
|---|---|---|
| T1→T3 | `ShowNotes`, `ShowWorkspace.notes`; T3's `run_vet_research` reads and writes `notes.json`'s `vet` list | agree |
| T1→T4 | `compute_gather(... align_provider=None, setlistfm=, structure_cfg=, jerrybase_enabled=)` → `GatherResult(show, reviews, notes, needs_llm: tuple)` consumed as `legs.gather` and `needs_llm` | agree (Legs converts the tuple to a list) |
| T1→T8 | `CanonicalBuild` gains `needs_llm`, then T8 adds `corroboration` (both trailing) | agree on shape; **M6**: existing test 3-tuple unpacks break |
| T1→T9/T10/T11/T13/T17/T18 | each appends to `GatherResult.notes` (`op_notes`), never to the local `notes` | agree, except **T18**'s structure note (MINOR) |
| T1→T19/T20 | `notes.json` written by `reapply` as `ShowNotes(gather=legs.gather.notes, vet=...)` | agree |
| T1→T21 | T21 test calls `compute_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT, align_provider=Boom())` and expects `needs_llm == ()` | agree (gd73 parses; override path skips `align()`) |
| T1 / T19 / T20 / T21 (cli.py) | `_print_show_entry`/`_print_show_json` (T1); `reapply` command (T19 names form, T20 list form); `fix --untitled` + triage (T21) | agree: disjoint blocks; T20 extends T19's stub `--from-list` |
| T2→T4/T5/T19 | `CacheOnlyIA`, `CacheOnlySetlistFM`, `setlistfm_client(config)` (the one choice point) | agree; T5 and T19 both pin the `slfm is None` parity |
| T2→T5/T6/T19/T20 | `input_digests` keys `{show.json, overrides.json, provenance.json, research.md, vetting.extraction}`; `config_fingerprint`; `code_identity` | agree (fix the T2 dict typo) |
| T2→T9/T10/T11/T13 | `capture_fixture.py --from-cache` for furthur, tnd, RRE, dso, guster and gd78 dodd | agree: all six cache files exist in `~/.llama/cache` (checked) |
| T3→T4 | `apply_vet(vetting, show) -> VetOutcome(show, result, notes)` | agree |
| T3→T15→T16 (vet_research.py) | `grounding_flags` 3-tuple (notes `[]`) → T15 adds `raw_date_flags` local + 4b window → T16 consumes `date_flags_raw` and emits the 4a note | agree; order T15 before T16 as listed |
| T4→T5 | `compute_legs`, `classify`, `shipped_diff`, `flag_family` → `replay_show` / `ShowReplay` | agree; **M7** (`date` missing from `ShowReplay`) |
| T4→T14 | `briefing_reusable` calls `briefing_guard`; T14 swaps in `normalize_briefing` first and stores the normalised briefing in `Legs.briefing` | agree |
| T4→T19 | `reapply` maps `classify` outcomes; `Legs.vet/.gather/.briefing/.brief/.flags` | agree |
| T5→T6→T7 | arm schema (`sha`, `config_fingerprint`, `setlistfm_configured`, `scope`, `root`, `llama_file`, `shows`) | agree; T6 needs per-show identifier and vetting data from `root` (MINOR) |
| T5→T6/T14/T18 tests | `fixture_library.build_library(root, held_for_real=)`; `_two_arms` | agree: probed that the `held_for_real` show reproduces through T15/T16, since 1974-01-01 is not adjacent and the own date is asserted |
| T5→T19/T20 tests | `build_library` + `config.toml` (`[jerrybase] enabled = false`) loaded via `load_config` | agree |
| T6→T19/T20 | `predicted_list.json` rows `{slug, outcome, briefing, digests}` + `sha`/`config_fingerprint` → `load_list` | agree |
| T6 ← notes from T9/T10/T11/T13/T16/T18 | `notes.txt` grouping and `closest_calls` regexes over the Contracts strings | agree; the "format sibling tagged" string is absent from Contracts (MINOR) |
| T6 ← T12 | `closest_calls` 1c uses `structure._place_tokens` (T12 changes its folding) | agree: the overlap ranking simply uses the new tokens |
| T7 ← T5 | reads `root` from the arm header and `show.json` from the library | agree |
| T8→T9 | `placeholders.is_placeholder/is_timestamp/is_residue/recording_level_junk`; `CanonicalBuild.corroboration` passed as `frozenset(keys)` | agree: Task 8 regexes emulated, all T8 and T9 table rows pass |
| T8→T10 | `is_junk_tag`; `corroboration: dict[str, tuple]` | agree |
| T9→T10 | `tag_layer(...)` → `tag_titles`/`tag_source` for `accept_short_tags`; 2b-demoted `tmp` passes `is_real_title`, so 2a never re-accepts it | agree |
| T9→T11 (titles.py) | `resolve_titles`/`tag_layer` call `clean_tag_titles`, which T11 extends | agree; T11's gather note compares `tag_layer` output with raw `clean_tag_title` |
| T9→T16 | 2b before 4a (junk titles become unresolved before the right-show gate) | agree; the order is enforced |
| T10 / T11 / T9 (test_titles.py) | T9 adds `_files`; T10 and T11 reuse it | agree: no name collision |
| T12→T13 | `venues_equivalent`, `cities_compatible` | agree on signatures; **B2** inside T12; **B3** in T13's effect on an old test |
| T12 / T17 (structure.py, test_structure.py) | disjoint code blocks; tests: T12 extends parametrizations, T17 adds helpers | **B4**: T17's `_tracks` collides with the existing helper |
| T13 / T17 / T18 (gather structure and venue blocks) | the venue block (T13) sits after the multi-event flags; T17 edits the `structure_guard` call; T18 edits the `anchored is None` branch and the closer tripwire | agree: disjoint; T13 uses `len(events)`, already in scope |
| T13 ← jerrybase CSV | DSO 2003-01-25 → Barrymore/Madison/WI; GD 1978-11-17 → Uptown/Chicago/IL; DSO 2012-05-19 → `''`/Tuxedo Park/NY | agree (verified against the CSV) |
| T14→T19 (brief.py, test_stage_brief.py) | `normalize_briefing` → `generate_briefing`'s two-attempt loop | agree (T19 needs a `generate_briefing` import) |
| T17→T18 | evidence sets vs `anchor_numbered_sets` labels | agree |
| T18 ← existing `_closer_candidates` users | `anchor_breaks`, `closer_contradictions` | **M1** |
| T19→T20 (reapply.py, test_reapply.py) | `reapply_show(..., row=, dry_run=)` → `ReapplyOutcome.outcome`/`briefing` strings consumed by the list form, dry-run summary and progress | agree |
| T19 ← package.py | `build_package` returns `(pkg, flags)`; `run_package` wraps it | agree: `run_package` really does end with a `show.json` append-write (`package.py:91-95`) |
| T20 ← cli pacing | `_meter`, `_meter_applies`, `decide`, `Progress`, `pace_options`, `PauseUntil.__str__ == reason` | agree (`decide` returns `Proceed` on a `None` reading; tests patch `cli.decide`) |
| T21 ← cli | `_edit_overrides(set_titles=, narration=, set_breaks=)`, `_clear_hold`, `_redo_show`, `_resolve_prompt(*, titles, include)` | agree: all exist with these keywords |
| T22 ← all | docs | n/a |

## Table 2: per-task self-consistency (tests vs code vs Interfaces vs files)

| Task | Self-consistent? | Notes |
|---|---|---|
| 1 | **No** | **B1** (extract_setlist test). **M6** (test unpacks). `longest` exists only in the provider branch: compute it for the `provider is None` case. The `_low_coverage_candidate` name returns metadata, not a candidate. Other tests verified: the align test reaches `align_structure`, the provider test calls it, the notes tests are fine, the `show` notes heading cannot be faked by `tmp_path` (no colon). |
| 2 | Yes (MINOR) | Fingerprint dict typo; `test_setlistfm` builder is `make`. CacheOnly clients, digests and `--from-cache` slim shape all match the tests. |
| 3 | Yes (MINOR) | No-op instruction about unpacks; grounding source is the disk show, not the parameter. |
| 4 | Yes (MAJOR M7, MINOR) | All 15 `flag_family` rows match the Contracts prefixes. The structure-changed test gives `[3,5]` against `[]`, verified. |
| 5 | Mostly | **M2**, **M3**; `logging.disable` cleanup; `selected_venue`/`selected_city` `(None, None)` is right, since the fixture's `RecordingSummary` has neither (only the item metadata does). |
| 6 | Yes (MINOR) | Exit 2/3 rules match the tests. The denominator excludes needs-llm and includes unreplayable, consistent with Contracts. |
| 7 | Yes | |
| 8 | Yes | All placeholder regexes emulated against all 9 test tables: zero mismatches. The residue ruling (`Jam 12-31-99`, `Master`, `Matrix` demoted) is reproduced. Corroboration fixtures verified (gd74 windsor and miller descriptions differ; the copy and spaced cases normalise equal). |
| 9 | Yes (MAJOR M9) | furthur: 19 mp3s, all tagged `tmp`, title fraction 1.0, so no format recovery; all-unresolved expectation holds. Expect the "format sibling tagged" note too (its FLAC tags are real). |
| 10 | Yes (MINOR) | tnd in-memory pipeline: 7 `J >` tracks stay unresolved through setlist-gap (hygiene vetoes `J`); the sibling parse yields item `J`; the chosen parse wins ranking. `tag_core` and `strip_taper_markers` emulated: all 11 rows pass. Missing `Track` import. |
| 11 | **Partly** | **M4** vacuous test; gather.py missing from Files; early-return note. The RRE fixture has 23 of 23 glued, so the strip fires. |
| 12 | **No** | **B2**. The city-compatibility rows reasoned through: all consistent with the specified folds. |
| 13 | **No** | **B3**. All 12 new tests reasoned through against the CSV and fixture metadata and are consistent: swap, signature, 1c, 1d, 1a, the per-event exclusion, Review Focus 1. |
| 14 | Yes (MINOR) | 3b rows (12) and 3c rows (17) emulated: zero mismatches. Missing imports. |
| 15 | Yes (MINOR) | 4c rows and 4b rows reasoned through against `normalize_date`; missing `pytest` import. |
| 16 | Yes (MINOR) | Note text `0.62` for 5/8 confirmed. Table rows reasoned through. `info["resolved"]` must be a count. |
| 17 | **No** | **B4**. 5a gather test verified: the gd73 description ends `Encore:\nJohnny B. Goode`, and `d3t01.mp3` is untagged. |
| 18 | **No** | **B5**, **M1**. 5c.1 test verified (`Tuning` and `Crowd` are filler, `Loser` is not). The 5c.3 rows match the fold. The gd73 5c.2 gather test gives `["1","1","1","2","2","encore"]` and a jerrybase alignment. |
| 19 | **No** | **B6**. Other tests consistent with Interfaces (write order list, stale manifest, package flags, lock held: a same-process second `flock` fd does conflict, so `Locked` is raised). |
| 20 | Yes (MAJOR M5, M3) | Pause and refusal output and the dry-run summary arithmetic (`~0.2 GB`) are consistent. |
| 21 | Yes (MINOR) | Helpers and keywords exist; the filename line format `"   1  t01.mp3"` matches `{index:2d}`. |
| 22 | Yes | |

## Other checks

- **Do-not-retune constants:** none are touched by any task's code as specified. `_TRACK_NUM_PREFIX`, `_STRUCTURE_PREFIX`, `_FOOTNOTE_TAIL`, `_ENUMERATED_MIN_*`, `is_filler`, `_RECOVER_*`, the tail guard and `align_coverage_threshold` are all reused or flanked.
- **Constant outside the spec's list:** `_REGION_FOLDS` is a new a-priori constant, flagged by the plan for operator sign-off.
- **Line-number references spot-checked:** `gather.py:1163` (now 1163, `evidence_sets`), `cli.py:2223`/`2933` (`_redo_show` at 2208, `_redo_batch` at 2933), `test_jerrybase.py:380-385` (actual 381-386), `brief.py:137-139`. All are present with the stated names and signatures.
