# Held-backlog guard fixes (Tier 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the deterministic false holds on the 1,073-show held backlog (venue spelling, short tags, briefing-guard misreads, adjacent-day dates, encore-as-a-set) without opening the strict surface, close the junk-title and wrong-venue gaps those removals would expose, and ship the two tools that make it measurable and applicable: an offline replay harness (`scripts/replay_holds.py`) and `llama reapply`.

**Architecture:** Gather is split into a pure `compute_gather` (returns a `GatherResult` carrying the show, the operator notes and a `needs_llm` verdict) and the writing `run_gather`; vet gains a pure `apply_vet`; brief gains a pure `generate_briefing` and a `normalize_briefing`. A new library module `llama/replay.py` holds the cache-only clients, the input digests, the per-show "legs" computation (LLM-free gather → stored-extraction vet → briefing-reuse decision) and the outcome classification; `scripts/replay_holds.py` (run/compare) and `llama reapply` are both thin wrappers over it, so prediction and apply cannot disagree. Every new operator note goes to a sibling `notes.json`, never into `show.json`/`vetting.json`/`structure.conflicts`. Each slice's rule is a narrower predicate beside the protected one, never a loosening in place.

**Tech Stack:** Python 3.11+, pydantic v2, typer (CliRunner in tests), `fcntl.flock`, pytest. All tests offline (`herder.FakeProvider`, captured archive.org fixtures, a two-show fixture library under a read-only root).

**Spec:** `docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md` (approved, authoritative). Every implementer reads the spec section their task names, plus this task, plus the "Contracts" section below.

## Execution setup (orchestrator, once, before Task 1)

- Worktree: `/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1` on a new branch `held-backlog-tier1` from `main`.
- Its own venv, from the worktree root:
  `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
- Check it imports the worktree: `./.venv/bin/python -c "import llama; print(llama.__file__)"` must print a path inside the worktree.
- **Always** run tests as `./.venv/bin/python -m pytest ...` from the worktree root, never a bare `pytest` and never `.venv/bin/pytest` (CLAUDE.md).
- Baseline before Task 1: `./.venv/bin/python -m pytest -q` (record the count; the suite was green at `4526886`).
- Harness output directory for every checkpoint: `H="$HOME/.llama-harness"` (`mkdir -p "$H"`). It is durable and outside `~/.llama`: the arms and lists must survive a multi-day run, so never under `/private/tmp`. Nothing in this plan writes under `~/.llama` except `llama reapply` at Checkpoint G, which has an operator checkpoint immediately before every real run.
- The library is read for fixtures and harness runs only. `~/.llama/cache/md_<id>.json` files are full archive.org metadata responses; Task 2 adds `scripts/capture_fixture.py --from-cache <id>` so fixtures are cut from the cache offline, with no network call.

## Global Constraints

- **Do-not-retune constants stay byte-identical** (spec "Stakes"): `is_real_title`, `title_fraction`, `_TRACK_NUM_PREFIX`, `songs.normalize_song`, `DEFAULT_ALIASES`, `GD_SHORTHAND`'s family gate, `gather._RECOVER_BELOW`/`_RECOVER_SIBLING_ABOVE`, the tail-guard constants, the junk-duration constants, `align_coverage_threshold`, `_ENUMERATED_MIN_FILES`/`_ENUMERATED_MIN_COVERAGE`, `structure._STRUCTURE_PREFIX`, `_FOOTNOTE_TAIL`. Every task's code-quality review greps the diff for them.
- **Narrow beside, never loosen in place** (ruling 2): a slice that needs more than a protected predicate gives adds a new predicate next to it with its own name and its own tests.
- **Corroboration is cross-source** (ruling 3): the parse vocabulary used by 2a and 2b excludes the selected recording's own description (`SourcedParse.source == "chosen"`) and every sibling parse whose whitespace-normalised description equals it (a pasted copy has the same author), and is built in exactly one place (`build_canonical`, Task 8).
- **Notes never reach the LLM** (ruling 6): every note added by this plan is appended to `GatherResult.notes` / `VetOutcome.notes` and lands in `notes.json`. Nothing new is appended to `StructureInfo.conflicts`, `Show.review_flags` (other than the flags the spec names), or `VettingResult`.
- **A real tag, a `sibling-format` title or an `override` is never overwritten** by any automatic pass. 2b may demote a `tags`/`sibling-format` placeholder to `unresolved` (title = filename) and never to other text. Only Task 21 (operator-confirmed) writes `overrides.json`.
- **Nothing here rewrites a package or a delivered show silently** (ruling 4). The harness reports; `reapply` changes only shows that are held, under the per-show lock, with `show.json` written last.
- **Tier 1 is LLM-free by scope** (ruling 5): the needs-LLM verdict is computed by `llama.replay.compute_legs` and turned into an outcome by `llama.replay.classify`, both used by the harness and `reapply` (which maps `classify`'s outcome). No other code decides it.
- New constants are fixed a priori (spec "New constants") and named in code with a comment citing the spec section; none is retuned after a harness run except `RIGHT_SHOW_MIN_TAPE_FRACTION` at Checkpoint E, before 4a ships.
- Message and note texts are verbatim from the "Contracts" section below; `compare` parses them.
- Tests are offline and deterministic; never commit audio; fixtures are captured real items slimmed by `capture_fixture.py`.
- Each task ends with the full suite green: `./.venv/bin/python -m pytest -q` from the worktree root.
- Commits: one per task as shown; end each commit message with the attribution trailer the orchestrating session specifies.
- **Mutation step** (spec "Testing"; required on every task that touches a strict predicate: Tasks 4, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19). After the full suite is green and before the commit, flip each mutant the task lists, one at a time, by this recipe:
  1. Write down the predicted red test (file::name) for the mutant BEFORE flipping it.
  2. Fresh copy per mutant, outside the worktree (`W` = the worktree root): `M=$(mktemp -d "$TMPDIR/mut-XXXX"); rsync -a --exclude .venv --exclude .git "$W/" "$M/tree/"`; apply the mutant in `$M/tree` only.
  3. Run with the worktree's interpreter, the copy shadowing the editable install, and a bytecode cache private to this mutant: `cd "$M/tree" && PYTHONPATH="$M/tree/packages/llama/src:$M/tree/packages/herder/src" PYTHONPYCACHEPREFIX="$M/pyc" "$W/.venv/bin/python" -m pytest <files> -q`. Never `.venv/bin/pytest` (CLAUDE.md: its shebang tests the worktree, not the copy).
  4. Prove the shadowing once per mutant: the same command line with `-c "import llama; print(llama.__file__)"` instead of `-m pytest ...` must print a path under `$M/tree`.
  5. Record `mutant → predicted test → caught by (test id) | SURVIVED` in the implementer's report; the orchestrator copies the table into the SDD ledger. A survivor gets a test (or a written reason it is equivalent) before the commit. A mutant counts as caught only by the predicted test or a named other test, never by "some failure".

## Review Focus

Inputs the spec implies but does not test directly; each has a test in the owning task:

1. **A show whose `provenance.json` candidate no longer lists the selected recording** (`show.identifier` absent from `candidate.recordings`, after a hand-edit or an older grouping). Expected: slice 1's swap and 1d simply do not fire (no selected venue/city), the show gathers as today. Test: Task 13 `test_selected_recording_missing_from_candidate_is_no_swap_and_no_1d`.
2. **An `overrides.json` that is unreadable or a non-object** in the library during a harness run. Expected: that one show is `unreplayable: overrides.json unreadable`, the run continues, the arm records it. Test: Task 5 `test_unreadable_overrides_marks_the_show_unreplayable_and_continues`.
3. **A stored `briefing.json` written before `narration` existed** (missing key, defaulting to `"full"`) on a show whose `overrides.narration` is `vague`. Expected: not reusable (narration disagrees), classified needs-brief. Test: Task 4 `test_reuse_refused_when_recorded_narration_differs`.
4. **A reapply list row whose slug no longer exists on disk** (the show was `llama rm`'d since the harness ran). Expected: skipped and reported as `missing`, the batch continues, the row is not recorded as finished. Test: Task 20 `test_missing_show_is_skipped_and_not_finished`.
5. **Research asserting the show's own date in a yearless form only** (`June 10`) with another full date two days off. Expected: 4a is not satisfied (own full date, year included, is required) and 4b does not treat the other date as context, so the wrong-date flag stands. Test: Task 15 `test_yearless_own_date_does_not_make_a_far_date_context` and Task 16 `test_right_show_gate_requires_the_own_full_date_with_year`.

---

## Contracts (shared by several tasks; implementers copy these exactly)

### `notes.json` (`llama.models.ShowNotes`)

```json
{"gather": ["...", "..."], "vet": ["..."]}
```

`ShowWorkspace.notes = dir / "notes.json"`. Written by `run_gather` (replacing the file: `gather` = `GatherResult.notes`, `vet` = `[]`), updated by `run_vet_research` (sets `vet`), written by `reapply` with the same two lists. It is a gather artifact in `show_stage_artifacts["gather"]` (dropped by `redo --from gather`). Read by `llama show` (printed under `notes:`) and therefore by triage. Never read by `brief.py`, `vet_research.py`'s prompt path or `package.py`.

### Exact note and flag strings

| id | where | text (Python f-string) |
|---|---|---|
| swap | gather note | `f"venue taken from the selected recording: '{sel_venue}' agrees with jerrybase '{event.venue}' (vote was '{vote_venue}')"` |
| 1c | gather note | `f"venue differs from jerrybase: archive '{sel_venue}' vs '{event.venue}' (same city)"` |
| 1d | **flag** | `f"recordings of this date disagree on city: '{sel_city}' (selected) vs '{vote_city}'"` |
| 2a | gather note, one per track | `f"accepted short tag title: track {n} '{title}' corroborated by {', '.join(sources)}"` (`sources` sorted, e.g. `lma:tnd2006-12-13.shnf, setlist.fm`) |
| 2b | gather note, one per track | `f"placeholder tag title: track {n} '{raw}' demoted to unresolved"` |
| 2c | gather note, one per track | `f"stripped glued track number: track {n} '{raw}' -> '{title}'"` |
| 5c.1 | gather note (via `jerrybase.filler_tail_closers` into `GatherResult.notes`; never `closer_contradictions`' soft list, never `structure.conflicts`) | `f"jerrybase set closer '{closer}' is followed only by filler before the set break"` |
| 5c.2 | gather note | `f"set breaks anchored from jerrybase numbered sets (encore row '{closer}' unmatched; {k} trailing track(s) stay in set {last})"` — **dropped at Checkpoint F (Task 18b); no producer** |
| 4a | vet note | `f"unknown-song flags suppressed by the right-show gate: {asserted}/{resolved} tape tracks asserted (ratio {ratio:.2f}), {n_unknown} unclaimed: {'; '.join(unknown)}; research date: {date_text}"` |

Existing flag texts (`venue mismatch: archive '{venue}' vs jerrybase '{event.venue}'`, `unresolved track titles`, `low-confidence structure alignment`, `research asserts ...`, `briefing ...`, `duration mismatch on ...`) are unchanged.

### Flag families (`llama.replay.flag_family(flag) -> str`)

`structure` (prefixes `low-confidence structure alignment`, `single-set structure`, `setlist evidence shows multiple sets`, `structure has `, `jerrybase set closer `, `low-confidence setlist`, `merged track(s)`), `titles` (`unresolved track titles`), `research-song` (`research asserts unknown song`), `research-sets` (`research asserts ` + `sets but structure has`), `venue` (`venue mismatch`), `city` (`recordings of this date disagree on city`), `research-date` (`research asserts wrong date`, `research asserts ` + `looks like a year-only placeholder`), `briefing` (`briefing `), `events` (`tape spans`, `unassigned multi-event`, `multi-event date`), `tracks` (`no playable tracks`), `package` (`duration mismatch on `), else `other`.

### Outcome classes (`ShowReplay.outcome`)

Held shows: `clears`, `needs-brief`, `needs-llm`, `structure-changed` (with `would_be` = `clears`|`needs-brief`), `still-held`, `still-held-package`, `unreplayable`. Non-held shows: `clean` (no flags, no shipped-field change), `clean-changed` (no flags, a shipped field differs from the stored show), `newly-held` (the arm raises a flag), `needs-llm`, `unreplayable`.

Shipped fields: per-track `title`, `title_source`, `set`, `segue`; `set_breaks`; `venue`; `city`; `date`; `structure.alignment`.

### Harness arm file (`run --out arm.json`)

```json
{"sha": "<code identity>", "config_fingerprint": "<hex>", "setlistfm_configured": true,
 "scope": "held|all|slugs", "generated_at": "<iso utc>", "llama_file": "<path>", "root": "<library root>",
 "shows": {"<slug>": {ShowReplay}}}
```

`ShowReplay` (a dataclass in `llama/replay.py`, `to_dict()` gives exactly these keys): `slug, state, stored_flags, stored_core_flags, gather_flags, vet_flags, brief_flags, stored_brief_guard (list[str]|null), needs_llm, outcome, would_be, briefing ("reuse"|"fresh"|"none"), reproduces, title_changes [{index, old, new, old_source, new_source}], venue {old,new}|null, city {old,new}|null, selected_venue (str|null), selected_city (str|null), set_changes [{index, old, new}], segue_changes [{index, old, new}], set_breaks {old,new}|null, alignment {old,new}|null, notes [str], digests {show.json, overrides.json, provenance.json, research.md, vetting.extraction}, slfm_miss, unreplayable (str|null)`.

`stored_core_flags` = stored `review_flags` minus the `package` AND `briefing` families. `reproduces` = sorted(`stored_core_flags`) == sorted(`gather_flags + vet_flags`); nothing else. `stored_brief_guard` = `briefing_guard` over the stored `briefing.json` against the stored `show.json` under this arm's code (Task 14 normalises the briefing first), `null` when there is no `briefing.json`; the briefing comparison is its own line in `compare` (stored `briefing`-family flags vs `stored_brief_guard`), never part of `reproduces`. `selected_venue`/`selected_city` = the stripped non-empty `venue`/`coverage` of the provenance candidate's recording whose identifier is the stored show's (`null` when absent).

### `compare base.json cand.json --out DIR` outputs

`summary.txt`, `drift.txt` (base shows with `reproduces == false` whose base `outcome` is not `needs-llm`), `flags.txt` (per family: removed, added), `outcomes.txt`, `packaged_exposure.txt`, `title_sources.txt`, `structure_changed.txt`, `hand_check_sample.txt` (20 newly cleared, or all when fewer: the 20 smallest `sha1(slug)`), `closest_calls.txt` (one section per slice, see Task 6), `needs_llm.txt`, `notes.txt` (every cand note, grouped by Contracts note id, then slug), `briefings.txt` (Task 6; Task 14 adds its suppressed-claims section), `narration_candidates.html` (Task 7), `predicted_list.json`, `structure_changed_list.json`, `pilot_list.json` (10 rows of `predicted_list.json` in `sha1(slug)` order, at least 2 of them `briefing == "reuse"` when the list has that many: take the first 10, then swap the last non-reuse rows for the next reuse rows in the same order until 2 are reuse). Exit 0; exit 2 on a digest, config-fingerprint or setlist.fm mismatch between arms; exit 3 when the base arm reproduces fewer than 99% of its held shows that are not needs-LLM (base `outcome != "needs-llm"`; needs-LLM shows are counted and listed apart, never as drift).

`predicted_list.json` / `structure_changed_list.json` / `pilot_list.json`:

```json
{"sha": "...", "config_fingerprint": "...", "written_at": "<iso>",
 "rows": [{"slug": "...", "outcome": "clears|needs-brief", "briefing": "reuse|fresh",
           "digests": {...}}]}
```

### Reapply batch state

`<config.root>/reapply/<sha256(list file bytes)[:16]>/` containing `list.json` (a copy) and `progress.jsonl`, one JSON object per line: `{"slug", "outcome", "retryable": bool, "at": "<iso>"}`. A slug is finished when its last row has `retryable == false`.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `packages/llama/src/llama/models.py` | modify (T1) | `ShowNotes` |
| `packages/llama/src/llama/workspace.py` | modify (T1) | `ShowWorkspace.notes`, gather artifact list |
| `packages/llama/src/llama/stages/gather.py` | modify (T1, T8, T10, T13, T17, T18) | `GatherResult`, `compute_gather`/`run_gather` split, `needs_llm`; 2a pass; venue block; 5a evidence sets; 5c.2 call (dropped at Checkpoint F) |
| `packages/llama/src/llama/cli.py` | modify (T1, T19, T20, T21) | `show` prints notes; `reapply` command; `fix --untitled`, triage `[u]` |
| `packages/llama/src/llama/setlistfm.py` | modify (T2) | `cache_key` |
| `packages/llama/src/llama/replay.py` | create (T2, T4, T5) | cache-only clients, digests, config fingerprint, code identity, `compute_legs`, `briefing_reusable`, `ShowReplay`, `replay_show`, `flag_family` |
| `scripts/capture_fixture.py` | modify (T2) | `--from-cache` |
| `packages/llama/src/llama/stages/vet_research.py` | modify (T3, T15, T16) | `grounding_flags` 3-tuple, `apply_vet`/`VetOutcome`; 4c, 4b; 4a |
| `packages/llama/src/llama/stages/brief.py` | modify (T4, T14, T19) | `normalize_briefing` (T14), `generate_briefing` (T19); guard 3b/3c (T14) |
| `scripts/replay_holds.py` | create (T5, T6, T7), modify (T14, T18) | `run`, `compare`, narration page; suppressed-claims section (T14); 5c sections (T18) |
| `scripts/test_replay_holds.py` | create (T5, T6, T7), modify (T14, T18) | harness tests on a fixture library |
| `packages/llama/src/llama/stages/package.py` | modify (T19) | `build_package` extraction (no `show.json` write) |
| `packages/llama/src/llama/placeholders.py` | create (T8) | placeholder/timestamp/date/residue predicates |
| `packages/llama/src/llama/titles.py` | modify (T9, T11) | `tag_layer`, `placeholder_positions`, 2b in `resolve_titles`; 2c glued strip |
| `packages/llama/src/llama/structure.py` | modify (T12, T17) | 1b `venues_equivalent`, `cities_compatible`, `_one_edit`; 5a encore-lost helper |
| `packages/llama/src/llama/jerrybase.py` | modify (T18) | 5c.1, `anchor_numbered_sets` (dropped at Checkpoint F), leading-parenthetical fold |
| `packages/llama/src/llama/prompts/vet_research.md` | modify (T15) | 4d wording |
| `packages/llama/src/llama/reapply.py` | create (T19, T20) | `reapply_show`, batch state, list checks |
| `packages/llama/tests/fixtures/*.json` | create (T2, T9, T10, T11, T13) | captured items cut from the cache |
| `packages/llama/tests/test_*.py` | create/modify | per task |
| `CLAUDE.md`, `README.md` | modify (T22) | docs |

## Task list and suggested implementer models

| # | Task | Implementer |
|---|---|---|
| 1 | `compute_gather`/`GatherResult`, `needs_llm` verdict, `notes.json`, `llama show` notes | **Opus** (a refactor of the 400-line `run_gather` with an invariant: byte-identical behaviour with providers) |
| 2 | `llama/replay.py` clients + digests + `setlistfm.cache_key` + `capture_fixture.py --from-cache` | Sonnet |
| 3 | `apply_vet` / `VetOutcome`, `grounding_flags` 3-tuple | Sonnet |
| 4 | `compute_legs`, `briefing_reusable`, classification (`ShowReplay`) | **Opus** (ruling 5 lives here; the classification is the harness's whole meaning) |
| 5 | `scripts/replay_holds.py run` + fixture library + zero-writes test | **Opus** (IO discipline, read-only root, identity check) |
| 6 | `scripts/replay_holds.py compare` (gates, reports, lists, closest calls) | Sonnet (escalate to Opus on a BLOCKED-for-reasoning status) |
| 7 | Narration-candidates page | Sonnet |
| — | **Checkpoint A** (operator): base arm, reproduction gate, drift list | — |
| 8 | Parse vocabulary without the chosen description + `placeholders.py` predicates | **Opus** (defines 2a's veto and 2b's classes) |
| 9 | 2b placeholder demotion at the tag rung | **Opus** (strict surface: a real title demoted) |
| 10 | 2a corroborated short tags | **Opus** (strict surface: a wrong title accepted) |
| 11 | 2c glued track-number strip | Sonnet |
| — | **Checkpoint B** (operator): slice 2 hand-check lists | — |
| 12 | 1b `venues_equivalent` + `cities_compatible` | Sonnet |
| 13 | Gather venue block: steps 1–3, 1a, 1c, swap, two-venue signature, 1d | **Opus** (strict surface; ordering of six arms) |
| — | **Checkpoint C** (operator): slice 1 hand-check lists | — |
| 14 | Briefing guard 3a/3b/3c + reuse normalisation | **Opus** (superset invariant) |
| — | **Checkpoint D** (operator): stored-briefing re-check | — |
| 15 | 4c `normalize_date` ranges, 4b adjacent-day context, 4d prompt | Sonnet |
| 16 | 4a right-show gate | **Opus** (strict surface; depends on 2b) |
| — | **Checkpoint E** (operator): 4a decision point (0.5 vs 2/3), 4b hand-read | — |
| 17 | 5a numbered-sets evidence + unplaced-encore exception | Sonnet |
| 18 | 5c closer tolerance (filler tail, numbered-set anchoring, leading parenthetical) | **Opus** (anchoring rule; "zero changes on already-anchored shows") |
| — | **Checkpoint F** (operator): 5a/5c lists; 5c ships only if its lists pass | — |
| 19 | `llama reapply <show>`: single-show apply (lock, legs, write order) | **Opus** (write order and partial-failure contract) |
| 20 | `reapply --from-list`/`--dry-run`: batch state, pacing gate, stop rules, list checks | **Opus** |
| 21 | `fix --untitled` and triage `[u]` | Sonnet |
| 22 | Docs: CLAUDE.md, README | Sonnet |
| — | **Checkpoint G** (operator): final harness compare, hand checks, dry run, bulk-cost re-ask, 10-show pilot, waves, post-run harness | — |

Task order is the spec's: slice 0 (1–7) first; 2b (9) before 4a (16); slice 6 (19–20) before any apply; 1, 2c, 3, 4b/4c, 5a, 5c, 7 are otherwise independent. The orchestrator stops at every checkpoint and reports; a failed checkpoint goes back to the owning task.

**Why the base arm is the slice-0 commit and not a `main` checkout.** The harness and its library module do not exist on `main` until slice 0 merges, so a `main` checkout cannot run `scripts/replay_holds.py`. Checkpoint A tags the slice-0 commit `tier1-base` (its gather/vet/brief code is `main`'s unchanged; acceptance item 2, ≥ 99 % reproduction of stored flags, is what proves that equivalence) and creates a second checkout of it. The library is live, so a saved arm goes stale (a triage, fix or `llama get` between checkpoints makes `compare` exit 2): **every checkpoint re-runs the base arm from the `tier1-base` checkout in the same sitting as the candidate**, per "Measuring at a checkpoint" below, and also compares the previous checkpoint's commit against the current one, so each slice gets its own delta.

**Operator time: an Opus pre-screen at every hand-check checkpoint (B, C, D, E, F, G).** This replaces the spec's full hand reads with pre-screen + flagged + sample; the operator confirms this at plan approval. Before asking the operator, the orchestrator announces and dispatches one read-only pre-screen agent per checkpoint on **Opus**. It reads that checkpoint's lists plus the arm JSON, and per show `show.json`, `research.md` and the cached description (`~/.llama/cache/md_<identifier>.json`), and writes only `$H/cmp-<X>-all/prescreen.md`: every row of every list classed `routine` or `flagged` with a one-line reason, flagged rows first, using the per-list rules given at each checkpoint. The operator reads every flagged row plus a fixed deterministic sample of 20 routine rows per list (the 20 with the smallest `sha1(row text)`), and signs off the rest on the pre-screen's summary; the full lists stay attached. The orchestrator keeps each checkpoint's approved rows in `$H/approved-<X>.txt` (one row per line, verbatim), which Checkpoint G uses.

---

### Task 1: `compute_gather` / `GatherResult`, the `needs_llm` verdict, `notes.json`

Spec: "Slice 0 — LLM-free gather", ruling 6.

**Files:**
- Modify: `packages/llama/src/llama/models.py` (append `ShowNotes` after `Overrides`)
- Modify: `packages/llama/src/llama/workspace.py` (`ShowWorkspace.__init__`, `show_stage_artifacts`)
- Modify: `packages/llama/src/llama/stages/gather.py` (`CanonicalBuild`, `build_canonical`, `run_gather`)
- Modify: `packages/llama/src/llama/cli.py` (`_print_show_entry`, after the needs-review block; `_print_show_json`)
- Test: `packages/llama/tests/test_stage_gather.py` (append), `packages/llama/tests/test_show_cmd.py` (append), `packages/llama/tests/test_workspace.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `llama.models.ShowNotes(BaseModel)`: `gather: list[str] = []`, `vet: list[str] = []`.
  - `ShowWorkspace.notes: Path` (= `dir / "notes.json"`); `show_stage_artifacts(ws, "gather")` returns `[ws.show, ws.reviews, ws.notes]`.
  - `gather.CanonicalBuild` gains a trailing field `needs_llm: bool = False` (True when `rank_parses` returned None, `provider is None`, and the longest description is non-blank: the `extract_setlist` branch was reached and not taken).
  - `gather.GatherResult(NamedTuple)`: `show: Show`, `reviews: list[dict]`, `notes: list[str]`, `needs_llm: tuple[str, ...]` (each of `"extract_setlist"`, `"align_structure"` at most once, in that order).
  - `gather.compute_gather(show_ws, ia, provider, candidate, identifier, *, audio_format="mp3", align_provider=None, setlistfm=None, structure_cfg=None, jerrybase_enabled=False) -> GatherResult`: everything `run_gather` does today except `should_run` and the writes. It reads `overrides.json` from `show_ws` and nothing else from it.
  - `gather.run_gather(...)` keeps its signature and return type; body = `should_run` check, `res = compute_gather(...)`, write `show.json`, `reviews.json`, `notes.json` (`ShowNotes(gather=res.notes, vet=[])`), return `res.show`.

`needs_llm` for `align_structure`: in the `elif canonical.items and result.coverage < threshold` branch, when `align_provider is None`, record `"align_structure"` (the flag `low-confidence structure alignment` is still appended, exactly as today, so existing behaviour and tests are unchanged). With a provider, the branch behaves as today and records nothing. `CanonicalBuild.needs_llm` maps to `"extract_setlist"`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_stage_gather.py`:

```python
# --- Tier 1 slice 0: LLM-free gather reports needs-LLM (spec "Slice 0") ---

from llama.models import ShowNotes
from llama.stages.gather import GatherResult, compute_gather


def _low_coverage_candidate():
    """gd73 fixture with a description whose setlist shares nothing with the
    tape's tags, so align() lands under the threshold and the
    align_structure branch is reached."""
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = "Set 1: Alpha, Beta, Gamma, Delta, Epsilon, Zeta\nSet 2: Eta, Theta"
    return md


def test_compute_gather_reports_align_structure_without_a_provider(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(_low_coverage_candidate()), None, make_candidate(), IDENT,
                         align_provider=None, jerrybase_enabled=False)
    assert isinstance(res, GatherResult)
    assert res.needs_llm == ("align_structure",)
    assert "low-confidence structure alignment" in res.show.review_flags   # degraded flag unchanged
    assert not sws.show.exists() and not sws.notes.exists()                 # compute writes nothing


def test_compute_gather_reports_extract_setlist_without_a_provider(tmp_path):
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = "a lovely tape, no setlist here, just prose about the night"
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(md), None, make_candidate(), IDENT, jerrybase_enabled=False)
    assert res.needs_llm == ("extract_setlist",)


def test_compute_gather_empty_description_is_not_needs_llm(tmp_path):
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = ""
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(md), None, make_candidate(), IDENT, jerrybase_enabled=False)
    assert res.needs_llm == ()


def test_compute_gather_with_a_provider_records_nothing_and_calls_it(tmp_path):
    provider = FakeProvider(completes=[json.dumps({"tracks": [
        {"index": i, "set": "1", "segue": False, "matched_title": "x"} for i in range(1, 7)]})])
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(_low_coverage_candidate()), FakeProvider(), make_candidate(),
                         IDENT, align_provider=provider, jerrybase_enabled=False)
    assert res.needs_llm == ()
    assert provider.calls


def test_run_gather_writes_notes_json_and_returns_the_show(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    notes = read_model(sws.notes, ShowNotes)
    assert notes == ShowNotes(gather=[], vet=[])
    assert show.tracks and sws.show.exists()


def test_run_gather_replaces_notes_json_on_force(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.notes, ShowNotes(gather=["stale"], vet=["stale"]))
    run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT, force=True)
    assert read_model(sws.notes, ShowNotes) == ShowNotes()
```

(`read_model` is imported at the top of the file already as part of `llama.workspace`; add it to that import if not.)

Append to `packages/llama/tests/test_workspace.py`:

```python
def test_notes_json_is_a_gather_artifact(tmp_path):
    from llama.workspace import ShowWorkspace, drop_stage_artifacts, show_stage_artifacts, write_artifact
    ws = ShowWorkspace(tmp_path / "s")
    assert ws.notes == tmp_path / "s" / "notes.json"
    assert ws.notes in show_stage_artifacts(ws, "gather")
    write_artifact(ws.notes, {"gather": [], "vet": []})
    drop_stage_artifacts(ws, "gather")
    assert not ws.notes.exists()
```

Append to `packages/llama/tests/test_show_cmd.py` (use that file's existing config/show builders; `build` from `test_catalog`):

```python
def test_show_prints_notes_json_under_a_notes_heading(tmp_path):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    write_artifact(ws.notes, {"gather": ["venue differs from jerrybase: archive 'A' vs 'B' (same city)"],
                              "vet": ["unknown-song flags suppressed by the right-show gate: 4/5 tape tracks asserted (ratio 0.80), 1 unclaimed: X; research date: 1973-06-10"]})
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert r.exit_code == 0, r.output
    assert "notes:" in r.output
    assert "  - venue differs from jerrybase: archive 'A' vs 'B' (same city)" in r.output
    assert "  - unknown-song flags suppressed by the right-show gate" in r.output


def test_show_without_notes_json_prints_no_notes_heading(tmp_path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert "notes:" not in r.output
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py packages/llama/tests/test_workspace.py packages/llama/tests/test_show_cmd.py -q`
Expected: `ImportError: cannot import name 'ShowNotes'` / `GatherResult`, then `AttributeError: 'ShowWorkspace' object has no attribute 'notes'`.

- [ ] **Step 3: Implement**

1. `models.ShowNotes` as in Interfaces.
2. `workspace.ShowWorkspace.notes`; add `show_ws.notes` to the `"gather"` list in `show_stage_artifacts`.
3. `gather.py`: add `needs_llm: bool = False` to `CanonicalBuild`; in `build_canonical`, set it when `best is None and provider is None and longest.strip()`. Change `run_gather`'s 3-tuple unpack of `build_canonical` to attribute access (`cb = build_canonical(...)`; `canonical, notes, canonical_source = cb.setlist, cb.notes, cb.source`). Grep for other `build_canonical(` callers (`cli.py`'s `_propose_titles_for_show`) and switch any tuple unpack to attribute access.
4. Move the body of `run_gather` after the `should_run` check into `compute_gather`, returning `GatherResult(show=Show(...), reviews=md.get("reviews", []), notes=[], needs_llm=tuple(...))`; `notes=[]` for now (later tasks append). `GatherResult.notes` is a new list (name it `op_notes` in the body), separate from gather's existing local `notes`, which keeps flowing into `structure.conflicts` exactly as today; no later task appends an operator note to the local `notes`. Do not call `write_artifact` inside `compute_gather`. `run_gather` becomes the thin wrapper described in Interfaces and writes the three artifacts.
5. `cli._print_show_entry`: after the needs-review block (and before the `show_tracks` block) print `notes:` followed by `  - {line}` for every entry of `ShowNotes.gather + ShowNotes.vet` when `sws.notes.exists()` and the lists are non-empty. `_print_show_json`: add a `"notes": {"gather": [...], "vet": [...]}` key (empty lists when the file is absent).

- [ ] **Step 4: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: all green; the gather count rises by the six new tests, `test_show_cmd` by two, `test_workspace` by one.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/models.py packages/llama/src/llama/workspace.py packages/llama/src/llama/stages/gather.py packages/llama/src/llama/cli.py packages/llama/tests/test_stage_gather.py packages/llama/tests/test_workspace.py packages/llama/tests/test_show_cmd.py
git commit -m "feat(gather): compute_gather with a needs-LLM verdict and notes.json"
```

---

### Task 2: Cache-only clients, input digests, `setlistfm.cache_key`, `capture_fixture.py --from-cache`

Spec: "Slice 0 — Replay, per show" (the two clients), "Each arm records ..." (digests, config fingerprint).

**Files:**
- Modify: `packages/llama/src/llama/setlistfm.py` (`SetlistFMClient.setlist`)
- Create: `packages/llama/src/llama/replay.py`
- Modify: `scripts/capture_fixture.py`
- Test: `packages/llama/tests/test_replay.py` (create), `packages/llama/tests/test_setlistfm.py` (append), `scripts/test_capture_fixture.py` (create)

**Interfaces:**
- Produces:
  - `setlistfm.cache_key(artist: str, date: str) -> str` = `"slfm_" + hashlib.sha1(f"{artist}|{date}".encode()).hexdigest()`; `SetlistFMClient.setlist` uses it (the literal moves, nothing else changes).
  - `replay.CacheMiss(LlamaError)`.
  - `replay.CacheOnlyIA(cache_dir: Path)`: `metadata(identifier) -> dict` reads `cache_dir / f"md_{identifier}.json"`, raises `CacheMiss(f"cache miss: md_{identifier}.json")` when absent; `search`, `scrape`, `download_file` raise `CacheMiss("network refused by the cache-only client")`; attribute `misses: list[str]` (identifiers that missed).
  - `replay.CacheOnlySetlistFM(cache_dir: Path)`: `setlist(artist, date, venue=None, city=None) -> dict | None` reads `cache_dir / (cache_key(artist, date) + ".json")` and returns `setlistfm._pick(data.get("setlist", []), venue, city)`; a missing file returns `None` and appends `(artist, date)` to `self.misses`.
  - `replay.input_digests(ws: ShowWorkspace) -> dict[str, str | None]` with keys `show.json`, `overrides.json`, `provenance.json`, `research.md`, `vetting.extraction`: sha256 hex of the file bytes, `None` when the file is absent; `vetting.extraction` = sha256 of `VettingResult.vetting.model_dump_json()` (never the flags).
  - `replay.config_fingerprint(config: Config) -> str`: sha256 of `json.dumps({"audio_format", "structure": config.structure.model_dump(), "jerrybase": config.jerrybase.model_dump(), "setlistfm_configured": bool(os.environ.get("SETLISTFM_API_KEY") or config.setlistfm.api_key)}, sort_keys=True)`.
  - `replay.code_identity() -> str`: `git -C <dir of llama.__file__> rev-parse HEAD` stripped, with `-dirty` appended when `git -C <same dir> status --porcelain` prints anything, when git succeeds; else `f"version:{llama.__version__}"`. (A list written from uncommitted code therefore never matches a later run's identity in `load_list`.)
  - `replay.setlistfm_configured(config: Config) -> bool` = `bool(os.environ.get("SETLISTFM_API_KEY") or config.setlistfm.api_key)` (the same test `setlistfm.make_client` makes); `config_fingerprint` uses it.
  - `replay.setlistfm_client(config: Config) -> CacheOnlySetlistFM | None`: `CacheOnlySetlistFM(config.root / "cache")` when `setlistfm_configured(config)`, else `None`. The ONE place the setlist.fm client is chosen: the harness (Task 5) and `reapply` (Task 19) both call it, so prediction and apply gather against the same setlist.fm evidence.
  - `scripts/capture_fixture.py --from-cache <identifier> [out.json] [--cache DIR]`: reads `<DIR>/md_<identifier>.json` (`--cache` defaults to `~/.llama/cache`) and writes the same slim shape `capture_ia` writes, with no network call.

- [ ] **Step 1: Write the failing tests**

`packages/llama/tests/test_replay.py`:

```python
"""llama.replay: cache-only clients and the harness's input digests (spec slice 0)."""
import json
from pathlib import Path

import pytest

from llama.config import Config
from llama.models import ResearchVetting, VettingResult
from llama.replay import (CacheMiss, CacheOnlyIA, CacheOnlySetlistFM, code_identity,
                          config_fingerprint, input_digests, setlistfm_client)
from llama.setlistfm import cache_key
from llama.workspace import ShowWorkspace, write_artifact


def test_cache_only_ia_reads_the_cache_and_refuses_the_network(tmp_path):
    (tmp_path / "md_x.json").write_text(json.dumps({"metadata": {"title": "t"}, "files": []}))
    ia = CacheOnlyIA(tmp_path)
    assert ia.metadata("x")["metadata"]["title"] == "t"
    with pytest.raises(CacheMiss):
        ia.metadata("missing")
    assert ia.misses == ["missing"]
    for call in (lambda: ia.search("q", ["identifier"]),
                 lambda: ia.scrape("q", ["identifier"]),
                 lambda: ia.download_file("x", "a.mp3", tmp_path / "a.mp3")):
        with pytest.raises(CacheMiss):
            call()


def test_cache_only_setlistfm_uses_the_clients_key_and_counts_misses(tmp_path):
    raw = {"setlist": [{"venue": {"name": "RFK Stadium"}, "sets": {"set": []}}]}
    (tmp_path / (cache_key("Grateful Dead", "1973-06-10") + ".json")).write_text(json.dumps(raw))
    sl = CacheOnlySetlistFM(tmp_path)
    assert sl.setlist("Grateful Dead", "1973-06-10", venue="RFK Stadium") == raw["setlist"][0]
    assert sl.setlist("Grateful Dead", "1973-06-11") is None
    assert sl.misses == [("Grateful Dead", "1973-06-11")]


def test_input_digests_cover_the_five_inputs_and_ignore_vet_flags(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.show, {"a": 1})
    write_artifact(ws.provenance, {"b": 2})
    ws.research.write_text("r")
    v = VettingResult(vetting=ResearchVetting(asserted_songs=["X"]), flags=["research asserts unknown song: X"])
    write_artifact(ws.vetting, v)
    d = input_digests(ws)
    assert set(d) == {"show.json", "overrides.json", "provenance.json", "research.md", "vetting.extraction"}
    assert d["overrides.json"] is None
    write_artifact(ws.vetting, v.model_copy(update={"flags": []}))
    assert input_digests(ws)["vetting.extraction"] == d["vetting.extraction"]
    write_artifact(ws.vetting, v.model_copy(update={"vetting": ResearchVetting(asserted_songs=["Y"])}))
    assert input_digests(ws)["vetting.extraction"] != d["vetting.extraction"]


def test_config_fingerprint_changes_with_structure_and_setlistfm(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    a = config_fingerprint(Config())
    assert a == config_fingerprint(Config())
    assert a != config_fingerprint(Config(structure={"align_coverage_threshold": 0.7}))
    monkeypatch.setenv("SETLISTFM_API_KEY", "k")
    assert a != config_fingerprint(Config())


def test_code_identity_is_a_git_sha_or_a_version_string():
    import re
    ident = code_identity()
    assert re.fullmatch(r"[0-9a-f]{40}(?:-dirty)?", ident) or ident.startswith("version:")


def test_setlistfm_client_is_none_unless_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    assert setlistfm_client(Config(root=tmp_path)) is None
    monkeypatch.setenv("SETLISTFM_API_KEY", "k")
    client = setlistfm_client(Config(root=tmp_path))
    assert isinstance(client, CacheOnlySetlistFM)
```

Append to `packages/llama/tests/test_setlistfm.py`:

```python
def test_cache_key_is_the_key_the_client_writes(tmp_path, monkeypatch):
    from llama.setlistfm import cache_key
    client = _client(tmp_path)   # the file's existing builder at line ~27; adapt its name
    # drive one lookup through the stub transport the file already uses, then:
    client.setlist("Grateful Dead", "1973-06-10")
    assert (tmp_path / "cache" / (cache_key("Grateful Dead", "1973-06-10") + ".json")).exists()
```

(Read `test_setlistfm.py` first and reuse its stubbed-`httpx.Client` builder; the assertion is the key's file existing after one call.)

`scripts/test_capture_fixture.py`:

```python
"""scripts/capture_fixture.py --from-cache cuts a fixture from ~/.llama/cache offline."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import capture_fixture as cf


def test_from_cache_writes_the_slim_shape(tmp_path):
    root = tmp_path / "root"
    (root / "cache").mkdir(parents=True)
    full = {"metadata": {"title": "t", "description": "d"},
            "files": [{"name": "a.mp3", "format": "VBR MP3", "length": "100", "md5": "m", "title": "A",
                       "size": "1", "crc32": "x"}],
            "reviews": [{"reviewtitle": "r"}], "server": "ia800"}
    (root / "cache" / "md_x.json").write_text(json.dumps(full))
    out = tmp_path / "x.json"
    cf.main(["--from-cache", "x", str(out), "--cache", str(root / "cache")])
    slim = json.loads(out.read_text())
    assert set(slim) == {"metadata", "files", "reviews"}
    assert slim["files"] == [{"name": "a.mp3", "format": "VBR MP3", "length": "100", "md5": "m", "title": "A"}]
```

(`capture_fixture.main` currently reads `sys.argv`; change it to `main(argv: list[str] | None = None)`.)

- [ ] **Step 2: Run the tests and watch them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_replay.py packages/llama/tests/test_setlistfm.py scripts/test_capture_fixture.py -q`
Expected: `ModuleNotFoundError: No module named 'llama.replay'`; `ImportError: cannot import name 'cache_key'`; `TypeError: main() takes 0 positional arguments`.

- [ ] **Step 3: Implement** per Interfaces. `replay.py` imports only `llama.errors`, `llama.setlistfm._pick`/`cache_key`, `llama.models`, `llama.workspace`, `llama.config`; no stage imports yet (Task 4 adds them).

- [ ] **Step 4: Run the full suite** — `./.venv/bin/python -m pytest -q`, all green.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/setlistfm.py packages/llama/src/llama/replay.py scripts/capture_fixture.py packages/llama/tests/test_replay.py packages/llama/tests/test_setlistfm.py scripts/test_capture_fixture.py
git commit -m "feat(replay): cache-only clients, input digests, config fingerprint, fixtures from the cache"
```

---

### Task 3: `apply_vet` / `VetOutcome`, `grounding_flags` returns notes

Spec: "Slice 0 — vet leg", ruling 6 ("vet adds 4a's note to the file gather wrote").

**Files:**
- Modify: `packages/llama/src/llama/stages/vet_research.py`
- Test: `packages/llama/tests/test_stage_vet.py` (modify the `grounding_flags` call sites; append)

**Interfaces:**
- Produces:
  - `grounding_flags(vetting, show) -> tuple[list[str], str | None, list[str]]`: the third element is the vet notes list, always `[]` until Task 16.
  - `vet_research.VetOutcome(NamedTuple)`: `show: Show` (a copy with the adoption applied and the `research asserts ` flags replaced), `result: VettingResult`, `notes: list[str]`.
  - `vet_research.apply_vet(vetting: ResearchVetting, show: Show) -> VetOutcome`: pure. Applies the placeholder-date adoption to a `model_copy` of `show` (`item_date`, `date`, `date_source="research"`), sets `review_flags` = flags not starting with `_VET_FLAG_PREFIX` + the new flags, `needs_review = bool(review_flags)`, and returns `VettingResult(vetting=vetting, flags=flags, adopted_date=adopted)`.
  - `run_vet_research` unchanged in signature; body: run the LLM task, `out = apply_vet(vetting, read_model(show_ws.show, Show))`, write `show.json` from `out.show`, write `vetting.json` from `out.result`, and update `notes.json` (`ShowNotes` read if present else empty; `vet = out.notes`; write).

- [ ] **Step 1: Write the failing tests**

Update every existing `grounding_flags(...)` 2-tuple unpack in `test_stage_vet.py` to a 3-tuple (`flags, adopted, notes = ...`). Append:

```python
from llama.models import ResearchVetting, ShowNotes, VettingResult
from llama.stages.vet_research import VetOutcome, apply_vet


def test_apply_vet_is_pure_and_replaces_only_its_own_flags():
    show = make_show().model_copy(update={"review_flags": ["unresolved track titles",
                                                           "research asserts wrong date: 1970-01-01"],
                                          "needs_review": True})
    out = apply_vet(ResearchVetting(asserted_songs=["Morning Dew", "Dark Star"],
                                    asserted_dates=["1973-06-10"]), show)
    assert isinstance(out, VetOutcome)
    assert out.show.review_flags == ["unresolved track titles"]
    assert out.show.needs_review is True
    assert show.review_flags[1].startswith("research asserts")        # input untouched
    assert out.result.flags == [] and out.result.adopted_date is None
    assert out.notes == []


def test_apply_vet_adopts_a_placeholder_date_on_the_copy():
    show = make_show().model_copy(update={"date": "1973-01-01"})
    out = apply_vet(ResearchVetting(asserted_songs=["Morning Dew", "Dark Star"],
                                    asserted_dates=["1973-06-10"]), show)
    assert (out.show.date, out.show.item_date, out.show.date_source) == ("1973-06-10", "1973-01-01", "research")
    assert out.result.adopted_date == "1973-06-10"
    assert show.date == "1973-01-01"


def test_run_vet_research_writes_vet_notes_into_notes_json(tmp_path):
    sws, show = setup(tmp_path)
    write_artifact(sws.notes, ShowNotes(gather=["g"], vet=["stale"]))
    run_vet_research(sws, FakeProvider([vet_json()]), show, "research")
    assert read_model(sws.notes, ShowNotes) == ShowNotes(gather=["g"], vet=[])
```

- [ ] **Step 2: Run** `./.venv/bin/python -m pytest packages/llama/tests/test_stage_vet.py -q` — Expected: `ImportError: cannot import name 'VetOutcome'`.

- [ ] **Step 3: Implement** per Interfaces. `run_vet_research` must produce byte-identical `show.json`/`vetting.json` to today (its existing tests pin that).

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Commit** — `git commit -m "refactor(vet): apply_vet, a pure grounding step with notes"`

---

### Task 4: `compute_legs`, `briefing_reusable`, outcome classification

Spec: "Slice 0 — Replay, per show" (the three legs), "Outcome classes", "Title-source changes", ruling 5, "Slice 6 — The command" step 3 (the reuse rule).

**Files:**
- Modify: `packages/llama/src/llama/replay.py`
- Test: `packages/llama/tests/test_replay.py` (append)

**Interfaces:**
- Consumes: `gather.compute_gather`, `vet_research.apply_vet`, `brief.briefing_guard` (Task 14 later swaps in `normalize_briefing` before the guard; until then `briefing_reusable` calls the guard directly).
- Produces, all in `llama/replay.py`:
  - `briefing_reusable(stored_show: Show, new_show: Show, briefing: Briefing, narration: str) -> str | None`: `None` when reusable; else the first failing reason among `"broadcast fields changed: <field list>"` (titles / sets / segues per track, `set_breaks`, `date`, `venue`, `city`), `"narration differs: briefing <x>, overrides <y>"`, `"briefing guard: <problem>; ..."`.
  - `Legs(dataclass)`: `gather: GatherResult`, `stored: Show`, `vet: VetOutcome | None`, `needs_llm: list[str]` (gather's verdicts, plus `"stored alignment llm"` when `stored.structure` is not None and its `alignment == "llm"`, plus `"no vetting.json"` when absent), `brief: str` (`"reuse"|"fresh"|"none"`), `brief_reason: str | None`, `brief_flags: list[str]`, `briefing: Briefing | None`, `carried_flags: list[str]` (stored `package` family), `flags: list[str]` (= gather flags + vet flags + carried + brief_flags; gather flags are `gather.show.review_flags`, vet flags are `vet.result.flags`).
  - `compute_legs(ws: ShowWorkspace, *, config: Config, ia, slfm: CacheOnlySetlistFM | None, scratch: Path) -> Legs` (`slfm` is `None` when no setlist.fm key is configured, exactly as `process_show` passes `make_client(config)`; every production caller passes `setlistfm_client(config)` from Task 2 and nothing else): copies `overrides.json` into `scratch` (a fresh `ShowWorkspace(scratch)`), reads `provenance.json` and `show.json`, runs `compute_gather(scratch_ws, ia, None, prov.candidate, stored.identifier, audio_format=config.audio_format, align_provider=None, setlistfm=slfm, structure_cfg=config.structure, jerrybase_enabled=config.jerrybase.enabled)`, then `apply_vet` over the stored `VettingResult.vetting` when `vetting.json` exists (the show passed to it is the replayed one), then the brief leg only when `flags` so far are empty: `briefing.json` present → `briefing_reusable(stored, vetted_show, briefing, read_overrides(ws).narration)`; `None` → `brief="reuse"`, `brief_flags = briefing_guard(briefing, vetted_show)` (empty by construction when reusable); a reason → `brief="fresh"`; absent → `brief="fresh"`. `flags` non-empty → `brief="none"`. Raises `CacheMiss` through; raises `LlamaError` on a missing `provenance.json`/`show.json`.
  - `classify(legs: Legs, stored_state: str) -> tuple[str, str | None]` → `(outcome, would_be)` per the Contracts: needs-LLM first (`legs.needs_llm` non-empty, except `"no vetting.json"` alone when gather flags are non-empty: that show is simply still held); then, for a held show: carried package flags → `still-held-package`; any flag → `still-held`; `brief == "reuse"` → `clears`, `"fresh"` → `needs-brief`; and when the would-clear show's shipped structure differs from the stored (`sets`, `segues`, `set_breaks`, `structure.alignment`) → `("structure-changed", would_be)`. For a non-held show: flags → `newly-held`; shipped fields differ → `clean-changed`; else `clean`.
  - `shipped_diff(stored: Show, new: Show) -> dict` with keys `title_changes, venue, city, set_changes, segue_changes, set_breaks, alignment, date` in the Contracts' shapes (`None`/`[]` when equal). A track-count change is reported as every index in `title_changes` with `new=None`.
  - `flag_family(flag: str) -> str` per the Contracts table.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_replay.py`:

```python
from herder import FakeProvider
from llama.models import Briefing, Candidate, Provenance, RecordingSummary, Show, Track
from llama.replay import Legs, briefing_reusable, classify, compute_legs, flag_family, shipped_diff
from llama.stages.gather import run_gather

FIXTURES = Path(__file__).parent / "fixtures"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"


def _config(root: Path) -> Config:
    """Jerrybase OFF: the vendored CSV has GD 1973-06-10 with three numbered
    sets, and the trimmed gd73 fixture has two, so an enabled dataset would
    hold the fixture show. The stored show and the replay use this same config."""
    return Config(root=root, jerrybase={"enabled": False})


def _library_show(root: Path, *, held: bool, date="1973-06-10",
                  held_flags=("unresolved track titles",), asserted_dates=None,
                  with_vetting=True, with_briefing=False, alignment=None, description=None):
    """A gathered gd73 show `gratefuldead-<date>` in <root>/shows/, produced by
    the real run_gather against the fixture under `_config(root)` (so the
    replay reproduces it), with the knobs the tests need. `held` appends
    `held_flags` to the stored flags; the default flag is one the replay does
    not raise (a synthetic hold: the replay clears it). `asserted_dates`
    defaults to `[date]`, so the vetting matches the show's own date."""
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
    cfg = _config(root)
    show = run_gather(ws, _IA(), FakeProvider(), cand, IDENT, structure_cfg=cfg.structure,
                      jerrybase_enabled=cfg.jerrybase.enabled)
    if alignment:
        show.structure = show.structure.model_copy(update={"alignment": alignment})
    if held:
        show.review_flags = show.review_flags + list(held_flags)
        show.needs_review = True
    write_artifact(ws.show, show)
    if with_vetting:
        write_artifact(ws.vetting, VettingResult(vetting=ResearchVetting(
            asserted_songs=["Morning Dew", "Dark Star"],
            asserted_dates=list(asserted_dates) if asserted_dates is not None else [date])))
    if with_briefing:
        write_artifact(ws.briefing_json, Briefing(context="c", significance="s",
                                                  per_set={"1": ["a"], "2": ["b"], "encore": ["c"]}))
    return ws, show


def _legs(root, ws):
    return compute_legs(ws, config=_config(root), ia=CacheOnlyIA(root / "cache"),
                        slfm=None, scratch=root / "scratch" / ws.dir.name)


def test_compute_legs_reproduces_a_stored_show_and_writes_nothing_to_it(tmp_path):
    ws, stored = _library_show(tmp_path, held=False, with_briefing=True)
    before = {p.name: p.read_bytes() for p in ws.dir.iterdir()}
    legs = _legs(tmp_path, ws)
    assert isinstance(legs, Legs)
    assert legs.gather.show.review_flags == [] and legs.vet.result.flags == []
    assert legs.brief == "reuse" and legs.brief_flags == []
    assert legs.needs_llm == []
    assert {p.name: p.read_bytes() for p in ws.dir.iterdir()} == before
    assert classify(legs, "briefed") == ("clean", None)


def test_stored_llm_alignment_is_needs_llm(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, alignment="llm")
    legs = _legs(tmp_path, ws)
    assert "stored alignment llm" in legs.needs_llm
    assert classify(legs, "held") == ("needs-llm", None)


def test_missing_vetting_json_is_needs_llm_only_when_gather_clears(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, with_vetting=False)
    legs = _legs(tmp_path, ws)
    assert legs.needs_llm == ["no vetting.json"]
    assert classify(legs, "held") == ("needs-llm", None)


def test_held_show_whose_replay_clears_with_a_reusable_briefing_is_clears(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, with_briefing=True)
    legs = _legs(tmp_path, ws)
    assert legs.flags == [] and legs.brief == "reuse"
    assert classify(legs, "held") == ("clears", None)


def test_held_show_whose_replay_clears_without_a_briefing_is_needs_brief(tmp_path):
    ws, _ = _library_show(tmp_path, held=True)
    legs = _legs(tmp_path, ws)
    assert legs.brief == "fresh"
    assert classify(legs, "held") == ("needs-brief", None)


def test_carried_package_flag_is_still_held_package(tmp_path):
    ws, show = _library_show(tmp_path, held=True)
    show.review_flags = ["duration mismatch on 01 - Morning Dew.mp3: file 10s vs metadata 20s"]
    write_artifact(ws.show, show)
    legs = _legs(tmp_path, ws)
    assert legs.carried_flags == show.review_flags and legs.brief == "none"
    assert classify(legs, "held") == ("still-held-package", None)


def test_structure_change_on_a_would_clear_show_is_listed_apart(tmp_path):
    ws, show = _library_show(tmp_path, held=True, with_briefing=True)
    show.tracks = [t.model_copy(update={"set": "1"}) for t in show.tracks]   # stored labels differ
    show.set_breaks = []
    write_artifact(ws.show, show)
    legs = _legs(tmp_path, ws)
    assert classify(legs, "held") == ("structure-changed", "needs-brief")   # fields changed, so no reuse
    d = shipped_diff(show, legs.gather.show)
    assert d["set_changes"] and d["set_breaks"] == {"old": [], "new": [3, 5]}


def test_briefing_reusable_reasons():
    show = Show(performance_id="A/1973-06-10", identifier="x", artist="A", date="1973-06-10",
                venue="V", tracks=[Track(index=1, set="1", title="Dew", filename="a.mp3", title_source="tags")])
    b = Briefing(context="c", significance="s", per_set={"1": ["x"]})
    assert briefing_reusable(show, show, b, "full") is None
    assert briefing_reusable(show, show.model_copy(update={"venue": "W"}), b, "full").startswith("broadcast fields changed: venue")
    assert briefing_reusable(show, show, b, "vague").startswith("narration differs")
    bad = b.model_copy(update={"mentioned_songs": ["Nope"]})
    assert briefing_reusable(show, show, bad, "full").startswith("briefing guard: briefing mentions unknown song: Nope")


def test_reuse_refused_when_recorded_narration_differs():
    # Review Focus 3: a briefing.json written before `narration` existed reads as "full".
    show = Show(performance_id="A/1973-06-10", identifier="x", artist="A", date="1973-06-10",
                tracks=[Track(index=1, set="1", title="Dew", filename="a.mp3", title_source="tags")])
    legacy = Briefing.model_validate({"context": "c", "significance": "s", "per_set": {"1": ["x"]}})
    assert legacy.narration == "full"
    assert briefing_reusable(show, show, legacy, "vague") is not None


@pytest.mark.parametrize("flag, family", [
    ("venue mismatch: archive 'A' vs jerrybase 'B'", "venue"),
    ("recordings of this date disagree on city: 'A' (selected) vs 'B'", "city"),
    ("unresolved track titles", "titles"),
    ("research asserts unknown song: X", "research-song"),
    ("research asserts 2 sets but structure has 1", "research-sets"),
    ("research asserts wrong date: 1 Jan", "research-date"),
    ("research asserts 1973-06-10; item date 1973-01-01 looks like a year-only placeholder", "research-date"),
    ("briefing mentions unknown song: X", "briefing"),
    ("low-confidence structure alignment", "structure"),
    ("structure has 1 sets but jerrybase shows 2", "structure"),
    ("jerrybase set closer 'X' is not at a set break", "structure"),
    ("duration mismatch on 01 - X.mp3: file 1s vs metadata 2s", "package"),
    ("tape spans 2 events", "events"),
    ("no playable tracks", "tracks"),
    ("something else", "other"),
])
def test_flag_family(flag, family):
    assert flag_family(flag) == family
```

- [ ] **Step 2: Run** `./.venv/bin/python -m pytest packages/llama/tests/test_replay.py -q` — Expected: `ImportError: cannot import name 'Legs'`.

- [ ] **Step 3: Implement** per Interfaces. `compute_legs` deletes and recreates `scratch` at entry (so a stale scratch never leaks state) and never touches `ws.dir`.

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_replay.py`. Mutants: (a) `classify` checks flags before needs-LLM; (b) `classify` drops the "`no vetting.json` alone with gather flags is still held" exception; (c) `compute_legs` omits `"stored alignment llm"`; (d) `briefing_reusable` skips the narration comparison. A survivor gets a test.

- [ ] **Step 6: Commit** — `git commit -m "feat(replay): compute_legs, briefing reuse rule and outcome classification"`

---

### Task 5: `scripts/replay_holds.py run`

Spec: "Slice 0 — What", "Two subcommands" (`run`), "Replay, per show", "Output per show", acceptance 3 (zero writes, read-only root).

**Files:**
- Modify: `packages/llama/src/llama/replay.py` (`ShowReplay`, `replay_show`)
- Create: `scripts/replay_holds.py`
- Create: `scripts/test_replay_holds.py`
- Create: `packages/llama/tests/fixture_library.py` (a plain helper module like `tests/helpers.py`: builds a two-show fixture library; imported by the scripts test via `sys.path` as `test_purge_delivered_audio.py` does)
- Test: `packages/llama/tests/test_replay.py` (append)

**Interfaces:**
- Consumes: `replay.compute_legs`, `classify`, `shipped_diff`, `input_digests`, `config_fingerprint`, `code_identity`, `setlistfm_client`, `flag_family`, `brief.briefing_guard`, `catalog.derive_state`, `Ledger`.
- Produces:
  - `replay.ShowReplay(dataclass)` with the Contracts' fields and `to_dict() -> dict`.
  - `replay.replay_show(ws: ShowWorkspace, *, config, ia, slfm, scratch: Path, delivered: set[str]) -> ShowReplay`: `state` from `catalog.derive_state(ws, delivered)[0]`; wraps `compute_legs` and `classify`; fills `stored_core_flags`, `reproduces`, `stored_brief_guard`, `selected_venue`, `selected_city` per the Contracts (read from the stored `show.json`, `briefing.json` and `provenance.json`; computed even when the show is needs-LLM); a `CacheMiss` → `outcome="unreplayable"`, `unreplayable=str(err)`; an unreadable/non-object `overrides.json` → `unreplayable="overrides.json unreadable"`; any other exception → `unreplayable=f"{type(err).__name__}: {err}"[:200]`. `slfm_miss` = whether `slfm.misses` grew during this show (`False` when `slfm` is `None`).
  - `fixture_library.build_library(root: Path, *, held_for_real: bool = False) -> dict[str, ShowWorkspace]`: a config.toml at `root/config.toml` (`root = "<root>"` plus `[jerrybase]\nenabled = false`, see Task 4's `_config`), a cache dir holding `md_<IDENT>.json` from `gd73_metadata.json`, and two shows, both produced through `run_gather` against the fixture (reuse Task 4's `_library_show` recipe; move that helper here and import it from `test_replay.py`):
    - `gratefuldead-1973-06-10` held, with a `vetting.json` and a reusable `briefing.json`. Default (`held_for_real=False`): a synthetic hold (`unresolved track titles` appended), which the replay clears: the shape of a hold a Tier 1 rule removes, used by the `run` and `reapply` tests. `held_for_real=True`: `asserted_dates=["1973-06-10", "1974-01-01"]` and `held_flags=("research asserts wrong date: 1974-01-01",)`, so the replay raises the same flag, the show is `still-held` and the base arm reproduces it: used by the `compare` tests.
    - `gratefuldead-1973-06-11` clean and packaged (a `package/manifest.json`), built with `date="1973-06-11"` so its vetting asserts its own date.
  - `scripts/replay_holds.py`:
    - `main(argv: list[str] | None = None) -> int`; subcommands `run` and `compare` (Task 6).
    - `run --out <arm.json> [--held | --all] [--slugs FILE] [--config PATH] [--scratch DIR]`: default scope `--held`; `--slugs` is one slug per line. `--config` defaults to `<root>/config.toml` as `llama` does (`LLAMA_ROOT` env else `~/.llama`), `--scratch` defaults to a `tempfile.mkdtemp(prefix="replay-")` that is removed at exit.
    - Identity check, first thing in `run` (before the config is read; `llama.__file__` is read at call time, so a test can patch it): prints `llama: <llama.__file__>` and exits 2 with `refusing to run: llama imports from <path>, not from this tree <repo root>` unless `Path(llama.__file__).resolve()` is under `Path(__file__).resolve().parents[1]`.
    - Logging disabled to CRITICAL for the replay (`logging.disable`), a progress line per 100 shows on stderr, a final one-line summary of outcome counts on stderr.
    - `slfm = setlistfm_client(config)` (Task 2; never constructed here); `replay_holds.py` imports `replay_show` and `setlistfm_client` by name from `llama.replay` (`from llama.replay import replay_show, setlistfm_client, ...`), so a test can patch `rh.replay_show`. The arm records `setlistfm_configured` and `root` (`str(config.root)`).
    - Writes exactly one file: the arm JSON.

- [ ] **Step 1: Write the failing tests**

`scripts/test_replay_holds.py`:

```python
"""scripts/replay_holds.py run: offline replay of a fixture library, zero writes
outside the scratch directory, identity check (spec slice 0 acceptance 3)."""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "llama" / "tests"))

import replay_holds as rh
from fixture_library import build_library


def _tree_state(root: Path) -> dict[str, tuple[int, int]]:
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def _read_only(path: Path):
    for p in [path, *path.rglob("*")]:
        p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _writable(path: Path):
    for p in [path, *path.rglob("*")]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)


def test_run_replays_the_library_under_a_read_only_root(tmp_path):
    root = tmp_path / "lib"
    build_library(root)
    before = _tree_state(root)
    _read_only(root)
    try:
        out = tmp_path / "arm.json"
        rc = rh.main(["run", "--out", str(out), "--all", "--config", str(root / "config.toml"),
                      "--scratch", str(tmp_path / "scratch")])
    finally:
        _writable(root)
    assert rc == 0
    assert _tree_state(root) == before
    arm = json.loads(out.read_text())
    assert set(arm) >= {"sha", "config_fingerprint", "setlistfm_configured", "scope", "shows", "llama_file"}
    held = arm["shows"]["gratefuldead-1973-06-10"]
    clean = arm["shows"]["gratefuldead-1973-06-11"]
    assert held["state"] == "held" and held["outcome"] == "clears" and held["reproduces"] is False
    assert clean["state"] == "packaged" and clean["outcome"] == "clean" and clean["reproduces"] is True
    assert set(held["digests"]) == {"show.json", "overrides.json", "provenance.json", "research.md", "vetting.extraction"}


def test_run_default_scope_is_held_only(tmp_path):
    root = tmp_path / "lib"
    build_library(root)
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--config", str(root / "config.toml")]) == 0
    assert list(json.loads(out.read_text())["shows"]) == ["gratefuldead-1973-06-10"]


def test_run_slugs_file_scopes_the_replay(tmp_path):
    root = tmp_path / "lib"
    build_library(root)
    (tmp_path / "slugs").write_text("gratefuldead-1973-06-11\n")
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--slugs", str(tmp_path / "slugs"),
                    "--config", str(root / "config.toml")]) == 0
    assert list(json.loads(out.read_text())["shows"]) == ["gratefuldead-1973-06-11"]


def test_cache_miss_marks_the_show_unreplayable_and_the_run_continues(tmp_path):
    root = tmp_path / "lib"
    shows = build_library(root)
    for p in (root / "cache").glob("md_*.json"):
        p.unlink()
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--all", "--config", str(root / "config.toml")]) == 0
    arm = json.loads(out.read_text())
    assert all(s["outcome"] == "unreplayable" and s["unreplayable"].startswith("cache miss")
               for s in arm["shows"].values())


def test_unreadable_overrides_marks_the_show_unreplayable_and_continues(tmp_path):
    # Review Focus 2.
    root = tmp_path / "lib"
    shows = build_library(root)
    shows["gratefuldead-1973-06-10"].overrides.write_text("[1, 2")
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--all", "--config", str(root / "config.toml")]) == 0
    arm = json.loads(out.read_text())
    assert arm["shows"]["gratefuldead-1973-06-10"]["unreplayable"] == "overrides.json unreadable"
    assert arm["shows"]["gratefuldead-1973-06-11"]["outcome"] == "clean"


def test_run_refuses_when_llama_imports_from_another_tree(tmp_path, monkeypatch, capsys):
    import llama
    monkeypatch.setattr(llama, "__file__", str(tmp_path / "elsewhere" / "llama" / "__init__.py"))
    rc = rh.main(["run", "--out", str(tmp_path / "arm.json"), "--config", str(tmp_path / "nope.toml")])
    assert rc == 2
    assert "refusing to run: llama imports from" in capsys.readouterr().err


def test_run_passes_no_setlistfm_client_when_no_key_is_configured(tmp_path, monkeypatch):
    # prediction/apply parity: the harness half (Task 19 pins the reapply half)
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    root = tmp_path / "lib"
    build_library(root)
    seen = []
    real = rh.replay_show
    def spy(ws, **kw):
        seen.append(kw["slfm"])
        return real(ws, **kw)
    monkeypatch.setattr(rh, "replay_show", spy)
    assert rh.main(["run", "--out", str(tmp_path / "arm.json"), "--all",
                    "--config", str(root / "config.toml")]) == 0
    assert seen and all(s is None for s in seen)
```

Append to `packages/llama/tests/test_replay.py`:

```python
from llama.replay import replay_show


def test_stored_briefing_flags_are_not_core_flags_and_are_reported_apart(tmp_path):
    # P2: a show held by the briefing guard reproduces on gather+vet; its briefing
    # flag is compared on its own line through stored_brief_guard.
    ws, show = _library_show(tmp_path, held=True,
                             held_flags=("briefing mentions unknown song: Nope",))
    write_artifact(ws.briefing_json, Briefing(context="c", significance="s",
                                              per_set={"1": ["a"], "2": ["b"], "encore": ["c"]},
                                              mentioned_songs=["Nope"]))
    r = replay_show(ws, config=_config(tmp_path), ia=CacheOnlyIA(tmp_path / "cache"), slfm=None,
                    scratch=tmp_path / "scratch" / ws.dir.name, delivered=set())
    assert r.stored_core_flags == [] and r.reproduces is True
    assert r.stored_brief_guard == ["briefing mentions unknown song: Nope"]
    assert (r.selected_venue, r.selected_city) == (None, None)   # the fixture's recording names neither
```

- [ ] **Step 2: Run** `./.venv/bin/python -m pytest scripts/test_replay_holds.py packages/llama/tests/test_replay.py -q` — Expected: `ModuleNotFoundError: No module named 'replay_holds'`; `ImportError: cannot import name 'replay_show'`.

- [ ] **Step 3: Implement** per Interfaces. The arm's `shows` are written in sorted slug order; `scope` is `"held"`, `"all"` or `"slugs"`. The scratch directory per show is `scratch / slug`, removed after each show.

- [ ] **Step 4: Full suite green** (`scripts` is in `testpaths`).

- [ ] **Step 5: Commit** — `git commit -m "feat(scripts): replay_holds run, the offline hold replay"`

---

### Task 6: `scripts/replay_holds.py compare`

Spec: "Two subcommands" (`compare`), "Aggregates", acceptance 2, "Slice 6 — Predicted lists are tied to what produced them", each slice's "Closest calls".

**Files:**
- Modify: `scripts/replay_holds.py`
- Modify: `scripts/test_replay_holds.py` (append)

**Interfaces:**
- Produces `compare <base.json> <cand.json> --out DIR` writing the files in the Contracts. Rules:
  - Exit 2 (`arms differ: ...`) when the two arms' `setlistfm_configured` or `config_fingerprint` differ, or when any slug present in both has different `digests`, or when a slug is in one arm only (reported by name); nothing is written.
  - Exit 3 (`baseline reproduces N/M held shows that are not needs-LLM (< 99%)`) when, over the base arm's `state == "held"` shows whose base `outcome != "needs-llm"`, `reproduces` is true on fewer than 99 % (an empty denominator passes); `drift.txt` IS written in that case so the operator can read it. Unreplayable shows stay in the denominator (they do not reproduce).
  - `drift.txt`: base shows (held and non-held) with `reproduces == false` and base `outcome != "needs-llm"`: slug, state, `stored_core_flags`, `gather_flags + vet_flags`.
  - `briefings.txt`: (1) the line `briefing guard reproduces N/M` over base shows carrying a stored `briefing`-family flag (sorted stored briefing flags == sorted base `stored_brief_guard`), with each non-reproducing slug; (2) `clean briefings firing: base K, cand L` over non-held shows with a non-empty `stored_brief_guard`, listing the cand ones; (3) every show whose `stored_brief_guard` differs between the arms (slug, state, base → cand). Reported, not gated.
  - `flags.txt`: per family, `removed` = count of held shows carrying the family in base but not in cand, `added` = the reverse, over `gather_flags + vet_flags + brief_flags`.
  - `outcomes.txt`: counts per outcome in cand, held and non-held separately; `newly cleared` = cand outcome in `{clears, needs-brief}` where base outcome was not.
  - `packaged_exposure.txt` (diffs the two arms, never cand vs stored): (1) every non-held show (state `packaged` or `delivered`) whose shipped-diff fields (`title_changes`, `venue`, `city`, `set_changes`, `segue_changes`, `set_breaks`, `alignment`) differ between base and cand: slug, state, and each field as base → cand; (2) every non-held show whose cand outcome is `newly-held` and whose base outcome was not, with the flags cand added.
  - `title_sources.txt`: for every would-clear show (`clears`, `needs-brief`, `structure-changed`), each `title_changes` row.
  - `structure_changed.txt`: slug, `would_be`, `set_changes`, `segue_changes`, `set_breaks`, `alignment`, and the stored description's first 300 characters (read from the cache file `md_<identifier>.json`'s `metadata.description` when present).
  - `hand_check_sample.txt`: the newly cleared shows sorted by `sha1(slug)`, first 20 (all when ≤ 20): slug, flags removed, notes.
  - `closest_calls.txt`, sections built from the cand notes by prefix (Contracts strings):
    - `slice 1 (1c)`: shows with a `venue differs from jerrybase:` note, ranked by token overlap `|tokens(X) ∩ tokens(Y)| / |tokens(X) ∪ tokens(Y)|` ascending (tokens via `structure._place_tokens`), bottom 10.
    - `slice 2a`: `accepted short tag title:` notes whose `corroborated by` list has one source, and those whose title core is numeric-only (`re.fullmatch(r"'?\d+", title)`).
    - `slice 4a`: `unknown-song flags suppressed by the right-show gate:` notes parsed into ratio, asserted, resolved, unclaimed count; ranked by ratio ascending, then by asserted ascending.
    - `slice 4b`: shows that lost a `research-date` flag, with the stored `vetting.json` `asserted_dates`.
    - `slice 5a`: shows that lost `setlist evidence shows multiple sets but alignment found none`, with minutes (sum of durations) and the description excerpt.
    - `slice 5c`: shows whose `alignment` changed or whose `set_breaks` changed, old → new (Task 18 adds two subsections).
  - `needs_llm.txt`: slug, state and `needs_llm` list for both arms (`base` and `cand` sections), with each base row's `reproduces`.
  - `notes.txt`: every cand note, grouped by its Contracts note id (`swap`, `1c`, `2a`, `2b`, `2c`, `5c.1`, `5c.2` (dropped at Checkpoint F), `4a`, matched on each string's fixed leading words), plus `format sibling tagged` and `other`, then by slug.
  - `predicted_list.json`, `structure_changed_list.json`, `pilot_list.json` per the Contracts (`sha`/`config_fingerprint` from the cand arm; rows carry the cand arm's `digests` and `briefing`).
  - `summary.txt`: the counts of every file above plus `base reproduces N/M (held, not needs-LLM)`, `needs-LLM held: base X, cand Y` and the `briefing guard reproduces` line, written last.

- [ ] **Step 1: Write the failing tests**

Append to `scripts/test_replay_holds.py`:

```python
def _two_arms(tmp_path, mutate_cand=None, mutate_base=None, held_for_real=True):
    """Both arms from one library and one code tree. By default the held show
    holds for real (`build_library(held_for_real=True)`), so the base arm
    reproduces it and any "newly cleared" comes only from a cand mutation."""
    root = tmp_path / "lib"
    build_library(root, held_for_real=held_for_real)
    base, cand = tmp_path / "base.json", tmp_path / "cand.json"
    cfg = str(root / "config.toml")
    assert rh.main(["run", "--out", str(base), "--all", "--config", cfg]) == 0
    assert rh.main(["run", "--out", str(cand), "--all", "--config", cfg]) == 0
    for path, mutate in ((base, mutate_base), (cand, mutate_cand)):
        if mutate:
            arm = json.loads(path.read_text())
            mutate(arm)
            path.write_text(json.dumps(arm))
    return base, cand


def _clear_it(arm):
    s = arm["shows"]["gratefuldead-1973-06-10"]
    s["gather_flags"], s["vet_flags"], s["outcome"], s["briefing"] = [], [], "clears", "reuse"
    s["notes"] = ["venue differs from jerrybase: archive 'Hall A' vs 'Hall B' (same city)"]


def test_compare_writes_the_report_set_and_the_lists(tmp_path):
    base, cand = _two_arms(tmp_path, _clear_it)
    b = json.loads(base.read_text())["shows"]["gratefuldead-1973-06-10"]
    assert b["outcome"] == "still-held" and b["reproduces"] is True     # a real hold, reproduced
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    for name in ("summary.txt", "drift.txt", "flags.txt", "outcomes.txt", "packaged_exposure.txt",
                 "title_sources.txt", "structure_changed.txt", "hand_check_sample.txt",
                 "closest_calls.txt", "needs_llm.txt", "notes.txt", "briefings.txt",
                 "predicted_list.json", "structure_changed_list.json", "pilot_list.json"):
        assert (out / name).exists(), name
    predicted = json.loads((out / "predicted_list.json").read_text())
    assert [r["slug"] for r in predicted["rows"]] == ["gratefuldead-1973-06-10"]
    assert predicted["sha"] == json.loads(cand.read_text())["sha"]
    assert set(predicted["rows"][0]["digests"]) == {"show.json", "overrides.json", "provenance.json",
                                                     "research.md", "vetting.extraction"}
    assert "research-date: removed 1, added 0" in (out / "flags.txt").read_text()
    assert "gratefuldead-1973-06-10" in (out / "hand_check_sample.txt").read_text()
    assert "slice 1 (1c)" in (out / "closest_calls.txt").read_text()
    assert "Hall A" in (out / "closest_calls.txt").read_text()
    assert "Hall A" in (out / "notes.txt").read_text()
    assert [r["slug"] for r in json.loads((out / "pilot_list.json").read_text())["rows"]] == \
        ["gratefuldead-1973-06-10"]


def test_compare_refuses_arms_whose_digests_differ(tmp_path, capsys):
    def touch(arm):
        arm["shows"]["gratefuldead-1973-06-11"]["digests"]["show.json"] = "deadbeef"
    base, cand = _two_arms(tmp_path, touch)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 2
    assert "arms differ" in capsys.readouterr().err
    assert not out.exists()


def test_compare_refuses_arms_whose_config_differs(tmp_path, capsys):
    def other_config(arm):
        arm["config_fingerprint"] = "0" * 64
    base, cand = _two_arms(tmp_path, other_config)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 2
    assert "arms differ" in capsys.readouterr().err
    assert not out.exists()


def test_compare_refuses_a_baseline_that_does_not_reproduce(tmp_path, capsys):
    # the default library's hold is synthetic: the replay does not raise it
    base, cand = _two_arms(tmp_path, held_for_real=False)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 3
    assert "< 99%" in capsys.readouterr().err
    assert (out / "drift.txt").exists()
    assert "gratefuldead-1973-06-10" in (out / "drift.txt").read_text()


def test_compare_gate_counts_only_held_shows_that_are_not_needs_llm(tmp_path):
    def needs_llm_hold(arm):
        s = arm["shows"]["gratefuldead-1973-06-11"]
        s["state"], s["outcome"], s["reproduces"] = "held", "needs-llm", False
        s["needs_llm"] = ["stored alignment llm"]
    base, cand = _two_arms(tmp_path, needs_llm_hold, needs_llm_hold)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0   # 1/1, not 1/2
    assert "gratefuldead-1973-06-11" not in (out / "drift.txt").read_text()
    assert "gratefuldead-1973-06-11" in (out / "needs_llm.txt").read_text()


def test_packaged_exposure_lists_a_clean_show_whose_fields_would_change(tmp_path):
    def change(arm):
        s = arm["shows"]["gratefuldead-1973-06-11"]
        s["outcome"], s["venue"] = "clean-changed", {"old": "RFK Stadium", "new": "Robert F. Kennedy Stadium"}
    base, cand = _two_arms(tmp_path, change)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "packaged_exposure.txt").read_text()
    assert "gratefuldead-1973-06-11" in text and "Robert F. Kennedy Stadium" in text


def test_packaged_exposure_is_base_versus_cand_and_lists_newly_held_shows(tmp_path):
    same = {"old": "RFK Stadium", "new": "Robert F. Kennedy Stadium"}
    def both(arm):
        arm["shows"]["gratefuldead-1973-06-11"]["venue"] = same
    def cand_holds(arm):
        both(arm)
        s = arm["shows"]["gratefuldead-1973-06-11"]
        s["outcome"], s["gather_flags"] = "newly-held", ["venue mismatch: archive 'A' vs jerrybase 'B'"]
    base, cand = _two_arms(tmp_path, cand_holds, both)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "packaged_exposure.txt").read_text()
    assert "Robert F. Kennedy Stadium" not in text          # the same diff in both arms is not exposure
    assert "gratefuldead-1973-06-11" in text and "venue mismatch: archive 'A' vs jerrybase 'B'" in text
```

- [ ] **Step 2: Run** `./.venv/bin/python -m pytest scripts/test_replay_holds.py -q` — Expected: the new compare tests fail (`compare` unknown / files missing).

- [ ] **Step 3: Implement** per Interfaces. Keep every report writer a small function taking the two arm dicts; `closest_calls.txt` section parsers are regexes over the Contracts' note strings, one per slice, and each section prints `(none)` when empty.

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Commit** — `git commit -m "feat(scripts): replay_holds compare: gates, reports, predicted lists, closest calls"`

---

### Task 7: Narration-candidates page

Spec: "Narration candidates", "Settled by the operator" (a browsable page).

**Files:**
- Modify: `scripts/replay_holds.py` (`compare` writes `narration_candidates.html`)
- Modify: `scripts/test_replay_holds.py` (append)

**Interfaces:**
- Candidates = cand-arm held shows whose remaining flags (`gather_flags + vet_flags + brief_flags`) are non-empty and every one is in `{"single-set structure for a long show ...", "low-confidence setlist"}` by prefix, where a `low-confidence setlist` flag counts only when the stored `structure.source` is `"none"` or the stored `structure.coverage == 0.0` (the "empty canonical" proxy available offline). A candidate is marked `untitled` when every stored track has `title_source == "unresolved"`.
- One table, one row per show: slug, artist, date, venue, minutes (sum of durations / 60, 0 decimals), flags, title sources (counts per `title_source`), `untitled` yes/no, description excerpt (first 300 characters of the cached description, HTML-escaped). Sortable by clicking a header (plain inline JS, no CDN). Nothing else is done with the list.

- [ ] **Step 1: Write the failing test**

```python
def test_narration_candidates_page_lists_unknowable_structure_holds(tmp_path):
    def hold_it(arm):
        s = arm["shows"]["gratefuldead-1973-06-10"]
        s["gather_flags"], s["vet_flags"] = ["single-set structure for a long show (160 min)"], []
        s["outcome"] = "still-held"
    base, cand = _two_arms(tmp_path, hold_it)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    html = (out / "narration_candidates.html").read_text()
    assert "<table" in html and "gratefuldead-1973-06-10" in html and "Grateful Dead" in html
    assert "gratefuldead-1973-06-11" not in html
```

- [ ] **Step 2: Run** — Expected: `FileNotFoundError: narration_candidates.html`.
- [ ] **Step 3: Implement.** The renderer needs `show.json` fields (artist, date, venue, tracks); `compare` reads them from the library root recorded in the arm header (`root`) and degrades to the slug alone when the file is unreadable.
- [ ] **Step 4: Full suite green.**
- [ ] **Step 5: Commit** — `git commit -m "feat(scripts): narration-candidates page from compare"`

---

## Measuring at a checkpoint (used by Checkpoints B–G)

The library is live, so no arm is reused across sittings. At checkpoint `X` (B, C, D, E, F, G), with `PREV` the previous checkpoint's tag (`tier1-base` at B):

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1
B=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1-base   # created at Checkpoint A, stays on tier1-base
P=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1-prev   # created at Checkpoint C (below), moved to $PREV each time
H="$HOME/.llama-harness"; mkdir -p "$H"
cd "$W" && test -z "$(git status --porcelain)" && git tag "tier1-cp-$X"      # the commit measured
for T in "$B" "$W"; do (cd "$T" && ./.venv/bin/python -c "import llama; print(llama.__file__)"); done   # each under its own tree
(cd "$B" && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-base-held.json" \
         && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-base-all.json" --all)
(cd "$W" && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-cand-held.json" \
         && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-cand-all.json" --all)
cd "$W"
./.venv/bin/python scripts/replay_holds.py compare "$H/$X-base-held.json" "$H/$X-cand-held.json" --out "$H/cmp-$X-held"
./.venv/bin/python scripts/replay_holds.py compare "$H/$X-base-all.json"  "$H/$X-cand-all.json"  --out "$H/cmp-$X-all"
```

From Checkpoint C on, also measure this slice's own delta against the previous checkpoint's commit, in the same sitting (the first time: `git -C "$W" worktree add "$P" "$PREV"` and give it its own venv as in Execution setup; later: `git -C "$P" checkout --detach "$PREV"`, which needs no reinstall because the install is editable):

```bash
(cd "$P" && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-prev-held.json" \
         && ./.venv/bin/python scripts/replay_holds.py run --out "$H/$X-prev-all.json" --all)
./.venv/bin/python scripts/replay_holds.py compare "$H/$X-prev-held.json" "$H/$X-cand-held.json" --no-repro-gate --out "$H/cmp-$X-slice-held"
./.venv/bin/python scripts/replay_holds.py compare "$H/$X-prev-all.json"  "$H/$X-cand-all.json"  --no-repro-gate --out "$H/cmp-$X-slice-all"
```

(`--no-repro-gate`: the -prev arm carries earlier slices and does not reproduce stored states by design; added at Checkpoint C, operator decision 2026-10-19.)

`cmp-$X-*` is the cumulative change since `tier1-base`; `cmp-$X-slice-*` is this slice alone. Exit 2 from any compare means the library moved between runs in one sitting: re-run all arms. The pre-screen (see "Operator time" above) then reads `cmp-$X-all`, `cmp-$X-held` and the slice comparisons, and the hand-check lists below are drawn from them.

## Checkpoint A (operator): the base arm and the reproduction gate

Spec acceptance for slice 0, items 1–2. The orchestrator runs these and reports; nothing is written under `~/.llama`.

```bash
W=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1
B=/Users/shawn/projects/llama/.claude/worktrees/held-backlog-tier1-base
H="$HOME/.llama-harness"; mkdir -p "$H"
cd "$W" && test -z "$(git status --porcelain)" && git tag tier1-base   # the slice-0 commit: main's gather/vet/brief, plus the harness
git -C "$W" worktree add "$B" tier1-base
cd "$B" && python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"
./.venv/bin/python -c "import llama; print(llama.__file__)"          # expect: under $B
time ./.venv/bin/python scripts/replay_holds.py run --out "$H/A-base-held.json"          # ~15 s expected
time ./.venv/bin/python scripts/replay_holds.py run --out "$H/A-base-all.json" --all     # < 1 min expected
./.venv/bin/python scripts/replay_holds.py compare "$H/A-base-held.json" "$H/A-base-held.json" --out "$H/cmp-A-held"; echo "exit $?"
./.venv/bin/python scripts/replay_holds.py compare "$H/A-base-all.json"  "$H/A-base-all.json"  --out "$H/cmp-A-all";  echo "exit $?"
cat "$H/cmp-A-held/summary.txt" "$H/cmp-A-held/drift.txt" "$H/cmp-A-all/drift.txt" "$H/cmp-A-all/briefings.txt"
```

Report to the operator, from `summary.txt`, `drift.txt`, `needs_llm.txt` and `briefings.txt`:

- **needs-LLM held count**, reported apart and never as drift. Expect roughly 490–500 (spec: `align_structure` reached on 487 held shows, 325 of them with a stored LLM structure; `extract_setlist` on 9; review probe: 326 held shows are stored `alignment: llm`, and a replay without an align provider appends `low-confidence structure alignment` to each, `gather.py:1076-1081`).
- **Reproduction gate** over the held shows that are not needs-LLM (roughly 1,073 minus the above): ≥ 99 %, exit 0. Drift there: at most `soulcoughing-1994-11-30` and `trampledbyturtles-2007-07-20` (either may be needs-LLM instead).
- **`base-all` drift** (non-held, not needs-LLM): at most the spec's 9 non-held drifts; the 349 clean LLM-aligned shows are needs-LLM, not drift.
- **Briefing line**: `briefing guard reproduces 55/55`; `clean briefings firing: base 0`.
- The cache-miss count (expect 0) and the runtimes.

**Ask:** do the drift list and the needs-LLM count match these expectations, and is `tier1-base` accepted as the baseline every later checkpoint re-runs? Stop until answered. If exit 3: the harness has a defect; back to Task 4/5 (never widen the denominator or feed stored LLM structures into `compute_legs` to pass it).

---

### Task 8: Cross-source parse vocabulary and `placeholders.py`

Spec: "2a — Corroborated short tags" (the vocabulary and the junk veto), "2b — Junk-title detector" (the classes), ruling 3, "New constants" (2b's vocabulary and residue tokens; 2a's date pattern and residue tokens).

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (`CanonicalBuild`, `build_canonical`)
- Create: `packages/llama/src/llama/placeholders.py`
- Test: `packages/llama/tests/test_placeholders.py` (create), `packages/llama/tests/test_stage_gather.py` (append)

**Interfaces:**
- Produces:
  - `gather.CanonicalBuild.corroboration: dict[str, tuple[str, ...]]` (trailing field, default `{}`): `fuzzy_norm_title(item.title)` → sorted tuple of the sources that list it, over every parse whose `source` is neither `"chosen"` nor `"llm"` (`"setlist.fm"` and `lma:<identifier>` only), minus every `lma:` parse whose description, whitespace-normalised (`" ".join(desc.split())`), equals the selected recording's own (ruling 3: a pasted copy has the same author). `_collect_parses` already returns `descriptions` parallel to `parses`; pair them there, compare each sibling's against the chosen one's, and skip a copy. Empty normalized titles are skipped. Built from the raw parses, before the head-banner strip (an item vocabulary, not the canonical). This one field is both 2a's vocabulary and 2b's exemption.
  - `placeholders.py`, pure, importing only `re` and `llama.structure.fuzzy_norm_title`:
    - `NUMBER_WORDS = ("one", ..., "twenty")`.
    - `is_placeholder(s: str) -> bool`: full match, case-insensitive, after `strip()`, of `(?:track|trac|trk|tr|cut)\s*[-_#.]?\s*(?:\d{1,3}|<number word>)` or `tmp|temp|no\s*title|title`. Never `untitled`, never `song\s*#?\d+`.
    - `is_timestamp(s) -> bool`: `^[\[(]?\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?[\])]?\s*-?$` (a full match: 2b's class).
    - `starts_with_timestamp(s) -> bool`: `re.match(r"[\[(]?\d{1,2}:\d{2}", s.strip())`, a LEADING-timestamp search (2a's veto: `07:22 - IB49` is junk to 2a though it is not a bare timestamp).
    - `is_date_like(s) -> bool`: numeric day, month and year in any order with `-`, `.`, `/` separators (`^\d{1,4}[-./]\d{1,2}[-./]\d{1,4}$`), or a month name (full or 3-letter, optional `.`) with a day and/or a year (`^<month>\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{2,4})?$`, `^\d{1,2}(?:st|nd|rd|th)?\s+<month>\.?(?:,?\s+\d{2,4})?$`, `^<month>\.?\s+\d{4}$`).
    - `looks_like_filename(s) -> bool`: 2a's residue shape: `^(?:[a-z]{2,8}_*\d{2,4}[-.]\d{2}[-.]\d{2,4}\s*)?(?:[sd]\d{1,2})?t\d{1,3}$` or `^\d{6,}_\d+$` or `^[sd]\d{1,2}t\d{1,3}$` (case-insensitive).
    - `RESIDUE_TOKENS` (2b's deletion set; one regex, compiled `re.I`): identifier+date prefix, start-anchored (`^[a-z&]+\s*\d{2,4}[-._]\d{2}[-._]\d{2,4}`, like `_ID_PREFIX`; unanchored it would eat `Begonias 1977-05-08` out of a real title), disc/track tokens (`(?:s|d|cd|disc)?\d{0,2}t\d{2,3}\b`), long digit runs (`\b\d{6,}(?:_\d+)?\b`), extensions (`\.(?:flac|shn|mp3|wav|ogg)\b`), lineage words (`\b(?:sbd|aud|fob|dfc|matrix|mtx|flac\d*|shnf?|remaster\w*|master|soundboard)\b`), `\btrack\s*\d+\b`.
    - `letters_after_residue(s) -> int`: ASCII letters remaining after `RESIDUE_TOKENS.sub(" ", s)`.
    - `is_residue(t: str) -> bool` (2b's filename-residue class alone): `t.strip()` non-empty and `not re.fullmatch(r"\d{4}", t.strip())` and `letters_after_residue(t) < 3`.
    - `is_placeholder_title(title: str) -> bool` (2b's per-title classes): `False` for a blank or whitespace-only title (explicitly: `is_placeholder_title("") is False`); else `is_placeholder` or `is_timestamp` or `is_residue`.
    - `is_junk_tag(core: str) -> bool` (2a's veto): `is_placeholder` or `starts_with_timestamp` or `is_date_like` or `looks_like_filename`. Does NOT count letters.
    - `recording_level_junk(titles: list[str], item_title: str | None) -> bool`: `len(titles) >= 3` and (all `t.strip().lower()` equal and non-empty, or every `fuzzy_norm_title(t)` equals `fuzzy_norm_title(item_title)` with `item_title` non-empty).

> **Ruled (P5 residue over-demotion):** `Jam 12-31-99`, `Master` and `Matrix` ARE demoted by the residue class (the anchored prefix consumes `Jam` + a date; `master`/`matrix` are lineage tokens). This is accepted as a documented limitation, not carved out: demotion only leaves a track `unresolved`, so the show stays held (the safe direction), and Checkpoint B's pre-screen flags every residue-class demotion for the operator. Pin the behaviour with a test that these three ARE demoted, so a later change to the residue rule is a deliberate decision.

- [ ] **Step 1: Write the failing tests**

`packages/llama/tests/test_placeholders.py`:

```python
"""placeholders: the fixed-a-priori junk classes of slices 2a/2b (spec 'Testing': near misses)."""
import pytest

from llama.placeholders import (is_date_like, is_junk_tag, is_placeholder, is_placeholder_title,
                                is_residue, is_timestamp, letters_after_residue, looks_like_filename,
                                recording_level_junk, starts_with_timestamp)


@pytest.mark.parametrize("s", ["Track 01", "track six", "Trac3", "Track ten", "Trk 7", "Tr-02", "Cut 3",
                               "tmp", "temp", "No Title", "Title", "TRACK  12"])
def test_placeholder_vocabulary(s):
    assert is_placeholder(s)


@pytest.mark.parametrize("s", ["Untitled", "Untitled #12", "Song #1", "1979", "Track", "Tracks of My Tears",
                               "Title Fight", "Temptation"])
def test_placeholder_near_misses(s):
    assert not is_placeholder(s)


@pytest.mark.parametrize("s, expected", [("27:36.27", True), ("05:27 -", True), ("[12:30]", True),
                                         ("07:22 - IB49", False), ("3AM", False), ("2001", False)])
def test_timestamp(s, expected):
    assert is_timestamp(s) is expected


@pytest.mark.parametrize("s, expected", [("07:22 - IB49", True), ("05:27", True), ("(1:02) Jam", True),
                                         ("3AM", False), ("2001", False), ("Jam 07:22", False)])
def test_starts_with_timestamp(s, expected):
    assert starts_with_timestamp(s) is expected


@pytest.mark.parametrize("s, expected", [("12-28-99", True), ("1999-12-28", True), ("28.12.1999", True),
                                         ("December 28", True), ("Dec 28, 1999", True), ("28 December", True),
                                         ("May 1977", True), ("7-11", False), ("1 in 7", False),
                                         ("I-55", False), ("1979", False), ("May", False)])
def test_date_like(s, expected):
    assert is_date_like(s) is expected


@pytest.mark.parametrize("s, expected", [("d1t02", True), ("t1", True), ("123456_01", True),
                                         ("gd73-06-10d1t04", True), ("FF", False), ("42", False),
                                         ("J", False), ("7-11", False)])
def test_filename_residue_shape(s, expected):
    assert looks_like_filename(s) is expected


def test_letters_after_residue():
    assert letters_after_residue("buckethead2004-06-04d2t05") == 0
    assert letters_after_residue("fIREHOSE 1992-02-19 t02") == 0
    assert letters_after_residue("Scarlet Begonias 1977-05-08") == 15   # the prefix is start-anchored
    assert letters_after_residue("sbd matrix remaster") == 0
    assert is_residue("buckethead2004-06-04d2t05") and not is_residue("1979") and not is_residue("")


@pytest.mark.parametrize("s, expected", [("Track 01", True), ("tmp", True), ("Trac3", True),
                                         ("27:36.27", True), ("buckethead2004-06-04d2t05", True),
                                         ("1979", False), ("1759", False), ("Song #1", False),
                                         ("Untitled", False), ("Untitled #12", False), ("Jam", False),
                                         ("", False), ("   ", False), ("Scarlet Begonias 1977-05-08", False)])
def test_is_placeholder_title(s, expected):
    assert is_placeholder_title(s) is expected


@pytest.mark.parametrize("s, expected", [("?", False), ("FF", False), ("J", False), ("42", False),
                                         ("7-11", False), ("I-55", False), ("1 in 7", False),
                                         ("Track 01", True), ("05:27", True), ("12-28-99", True),
                                         ("d1t02", True), ("t1", True), ("07:22 - IB49", True)])
def test_is_junk_tag_never_counts_letters(s, expected):
    assert is_junk_tag(s) is expected


def test_recording_level_junk():
    assert recording_level_junk(["tmp"] * 19, None)
    assert recording_level_junk(["Live at X", "live at x", "Live At X"], "Live at X")
    assert not recording_level_junk(["tmp", "tmp"], None)            # under 3 tracks
    assert not recording_level_junk(["Dew", "Dew", "Star"], None)
    assert recording_level_junk(["Dew", "Dew", "Dew"], "Dew")       # identical on three tracks IS the class
```

Append to `packages/llama/tests/test_stage_gather.py`:

```python
# --- slice 2: the cross-source vocabulary (ruling 3) ---

from llama.stages.gather import build_canonical


def test_build_canonical_corroboration_excludes_the_chosen_description():
    base = json.loads(FIXTURE.read_text())
    chosen = dict(base["metadata"], description="Set 1\nOnly In The Chosen\nMorning Dew")
    sib = {"metadata": dict(base["metadata"], description="Set 1\nMorning Dew\nFrom A Sibling"),
           "files": []}
    ia = MultiIA({IDENT: {"metadata": chosen, "files": base["files"]}, "sib": sib})
    cand = make_candidate().model_copy(update={"recordings": [RecordingSummary(identifier=IDENT),
                                                               RecordingSummary(identifier="sib")]})
    kept, _, _ = filter_files(base["files"], want_format=("VBR MP3",))
    cb = build_canonical(ia, cand, IDENT, chosen, kept, "Grateful Dead", [])
    assert cb.corroboration == {fuzzy_norm_title("Morning Dew"): ("lma:sib",),
                                fuzzy_norm_title("From A Sibling"): ("lma:sib",)}
    assert fuzzy_norm_title("Only In The Chosen") not in cb.corroboration


def test_build_canonical_corroboration_names_setlistfm(tmp_path):
    import httpx
    slfm_body = json.loads((FIXTURES / "slfm_gd_1974_02_24.json").read_text())
    client = SetlistFMClient(
        cache_dir=tmp_path / "slfm-cache", api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=slfm_body))),
        backoff_s=0, rate_limit_s=0)
    ia = gd74_ia()
    meta = ia.metadata(W_IDENT)["metadata"]
    kept, _, _ = filter_files(ia.metadata(W_IDENT)["files"], want_format=("VBR MP3",))
    cb = build_canonical(ia, gd74_candidate(), W_IDENT, meta, kept, "Grateful Dead", [], setlistfm=client)
    assert any("setlist.fm" in sources for sources in cb.corroboration.values())
    assert any(sources == (f"lma:{M_IDENT}",) for sources in cb.corroboration.values()) or \
           any(f"lma:{M_IDENT}" in sources for sources in cb.corroboration.values())
    assert not any("chosen" in sources for sources in cb.corroboration.values())


def test_build_canonical_corroboration_drops_a_sibling_that_copies_the_chosen_description():
    # ruling 3: a byte-identical sibling (the bobbyleerodgers-2010-01-13 shape) is the same author
    base = json.loads(FIXTURE.read_text())
    chosen = dict(base["metadata"], description="Set 1\n07:22 - IB49\nMorning Dew")
    copy = {"metadata": dict(base["metadata"], description="Set 1\n07:22 - IB49\nMorning Dew"), "files": []}
    spaced = {"metadata": dict(base["metadata"], description="Set 1\n  07:22 - IB49\n\nMorning  Dew\n"),
              "files": []}
    ia = MultiIA({IDENT: {"metadata": chosen, "files": base["files"]}, "copy": copy, "spaced": spaced})
    cand = make_candidate().model_copy(update={"recordings": [RecordingSummary(identifier=IDENT),
                                                               RecordingSummary(identifier="copy"),
                                                               RecordingSummary(identifier="spaced")]})
    kept, _, _ = filter_files(base["files"], want_format=("VBR MP3",))
    cb = build_canonical(ia, cand, IDENT, chosen, kept, "Grateful Dead", [])
    assert cb.corroboration == {}
```

- [ ] **Step 2: Run** `./.venv/bin/python -m pytest packages/llama/tests/test_placeholders.py packages/llama/tests/test_stage_gather.py -q` — Expected: `ModuleNotFoundError: llama.placeholders`; `AttributeError: 'CanonicalBuild' object has no attribute 'corroboration'`.

- [ ] **Step 3: Implement** per Interfaces. Each regex in `placeholders.py` carries a one-line comment naming its spec class and the near miss that bounds it (`1979`, `Song #1`, `Untitled #12`, `3AM`, `7-11`, `07:22 - IB49`, `Scarlet Begonias 1977-05-08`).

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_placeholders.py` and the corroboration tests. Mutants: (a) `is_junk_tag` uses `is_timestamp` instead of `starts_with_timestamp`; (b) the identifier+date prefix loses its `^`; (c) `is_placeholder` accepts `untitled`; (d) `is_placeholder_title("")` returns True; (e) `corroboration` keeps a sibling whose description copies the chosen one; (f) `corroboration` includes the `chosen` parse. A survivor gets a test.

- [ ] **Step 6: Commit** — `git commit -m "feat(titles): cross-source parse vocabulary and the placeholder predicates"`

---

### Task 9: 2b — placeholder demotion at the tag rung

Spec: "2b. Junk-title detector (must land before slice 4)", Evidence "Junk titles on packaged and delivered shows", "Positional fill of junk tapes".

**Files:**
- Modify: `packages/llama/src/llama/titles.py` (`resolve_titles`; new `tag_layer`, `placeholder_positions`)
- Modify: `packages/llama/src/llama/stages/gather.py` (`compute_gather`: pass the vocabulary, emit notes, recompute `fetch_siblings`, the format-sibling count note)
- Create fixture: `packages/llama/tests/fixtures/furthur2012-07-15.json` via `./.venv/bin/python scripts/capture_fixture.py --from-cache furthur2012-07-15 packages/llama/tests/fixtures/furthur2012-07-15.json`
- Test: `packages/llama/tests/test_titles.py` (append), `packages/llama/tests/test_stage_gather.py` (append)

**Interfaces:**
- Consumes: `placeholders.is_placeholder`, `is_timestamp`, `is_residue`, `recording_level_junk`; `titles.is_real_title` (untouched); `CanonicalBuild.corroboration` (Task 8).
- Produces:
  - `titles.tag_layer(kept_files, format_titles, gate_basis) -> tuple[list[str], str]`: the titles and source (`"sibling-format"` when `format_titles is not None`, else `"tags"`) exactly as `resolve_titles` computes them today; `resolve_titles` calls it.
  - `titles.placeholder_positions(tag_titles: list[str], *, corroboration: frozenset[str], item_title: str | None) -> list[int]`: 0-based positions `i` where `t = tag_titles[i]` is not blank (`t.strip()`: a blank tag is never demoted and takes today's path, including the whole-tape `setlist` rung), `fuzzy_norm_title(t) not in corroboration`, and any of:
    - `is_placeholder(t) or is_timestamp(t)`, whether or not `is_real_title(t)` (so `Tr-02` and `27:36.27` never reach the positional `setlist` rung);
    - `recording_level_junk(tag_titles, item_title)` (the spec's recording-level class, as specified);
    - `is_real_title(t) and is_residue(t)` (the letters class judges only titles the tags rung would otherwise adopt).
  - `resolve_titles(kept_files, setlist, format_titles=None, gate_basis=None, *, corroboration: frozenset[str] = frozenset(), item_title: str | None = None)`: a demoted position gets `title=f["name"]`, `title_source="unresolved"` directly, never the `setlist` rung.
  - `compute_gather`: passes `corroboration=frozenset(cb.corroboration)` and `item_title=meta.get("title")`; computes `demoted = placeholder_positions(tag_titles, ...)` from `tag_layer(kept, format_titles, tag_gate_basis)` for the notes (Contracts 2b string, `raw` = the tag-layer title; a note only for a demoted position); `fetch_siblings = bool(kept and (title_fraction(clean_tag_titles(kept)) < 1.0 or demoted))`; when `demoted` is non-empty, for the first lossless format in `LOSSLESS_TITLE_FORMATS` other than `ordering["format"]` whose `sibling_format_titles(recovery_basis, other)` is non-None with `title_fraction >= _RECOVER_SIBLING_ABOVE`, add the note `f"format sibling tagged: {fmt} title fraction {frac:.2f} (recovery not triggered; filed, not acted on)"`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_titles.py`:

```python
# --- slice 2b: placeholder tags demote to unresolved at the tag rung ---

from llama.structure import fuzzy_norm_title
from llama.titles import placeholder_positions, tag_layer


def _files(titles):
    return [{"name": f"t{i:02d}.mp3", "title": t, "length": "300"} for i, t in enumerate(titles, 1)]


def test_tag_layer_matches_resolve_titles_layer():
    files = _files(["Dew", "Star", "Rider"])
    assert tag_layer(files, None, None) == (["Dew", "Star", "Rider"], "tags")
    assert tag_layer(files, {"t01.mp3": "A"}, None) == (["A", "", ""], "sibling-format")


def test_placeholder_positions_classes():
    assert placeholder_positions(["Track 01", "Dew", "tmp", "27:36.27", "fIREHOSE 1992-02-19 t02"],
                                 corroboration=frozenset(), item_title=None) == [0, 2, 3, 4]
    # placeholders and timestamps are judged whether or not is_real_title passes; a blank never is
    assert placeholder_positions(["", "Dew", "Tr-02", "05:27"],
                                 corroboration=frozenset(), item_title=None) == [2, 3]
    assert placeholder_positions(["tmp"] * 19, corroboration=frozenset(), item_title=None) == list(range(19))
    assert placeholder_positions(["Live at X"] * 4, corroboration=frozenset(), item_title="Live at X") == [0, 1, 2, 3]


def test_placeholder_positions_exemptions():
    assert placeholder_positions(["1979", "1759", "Song #1", "Untitled", "Untitled #12",
                                  "Scarlet Begonias 1977-05-08"],
                                 corroboration=frozenset(), item_title=None) == []
    # a sibling description (or setlist.fm) naming "Track 01" exempts it; the chosen description never
    # reaches this function (Task 8 builds `corroboration` without it)
    assert placeholder_positions(["Track 01", "Track 02"] + ["x"] * 2,
                                 corroboration=frozenset({fuzzy_norm_title("Track 01")}),
                                 item_title=None) == [1]


def test_resolve_titles_demotes_a_placeholder_and_never_lets_it_fall_to_the_setlist_rung():
    files = _files(["tmp", "tmp", "tmp"])
    setlist = ParsedSetlist(items=[SetlistItem(title=t, normalized=t.lower(), set="1")
                                   for t in ("Dew", "Star", "Rider")], confidence="high")
    tracks = resolve_titles(files, setlist)
    assert [(t.title, t.title_source) for t in tracks] == [
        ("t01.mp3", "unresolved"), ("t02.mp3", "unresolved"), ("t03.mp3", "unresolved")]
    # a non-placeholder blank tag still takes the whole-tape setlist rung, as today
    tracks = resolve_titles(_files(["", "", ""]), setlist)
    assert [t.title_source for t in tracks] == ["setlist"] * 3


def test_resolve_titles_never_demotes_a_corroborated_tag():
    files = _files(["Song #1", "Song #2", "Song #3"])
    tracks = resolve_titles(files, ParsedSetlist(), corroboration=frozenset({fuzzy_norm_title("Song #1")}))
    assert tracks[0].title_source == "tags"
```

(Import `ParsedSetlist`, `SetlistItem` as the file already does.)

Append to `packages/llama/tests/test_stage_gather.py`:

```python
# --- slice 2b on a captured tape: furthur2012-07-15, every tag "tmp" ---

FURTHUR = FIXTURES / "furthur2012-07-15.json"
F_IDENT = "furthur2012-07-15"


def _furthur_candidate():
    return Candidate(performance_id="Furthur/2012-07-15", collection="Furthur", date="2012-07-15",
                     venue="Bethel Woods Center for the Arts", city="Bethel, NY",
                     recordings=[RecordingSummary(identifier=F_IDENT)])


def test_2b_demotes_a_whole_tmp_tape_and_notes_each_track(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(json.loads(FURTHUR.read_text())), None, _furthur_candidate(),
                         F_IDENT, jerrybase_enabled=False)
    assert all(t.title_source == "unresolved" for t in res.show.tracks)
    assert all(t.title == t.filename for t in res.show.tracks)
    assert "unresolved track titles" in res.show.review_flags
    demotions = [n for n in res.notes if n.startswith("placeholder tag title: ")]
    assert len(demotions) == len(res.show.tracks)
    assert demotions[0] == f"placeholder tag title: track 1 '{'tmp'}' demoted to unresolved"


def test_2b_does_not_touch_a_real_tagged_tape(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    res = compute_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert not any(n.startswith("placeholder tag title") for n in res.notes)
    assert [t.title for t in res.show.tracks][:2] == ["Morning Dew", "China Cat Sunflower"]
```

- [ ] **Step 2: Run** the two test files — Expected: `ImportError: cannot import name 'tag_layer'`.

- [ ] **Step 3: Implement** per Interfaces. `tag_layer` is a straight extraction; `resolve_titles`'s loop gains one branch ahead of `is_real_title`'s `tags` branch. Keep `is_real_title` and `title_fraction` untouched.

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_titles.py` and the 2b gather tests. Mutants: (a) drop the corroboration exemption; (b) demote a blank tag; (c) gate the placeholder/timestamp class on `is_real_title` again; (d) drop `is_real_title` from the residue class; (e) a demoted position falls through to the `setlist` rung. A survivor gets a test.

- [ ] **Step 6: Commit** — `git commit -m "feat(titles): 2b placeholder tags demote to unresolved at the tag rung"`

---

### Task 10: 2a — corroborated short tags

Spec: "2a. Corroborated short tags", Evidence "Short real tags (2a)", ruling 3.

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (new `accept_short_tags`, called in `compute_gather` after `adopt_gap_titles` and before the structure branch)
- Modify: `packages/llama/src/llama/titles.py` (`strip_taper_markers`, `tag_core`)
- Create fixture: `packages/llama/tests/fixtures/tnd2006-12-13.json` via `--from-cache tnd2006-12-13.flac16`
- Test: `packages/llama/tests/test_titles.py` (append), `packages/llama/tests/test_stage_gather.py` (append)

**Interfaces:**
- Consumes: `placeholders.is_junk_tag`, `CanonicalBuild.corroboration`, `metadata_norms`, `tag_layer`.
- Produces:
  - `titles.tag_core(tag: str) -> str`: the tag minus trailing taper markers for matching: `re.sub(r"(?:\s*(?:=>|->|[>\-*%#@^~$+]))+\s*$", "", tag).strip()`.
  - `titles.strip_taper_markers(tag: str) -> str`: the shipped title: `re.sub(r"(?:\s*(?:=>|->|>|\*|\$|\+))+\s*$", "", tag)`, then `re.sub(r"\s+#+\s*$", "", ...)`, `.strip()`. `#` is removed only when free-standing (`F#` keeps it); `%`, `@`, `^`, `~` are never removed (`100%` keeps it).
  - `gather.accept_short_tags(tracks: list[Track], tag_titles: list[str], tag_source: str, *, corroboration: dict[str, tuple[str, ...]], metadata_norms: set[str]) -> tuple[list[Track], list[str]]`: for each track with `title_source == "unresolved"` whose `tag_titles[i]` is non-empty and fails `is_real_title`: `core = tag_core(tag)`; accept when `any(ch.isalnum() for ch in core)`, `not is_junk_tag(core)` (Task 8: its timestamp arm is the leading-timestamp search, so `07:22 - IB49` is vetoed), every component of `re.split(r"\s*(?:->|>)\s*", core)` (non-empty) has `fuzzy_norm_title(c) in corroboration`, and `fuzzy_norm_title(core) not in metadata_norms`. Accepted: `title=strip_taper_markers(tag)`, `title_source=tag_source`, `matched` untouched (None), note per the Contracts with `sources` = sorted union of the components' sources. Returns a new list.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_titles.py`:

```python
# --- slice 2a: cores and shipped titles ---

from llama.titles import strip_taper_markers, tag_core


@pytest.mark.parametrize("tag, core, shipped", [
    ("FF>", "FF", "FF"), ("ML**", "ML", "ML"), ("7-11**", "7-11", "7-11"), ("FF =>", "FF", "FF"),
    ("F#", "F", "F#"), ("100%", "100", "100%"), ("Dew #", "Dew", "Dew"), ("J >", "J", "J"),
    ("? >", "?", "?"), ("R&E ->", "R&E", "R&E"), ("Ravine > J", "Ravine > J", "Ravine > J"),
])
def test_tag_core_and_shipped_title(tag, core, shipped):
    assert tag_core(tag) == core
    assert strip_taper_markers(tag) == shipped
```

Append to `packages/llama/tests/test_stage_gather.py`:

```python
# --- slice 2a on a captured tape: tnd2006-12-13, "J >" tags ---

from llama.stages.gather import accept_short_tags

TND = FIXTURES / "tnd2006-12-13.json"
T_IDENT = "tnd2006-12-13.flac16"
T_SIB = "tnd2006-12-13.sib"
# Both descriptions list "J", but neither has 19 items (the tape's count), so the
# whole-tape `setlist` rung cannot fire and the "J >" tracks reach 2a unresolved.
CHOSEN_DESC = "Set 1\nJ >\nJ (Da Funk) >\nRavine > J\nG-nome > J >\nJ > G-nome\nSet 2\nGlide >\nHome\nJ > Moment #2 >\nVL Tone > J > VL Tone"
SIB_DESC = "set one: J > , J (Da Funk) > , Ravine > J\nset two: Glide > , Home, J > Moment #2"


def _tnd(with_sibling: bool):
    md = json.loads(TND.read_text())
    md["metadata"]["description"] = CHOSEN_DESC
    recs = [RecordingSummary(identifier=T_IDENT)]
    mapping = {T_IDENT: md}
    if with_sibling:
        recs.append(RecordingSummary(identifier=T_SIB))
        mapping[T_SIB] = {"metadata": dict(md["metadata"], description=SIB_DESC), "files": []}
    cand = Candidate(performance_id="TheNewDeal/2006-12-13", collection="TheNewDeal", date="2006-12-13",
                     venue="Water Street Music Hall", city="Rochester, NY", recordings=recs)
    return MultiIA(mapping), cand


def _files_tagged(ia, tag):
    return {f["name"] for f in ia.mapping[T_IDENT]["files"] if (f.get("title") or "").strip() == tag}


def test_2a_accepts_j_when_a_sibling_description_corroborates_it(tmp_path):
    ia, cand = _tnd(with_sibling=True)
    res = compute_gather(ShowWorkspace(tmp_path / "s"), ia, None, cand, T_IDENT, jerrybase_enabled=False)
    j_tracks = [t for t in res.show.tracks if t.filename in _files_tagged(ia, "J >")]
    assert len(j_tracks) >= 5 and all((t.title, t.title_source) == ("J", "tags") for t in j_tracks)
    assert f"accepted short tag title: track {j_tracks[0].index} 'J' corroborated by lma:{T_SIB}" in res.notes
    q_tracks = [t for t in res.show.tracks if t.filename in _files_tagged(ia, "? >")]
    assert q_tracks and all(t.title_source == "unresolved" for t in q_tracks)   # "?" never qualifies


def test_2a_does_not_count_the_chosen_recordings_own_description(tmp_path):
    ia, cand = _tnd(with_sibling=False)
    res = compute_gather(ShowWorkspace(tmp_path / "s"), ia, None, cand, T_IDENT, jerrybase_enabled=False)
    assert not any(n.startswith("accepted short tag title") for n in res.notes)
    assert all(t.title_source == "unresolved" for t in res.show.tracks if t.filename in _files_tagged(ia, "J >"))
    assert "unresolved track titles" in res.show.review_flags


def test_accept_short_tags_rules():
    tracks = [Track(index=i, set="1", title=f"t{i}.mp3", filename=f"t{i}.mp3", title_source="unresolved")
              for i in range(1, 8)]
    tracks[5] = tracks[5].model_copy(update={"title": "Ramone & Emiglio", "title_source": "setlist-gap"})
    tracks.append(Track(index=8, set="1", title="t8.mp3", filename="t8.mp3", title_source="unresolved"))
    # row 5 is the metadata-norms veto: "NY" fails is_real_title, so it reaches 2a and is vetoed there;
    # row 8 is the spec's named timestamp trap, corroborated (as by a copied description) and still vetoed
    tags = ["FF>", "? >", "05:27 -", "12-28-99", "NY", "R&E", "42", "07:22 - IB49"]
    corroboration = {fuzzy_norm_title("FF"): ("setlist.fm",), fuzzy_norm_title("?"): ("lma:x",),
                     fuzzy_norm_title("05:27"): ("lma:x",), fuzzy_norm_title("12-28-99"): ("lma:x",),
                     fuzzy_norm_title("NY"): ("lma:x",), fuzzy_norm_title("R&E"): ("lma:x",),
                     fuzzy_norm_title("42"): ("lma:x", "setlist.fm"),
                     fuzzy_norm_title("07:22 - IB49"): ("lma:x",)}
    out, notes = accept_short_tags(tracks, tags, "tags", corroboration=corroboration,
                                   metadata_norms={fuzzy_norm_title("NY")})
    assert [(t.title, t.title_source) for t in out] == [
        ("FF", "tags"), ("t2.mp3", "unresolved"), ("t3.mp3", "unresolved"), ("t4.mp3", "unresolved"),
        ("t5.mp3", "unresolved"), ("Ramone & Emiglio", "setlist-gap"), ("42", "tags"),
        ("t8.mp3", "unresolved")]
    assert notes == ["accepted short tag title: track 1 'FF' corroborated by setlist.fm",
                     "accepted short tag title: track 7 '42' corroborated by lma:x, setlist.fm"]
    assert tracks[0].title_source == "unresolved"     # input untouched


def test_accept_short_tags_ignores_tags_that_pass_is_real_title():
    # a 2b-demoted "tmp" is unresolved with a real-looking tag: 2a must not re-accept it
    tracks = [Track(index=1, set="1", title="t1.mp3", filename="t1.mp3", title_source="unresolved")]
    out, notes = accept_short_tags(tracks, ["tmp"], "tags", corroboration={fuzzy_norm_title("tmp"): ("lma:x",)},
                                   metadata_norms=set())
    assert out[0].title_source == "unresolved" and notes == []
```

- [ ] **Step 2: Run** the two files — Expected: `ImportError: cannot import name 'tag_core'` / `accept_short_tags`.

- [ ] **Step 3: Implement** per Interfaces. The call site in `compute_gather` sits immediately after `adopt_gap_titles(...)` and before `flags = []`; `tag_titles`/`tag_source` come from the `tag_layer(...)` call Task 9 added. `TAUTOLOGICAL_TITLE_SOURCES` is not touched.

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_titles.py` and the 2a gather tests. Mutants: (a) drop the alphanumeric check; (b) drop the `metadata_norms` veto; (c) accept when ANY segue component is corroborated instead of every one; (d) drop `is_junk_tag`; (e) `strip_taper_markers` removes an attached `#`. A survivor gets a test.

- [ ] **Step 6: Commit** — `git commit -m "feat(gather): 2a corroborated short tags"`

---

### Task 11: 2c — glued track-number prefix

Spec: "2c. Glued track-number prefix", Evidence "Glued prefixes (2c)".

**Files:**
- Modify: `packages/llama/src/llama/titles.py` (`clean_tag_titles`)
- Create fixture: `packages/llama/tests/fixtures/rre2013-11-30.json` via `--from-cache RRE2013-11-30.ShermanTheaterStroudsburgPa`
- Test: `packages/llama/tests/test_titles.py` (append), `packages/llama/tests/test_stage_gather.py` (append)

**Interfaces:**
- Produces: `titles._GLUED_NUM_PREFIX = re.compile(r"^\d{2}(?=[A-Z][a-z])")`; in `clean_tag_titles`, after the existing (unchanged) `_TRACK_NUM_PREFIX` vote and strip, a second independent vote over the same `voters`: `glued = sum(1 for t in voters if _GLUED_NUM_PREFIX.match(t))`; when `glued >= _ENUMERATED_MIN_FILES and glued >= _ENUMERATED_MIN_COVERAGE * len(voters)`, every title gets `_GLUED_NUM_PREFIX.sub("", t, count=1)`. `_TRACK_NUM_PREFIX` and both `_ENUMERATED_MIN_*` constants are untouched. Gather emits the Contracts 2c note per changed title, only when `tag_source == "tags"` (when format recovery fired, `tag_titles` are the lossless sibling's titles and a comparison with the mp3's own tags would note spurious strips): compare the pre- and post-strip tag layers, `raw = [clean_tag_title(f.get("title")) for f in kept]`, and note where `tag_titles[i] != raw[i]` and `_GLUED_NUM_PREFIX.match(raw[i])`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_titles.py`:

```python
# --- slice 2c: a glued two-digit prefix on an enumerated tape ---

def test_clean_tag_titles_strips_a_glued_prefix_when_the_recording_votes_for_it():
    files = _files(["01Pig In A Pen", "02Midnight Moonlight", "03Old And In The Way", "03Colorado"])
    assert clean_tag_titles(files) == ["Pig In A Pen", "Midnight Moonlight", "Old And In The Way", "Colorado"]


@pytest.mark.parametrize("titles", [
    ["01Pig In A Pen", "02Midnight Moonlight", "Dew"],                   # 2 of 3: under the count floor
    ["01Pig In A Pen", "02Midnight Moonlight", "03Old", "Dew", "Star"],  # 3 of 5: under 0.8 coverage
])
def test_clean_tag_titles_leaves_glued_prefixes_alone_under_the_vote(titles):
    assert clean_tag_titles(_files(titles)) == titles


def test_glued_strip_never_reaches_uppercase_or_digit_second_characters():
    files = _files(["01Pig In A Pen", "02Midnight Moonlight", "03Old And In The Way", "3AM", "M80", "7-Up", "01ABBA"])
    out = clean_tag_titles(files)
    assert out[3:] == ["3AM", "M80", "7-Up", "01ABBA"]
```

Append to `packages/llama/tests/test_stage_gather.py`:

```python
RRE = FIXTURES / "rre2013-11-30.json"
R_IDENT = "RRE2013-11-30.ShermanTheaterStroudsburgPa"


def test_2c_strips_railroad_earths_glued_numbers_and_notes_each(tmp_path):
    cand = Candidate(performance_id="RailroadEarth/2013-11-30", collection="RailroadEarth",
                     date="2013-11-30", venue="Sherman Theater", city="Stroudsburg, PA",
                     recordings=[RecordingSummary(identifier=R_IDENT)])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(json.loads(RRE.read_text())), None,
                         cand, R_IDENT, jerrybase_enabled=False)
    titles = [t.title for t in res.show.tracks]
    assert titles[:2] == ["Pig In A Pen", "Midnight Moonlight"]
    assert "stripped glued track number: track 1 '01Pig In A Pen' -> 'Pig In A Pen'" in res.notes
```

- [ ] **Step 2: Run** — Expected: the glued titles come back unchanged.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Full suite green.**
- [ ] **Step 5: Commit** — `git commit -m "feat(titles): 2c glued track-number prefix strip under the enumerated vote"`

---

## Checkpoint B (operator): slice 2 hand-check lists

Spec acceptance for 2a, 2b, 2c. Measure per "Measuring at a checkpoint" with `X=B`, `PREV=tier1-base` (B's slice delta is the cumulative one).

**Pre-screen (Opus, read-only; see "Operator time").** Rules for this checkpoint: bucket the 2b demotions by class (placeholder vocabulary, timestamp, residue, recording-level) and flag every recording-level and residue row (vocabulary and timestamp rows are exact matches and routine); for each 2a acceptance, quote the corroborating line from the sibling description or setlist.fm beside the core, and flag any where the core is a substring of a line rather than an item of it.

The orchestrator assembles, from `cmp-B-all` (library-wide, `notes.txt`) and `cmp-B-held`, and hands the operator the pre-screen plus:

1. **2b demotion list** (the `2b` group of `notes.txt`, by show; ≈ 650 tracks, mostly whole tapes). Pass = zero demoted pure-4-digit titles (grep `'\d{4}'` in the notes: must be empty) and zero demoted titles that a sibling or setlist.fm lists (by construction; spot-check 10). The packaged-exposure list must name exactly `eotoband-2007-10-09`, `gratefuldead-1977-03-18`, `newmastersounds-2018-05-08`, `blitzentrapper-2013-11-12`, `motherhips-2013-06-21` (plus any the spec's Evidence missed, each explained). The `format sibling tagged:` count is filed in the report, not acted on.
2. **2a accepted list** (the `2a` group of `notes.txt`, with its sources) for a hand check against the corroborating line (flagged rows plus the 20-row sample) (`llama show <slug> --tracks` is read-only and fine to run from the main checkout). Pass = zero cores without an alphanumeric, in `metadata_norms`, junk-vetoed or corroborated only by the chosen description (grep the sources: `chosen` must never appear), and no shipped title ending in a taper marker. `title_sources.txt` must show no change on any track that was not `unresolved` in the base arm.
3. **2c strip list** (every `stripped glued track number:` note); the four Railroad Earth shows lose the research flag where the strip was its cause.
4. `closest_calls.txt` slice 2a section; `structure_changed.txt` (every entry is hand-checked before it can join an apply list).

**Ask:** approve slice 2 as measured, or name the entries that fail. Stop until answered. On approval, the approved rows go to `$H/approved-B.txt`.

**Recorded at Checkpoint B (operator, 2026-10-19):**
- Check (a) is read as covering the residue class only: `ryanadams-2006-07-20`'s `6040` (the 60/40 SBD/AUD matrix ratio) is correctly demoted, by the recording-level class.
- Known limitation: the timestamp arm demotes the real song `2:22` (`gracepotterandthenocturnals-2009-07-24` and `-2009-07-26`, track 5). `parse_setlist`'s `_JUNK_TITLE` drops it too, so no cross-source item exempts it. Those shows stay held and are resolved by `llama fix --set-title`.
- Task 11b added. Part A: the `setlist` and `setlist-gap` rungs (and `sibling-align`'s row hygiene) never adopt a placeholder item (zachdeputy-2008-12-06, infamousstringdusters-2010-10-15). Part B: shipped-title cosmetics on the 2a (`M80,`, `E: 2x2`, `42(1)`) and 2c (`The Cuckoo #`, `Walls Of Time #^`) paths.

---

### Task 12: 1b `venues_equivalent` and `cities_compatible`

Spec: "Slice 1 — 1b. Better equivalence", "City compatibility", "New constants" (metro aliases, city folds, 6-character floor). `_REGION_FOLDS` below is a new a-priori constant table not in the spec's list; the operator signs it off with this plan.

**Files:**
- Modify: `packages/llama/src/llama/structure.py` (venue block, lines 240–320)
- Test: `packages/llama/tests/test_structure.py` (extend the two venue parametrizations; append)

**Interfaces:**
- Produces, in `structure.py`:
  - `_one_edit(a: str, b: str) -> bool`: Levenshtein distance ≤ 1 (one substitution, insertion or deletion); callers apply the length floor.
  - `_place_tokens(s)`: apostrophes (`'`, `’`) are deleted before tokenising (so `Penn's` → `penns`); tokens are folded through `_PLACE_FOLD = {"amphitheatre": "amphitheater", "ampitheater": "amphitheater", "ampitheatre": "amphitheater", "pavillion": "pavilion"}` before the stopword drop. (`theatre` stays in `_PLACE_ABBREV` as today.)
  - `_tokens_equal(a, b)`: as today, or `min(len(a), len(b)) >= 6 and _one_edit(a, b)`.
  - `_UNIVERSITY_TOKENS = frozenset({"u", "univ", "uc", "ucla", "ucsb", "uiuc", "mit", "university"})`.
  - `venues_equivalent(a, b)`: tokens as today → both empty True / one empty False → **joined-string test** (`"".join(ta) == "".join(tb)`: `Jahrhundert Halle` = `Jahrhunderthalle`, `race track` = `racetrack`) → subset test over `ta`/`tb` with university tokens removed, declined (not True, not short-circuit False) when the removal empties either side → acronym test as today.
  - `_CITY_FOLDS = {"ft": "fort", "st": "saint", "mt": "mount", "nyc": "new york city"}`, `_METRO_ALIASES = {"goleta": "santa barbara", "salinas": "monterey", "yuzawa": "naeba", "thornville": "legend valley"}`.
  - `_REGION_FOLDS` (new a-priori constant; comment: "decision P8, signed off with the plan"): US state names (and `district of columbia`) and Canadian province/territory names, lowercase, to their postal codes:
    ```python
    _REGION_FOLDS = {
        "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca",
        "colorado": "co", "connecticut": "ct", "delaware": "de", "district of columbia": "dc",
        "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id", "illinois": "il",
        "indiana": "in", "iowa": "ia", "kansas": "ks", "kentucky": "ky", "louisiana": "la",
        "maine": "me", "maryland": "md", "massachusetts": "ma", "michigan": "mi", "minnesota": "mn",
        "mississippi": "ms", "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
        "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
        "north carolina": "nc", "north dakota": "nd", "ohio": "oh", "oklahoma": "ok", "oregon": "or",
        "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc", "south dakota": "sd",
        "tennessee": "tn", "texas": "tx", "utah": "ut", "vermont": "vt", "virginia": "va",
        "washington": "wa", "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
        "alberta": "ab", "british columbia": "bc", "manitoba": "mb", "new brunswick": "nb",
        "newfoundland and labrador": "nl", "nova scotia": "ns", "ontario": "on",
        "prince edward island": "pe", "quebec": "qc", "saskatchewan": "sk",
        "northwest territories": "nt", "nunavut": "nu", "yukon": "yt",
    }
    _COUNTRY_NOISE = ("united states", "usa", "us")   # folded to nothing in a region
    ```
  - `_city_parts(s: str | None) -> tuple[str, str]`: `(key, region)`; key = first comma field lowercased, punctuation to spaces, whitespace collapsed, each token folded through `_CITY_FOLDS`, then the whole key through `_METRO_ALIASES`; region = second comma field, lowercased, punctuation dropped, whitespace collapsed, every whole-word occurrence of a `_COUNTRY_NOISE` phrase removed (`ca usa` → `ca`, `us` → `""`), stripped, then the whole remainder through `_REGION_FOLDS` (`new york` → `ny`, `michigan` → `mi`); `""` when absent or emptied. Other countries' names are not folded (`Germany` vs `GER` still differ).
  - `cities_compatible(a: str | None, b: str | None) -> bool`: `False` when either key is empty; `False` when both regions are non-empty and differ; else True on key equality, or `min(len) >= 6 and _one_edit(ka, kb)`, or whole-token containment (every token of the shorter token list appears in the longer; `la` vs `dallas` is False because `la` is not a token of `dallas`).

- [ ] **Step 1: Write the failing tests**

In `test_structure.py`, add to the `test_venues_equivalent_true` parametrization:

```python
    ("Penn's Landing", "Penns Landing"),
    ("Merriweather Post Pavillion", "Merriweather Post Pavilion"),
    ("Red Rocks Amphitheatre", "Red Rocks Ampitheater"),
    ("Cornell U", "Cornell University"),
    ("Barton Hall, Cornell University", "Barton Hall, Cornell U"),
    ("Jahrhundert Halle", "Jahrhunderthalle"),
    ("Meramec Race Track", "Merramec Racetrack"),
    ("Barrymore Theater", "Barrymore Theatre"),
```

and to `test_venues_not_equivalent`:

```python
    ("UCLA", "UCSB"),
    ("Buffalo Auditorium", "Community War Memorial Auditorium"),
    ("The Pageant", "Barrymore Theatre"),
    ("Shrine Auditorium", "Shrine Exhibition Hall"),
```

(The subset rule is unchanged: `Fox Theatre` vs `Fox Theatre Pavilion` is still equivalent, as today.)

Append:

```python
from llama.structure import _one_edit, cities_compatible


def test_one_edit():
    assert _one_edit("merramec", "meramec") and _one_edit("abc", "abd") and _one_edit("abc", "abcd")
    assert not _one_edit("abc", "xyz") and not _one_edit("abc", "abcde")


@pytest.mark.parametrize("a, b", [
    ("Madison, WI", "Madison, WI"), ("Ft. Lauderdale, FL", "Fort Lauderdale, FL"),
    ("St. Louis, MO", "Saint Louis, MO"), ("NYC", "New York City, NY"), ("Mt. Vernon", "Mount Vernon"),
    ("Detroit Lakes, MN", "Soo Pass Ranch Detroit Lakes, MN"), ("Goleta, CA", "Santa Barbara, CA"),
    ("Thornville, OH", "Legend Valley, OH"), ("Tuxedo, NY", "Tuxedo Park, NY"),
    ("Merramec, MO", "Meramec, MO"), ("Portland", "Portland, OR"),
    ("Utica, New York", "Utica, NY"), ("Rothbury, Michigan", "Rothbury, MI"),
    ("Santa Cruz, CA", "Santa Cruz, CA USA"), ("Washington, District of Columbia", "Washington, DC"),
])
def test_cities_compatible(a, b):
    assert cities_compatible(a, b) and cities_compatible(b, a)


@pytest.mark.parametrize("a, b", [
    ("Portland, OR", "Portland, ME"), ("LA", "Dallas, TX"), ("Dallas", "LA"), (None, "Madison"),
    ("", "Madison"), ("St. Louis, MO", "Madison, WI"), ("Apple Valley, MN", "Minneapolis, MN"),
    ("Bonnaroo", "Manchester, TN"), ("Portland, Oregon", "Portland, ME"), ("Utica, New York", "Utica, MI"),
])
def test_cities_not_compatible(a, b):
    assert not cities_compatible(a, b)
```

- [ ] **Step 2: Run** `./.venv/bin/python -m pytest packages/llama/tests/test_structure.py -q -k "venue or cities or one_edit"` — Expected: ImportError on `cities_compatible`, then the new venue rows failing.

- [ ] **Step 3: Implement** per Interfaces. Grep `venues_equivalent(` across `packages/` first and record the callers in the commit message (today: the gather tripwire only).

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_structure.py -k "venue or cities or one_edit"`. Mutants: (a) the one-edit length floor `>= 6` becomes `>= 5`; (b) the university-token strip returns True instead of declining when it empties a side; (c) `cities_compatible` ignores differing regions; (d) containment by substring instead of whole tokens; (e) `_COUNTRY_NOISE` not removed. A survivor gets a test.

- [ ] **Step 6: Commit** — `git commit -m "feat(structure): 1b venue equivalence folds and the city-compatibility predicate"`

---

### Task 13: Gather venue block — steps 1–3, 1a, 1c, the swap, the two-venue signature, 1d

Spec: "Slice 1 — What changes" (all of it), "Failure modes" (1c), Evidence "Venue (1)".

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (the venue block after the multi-event flags; `two_venue_signature`)
- Create fixtures via `--from-cache`: `packages/llama/tests/fixtures/dso2003-01-25.json` (`dso2003-01-25.shnf`), `packages/llama/tests/fixtures/guster2003-07-10.json` (`guster2003-07-10.shnf`), `packages/llama/tests/fixtures/gd78-11-17_dodd.json` (`gd78-11-17.acoustic.sbd.dodd.7687.sbeok.shnf`)
- Test: `packages/llama/tests/test_stage_gather.py` (append)

**Interfaces:**
- Consumes: `structure.venues_equivalent`, `structure.cities_compatible`, `jerrybase.lookup` (vendored CSV: DSO 2003-01-25 → `Barrymore Theatre`, `Madison`, `WI`; GD 1978-11-17 → `Uptown Theatre`, `Chicago`, `IL`; DSO 2012-05-19 → venue `''`, `Tuxedo Park`, `NY`).
- Produces:
  - `gather.two_venue_signature(candidate: Candidate) -> bool`: True when some pair of recordings with non-empty venues has `not venues_equivalent(a.venue, b.venue)` and `cities_compatible(a.coverage or candidate.city, b.coverage or candidate.city)`.
  - `gather.jerrybase_city(event) -> str`: `f"{event.city}, {event.state}"` when `event.state` else `event.city`.
  - The venue block in `compute_gather`, in this order, with `sel` = the recording in `candidate.recordings` whose identifier is `identifier` (may be None), `sel_venue`/`sel_city` its stripped non-empty `venue`/`coverage` or None, `vote_venue, vote_city = candidate.venue, candidate.city`:
    1. `venue, city, venue_source = vote_venue, vote_city, "item"`.
    2. If `event is not None`:
       - enrichment first: blank `venue` and non-blank `event.venue` → `event.venue`, `event.city`, `"jerrybase"`, byte-identical to today; blank `venue` and blank `event.venue` → nothing changes (1a: a blank jerrybase venue neither enriches nor flags, so the vote's city stays and `venue_source` stays `"item"`); in both cases nothing else in this list runs;
       - else `jb_city = jerrybase_city(event)`, `archive_city = sel_city or vote_city`;
       - **1a**: `event.venue` blank → flag only when `not cities_compatible(archive_city, jb_city)` (today's text with `jerrybase ''`);
       - **step 1**: `venues_equivalent(venue, event.venue) and cities_compatible(archive_city, jb_city)` → nothing;
       - **step 2 (swap)**: `sel_venue and venues_equivalent(sel_venue, event.venue) and cities_compatible(sel_city or vote_city, jb_city) and not two_venue_signature(candidate)` → `venue, city = sel_venue, sel_city or vote_city`; note `swap`;
       - **signature**: `two_venue_signature(candidate)` → today's `venue mismatch` flag;
       - **1c**: `len(events) == 1` (the spec's single-event date: never on a per-event `/eN` candidate of a multi-event date) `and sel_venue and cities_compatible(sel_city or vote_city, jb_city)` → `venue, city = sel_venue, sel_city or vote_city`; note `1c`;
       - else today's `venue mismatch` flag.
    3. **1d**, every show: `sel_venue and sel_city and vote_city and not cities_compatible(sel_city, vote_city)` → `venue, city = sel_venue, sel_city`; flag `1d` (Contracts text, `sel_city` and `vote_city` verbatim).
    4. Overrides block as today, extended: `overrides.venue is not None or overrides.city is not None` also removes any flag starting with `recordings of this date disagree on city`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_stage_gather.py`:

```python
# --- slice 1: venue tripwire steps, the swap, the signature, 1d (spec "Slice 1") ---

from llama.stages.gather import two_venue_signature

DSO = FIXTURES / "dso2003-01-25.json"; DSO_IDENT = "dso2003-01-25.shnf"
GUSTER = FIXTURES / "guster2003-07-10.json"; G_IDENT = "guster2003-07-10.shnf"
GD78 = FIXTURES / "gd78-11-17_dodd.json"; GD78_IDENT = "gd78-11-17.acoustic.sbd.dodd.7687.sbeok.shnf"


def _dso_candidate():
    return Candidate(performance_id="DarkStarOrchestra/2003-01-25", collection="DarkStarOrchestra",
                     date="2003-01-25", venue="The Pageant", city="St. Louis, MO",
                     recordings=[RecordingSummary(identifier="ds2003-01-25.shnf", venue="The Pageant",
                                                  coverage="St. Louis, MO"),
                                 RecordingSummary(identifier=DSO_IDENT, venue="Barrymore Theater",
                                                  coverage="Madison, WI")])


def _gather(tmp_path, fixture, cand, ident, **kw):
    sws = ShowWorkspace(tmp_path / "s")
    md = json.loads(fixture.read_text())
    return compute_gather(sws, StubIA(md), None, cand, ident, jerrybase_enabled=True, **kw)


def test_swap_ships_the_selected_venue_when_it_agrees_with_jerrybase_and_1d_still_holds(tmp_path):
    res = _gather(tmp_path, DSO, _dso_candidate(), DSO_IDENT)
    assert (res.show.venue, res.show.city) == ("Barrymore Theater", "Madison, WI")
    assert ("venue taken from the selected recording: 'Barrymore Theater' agrees with jerrybase "
            "'Barrymore Theatre' (vote was 'The Pageant')") in res.notes
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)
    assert "recordings of this date disagree on city: 'Madison, WI' (selected) vs 'St. Louis, MO'" in res.show.review_flags


def test_an_operator_venue_override_suppresses_the_1d_hold(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.overrides, Overrides(venue="Barrymore Theatre", city="Madison, WI"))
    res = compute_gather(sws, StubIA(json.loads(DSO.read_text())), None, _dso_candidate(), DSO_IDENT,
                         jerrybase_enabled=True)
    assert res.show.venue == "Barrymore Theatre" and res.show.venue_source == "override"
    assert not any("disagree on city" in f for f in res.show.review_flags)


def test_two_venue_signature_keeps_the_same_city_double_held(tmp_path):
    recs = [RecordingSummary(identifier="gd1978-11-17.135718.sbd.partial.schley.andrewf.flac1644",
                             venue="Uptown Theater", coverage="Chicago, IL"),
            RecordingSummary(identifier=GD78_IDENT, venue="Rambler Room, Loyola College", coverage="Chicago, IL"),
            RecordingSummary(identifier="gd78-11-17.paud.wiley.11488.sbeok.shnf", venue="Uptown Theatre",
                             coverage="Chicago, IL")]
    cand = Candidate(performance_id="GratefulDead/1978-11-17", collection="GratefulDead", date="1978-11-17",
                     venue="Rambler Room, Loyola College", city="Chicago, IL", recordings=recs)
    assert two_venue_signature(cand)
    res = _gather(tmp_path, GD78, cand, GD78_IDENT)
    assert "venue mismatch: archive 'Rambler Room, Loyola College' vs jerrybase 'Uptown Theatre'" in res.show.review_flags
    assert res.show.venue == "Rambler Room, Loyola College"
    assert not any(n.startswith("venue differs from jerrybase") for n in res.notes)


def test_signature_also_fires_on_spellings_of_one_hall():
    cand = Candidate(performance_id="GratefulDead/1981-09-26", collection="GratefulDead", date="1981-09-26",
                     recordings=[RecordingSummary(identifier="a", venue="Buffalo Auditorium", coverage="Buffalo, NY"),
                                 RecordingSummary(identifier="b", venue="Community War Memorial Auditorium",
                                                  coverage="Buffalo, NY")])
    assert two_venue_signature(cand)
    assert not two_venue_signature(cand.model_copy(update={"recordings": [cand.recordings[0]]}))


def test_1d_ships_the_selected_recording_on_a_city_conflict_without_jerrybase(tmp_path):
    cand = Candidate(performance_id="Guster/2003-07-10", collection="Guster", date="2003-07-10",
                     venue="Cities 97 Studio C", city="Minneapolis, MN",
                     recordings=[RecordingSummary(identifier="guster2003-07-10.fm.shnf", venue="Cities 97 Studio C",
                                                  coverage="Minneapolis, MN"),
                                 RecordingSummary(identifier=G_IDENT, venue="Weesner Amphitheater, MN Zoo",
                                                  coverage="Apple Valley, MN")])
    res = _gather(tmp_path, GUSTER, cand, G_IDENT)
    assert (res.show.venue, res.show.city) == ("Weesner Amphitheater, MN Zoo", "Apple Valley, MN")
    assert "recordings of this date disagree on city: 'Apple Valley, MN' (selected) vs 'Minneapolis, MN'" in res.show.review_flags


def test_1d_does_not_fire_without_a_selected_city_or_with_compatible_cities(tmp_path):
    base = _dso_candidate()
    no_city = base.model_copy(update={"recordings": [base.recordings[0],
                                                     base.recordings[1].model_copy(update={"coverage": None})]})
    res = _gather(tmp_path, DSO, no_city, DSO_IDENT)
    assert not any("disagree on city" in f for f in res.show.review_flags)
    same_city = base.model_copy(update={"city": "Madison, WI", "venue": "Barrymore Theatre"})
    res = _gather(tmp_path, DSO, same_city, DSO_IDENT)
    assert not any("disagree on city" in f for f in res.show.review_flags)
    assert res.show.venue == "Barrymore Theatre"          # step 1: the vote ships, no churn


def test_1a_blank_jerrybase_venue_is_no_evidence_when_cities_agree(tmp_path):
    md = json.loads(DSO.read_text())
    cand = Candidate(performance_id="DarkStarOrchestra/2012-05-19", collection="DarkStarOrchestra",
                     date="2012-05-19", venue="Mighty High Festival-Tuxedo Ridge", city="Tuxedo, NY",
                     recordings=[RecordingSummary(identifier=DSO_IDENT, venue="Mighty High Festival-Tuxedo Ridge",
                                                  coverage="Tuxedo, NY")])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(md), None, cand, DSO_IDENT, jerrybase_enabled=True)
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)
    far = cand.model_copy(update={"city": "Albany, NY",
                                  "recordings": [cand.recordings[0].model_copy(update={"coverage": "Albany, NY"})]})
    res = compute_gather(ShowWorkspace(tmp_path / "s2"), StubIA(md), None, far, DSO_IDENT, jerrybase_enabled=True)
    assert "venue mismatch: archive 'Mighty High Festival-Tuxedo Ridge' vs jerrybase ''" in res.show.review_flags


def test_1c_same_city_different_name_becomes_a_note_and_ships_the_selected_string(tmp_path):
    cand = _dso_candidate().model_copy(update={
        "venue": "Orpheum", "city": "Madison, WI",
        "recordings": [RecordingSummary(identifier=DSO_IDENT, venue="Orpheum", coverage="Madison, WI")]})
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Orpheum"
    assert "venue differs from jerrybase: archive 'Orpheum' vs 'Barrymore Theatre' (same city)" in res.notes
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)


def test_1a_blank_vote_venue_on_a_blank_jerrybase_venue_takes_nothing_from_jerrybase(tmp_path):
    md = json.loads(DSO.read_text())
    cand = Candidate(performance_id="DarkStarOrchestra/2012-05-19", collection="DarkStarOrchestra",
                     date="2012-05-19", venue="", city="Tuxedo, NY",
                     recordings=[RecordingSummary(identifier=DSO_IDENT, coverage="Tuxedo, NY")])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(md), None, cand, DSO_IDENT, jerrybase_enabled=True)
    assert (res.show.city, res.show.venue_source) == ("Tuxedo, NY", "item")   # not jerrybase's "Tuxedo Park"
    assert not any(f.startswith("venue mismatch") for f in res.show.review_flags)


def test_1c_does_not_apply_on_a_per_event_candidate_of_a_multi_event_date(tmp_path, monkeypatch):
    from llama.models import JerrybaseEvent
    early = JerrybaseEvent(event_id="e1", venue="Barrymore Theatre", city="Madison", state="WI")
    late = JerrybaseEvent(event_id="e2", venue="Barrymore Theatre", city="Madison", state="WI")
    monkeypatch.setattr(gather_mod.jerrybase, "lookup", lambda artist, date: [early, late])
    cand = _dso_candidate().model_copy(update={
        "performance_id": "DarkStarOrchestra/2003-01-25/e1", "venue": "Orpheum", "city": "Madison, WI",
        "recordings": [RecordingSummary(identifier=DSO_IDENT, venue="Orpheum", coverage="Madison, WI")]})
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert not any(n.startswith("venue differs from jerrybase") for n in res.notes)
    assert "venue mismatch: archive 'Orpheum' vs jerrybase 'Barrymore Theatre'" in res.show.review_flags


def test_1c_declines_on_incompatible_cities_and_keeps_the_flag(tmp_path):
    cand = _dso_candidate().model_copy(update={
        "recordings": [RecordingSummary(identifier=DSO_IDENT, venue="Orpheum", coverage="St. Louis, MO")]})
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert "venue mismatch: archive 'The Pageant' vs jerrybase 'Barrymore Theatre'" in res.show.review_flags


def test_selected_recording_missing_from_candidate_is_no_swap_and_no_1d(tmp_path):
    # Review Focus 1.
    cand = _dso_candidate().model_copy(update={"recordings": [_dso_candidate().recordings[0]]})
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "The Pageant"
    assert "venue mismatch: archive 'The Pageant' vs jerrybase 'Barrymore Theatre'" in res.show.review_flags
    assert not any("disagree on city" in f for f in res.show.review_flags)
```

- [ ] **Step 2: Run** — Expected: `ImportError: two_venue_signature`, then the DSO swap assertion failing (`The Pageant`).

- [ ] **Step 3: Implement** per Interfaces. Keep the enrichment arm first and byte-identical apart from the 1a guard (no enrichment from a blank `event.venue`). `build_canonical`'s `candidate.venue`/`city` are untouched (the block runs after it).

- [ ] **Step 4: Full suite green.** The gd73 fixture tests must still pass unchanged (its RFK Stadium vote equals jerrybase: step 1).

- [ ] **Step 5: Mutation step** (Global Constraints recipe) over the slice-1 gather tests. Mutants: (a) the swap without `not two_venue_signature(candidate)`; (b) 1c without `len(events) == 1`; (c) 1d evaluated before the swap; (d) the overrides block no longer removes the 1d flag; (e) enrichment fires on a blank `event.venue`. A survivor gets a test.

- [ ] **Step 6: Commit** — `git commit -m "feat(gather): slice 1 venue tripwire: swap, 1a, 1c, two-venue signature, 1d city-conflict hold"`

---

## Checkpoint C (operator): slice 1 lists

Spec "Slice 1 — Acceptance". Measure per "Measuring at a checkpoint" with `X=C`, `PREV=tier1-cp-B`.

**Pre-screen (Opus, read-only; see "Operator time").** Rules: split the venue clears into spelling-only (a 1b fold, the one-edit rule or the joined-string test explains the whole difference) and different-name; flag every different-name clear, every swap and every 1c.

Hand the operator the pre-screen plus:

1. Every cleared venue pair (shows that lost the `venue` family): archive string vs jerrybase string, and for 1c entries whether the shipped string is right (flagged rows plus the 20-row sample). Known wrong strings the operator may `--set-venue`: `gratefuldead-1967-11-10`, `gratefuldead-1968-08-23`, `philleshandfriends-2005-12-04`.
2. Zero cleared shows whose cities are not compatible (the orchestrator re-derives this from the notes: every swap/1c note's show must have compatible cities; also unit-tested).
3. `darkstarorchestra-2003-01-25` is in the `city` family (held by 1d) with venue `Barrymore Theater`, and `gratefuldead-1978-11-17` still carries `venue mismatch`.
4. Library-wide (`cmp-C-all`): `packaged_exposure.txt` lists every venue/city string change; each one must carry a swap, 1c or 1d note (step 1, 1a and 1b change no string). Every clear whose shipped venue is not equivalent to the selected recording's own is listed (from the arm: the shipped venue, `venue.new` or else the stored venue, vs `selected_venue`).
5. `closest_calls.txt` slice 1 (1c) section: the bottom 10 by token overlap.

**Ask:** approve slice 1, or name failures. Stop until answered. On approval, the approved rows go to `$H/approved-C.txt`.

**Recorded at Checkpoint C (operator, 2026-10-19):**
- First measurement (tier1-cp-C = 88f087a): slice 1 cleared 60 held shows but newly held 45 currently-clean delivered/packaged shows, of which only 3 were true conflicts. The rest were false: country name vs code, suburb vs metro, comma-less `City ST`, venue text in the city field, and identical venue names whose cities did not compare.
- Task 13b (operator-approved narrowing):
  - **V:** 1d fires only when the selected recording's venue is NOT `venues_equivalent` to the vote's venue. A blank vote venue counts as not equivalent.
  - **S:** step 1's city check applies only to pairs that 1b newly made equivalent. Pairs equivalent under the pre-slice rule (`structure._venues_equivalent_pre1b`, a frozen copy of the tier1-cp-B2 rule) pass on equivalence alone.
- Task 13c: `replay_holds compare --no-repro-gate`, used for every `-prev`-vs-cand compare.
- Re-measure (tier1-cp-C2 = b6f353a): 54 cleared, 4 newly held:
  - ryanadams-2007-06-06 (true);
  - beneventorusso-2005-08-27, gratefuldead-1978-09-16, smashingpumpkins-1997-06-28 (false; the venue names differ).
  Slice 1 approved as narrowed.
- Documented limitation: V uses the live `venues_equivalent`, so Task 12's loosenings widen V's suppression. `Cornell University` vs `Cornell College` (university strip) and `Capitol` vs `Capital Theatre` (one-edit) count as the same hall. There are 0 such pairs in the library today; the operator chose to leave it.
- Live-library fixes made by the operator at C, outside this branch, with `llama fix --set-venue/--set-city`:
  - gratefuldead-1978-04-15, gratefuldead-1985-06-14, darkstarorchestra-2005-06-07, darkstarorchestra-2005-07-17, darkstarorchestra-2017-06-27, philleshandfriends-1999-10-31;
  - re-delivered with a corrected venue: belafleckandtheflecktones-2006-04-21, guster-2003-07-10, stuallenandmarshotel-2012-11-11, ginblossoms-2003-01-24, belafleckandtheflecktones-2004-04-06;
  - overrides staged: soundtribesector9-2003-06-13, yondermountainstringband-2005-07-16.
  Later checkpoints treat these as expected drift.

---

### Task 14: Briefing guard 3a/3b/3c and reuse normalisation

Spec: "Slice 3 — Briefing guard", "Which briefing ships", "New constants" (3c lists).

**Files:**
- Modify: `packages/llama/src/llama/stages/brief.py`
- Modify: `packages/llama/src/llama/replay.py` (`briefing_reusable` and `replay_show`'s `stored_brief_guard` normalise before the guard)
- Modify: `scripts/replay_holds.py` (`compare`: the suppressed-claims section of `briefings.txt`, replacing an ad-hoc Checkpoint D probe)
- Test: `packages/llama/tests/test_stage_brief.py` (append), `packages/llama/tests/test_replay.py` (append), `scripts/test_replay_holds.py` (append)

**Interfaces:**
- Produces:
  - `brief.normalize_briefing(b: Briefing) -> Briefing` (3a): a copy with every `per_set` entry whose list is empty removed; everything else byte-identical.
  - `run_brief`: after each generation, `briefing = normalize_briefing(briefing)` before the guard and the writes.
  - `brief._BRIEF_STRUCTURE_PREFIX = re.compile(r"^\s*(?:e\d*|encore)\s*:\s*", re.I)` (brief-local; `structure._STRUCTURE_PREFIX` untouched), `_BRIEF_TRAILING = re.compile(r"[\s>\-*%#@^~+]+$")`, `_BRIEF_PAREN = re.compile(r"\s*\([^)]*\)\s*$")`, `_BRIEF_SEGUE = re.compile(r"\s*(?:->|>|→)\s*")`.
  - `brief.song_components(title: str) -> list[str]`: strip the prefix, the trailing markers, one trailing parenthetical (then trailing markers again), split on segues, `normalize_song` each, drop empties.
  - `brief.known_song(song: str, exact: set[str], components: set[str]) -> bool` (3b): `normalize_song(song) in exact` (today's test, first) or (`cs = song_components(song)` non-empty and every `c in components`).
  - `briefing_guard`: `exact = {normalize_song(t.title) for t in show.tracks}`; `components = exact | {c for t in show.tracks for c in song_components(t.title)} | {" ".join(song_components(t.title)) for t in show.tracks}`; a mentioned song is unknown when `not known_song(...)`.
  - 3c: today's `_SET_COUNT_CLAIM` and `_ORDINAL_SET` stay byte-identical (the vague branch keeps using them). New `_SET_COUNT_CLAIM_3C = re.compile(r"\b(both|two|three|four|[234])\s+(?:(\w+)\s+)?sets\b(?!\s+of\b)", re.I)`: today's pattern with its single optional intervening word captured as group 2, still `\w+` (never `[\w-]+`: widening it would make "two hard-hitting sets" a new claim). `_NOT_SHOW_WIDE = frozenset({"electric", "acoustic", "night", "late-night", "afternoon", "weekend", "more", "festival", "day"})`, with a comment that `late-night` is unreachable under `\w+` (the hyphen ends the word) and is kept only because the spec lists it; `_NEGATION_2 = frozenset({"no", "not", "never"})`, `_NEGATION_4 = ("instead of", "expected", "without")`; `_SCOPE_AFTER = re.compile(r"^\s*(?:each|every|a|per)\s+(?:night|day|weekend|tour)\b", re.I)`.
  - `brief._claim_counts(prose: str) -> tuple[set[int], dict[int, str]]`: iterates `_SET_COUNT_CLAIM_3C` and `_ORDINAL_SET`; a count match whose group 2 (lowercased) is in `_NOT_SHOW_WIDE` is skipped; any match (count or ordinal) is skipped when the two words before it (tokens of `prose[:m.start()]`, lowercased, punctuation stripped) contain a `_NEGATION_2` word, or the four words before it contain `expected`/`without` or the bigram `instead of`, or `_SCOPE_AFTER.match(prose[m.end():])`.
  - `briefing_guard`: the full-narration branch takes `claimed`/`implied` from `_claim_counts(prose)`; the vague branch keeps today's computation exactly (`_SET_COUNT_CLAIM`/`_ORDINAL_SET` `finditer`, no qualifier/negation/scope skipping), as the spec leaves it unchanged.
  - `replay.briefing_reusable`: calls `briefing_guard(normalize_briefing(briefing), new_show)`; `compute_legs` stores the normalised briefing in `Legs.briefing`; `replay_show`'s `stored_brief_guard` becomes `briefing_guard(normalize_briefing(stored briefing), stored show)`.
  - `compare`, `briefings.txt` section (4) `suppressed set-count/ordinal matches` (from the cand arm's `root`, read-only): for every `shows/*/briefing.json` with its `show.json`, under full narration, every match of today's `_SET_COUNT_CLAIM`/`_ORDINAL_SET` over the guard's prose (the same fields `briefing_guard` joins) whose span `_claim_counts` drops: slug, the matched text, and 60 characters of context either side. The count heads the section (the prototype found about 68).

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_stage_brief.py`:

```python
# --- slice 3 (spec "Slice 3 — Briefing guard") ---

from llama.stages.brief import briefing_guard, known_song, normalize_briefing, song_components


def test_3a_empty_sets_are_dropped_and_the_guard_never_sees_them():
    b = _briefing(per_set={"1": ["a"], "2": ["b"], "encore": []})
    assert briefing_guard(b, _show(encore=False)) == ["briefing references nonexistent set: encore"]  # today's reading, pre-normalisation
    n = normalize_briefing(b)
    assert n.per_set == {"1": ["a"], "2": ["b"]}
    assert briefing_guard(n, _show(encore=False)) == []
    assert "## Encore" not in render_briefing_md(n, _show(encore=False))


def test_run_brief_normalises_before_the_guard_and_the_writes(tmp_path):
    show = _show(encore=False)
    ws = _ws(tmp_path, show)
    with_empty_encore = json.dumps({**json.loads(GOOD_BRIEFING), "per_set": {"1": ["a"], "2": ["b"], "encore": []}})
    run_brief(ws, FakeProvider(completes=[with_empty_encore]), show, "r", [])
    assert read_model(ws.show, Show).needs_review is False
    assert "encore" not in json.loads(ws.briefing_json.read_text())["per_set"]
    assert "## Encore" not in ws.briefing_md.read_text()


@pytest.mark.parametrize("song, titles, known", [
    ("E1: Ripple", ["Ripple"], True),
    ("Encore: Ripple", ["Ripple"], True),
    ("1979 (Kerry Brown on drums)", ["1979"], True),
    ("Storms (fades in)", ["Storms"], True),
    ("Drums > Space", ["Drums", "Space"], True),
    ("Drums > Space", ["Drums > Space"], True),
    ("Drums", ["Drums > Space"], True),               # a merged track's component is a known title
    ("Scarlet Begonias", ["Scarlet Begonias > Fire on the Mountain"], True),
    ("Fire", ["Scarlet Begonias > Fire on the Mountain"], False),   # no subphrase matching
    ("Ripple", ["Ripple (reprise)"], True),
    ("44 Blues", ["Ripple"], False),
    ("Dark Star", ["Dark Star Jam"], False),          # no loosely_same_title
])
def test_3b_tolerant_matching_narrowly(song, titles, known):
    exact = {normalize_song(t) for t in titles}
    comps = exact | {c for t in titles for c in song_components(t)} | {" ".join(song_components(t)) for t in titles}
    assert known_song(song, exact, comps) is known


def test_3b_is_a_superset_of_todays_matcher():
    # every pair today's exact test accepts, the new one accepts
    titles = ["Ripple", "Drums > Space", "E: Casey Jones", "1979 (live)", "Me & My Uncle"]
    exact = {normalize_song(t) for t in titles}
    comps = exact | {c for t in titles for c in song_components(t)} | {" ".join(song_components(t)) for t in titles}
    for t in titles:
        assert normalize_song(t) in exact
        assert known_song(t, exact, comps)


@pytest.mark.parametrize("prose, claims, ordinals", [
    ("two electric sets tonight", set(), {}),
    ("two excellent sets", {2}, {}),
    ("two sets that night", {2}, {}),
    ("two night sets", set(), {}),
    ("there is no second set", set(), {}),
    ("not three sets but two", set(), {}),          # "three sets" negated; "but two" is not followed by "sets"
    ("instead of the usual two sets", set(), {}),
    ("expected two sets", set(), {}),
    ("without the second set", set(), {}),
    ("two sets each night of the run", set(), {}),
    ("two sets a night", set(), {}),
    ("two sets per weekend", set(), {}),
    ("the second of Panic's two weekend sets", set(), {}),   # "second of" is not "second set"; the count is qualified
    ("two hard-hitting sets", set(), {}),                     # no match today, none now: the word stays \w+
    ("the band played both sets", {2}, {}),
    ("two sets of fiddle tunes", set(), {}),
    ("a monster second set", set(), {2: "second"}),
])
def test_3c_set_count_claims(prose, claims, ordinals):
    from llama.stages.brief import _claim_counts
    assert _claim_counts(prose) == (claims, ordinals)


def test_3c_leaves_the_vague_branch_on_todays_regexes():
    show = _show(encore=False)
    # under full narration 3c drops this qualified count; under vague today's regex still catches it
    b = _briefing(per_set={}, narration="vague", context="the band played two electric sets")
    assert "briefing asserts set structure under vague narration" in briefing_guard(b, show)
```

Append to `packages/llama/tests/test_replay.py`:

```python
def test_briefing_reusable_normalises_empty_sets_before_the_guard():
    show = Show(performance_id="A/1973-06-10", identifier="x", artist="A", date="1973-06-10",
                tracks=[Track(index=1, set="1", title="Dew", filename="a.mp3", title_source="tags")])
    b = Briefing(context="c", significance="s", per_set={"1": ["x"], "encore": []})
    assert briefing_reusable(show, show, b, "full") is None
```

Append to `scripts/test_replay_holds.py`:

```python
def test_briefings_lists_a_set_count_match_the_new_guard_suppresses(tmp_path):
    base, cand = _two_arms(tmp_path)
    root = tmp_path / "lib"
    ws = root / "shows" / "gratefuldead-1973-06-10"
    b = json.loads((ws / "briefing.json").read_text())
    b["context"] = "They played two electric sets that night, a long one and a short one."
    (ws / "briefing.json").write_text(json.dumps(b))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "briefings.txt").read_text()
    assert "suppressed set-count/ordinal matches" in text
    assert "gratefuldead-1973-06-10" in text and "two electric sets" in text
```

- [ ] **Step 2: Run** the two files — Expected: ImportError on `normalize_briefing`.

- [ ] **Step 3: Implement** per Interfaces. The existing `test_guard_flags_bogus_set_key_but_allows_encore` and `test_guard_flags_empty_per_set_under_full` must still pass: an empty `per_set` dict (no talking points at all) is still a problem; only empty entries are dropped.

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_stage_brief.py` and `test_replay.py`. Mutants: (a) `known_song` accepts when ANY component is known; (b) `_claim_counts` drops the two-word negation window; (c) the vague branch uses `_claim_counts`; (d) `_SET_COUNT_CLAIM_3C` widened to `[\w-]+`; (e) `normalize_briefing` also drops a non-empty set. A survivor gets a test.

- [ ] **Step 6: Commit** — `git commit -m "feat(brief): guard 3a empty sets, 3b narrow tolerant matching, 3c qualified set counts"`

---

## Checkpoint D (operator): the stored-briefing re-check

Spec "Slice 3 — Acceptance". Measure per "Measuring at a checkpoint" with `X=D`, `PREV=tier1-cp-C`. Everything this checkpoint needs is a `compare` output (no ad-hoc probe): `briefings.txt` in `cmp-D-all` gives (a) the held shows whose `stored_brief_guard` changed between the arms (the 55 held briefings, cleared or still held), (b) `clean briefings firing` (must be `cand 0`), and (c) the suppressed set-count/ordinal matches with 60 characters of context; `outcomes.txt`/`predicted_list.json` give which cleared shows ship their briefing by reuse.

**Pre-screen (Opus, read-only; see "Operator time").** Rules: pre-read each briefing that will ship by reuse against its `show.json` and flag any claim (song, set, segue, venue, date) it cannot find there; class each suppressed set-count/ordinal match as qualifier, negation or scope from its context, and flag any whose class does not fit the text.

Hand the operator the pre-screen plus: (1) the reused-briefing list (flagged briefings are read whole, plus the 20-row sample; this is where the spec's "every reused briefing read whole by hand" becomes pre-screen + flagged + sample); (2) zero newly firing on clean briefings; (3) the suppressed-match list (prototype ≈ 68; flagged rows plus the sample); (4) the remaining ~20 holds. **Ask:** approve slice 3, or name failures. Stop until answered. On approval, the approved rows go to `$H/approved-D.txt`.

**Recorded at Checkpoint D (operator, 2026-10-19):**
- Measured at tier1-cp-D = b9ae699 (slice 3 alone; Task 15 was implemented after the measurement so it could not reach the cand arm), with PREV = tier1-cp-C2. Slice 3 changed 34 stored briefing-guard verdicts (3a 11, 3b 15, 3c 8) and moved 27 held shows to `clears`, each shipping its stored briefing by reuse. Zero clean briefings newly fire (base 0, cand 0). Suppressed set-count/ordinal matches: 21, not the prototype's ~68 (the Task 14 fix round clips 3c's negation windows at clause punctuation and briefing-field boundaries).
- Slice 3 approved as measured; approved rows in `$H/approved-D.txt`.
- Five reused briefings REJECTED: smashingpumpkins-1996-04-27, wacobrothers-2005-12-22, warrenzevon-1988-11-30, thewaybacks-2006-04-29, deadandcompany-2015-11-20. Their prose asserts encore or segue detail the guard does not check, and show.json does not support it. They stay held, are listed in `$H/rejected-D.txt`, and **Checkpoint G drops them from `predicted_list.json`** before any apply. The operator re-briefs them after the merge.
- furthur-2011-02-12's suppressed match ("had expected a spacier second set", classed as negation) is accepted as harmless: the show has two sets.
- moe-2002-06-22 stays held. Its briefing's "two sets and an encore" is right; show.json labels the `E:` encore tracks set 3. The operator fixes the structure after the run.
- For slice 6: 9 of the 27 reused stored `briefing.md` files still carry an empty `## Encore` heading, so reapply's re-render of `briefing.md` from the normalised briefing (spec 3a) is load-bearing for them.

---

### Task 15: 4c `normalize_date` range checks, 4b adjacent-day context, 4d prompt wording

Spec: "Slice 4 — 4b", "4c", "4d"; "New constants" (4b's one-day window).

**Files:**
- Modify: `packages/llama/src/llama/stages/vet_research.py` (`normalize_date`, `grounding_flags`)
- Modify: `packages/llama/src/llama/prompts/vet_research.md` (item 1)
- Test: `packages/llama/tests/test_stage_vet.py` (append), `packages/llama/tests/test_prompts.py` (append)

**Interfaces:**
- Produces:
  - `vet_research._valid_ymd(y, m, d) -> bool`: `1 <= m <= 12 and 1 <= d <= 31`.
  - `normalize_date`: every branch validates with `_valid_ymd`; the slash form `(\d{1,2})/(\d{1,2})/(\d{2,4})`, when month-first is invalid and day-first (`m[2]` month, `m[1]` day) is valid, returns the day-first reading; any other invalid result returns `None`. The yearless slash form `(\d{1,2})/(\d{1,2})` gets the same swap rule.
  - `grounding_flags`: `own_full = show.date in full` (the full-date set). When `own_full`, a mismatched full date whose `datetime.date` is within one day of `show.date` is dropped from `mismatched` BEFORE the flag loop; `raw_date_flags` (the flags that loop would have produced without the window) is kept in a local for Task 16. Placeholder adoption is unchanged (it reads `full`/`mismatched` before the window is applied: compute `mismatched_raw` first, adoption from it, then the windowed `mismatched` for flags).
  - `vet_research.md` item 1 reads: `asserted_songs: every song title the document asserts was performed on this recording — at this show, on this date. List each song as its own entry: ...` (the rest unchanged).

- [ ] **Step 1: Write the failing tests**

Append to `test_stage_vet.py`:

```python
# --- slice 4c/4b (spec "Slice 4") ---

from llama.stages.vet_research import grounding_flags


@pytest.mark.parametrize("text, expected", [
    ("16/11/08", "2008-11-16"),          # month-first invalid, day-first valid: day-first
    ("11/16/08", "2008-11-16"),          # month-first valid stays month-first
    ("13/13/08", None), ("2008-13-01", None), ("2008-00-10", None), ("June 32, 1973", None),
    ("0/5/08", None), ("31/4", "--04-31"),
])
def test_4c_normalize_date_ranges(text, expected):
    assert normalize_date(text) == expected


def _vet(dates, songs=("Morning Dew", "Dark Star")):
    return ResearchVetting(asserted_songs=list(songs), asserted_dates=list(dates))


def test_4b_adjacent_day_is_context_when_the_own_full_date_is_asserted():
    flags, _, _ = grounding_flags(_vet(["June 10, 1973", "1973-06-11"]), make_show())
    assert not any("wrong date" in f for f in flags)
    flags, _, _ = grounding_flags(_vet(["1973-06-10", "1973-06-09"]), make_show())
    assert not any("wrong date" in f for f in flags)


def test_4b_two_days_off_still_flags():
    flags, _, _ = grounding_flags(_vet(["1973-06-10", "1973-06-12"]), make_show())
    assert flags == ["research asserts wrong date: 1973-06-12"]


def test_4b_without_the_own_date_an_adjacent_date_still_flags():
    flags, _, _ = grounding_flags(_vet(["1973-06-11"]), make_show())
    assert flags == ["research asserts wrong date: 1973-06-11"]


def test_yearless_own_date_does_not_make_a_far_date_context():
    # Review Focus 5: "June 10" is not the own FULL date, so 1973-06-12 is not context.
    flags, _, _ = grounding_flags(_vet(["June 10", "1973-06-12"]), make_show())
    assert "research asserts wrong date: 1973-06-12" in flags


def test_4b_leaves_placeholder_adoption_unchanged():
    show = make_show().model_copy(update={"date": "1973-01-01"})
    flags, adopted, _ = grounding_flags(_vet(["1973-06-10"]), show)
    assert adopted == "1973-06-10" and flags == []
```

Append to `test_prompts.py`:

```python
def test_vet_research_prompt_asks_for_songs_on_this_recording():
    from llama.prompts import load_prompt
    assert "on this recording" in load_prompt("vet_research")
```

- [ ] **Step 2: Run** — Expected: `normalize_date("16/11/08")` returns `"2008-16-11"`; the 4b tests fail on the adjacent date.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Full suite green.**
- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_stage_vet.py`. Mutants: (a) the 4b window is two days; (b) the window applies without `own_full`; (c) the window runs before placeholder adoption; (d) `normalize_date` swaps to day-first when month-first is valid. A survivor gets a test.
- [ ] **Step 6: Commit** — `git commit -m "feat(vet): 4c date ranges (day-first fallback), 4b adjacent-day context, 4d prompt wording"`

---

### Task 16: 4a — the right-show gate on unknown songs

Spec: "Slice 4 — 4a", "Failure modes" (4a), "New constants", ruling 6. **Depends on Task 9 (2b).**

**Files:**
- Modify: `packages/llama/src/llama/stages/vet_research.py`
- Test: `packages/llama/tests/test_stage_vet.py` (append)

**Interfaces:**
- Produces:
  - `RIGHT_SHOW_MIN_TAPE_FRACTION = 0.5`, `RIGHT_SHOW_MIN_ASSERTED = 4` (module constants, comment: spec "New constants"; the first may move to `2 / 3`, written exactly so, only at Checkpoint E).
  - `vet_research.right_show_gate(vetting: ResearchVetting, show: Show, *, date_flags_raw: list[str]) -> tuple[bool, dict]`: `resolved` = tracks with `title_source != "unresolved"`, not `is_filler`, and `title_source not in TAUTOLOGICAL_TITLE_SOURCES`; `asserted` = those with `_known_song(t.title, research_known)` where `research_known = [normalize_song(s).split() for s in vetting.asserted_songs]`; `unknown` = research songs not known against the tape (today's list); `unresolved_n` = tracks with `title_source == "unresolved"`; `own_full` = `show.date in {normalize_date(d) for d in vetting.asserted_dates}`; gate = `len(resolved) > 0 and len(asserted) >= RIGHT_SHOW_MIN_TAPE_FRACTION * len(resolved) and len(asserted) >= RIGHT_SHOW_MIN_ASSERTED and len(unknown) <= len(asserted) and unresolved_n * 2 < len(show.tracks) and not date_flags_raw and own_full`. The dict carries `asserted, resolved, ratio, unknown, date_text` (the asserted_dates entry that normalises to the own date).
  - `grounding_flags`: when the unknown-song flags would fire (`not songs_grounded`) and the gate holds, the flags are not added; instead the 4a note (Contracts) is appended to the returned notes. `date_flags_raw` is computed BEFORE 4b's window (Task 15's local).

- [ ] **Step 1: Write the failing tests**

```python
# --- slice 4a (spec "Slice 4 — 4a") ---

from llama.stages.vet_research import RIGHT_SHOW_MIN_ASSERTED, RIGHT_SHOW_MIN_TAPE_FRACTION, right_show_gate


def _tape(n_titled, n_unresolved=0, sources="tags"):
    tracks = [Track(index=i, set="1", title=f"Song {i}", filename=f"{i}.mp3", title_source=sources)
              for i in range(1, n_titled + 1)]
    tracks += [Track(index=i, set="1", title=f"{i}.mp3", filename=f"{i}.mp3", title_source="unresolved")
               for i in range(n_titled + 1, n_titled + n_unresolved + 1)]
    return make_show().model_copy(update={"tracks": tracks})


def test_constants_are_the_spec_values():
    assert RIGHT_SHOW_MIN_TAPE_FRACTION == 0.5 and RIGHT_SHOW_MIN_ASSERTED == 4


def test_4a_suppresses_unknown_songs_on_a_right_show_tape_and_notes_them():
    show = _tape(8)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 6)] + ["Alpha", "Beta", "Gamma"],
                          asserted_dates=["June 10, 1973"])
    flags, _, notes = grounding_flags(vet, show)
    assert not any("unknown song" in f for f in flags)
    assert notes == ["unknown-song flags suppressed by the right-show gate: 5/8 tape tracks asserted "
                     "(ratio 0.62), 3 unclaimed: Alpha; Beta; Gamma; research date: June 10, 1973"]


@pytest.mark.parametrize("n_titled, n_unresolved, asserted, dates, expect_gate", [
    (8, 0, 5, ["1973-06-10"], True),
    (8, 0, 3, ["1973-06-10"], False),            # below 0.5
    (4, 0, 3, ["1973-06-10"], False),            # 0.75 but fewer than 4 asserted
    (8, 9, 5, ["1973-06-10"], False),            # over half the tape unresolved
    (8, 0, 5, ["June 10"], False),               # own date yearless only
    (8, 0, 5, [], False),                        # no own date
    (8, 0, 5, ["1973-06-10", "1973-06-11"], False),   # a date flag read BEFORE 4b suppresses it
])
def test_right_show_gate_table(n_titled, n_unresolved, asserted, dates, expect_gate):
    show = _tape(n_titled, n_unresolved)
    songs = [f"Song {i}" for i in range(1, asserted + 1)] + ["Alpha", "Beta"]
    vet = ResearchVetting(asserted_songs=songs, asserted_dates=dates)
    raw = ["research asserts wrong date: 1973-06-11"] if "1973-06-11" in dates else []
    ok, info = right_show_gate(vet, show, date_flags_raw=raw)
    assert ok is expect_gate


def test_right_show_gate_requires_the_own_full_date_with_year():
    # Review Focus 5.
    show = _tape(8)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 6)] + ["Alpha", "Beta", "Gamma"],
                          asserted_dates=["June 10"])
    flags, _, notes = grounding_flags(vet, show)
    assert any("unknown song" in f for f in flags) and notes == []


def test_4a_unknown_songs_may_not_outnumber_the_asserted_tracks():
    show = _tape(8)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 5)] + [f"X{i}" for i in range(5)],
                          asserted_dates=["1973-06-10"])
    ok, _ = right_show_gate(vet, show, date_flags_raw=[])
    assert ok is False


def test_4a_excludes_tautological_titles_from_both_sides():
    show = _tape(8, sources="setlist-gap")
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 9)] + ["Alpha", "Beta"],
                          asserted_dates=["1973-06-10"])
    ok, info = right_show_gate(vet, show, date_flags_raw=[])
    assert ok is False and info["resolved"] == 0


def test_4a_a_tmp_tape_demoted_by_2b_cannot_pass():
    show = _tape(0, n_unresolved=19)
    vet = ResearchVetting(asserted_songs=[f"Song {i}" for i in range(1, 20)], asserted_dates=["1973-06-10"])
    ok, _ = right_show_gate(vet, show, date_flags_raw=[])
    assert ok is False
```

- [ ] **Step 2: Run** — Expected: ImportError on `right_show_gate`.
- [ ] **Step 3: Implement** per Interfaces. The unknown-song flag texts and the `songs_grounded` rule are unchanged; the gate only decides whether they are emitted or noted.
- [ ] **Step 4: Full suite green.**
- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_stage_vet.py`. Mutants: (a) drop `own_full`; (b) drop `not date_flags_raw` (or read the windowed date flags instead); (c) drop `len(unknown) <= len(asserted)`; (d) count tautological sources as resolved; (e) `>=` → `>` on the tape fraction. A survivor gets a test.
- [ ] **Step 6: Commit** — `git commit -m "feat(vet): 4a right-show gate turns unknown-song holds into notes"`

---

## Checkpoint E (operator): 4a's decision point and 4b's hand-read

Spec "Slice 4 — Acceptance", "Open questions for Shawn" 1. Measure per "Measuring at a checkpoint" with `X=E`, `PREV=tier1-cp-D`.

**Pre-screen (Opus, read-only; see "Operator time").** Rules: read each 4a clear's `research.md` and flag any whose research names a date, venue or city other than the show's own; read each 4b clear's date discussion and flag any with "misdated", "actually", "wrong date" or similar correction language.

Hand the operator the pre-screen plus:

1. **4a list**: every newly cleared show with its ratio, absolute counts (asserted, unknown), the unclaimed songs and the research date line (all parsed from the 4a note; `closest_calls.txt` slice 4a is the ranked form), ranked by absolute counts as well as ratio. The operator reads every flagged row and the 20-row sample for wrong-show research. **Decision point:** does the 0.5–2/3 band (`ratio < 2 / 3`, compared exactly, so a 4-of-6 tape is at 2/3 and not in the band) contain any wrong-show research? If yes, `RIGHT_SHOW_MIN_TAPE_FRACTION` moves to `2 / 3` (the expression, never a rounded decimal) in a follow-up commit on Task 16 *before* anything ships, and Checkpoint E is re-run. If no, 0.5 stands.
2. **4b list**: every show that lost a `research-date` flag, with its `asserted_dates`; the operator reads the flagged rows' research date discussion and the 20-row sample (`research.md` is read-only).
3. **4c**: the four instances of invalid dates; exactly `ryanadams-2008-11-16` changes.

**Ask:** the 0.5 vs 2/3 decision, and approval of the 4b/4c lists. Stop until answered. On approval, the approved rows go to `$H/approved-E.txt`.

**Recorded at Checkpoint E (operator, 2026-10-19):**
- First measurement at tier1-cp-E = 3928398 (PREV = tier1-cp-D): slice 4 changed 32 outcomes (25 from 4a, 7 from 4b/4c), 0 newly held, 0 clean-changed. The 4a band (`0.5 <= ratio < 2/3`, compared exactly) held 18 rows and no wrong-show research; moving to `2 / 3` would have lost 8 of the 25 4a clears. **`RIGHT_SHOW_MIN_TAPE_FRACTION` stays 0.5.**
- Six clears REJECTED, listed in `$H/rejected-E.txt`; they stay held and **Checkpoint G drops them from `predicted_list.json`**: gratefuldead-1970-06-24-e2 (the tape merges both events of the date; a gather event-split miss, not wrong-show research), soulive-2001-07-20 (would ship the other same-date performance's venue), and four 4b clears on a disputed adjacent date: littlefeat-1973-07-19, littlefeat-1975-01-20, minutemen-1983-12-16, minutemen-1985-11-30.
- 4c as specified ("exactly `ryanadams-2008-11-16` changes") did not hold: `billycorgan-1991-09-01`'s only hold was a research date `1991-09-00`, which 4c stopped reading. Operator decision: a day-00 date is a "day unknown" assertion and keeps flagging. **Task 16b** adds `vet_research.day_unknown_date` (full-year forms, day exactly 0, month 1-12, sharing `normalize_date`'s parsing incl. 4c's day-first slash fallback): on a specific show date each day-00 entry raises `research asserts wrong date: <text>`, also feeds the 4a gate's raw date flags, and is never dropped by 4b's window; on a year-only placeholder show it is ignored.
- littlefeat-1970-01-01 (delivered; a placeholder show asserting `1970-08-00`) reverts its invalid research-adopted date to the item placeholder under 4c; accepted as code behaviour, not held. The operator hand-checks its date after the run.
- **Task 16c** fixed `replay_holds compare`: the slice-4b closest-calls rows now read `vetting.json["vetting"]["asserted_dates"]` (they printed `(vetting.json unavailable)`).
- Re-measure at tier1-cp-E2 = e59a6d8 (PREV = tier1-cp-D): exactly one show differs from the first measurement in any field, billycorgan-1991-09-01 (needs-brief → still-held). Slice 4 approved; approved rows in `$H/approved-E.txt`.

---

### Task 17: 5a — numbered sets only, with the unplaced-encore exception

Spec: "Slice 5 — 5a".

**Files:**
- Modify: `packages/llama/src/llama/structure.py` (`encore_lost`)
- Modify: `packages/llama/src/llama/stages/gather.py` (the `structure_guard` call)
- Test: `packages/llama/tests/test_structure.py` (append), `packages/llama/tests/test_stage_gather.py` (append)

**Interfaces:**
- Produces:
  - `structure._ENCORE_MARKER = re.compile(r"^\s*e\d?\s*[:\]]|\bencore\b", re.I)` (local to this check).
  - `structure.encore_lost(tracks: list[Track], canonical: ParsedSetlist, aliases=None) -> bool`: True when the canonical has at least one `set == "encore"` item and either some encore item's `fuzzy_norm_title(item.title, aliases)` is not among `{c for t in tracks for c in title_components(t.title, aliases)}`, or some track title matches `_ENCORE_MARKER`.
  - `compute_gather`: `evidence = {i.set for i in canonical.items}`; `if not encore_lost(tracks, canonical, family_aliases): evidence.discard("encore")`; pass `evidence_sets=evidence`.

- [ ] **Step 1: Write the failing tests**

Append to `test_structure.py`:

```python
from llama.structure import encore_lost


def _items(*pairs):
    return ParsedSetlist(items=[SetlistItem(title=t, normalized=normalize_song(t), set=s) for t, s in pairs],
                         confidence="high")


def _tracks(*titles):
    return [Track(index=i, set="1", title=t, filename=f"{i}.mp3", title_source="tags")
            for i, t in enumerate(titles, 1)]


def test_encore_lost_is_false_without_an_encore_item_or_when_it_matched():
    assert not encore_lost(_tracks("A", "B"), _items(("A", "1"), ("B", "2")))
    assert not encore_lost(_tracks("A", "B", "Willin'"), _items(("A", "1"), ("B", "2"), ("Willin'", "encore")))


def test_encore_lost_on_an_unmatched_encore_item_or_a_marked_track():
    assert encore_lost(_tracks("A", "B"), _items(("A", "1"), ("B", "2"), ("Willin'", "encore")))
    assert encore_lost(_tracks("A", "B", "E] Willin' >"), _items(("A", "1"), ("B", "2"), ("Willin'", "encore")))
    assert encore_lost(_tracks("A", "E: Rilly Wut?"), _items(("A", "1"), ("Rilly Wut?", "encore")))
    assert encore_lost(_tracks("A", "Crowd Encore Call > B"), _items(("A", "1"), ("B", "encore")))
    assert not encore_lost(_tracks("A", "Encore Call > B"), _items(("A", "1"), ("B", "2")))   # no encore item at all
```

Append to `test_stage_gather.py` (the gd73 fixture's description has set 1, set 2 and an encore; the whole-tape flow has breaks so the guard is inert; use the structure_guard call directly through a patched `structure_guard` recorder):

```python
def test_5a_passes_numbered_sets_only_unless_the_encore_was_lost(tmp_path, monkeypatch):
    seen = {}
    real = gather_mod.structure_guard
    def spy(tracks, breaks, evidence_sets=None, **kw):
        seen["evidence"] = set(evidence_sets or ())
        return real(tracks, breaks, evidence_sets=evidence_sets, **kw)
    monkeypatch.setattr(gather_mod, "structure_guard", spy)
    compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(), make_candidate(), IDENT,
                   jerrybase_enabled=False)
    assert seen["evidence"] == {"1", "2"}            # the encore matched: dropped from the evidence
    md = json.loads(FIXTURE.read_text())
    md["metadata"]["description"] = md["metadata"]["description"].replace("Johnny B. Goode", "Casey Jones")
    sixth = next(f for f in md["files"] if f["name"] == "gd73-06-10d3t01.mp3")
    sixth["title"] = "Johnny B. Goode"               # a real tag, so the count-equal setlist rung cannot copy "Casey Jones" onto it
    compute_gather(ShowWorkspace(tmp_path / "s2"), StubIA(md), FakeProvider(), make_candidate(), IDENT,
                   jerrybase_enabled=False)
    assert "encore" in seen["evidence"]              # the encore item no longer matches: kept
```

(The fixture's description ends `Encore:\nJohnny B. Goode` and its sixth mp3, `gd73-06-10d3t01.mp3`, has no tag, so in the first half the positional `setlist` rung titles it `Johnny B. Goode`. In the second half the canonical's encore item is `Casey Jones` and the sixth file carries the real tag `Johnny B. Goode`, so no track matches the encore item.)

- [ ] **Step 2: Run** — Expected: ImportError on `encore_lost`.
- [ ] **Step 3: Implement** per Interfaces. `structure_guard` itself is unchanged.
- [ ] **Step 4: Full suite green.**
- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_structure.py -k encore_lost` and the 5a gather test. Mutants: (a) `encore_lost` ignores `_ENCORE_MARKER`; (b) `encore_lost` returns True whenever an encore item exists; (c) `compute_gather` always discards `"encore"`. A survivor gets a test.
- [ ] **Step 6: Commit** — `git commit -m "feat(structure): 5a numbered-set evidence with the unplaced-encore exception"`

---

### Task 18: 5c — closer tripwire tolerance and numbered-set anchoring

Spec: "Slice 5 — 5c" (1–3), "Acceptance" for 5c.

**Files:**
- Modify: `packages/llama/src/llama/jerrybase.py`
- Modify: `packages/llama/src/llama/stages/gather.py` (after `anchor_breaks` declines; the closer tripwire)
- Modify: `scripts/replay_holds.py` (`compare`: two `closest_calls.txt` slice 5c subsections, replacing an ad-hoc Checkpoint F probe)
- Test: `packages/llama/tests/test_jerrybase.py` (append; REWRITE one existing test, named below), `packages/llama/tests/test_stage_gather.py` (append), `scripts/test_replay_holds.py` (append)

**Interfaces:**
- `structure._FILLER` / `is_filler` are NOT touched (the spec's "existing filler regex only"; it also feeds `_songish_coverage` and the low-confidence flag). The spec's `Donor Rap` is illustrative: today's regex does not call it filler, and that stays so.
- Produces, in `jerrybase.py`:
  - `_LEADING_PAREN = re.compile(r"^\s*\([^)]*\)\s*")`; `_closer_candidates` applies it to the closer and to each track title before `title_components` (5c.3). `_resolve_positions` and `anchor_breaks` untouched: on a fold-created ambiguity `anchor_breaks` still resolves to the latest candidate by its existing rule, which is why Checkpoint F lists every show where 5c.3 created a second candidate.
  - `_followed_only_by_filler(tracks, i) -> bool`: every track after position `i` up to the set's last track (the next set change, or the tape's end) satisfies `structure.is_filler`, and there is at least one such track.
  - `closer_contradictions` (5c.1), signature and return shape unchanged: when the single hit is not at a break and `_followed_only_by_filler(tracks, hit)`, no hard flag is added and nothing is added to `soft` either.
  - `filler_tail_closers(tracks, event) -> list[str]` (5c.1): the Contracts 5c.1 note for exactly the closers `closer_contradictions` excused (single hit, not at a break, `_followed_only_by_filler`), in event order.
  - **Dropped at Checkpoint F (Task 18b).** `anchor_numbered_sets(tracks, event, aligned_sets) -> tuple[list[str], str | None] | None` (5c.2): returns `None` unless the event has at least one numbered set AND at least one `encore` row; every numbered closer has exactly one candidate (`_closer_candidates`) and every encore row's closer has none; the numbered positions are strictly increasing. Labels: tracks up to and including numbered closer i → that set's name; tracks after the last numbered closer: `"encore"` where `aligned_sets` is given and `aligned_sets[i] == "encore"` (the deterministic alignment already said encore), else the last numbered set's name. The note is the Contracts 5c.2 string (`closer` = the first encore row's closer) when at least one trailing track stays in the last set, else `None`.
  - **Dropped at Checkpoint F (Task 18b).** `compute_gather`: in the `anchored is None` case and `event is not None`, `numbered = jerrybase.anchor_numbered_sets(tracks, event, result.sets)`; when not None: `result = result.model_copy(update={"sets": labels})`, `alignment = "jerrybase"`, append `"set breaks anchored from jerrybase"` (+ ` (was ...)`) to the local structure `notes` exactly as the existing anchoring branch does, and the 5c.2 note (when given) to `GatherResult.notes`. The LLM/low-coverage `elif` is then skipped exactly as for a full anchoring. At the closer tripwire, `filler_tail_closers(tracks, event)` goes to `GatherResult.notes` (never to the local `notes`, which reach `structure.conflicts` and the briefing LLM).
- `compare`, two `closest_calls.txt` slice 5c subsections (read-only, from the cand arm's `root`, importing `llama.jerrybase` from the running tree):
  - `5c.3 second closer candidates`: every show whose stored `show.json` tracks give some closer of a jerrybase event on its date (`jerrybase.lookup(show.artist, show.date)`, every event) two or more `_closer_candidates`, where the closer or a candidate's title starts with a parenthetical (`_LEADING_PAREN.match`): slug, closer, the candidate titles. A superset of the shows where the fold created the second candidate.
  - `5c.1 short-track arm (not adopted)`: the count, then the list, of shows whose cand arm still carries `jerrybase set closer '<c>' is not at a set break` where `<c>` has a single candidate in the stored tracks and every track after it up to the next set change is under 420 s (stored `duration_sec`).

- [ ] **Step 1: Write the failing tests**

Append to `test_jerrybase.py` (the file's builders: `_tracks(titles)` labels every track set `"1"`, `_tracks_with_sets([(title, set), ...])`, `_event([(closer, name), ...])`):

```python
from llama.jerrybase import _closer_candidates, anchor_numbered_sets


def test_5c1_closer_followed_only_by_filler_is_an_operator_note_not_a_soft_note():
    # Tuning and Crowd are filler under today's _FILLER, which this task does not widen
    tracks = _tracks_with_sets([("Bertha", "1"), ("Deal", "1"), ("Tuning", "1"), ("Crowd", "1"),
                                ("Playin", "2"), ("Sugar Magnolia", "2")])
    event = _event([("Deal", "1"), ("Sugar Magnolia", "2")])
    hard, soft = jerrybase.closer_contradictions(tracks, event)
    assert hard == [] and soft == []      # nothing reaches structure.conflicts
    assert jerrybase.filler_tail_closers(tracks, event) == [
        "jerrybase set closer 'Deal' is followed only by filler before the set break"]
    tracks = _tracks_with_sets([("Bertha", "1"), ("Deal", "1"), ("Loser", "1"), ("Crowd", "1"),
                                ("Playin", "2"), ("Sugar Magnolia", "2")])
    hard, _ = jerrybase.closer_contradictions(tracks, event)
    assert hard == ["jerrybase set closer 'Deal' is not at a set break"]
    assert jerrybase.filler_tail_closers(tracks, event) == []


def test_5c3_leading_parenthetical_folds_on_both_sides():
    assert _closer_candidates(_tracks(["(I Can't Get No) Satisfaction", "Deal"]), "Satisfaction") == [0]
    assert _closer_candidates(_tracks(["Satisfaction"]), "(I Can't Get No) Satisfaction") == [0]
    assert _closer_candidates(_tracks(["Libery"]), "Liberty") == []            # typos stay failures
    assert _closer_candidates(_tracks(["Unlce John's Band"]), "Uncle John's Band") == []


def test_5c2_anchors_numbered_sets_when_only_the_encore_closer_is_missing():
    tracks = _tracks(["Bertha", "Deal", "Playin", "Sugar Magnolia", "Casey Jones"])
    event = _event([("Deal", "1"), ("Sugar Magnolia", "2"), ("Johnny B. Goode", "encore")])
    assert jerrybase.anchor_breaks(tracks, event) is None                      # today declines
    labels, note = anchor_numbered_sets(tracks, event, ["1", "1", "1", "1", "1"])
    assert labels == ["1", "1", "2", "2", "2"]
    assert note == ("set breaks anchored from jerrybase numbered sets (encore row 'Johnny B. Goode' "
                    "unmatched; 1 trailing track(s) stay in set 2)")
    labels, note = anchor_numbered_sets(tracks, event, ["1", "1", "1", "1", "encore"])
    assert labels == ["1", "1", "2", "2", "encore"] and note is None


def test_5c2_trailing_tracks_stay_in_the_last_set_and_a_matched_encore_closer_declines():
    tracks = _tracks(["Bertha", "Deal", "Playin", "Sugar Magnolia", "JBG"])
    event = _event([("Deal", "1"), ("Sugar Magnolia", "2"), ("Johnny B. Goode", "encore")])
    labels, note = anchor_numbered_sets(tracks, event, None)
    assert labels == ["1", "1", "2", "2", "2"] and note is not None
    tracks = _tracks(["Bertha", "Deal", "Playin", "Sugar Magnolia", "Johnny B. Goode"])
    assert anchor_numbered_sets(tracks, event, None) is None                  # every closer matches: anchor_breaks' job
    two_encores = _event([("Deal", "1"), ("Sugar Magnolia", "2"), ("Johnny B. Goode", "encore"),
                          ("Bertha", "encore")])
    assert anchor_numbered_sets(_tracks(["Bertha", "Deal", "Playin", "Sugar Magnolia", "JBG"]),
                                two_encores, None) is None                   # every encore row's closer must be absent


def test_5c2_declines_without_an_encore_row_or_on_an_ambiguous_numbered_closer():
    tracks = _tracks(["Bertha", "Deal", "Playin", "Deal"])
    assert anchor_numbered_sets(tracks, _event([("Deal", "1"), ("Playin", "2")]), None) is None
    assert anchor_numbered_sets(tracks, _event([("Deal", "1"), ("Playin", "2"), ("X", "encore")]), None) is None
```

REWRITE (replace in place, keeping its position in the file) the existing `test_closer_matching_preserves_a_leading_parenthetical` (`test_jerrybase.py:380-385`), which pins the pre-5c.3 behaviour `== [0]`:

```python
def test_closer_matching_folds_a_leading_parenthetical_and_anchoring_declines_on_the_ambiguity():
    # 5c.3 folds "(I'm A) Road Runner" and "Road Runner" together, so a tape carrying both has an
    # ambiguous closer: the numbered-set anchoring and the closer tripwire both decline on it
    # (anchor_breaks keeps its latest-candidate rule; Checkpoint F lists every such show).
    tracks = _tracks(["(I'm A) Road Runner", "Road Runner", "Deal"])
    assert jerrybase._closer_candidates(tracks, "(I'm A) Road Runner") == [0, 1]
    event = _event([("(I'm A) Road Runner", "1"), ("Deal", "2"), ("X", "encore")])
    assert anchor_numbered_sets(tracks, event, None) is None
    hard, _ = jerrybase.closer_contradictions(tracks, event)
    assert hard == []
```

Append to `test_stage_gather.py`:

```python
def test_5c2_anchors_the_gd73_tape_when_only_the_encore_row_is_missing(tmp_path, monkeypatch):
    from llama.models import JerrybaseEvent, JerrybaseSet
    event = JerrybaseEvent(event_id="x", venue="RFK Stadium", city="Washington", state="DC", sets=[
        JerrybaseSet(name="1", closer="I Know You Rider", break_length="long"),
        JerrybaseSet(name="2", closer="Eyes of the World", break_length="long"),
        JerrybaseSet(name="encore", closer="Casey Jones", break_length="short")])
    monkeypatch.setattr(gather_mod.jerrybase, "lookup", lambda artist, date: [event])
    res = compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(), FakeProvider(), make_candidate(), IDENT,
                         jerrybase_enabled=True)
    assert res.show.structure.alignment == "jerrybase"
    assert [t.set for t in res.show.tracks] == ["1", "1", "1", "2", "2", "encore"]
    assert "set breaks anchored from jerrybase" in " ".join(res.show.structure.conflicts)
    assert not any(f.startswith("jerrybase set closer") for f in res.show.review_flags)
    assert not any("followed only by filler" in c for c in res.show.structure.conflicts)
```

Append to `scripts/test_replay_holds.py`:

```python
def test_closest_calls_has_the_two_5c_subsections(tmp_path):
    base, cand = _two_arms(tmp_path)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "closest_calls.txt").read_text()
    assert "5c.3 second closer candidates" in text and "5c.1 short-track arm (not adopted)" in text
```

- [ ] **Step 2: Run** — Expected: ImportError on `anchor_numbered_sets`; the 5c.1 test's `hard` is non-empty.
- [ ] **Step 3: Implement** per Interfaces. No other anchoring rule or constant changes.
- [ ] **Step 4: Full suite green** — the existing `test_jerrybase.py` (apart from the one rewritten test) and the two anchoring gather fixtures must pass unchanged.
- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_jerrybase.py` and the 5c gather test. Mutants: (a) `_followed_only_by_filler` accepts when ANY following track is filler; (b) `anchor_numbered_sets` accepts a numbered closer with two candidates; (c) drop the strictly-increasing check; (d) `_LEADING_PAREN` applied to the closer only; (e) the 5c.1 note sent to the local `notes`. A survivor gets a test.
- [ ] **Step 6: Commit** — `git commit -m "feat(jerrybase): 5c closer tolerance: filler tails, numbered-set anchoring, leading parenthetical"`

---

## Checkpoint F (operator): slice 5 lists; 5c ships only if its lists pass

Spec "Slice 5 — Acceptance", "Order and dependencies" (5c is prototyped on its branch first). Measure per "Measuring at a checkpoint" with `X=F`, `PREV=tier1-cp-E`; `cmp-F-slice-*` isolates Tasks 17–18.

**Pre-screen (Opus, read-only; see "Operator time").** Rules: render every anchoring change as old breaks → new breaks beside the jerrybase event's closers, and flag any break that moves past a non-filler track (`is_filler` false).

Hand the operator the pre-screen plus:

1. **5a**: the cleared list (shows that lost `setlist evidence shows multiple sets but alignment found none`) with each show's canonical set count, minutes and description excerpt (`closest_calls.txt` slice 5a); flagged rows and the 20-row sample are hand-checked. The shows that picked up `single-set structure for a long show` instead are listed too.
2. **5c**: every anchoring change as old breaks → new breaks (`closest_calls.txt` slice 5c, from `set_breaks`/`alignment` diffs), checked against the jerrybase event (flagged rows plus the sample); **zero changes on shows whose stored `structure.alignment` was already `jerrybase`** (the orchestrator greps the arm: any such show with a `set_breaks` diff fails the checkpoint); no set-label change on non-target shows (`structure_changed.txt` must list only shows carrying a 5c.2 note or a lost closer flag (after Task 18b: a lost closer flag only)).
3. **5c.3**: every show in `closest_calls.txt`'s `5c.3 second closer candidates` subsection (every show where the leading-parenthetical fold can have created a second closer candidate), each read by hand: on such a show `anchor_breaks` resolves to the latest candidate, so a break can move one track.
4. The 5c.1 short-track arm is NOT adopted; report the count from `closest_calls.txt`'s `5c.1 short-track arm (not adopted)` subsection (hard flags a `< 7 min` arm would additionally have removed).

**Ask:** approve 5a; approve 5c to ship, or revert Task 18 (`git revert`) and leave 5c for a later tier. Stop until answered. On approval, the approved rows go to `$H/approved-F.txt`.

**Recorded at Checkpoint F (operator, 2026-10-20):**
- First measurement at tier1-cp-F = a92dd72 (Tasks 17, 18 and the E docs; PREV = tier1-cp-E2): hard check 1 passed (0 `set_breaks` changes on the 636 shows whose stored alignment is already `jerrybase`; the 5c.3 fold never created a second candidate). 5a cleared 2 shows, both right (railroadearth-2007-09-13, yondermountainstringband-2000-11-02). 5c.1 (6/6) and 5c.3 (8/8) read clean.
- **5c.2 REJECTED and dropped.** `anchor_numbered_sets` produced 5 wrong structures: gratefuldead-1971-04-29 (delivered; moved the Uncle John's Band encore into set 2), deadandcompany-2018-06-16 (released a hold on a wrong structure), and removed correct set breaks on gratefuldead-1980-10-31, gratefuldead-1970-05-14 and ratdog-2003-05-01, where jerrybase records fewer numbered sets than the tape (ratdog's set-2 row is one of the CSV loader's 117 skipped malformed rows). It also released 9 holds with a visible encore left in the last numbered set. **Task 18b** (098c2b2) removed the arm, its gather call and notes.json routing, its tests and the `compare` note-id row; 5c.1 and 5c.3 are kept unchanged.
- Re-measure at tier1-cp-F2 = 098c2b2 (PREV = tier1-cp-E2): 39 shows differ from the first F; 36 return exactly to their E2 replay (the 3 breaks restored, both wrong structures held again, the encore releases held again). The other 3 (darkstarorchestra-2008-08-31, philleshandfriends-2001-11-17, philleshandfriends-2008-07-06) carry a 5c.1 filler-tail note in place of one hard closer flag — 5c.2 had masked them at F — with no outcome change. Hard check 1 passed again. Slice 5 approved as 5a + 5c.1 + 5c.3; approved rows in `$H/approved-F.txt`; there is no `rejected-F.txt`.

---

### Task 19: `llama reapply <show>` — the single-show apply

Spec: "Slice 6 — The command" (steps 1–4, the write order, the partial-failure contract), "Testing" (the `reapply` bullets).

**Files:**
- Modify: `packages/llama/src/llama/stages/brief.py` (`generate_briefing`, `vetting_summary_text`)
- Modify: `packages/llama/src/llama/stages/package.py` (`build_package` extraction)
- Create: `packages/llama/src/llama/reapply.py`
- Modify: `packages/llama/src/llama/cli.py` (the `reapply` command, names form only; Task 20 adds the list form)
- Test: `packages/llama/tests/test_reapply.py` (create), `packages/llama/tests/test_stage_brief.py` (append)

**Interfaces:**
- Consumes: `replay.compute_legs`, `Legs`, `classify`, `input_digests`, `CacheOnlyIA`, `setlistfm_client`; `brief.normalize_briefing`, `render_briefing_md`, `briefing_guard`; `workspace.drop_stage_artifacts`; `locks.file_lock`; `catalog.CatalogEntry`.
- Produces:
  - `package.build_package(show_ws, ia, show, force: bool = False, profile: str | None = None) -> tuple[Path, list[str]]`: today's `run_package` body minus its trailing `show.json` write, returning the package dir and the package-stage flags (`duration mismatch on ...`). `run_package` becomes `pkg, flags = build_package(...)` plus that unchanged write, so its behaviour and tests are byte-identical.
  - `brief.vetting_summary_text(vr: VettingResult | None) -> str` (the body of today's `vetting_summary`; `vetting_summary(show_ws)` becomes a wrapper reading the file).
  - `brief.generate_briefing(provider, show: Show, research_md: str, reviews: list[dict], *, narration: str, vetting: VettingResult | None) -> tuple[Briefing, list[str]]`: today's two-attempt loop, returning the normalised, narration-stamped briefing and the remaining guard problems (`[]` on success). Writes nothing. `run_brief` calls it and keeps its writes.
  - `reapply.ReapplyOutcome(dataclass)`: `slug: str`, `outcome: str` (`"cleared"`, `"held"`, `"needs-llm"`, `"skipped: not held"`, `"skipped: inputs changed"`, `"dry-run: <predicted>"`), `briefing: str` (`"reuse"|"fresh"|"none"`), `flags: list[str]`, `delivered: bool`, `written: list[str]` (artifact names in write order).
  - `reapply.reapply_show(config: Config, ia, ledger, entry: CatalogEntry, *, providers: dict, row: dict | None, dry_run: bool, echo) -> ReapplyOutcome`. `ia` is the real network client, used ONLY for `build_package`. Under `file_lock(entry.ws.lock)` (blocking), from before the still-held check to after the last write:
    1. re-read `show.json`; not `needs_review` → `skipped: not held`. `row` given and `input_digests(ws) != row["digests"]` → `skipped: inputs changed`.
    2. `legs = compute_legs(ws, config=config, ia=CacheOnlyIA(config.root / "cache"), slfm=setlistfm_client(config), scratch=<mkdtemp, removed in finally>)`: the same client choice as the harness (Task 2's one helper).
    3. `outcome, would_be = classify(legs, "held")` — `reapply` maps `classify`'s outcome and never re-derives needs-LLM itself. `needs-llm` → `needs-llm`, nothing written.
    4. `dry_run` → `dry-run: cleared` (`clears`) / `dry-run: needs-brief` (`needs-brief`) / `dry-run: structure-changed` (`structure-changed`) / `dry-run: held` (`still-held`, `still-held-package`), nothing written.
    5. In memory: `final_show = legs.vet.show if legs.vet else legs.gather.show` (the replayed show with vet applied; `legs.vet` is None only on a `no vetting.json` show that `classify` called still-held); `flags = list(legs.flags)`; `briefing = legs.briefing` when `legs.brief == "reuse"`; when `legs.brief == "fresh"`: `briefing, problems = generate_briefing(providers["brief"], final_show, research_md, reviews, narration=read_overrides(ws).narration, vetting=legs.vet.result if legs.vet else None)`; `flags += problems`.
    6. Writes, in order: `vetting.json` (`legs.vet.result`, only when `legs.vet`); `notes.json` (`ShowNotes(gather=legs.gather.notes, vet=legs.vet.notes if legs.vet else [])`); when a briefing was produced (reuse or fresh): `briefing.json`, `briefing.md` (`render_briefing_md(briefing, final_show)`); when `flags` is empty: drop a pre-existing `package/manifest.json` (`drop_stage_artifacts(ws, "package")`, as `redo --from package` does, so a stale manifest can never short-circuit the package and mark the show cleared), then `pkg, pkg_flags = build_package(ws, ia, final_show, force=False, profile=prov.profile)` and `flags += pkg_flags` (`build_package` writes no `show.json`); finally `show.json`, written once and last, from `final_show` with `review_flags=flags`, `needs_review=bool(flags)`. Outcome `cleared` when `flags` is empty, else `held`.
    7. `delivered` = the ledger has a `delivered` entry for the performance id; the caller prints the reminder.
    `reviews.json`, `provenance.json`, `research.md` and the ledger are never written.
  - `cli.reapply(names: list[str] = Argument(None), from_list: Path = Option(None, "--from-list"), dry_run: bool = Option(False, "--dry-run"))`: this task implements the `names` form: for each name `_resolve_show`, `reapply_show(..., row=None)`, print `reapplied: {slug} -> {outcome}` (+ `  re-deliver with: llama deliver {slug}` when `delivered`); `LlamaError`/`HerderError`/`IAError`/`TaskFailed` → `FAILED {slug}: {exc}` on stderr and continue; exit 1 if any failed. `--from-list` prints `not implemented` until Task 20.

- [ ] **Step 1: Write the failing tests**

Append to `test_stage_brief.py`:

```python
def test_generate_briefing_returns_the_normalised_briefing_and_problems_without_writing(tmp_path):
    show = _show()
    ok = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"], "2": ["b"], "encore": []},
                         mentioned_songs=[]))
    b, problems = generate_briefing(FakeProvider([ok]), show, "r", [], narration="full", vetting=None)
    assert problems == [] and b.per_set == {"1": ["a"], "2": ["b"]} and b.narration == "full"
    bad = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"], "2": ["b"]},
                          mentioned_songs=["Nope"]))
    b, problems = generate_briefing(FakeProvider([bad, bad]), show, "r", [], narration="full", vetting=None)
    assert problems == ["briefing mentions unknown song: Nope"]
```

`packages/llama/tests/test_reapply.py`:

```python
"""llama reapply: exactly the harness's computation, applied under the show lock
with show.json written last (spec slice 6)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_library import build_library

import llama.reapply as reapply_mod
from herder import FakeProvider
from llama.config import load_config
from llama.errors import LlamaError
from llama.ia_client import IAError
from llama.ledger import Ledger
from llama.locks import Locked, file_lock
from llama.models import LedgerEntry, Show, ShowNotes
from llama.reapply import ReapplyOutcome, reapply_show
from llama.replay import input_digests
from llama.workspace import read_model, write_artifact

HELD = "gratefuldead-1973-06-10"


def _env(tmp_path, *, stub_package=True):
    root = tmp_path / "lib"
    shows = build_library(root)
    # the fixture library's own config.toml: `[jerrybase] enabled = false`, as the arms were built.
    # A bare Config(root=root) enables jerrybase, whose 3-set GD 1973-06-10 row would hold the show.
    config = load_config(root / "config.toml")
    ledger = Ledger(root / "ledger.jsonl")
    from llama.catalog import resolve_show
    entry = resolve_show(root, ledger, HELD)
    return root, config, ledger, entry, shows


def _stub_package(monkeypatch, fail_first=False, flags=()):
    calls = []
    def fake(show_ws, ia, show, force=False, profile=None):
        if (show_ws.package_dir / "manifest.json").exists() and not force:
            return show_ws.package_dir, []          # the real early return on an existing manifest
        calls.append(show.performance_id)
        if fail_first and len(calls) == 1:
            raise IAError("download failed")
        write_artifact(show_ws.package_dir / "manifest.json", {"schema_version": 3, "tracks": []})
        return show_ws.package_dir, list(flags)
    monkeypatch.setattr(reapply_mod, "build_package", fake)
    return calls


def _providers(*responses):
    return {"brief": FakeProvider(list(responses))}


def test_reapply_clears_a_held_show_with_a_reusable_briefing_and_writes_show_json_last(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    calls = _stub_package(monkeypatch)
    out = reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)
    assert isinstance(out, ReapplyOutcome)
    assert out.outcome == "cleared" and out.briefing == "reuse"
    assert out.written == ["vetting.json", "notes.json", "briefing.json", "briefing.md", "package", "show.json"]
    show = read_model(entry.ws.show, Show)
    assert show.needs_review is False and show.review_flags == []
    assert calls == [show.performance_id]
    assert read_model(entry.ws.notes, ShowNotes) == ShowNotes(gather=[], vet=[])


def test_reapply_makes_no_llm_call_on_a_reusable_briefing_and_no_network_call_outside_package(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    class NetIA:
        def __getattr__(self, name): raise AssertionError(f"network client used for {name}")
    providers = _providers()
    reapply_show(config, NetIA(), ledger, entry, providers=providers, row=None, dry_run=False, echo=lambda s: None)
    assert providers["brief"].calls == []


def test_reapply_generates_one_fresh_brief_when_none_is_stored(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    entry.ws.briefing_json.unlink()
    _stub_package(monkeypatch)
    ok = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"], "2": ["b"], "encore": ["c"]}))
    providers = _providers(ok)
    out = reapply_show(config, object(), ledger, entry, providers=providers, row=None, dry_run=False, echo=lambda s: None)
    assert out.outcome == "cleared" and out.briefing == "fresh" and len(providers["brief"].calls) == 1
    assert entry.ws.briefing_json.exists() and entry.ws.briefing_md.exists()


def test_reapply_leaves_a_show_held_when_the_fresh_brief_fails_its_guard(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    entry.ws.briefing_json.unlink()
    calls = _stub_package(monkeypatch)
    bad = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"]}, mentioned_songs=["Nope"]))
    out = reapply_show(config, object(), ledger, entry, providers=_providers(bad, bad), row=None, dry_run=False, echo=lambda s: None)
    assert out.outcome == "held" and out.flags == ["briefing mentions unknown song: Nope"]
    assert read_model(entry.ws.show, Show).needs_review is True
    assert calls == []


def test_reapply_writes_nothing_on_a_needs_llm_show(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    show = read_model(entry.ws.show, Show)
    show.structure = show.structure.model_copy(update={"alignment": "llm"})
    write_artifact(entry.ws.show, show)
    before = {p.name: p.read_bytes() for p in entry.ws.dir.iterdir()}
    out = reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)
    assert out.outcome == "needs-llm" and out.written == []
    assert {p.name: p.read_bytes() for p in entry.ws.dir.iterdir()} == before


def test_reapply_writes_nothing_on_a_refusal_mid_show(tmp_path, monkeypatch):
    from herder.limits import RateLimited
    root, config, ledger, entry, _ = _env(tmp_path)
    entry.ws.briefing_json.unlink()
    before = {p.name: p.read_bytes() for p in entry.ws.dir.iterdir()}
    with pytest.raises(RateLimited):
        reapply_show(config, object(), ledger, entry, providers=_providers(RateLimited("limit")), row=None,
                     dry_run=False, echo=lambda s: None)
    assert {p.name: p.read_bytes() for p in entry.ws.dir.iterdir()} == before


def test_a_package_failure_leaves_the_show_held_and_a_rerun_completes_it(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch, fail_first=True)
    with pytest.raises(IAError):
        reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)
    assert read_model(entry.ws.show, Show).needs_review is True          # show.json not yet rewritten
    assert entry.ws.vetting.exists() and entry.ws.briefing_json.exists()  # earlier writes stay
    out = reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)
    assert out.outcome == "cleared"


def test_reapply_passes_no_setlistfm_client_when_no_key_is_configured(tmp_path, monkeypatch):
    # prediction/apply parity: the reapply half (Task 5 pins the harness half)
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    seen = []
    real = reapply_mod.compute_legs
    def spy(ws, **kw):
        seen.append(kw["slfm"])
        return real(ws, **kw)
    monkeypatch.setattr(reapply_mod, "compute_legs", spy)
    reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)
    assert seen == [None]


def test_a_stale_manifest_never_short_circuits_the_package(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    write_artifact(entry.ws.package_dir / "manifest.json", {"schema_version": 3, "tracks": ["stale"]})
    calls = _stub_package(monkeypatch)
    out = reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)
    assert out.outcome == "cleared" and len(calls) == 1
    assert json.loads((entry.ws.package_dir / "manifest.json").read_text())["tracks"] == []


def test_package_flags_land_in_the_one_final_show_json_write(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    flag = "duration mismatch on 01 - Morning Dew.mp3: file 10s vs metadata 664s"
    _stub_package(monkeypatch, flags=[flag])
    out = reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)
    assert out.outcome == "held" and out.written[-1] == "show.json"
    show = read_model(entry.ws.show, Show)
    assert show.review_flags == [flag] and show.needs_review is True


def test_reapply_holds_the_show_lock_throughout(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    real = reapply_mod.compute_legs
    def spy(ws, **kw):
        with pytest.raises(Locked):
            with file_lock(ws.lock, blocking=False):
                pass
        return real(ws, **kw)
    monkeypatch.setattr(reapply_mod, "compute_legs", spy)
    reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)


def test_a_show_edited_after_its_row_was_written_is_skipped(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    row = {"slug": HELD, "digests": input_digests(entry.ws)}
    write_artifact(entry.ws.overrides, {"narration": "vague"})
    out = reapply_show(config, object(), ledger, entry, providers=_providers(), row=row, dry_run=False, echo=lambda s: None)
    assert out.outcome == "skipped: inputs changed" and out.written == []


def test_a_show_no_longer_held_is_skipped(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    show = read_model(entry.ws.show, Show); show.needs_review = False; show.review_flags = []
    write_artifact(entry.ws.show, show)
    out = reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)
    assert out.outcome == "skipped: not held"


def test_dry_run_predicts_and_writes_nothing(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    before = {p.name: p.read_bytes() for p in entry.ws.dir.iterdir()}
    out = reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=True, echo=lambda s: None)
    assert out.outcome == "dry-run: cleared" and out.briefing == "reuse"
    assert {p.name: p.read_bytes() for p in entry.ws.dir.iterdir()} == before


def test_reapply_flags_a_delivered_show_for_redelivery_and_writes_no_ledger_row(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    ledger.record(LedgerEntry(performance_id="GratefulDead/1973-06-10", artist="Grateful Dead", date="1973-06-10",
                              status="delivered", run="r1", recorded_at="2026-10-01T00:00:00+00:00"))
    n = len(ledger.entries())
    out = reapply_show(config, object(), ledger, entry, providers=_providers(), row=None, dry_run=False, echo=lambda s: None)
    assert out.delivered is True and len(ledger.entries()) == n


def test_cli_reapply_names_form(tmp_path, monkeypatch):
    from conftest import cli_invoke
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    import llama.cli as cli
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r = cli_invoke(root / "config.toml", "reapply", "gratefuldead-1973-06-10")   # the library's own config
    assert r.exit_code == 0, r.output
    assert "reapplied: gratefuldead-1973-06-10 -> cleared" in r.output
```

- [ ] **Step 2: Run** — Expected: `ModuleNotFoundError: llama.reapply`; `ImportError: generate_briefing`.

- [ ] **Step 3: Implement** per Interfaces. `reapply_show` builds `research_md` from `ws.research.read_text()` (`""` when absent) and `reviews` from `reviews.json` (`[]` when absent), exactly as `process_show` does.

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Mutation step** (Global Constraints recipe) over `test_reapply.py` and the package tests. Mutants: (a) `show.json` written before `build_package`; (b) the lock released before the writes; (c) `vetting.json` written before the needs-LLM check; (d) `build_package`'s flags dropped; (e) the stale `package/manifest.json` not dropped before `build_package`; (f) `slfm` built unconditionally. A survivor gets a test.

- [ ] **Step 6: Commit** — `git commit -m "feat(reapply): single-show apply under the show lock, show.json last"`

---

### Task 20: `reapply --from-list` / `--dry-run`: batch state, pacing gate, stop rules, list checks

Spec: "Slice 6 — Batch state", "Predicted lists are tied to what produced them", "Cost, refined by the harness", "Acceptance".

**Files:**
- Modify: `packages/llama/src/llama/reapply.py` (`load_list`, `batch_dir`, `read_progress`, `record_progress`)
- Modify: `packages/llama/src/llama/cli.py` (`reapply` list form)
- Test: `packages/llama/tests/test_reapply.py` (append)

**Interfaces:**
- Produces:
  - `reapply.load_list(path: Path, *, sha: str, fingerprint: str) -> dict`: parses the Contracts list shape; raises `LlamaError(f"list {path} was written for code {list_sha} and config {list_fp}; running code is {sha}, config {fingerprint}")` on either mismatch.
  - `reapply.batch_dir(root: Path, list_path: Path) -> Path` = `root / "reapply" / sha256(list bytes).hexdigest()[:16]`.
  - `reapply.read_progress(batch: Path) -> dict[str, dict]` (slug → last row); `record_progress(batch: Path, slug, outcome, retryable: bool)` appends one line (unique-temp append is unnecessary: open in `"a"` under `file_lock(batch / "progress.lock")`).
  - `reapply.STOP_AFTER_LLM_FAILURES = 3`.
  - `cli.reapply` list form: `names` and `--from-list` are mutually exclusive (exit 1). `rows = load_list(...)`; `batch = batch_dir(...)`; unless `--dry-run`: `batch.mkdir`, copy `list.json`; `finished = {s for s, r in read_progress(batch).items() if not r["retryable"]}`; `entries = {e.slug: e for e in iter_shows(config.root, ledger)}`; `pace = pace_options(config)`; `state = pacing_state.read_state(config.root)`; `consecutive = 0`. Per row not in `finished`: (a) `reading = _meter(config, pace)`; `decide(_pacing._now(), reading, Progress(state.per_show_delta), pace)` → `PauseUntil` → print `f"paused: {str(verdict)}"` (`PauseUntil.__str__` is its `reason`, the same `str()` `_render_pause` renders; never `repr` or a field) and then the resume line in `_render_pause`'s format, two-space indented: `f"  resume with: llama reapply --from-list {path}"`, and return; (b) slug not in `entries` → print `missing: {slug}`, `record_progress(..., "skipped: missing", retryable=True)`, continue; (c) `reapply_show(..., row=row, dry_run=dry_run)`; on `RateLimited` → print `f"paused: {str(exc)}"` + the same resume line and return (nothing recorded for that show); on `TaskFailed`/`HerderError` → print `FAILED {slug}: {exc}`, `record_progress(retryable=True)`, `consecutive += 1`; when `consecutive >= STOP_AFTER_LLM_FAILURES` print `stopping after 3 consecutive LLM failures; resume with: ...` and return; on `IAError`/`LlamaError` → `FAILED`, `record_progress(retryable=True)`, continue; on success → `consecutive = 0`, `record_progress(retryable=False)` (for `cleared`, `held`, `needs-llm`, `skipped: not held`, `skipped: inputs changed`), print `reapplied: {slug} -> {outcome}`; when `_meter_applies(config, pace)` print `  meter: 5h {before}% -> {after}%` from a reading before and after the show. `--dry-run`: no batch dir, no progress; per row print `would: {slug} -> {predicted}`, where `predicted` is `reapply_show`'s `dry-run: <x>` outcome without the `dry-run: ` prefix (or its other outcome verbatim: `needs-llm`, `skipped: ...`); end with `summary: {n} rows, {finished} already finished, {fresh} fresh briefs, {downloads} first-time downloads (~175 MB each, ~{downloads*175/1024:.1f} GB)` where `downloads` counts rows whose `package/manifest.json` is absent.

- [ ] **Step 1: Write the failing tests**

Append to `test_reapply.py`:

```python
from llama.reapply import STOP_AFTER_LLM_FAILURES, batch_dir, load_list, read_progress
from llama.replay import code_identity, config_fingerprint


def _list_file(tmp_path, root, config, entries, sha=None, fp=None):
    rows = [{"slug": e.slug, "outcome": "clears", "briefing": "reuse", "digests": input_digests(e.ws)} for e in entries]
    data = {"sha": sha or code_identity(), "config_fingerprint": fp or config_fingerprint(config),
            "written_at": "2026-10-19T00:00:00+00:00", "rows": rows}
    p = tmp_path / "predicted_list.json"
    p.write_text(json.dumps(data))
    return p


def _cli(root):
    return root / "config.toml"     # the fixture library's own config ([jerrybase] enabled = false)


def test_list_from_another_sha_or_config_is_refused(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    bad = _list_file(tmp_path, root, config, [entry], sha="0" * 40)
    with pytest.raises(LlamaError) as exc:
        load_list(bad, sha=code_identity(), fingerprint=config_fingerprint(config))
    assert "was written for code" in str(exc.value)
    bad = _list_file(tmp_path, root, config, [entry], fp="deadbeef")
    with pytest.raises(LlamaError):
        load_list(bad, sha=code_identity(), fingerprint=config_fingerprint(config))


def test_rerun_of_the_same_list_skips_finished_shows_but_not_failed_ones(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    cfg = _cli(root)
    lst = _list_file(tmp_path, root, config, [entry])
    calls = _stub_package(monkeypatch, fail_first=True)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r1 = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert "FAILED gratefuldead-1973-06-10" in r1.output
    progress = read_progress(batch_dir(root, lst))
    assert progress[HELD]["retryable"] is True
    r2 = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert "reapplied: gratefuldead-1973-06-10 -> cleared" in r2.output
    r3 = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert "gratefuldead-1973-06-10" not in r3.output.replace(str(root), "")   # finished: skipped silently
    assert len(calls) == 2


def test_batch_stops_after_three_consecutive_llm_failures(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    from herder import HerderError
    root, config, ledger, entry, shows = _env(tmp_path)
    # three held rows: clone the held show under three slugs
    import shutil
    for i in (2, 3, 4):
        shutil.copytree(entry.ws.dir, root / "shows" / f"held-{i}")
    for d in (root / "shows").glob("held-*"):
        (d / "briefing.json").unlink()
    entry.ws.briefing_json.unlink()
    from llama.catalog import iter_shows
    held = [e for e in iter_shows(root, ledger) if e.state == "held"]
    assert len(held) == 4
    lst = _list_file(tmp_path, root, config, held)
    cfg = _cli(root)
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"brief": FakeProvider([HerderError("boom")] * 12)})   # run_json_task retries
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert r.output.count("FAILED") == STOP_AFTER_LLM_FAILURES
    assert "stopping after 3 consecutive LLM failures" in r.output


def test_missing_show_is_skipped_and_not_finished(tmp_path, monkeypatch):
    # Review Focus 4.
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    data = json.loads(lst.read_text()); data["rows"][0]["slug"] = "gone-1999-01-01"; lst.write_text(json.dumps(data))
    cfg = _cli(root)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert r.exit_code == 0 and "missing: gone-1999-01-01" in r.output
    assert read_progress(batch_dir(root, lst))["gone-1999-01-01"]["retryable"] is True


def test_a_pause_verdict_stops_the_batch_at_the_show_boundary(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    from llama.pacing import PauseUntil
    from datetime import datetime, timezone
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    cfg = _cli(root)
    calls = _stub_package(monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    monkeypatch.setattr(cli, "decide", lambda *a, **k: PauseUntil(datetime.now(timezone.utc), "five_hour", "5h window at 95%"))
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert r.exit_code == 0 and "paused: 5h window at 95%" in r.output
    assert f"resume with: llama reapply --from-list {lst}" in r.output
    assert calls == [] and read_progress(batch_dir(root, lst)) == {}


def test_a_refusal_mid_show_leaves_it_uncommitted_and_the_list_resumable(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    from herder.limits import RateLimited
    root, config, ledger, entry, _ = _env(tmp_path)
    entry.ws.briefing_json.unlink()
    lst = _list_file(tmp_path, root, config, [entry])
    cfg = _cli(root)
    monkeypatch.setattr(cli, "make_providers", lambda config: {"brief": FakeProvider([RateLimited("limit")])})
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert r.exit_code == 0 and "paused: limit" in r.output and "resume with: llama reapply --from-list" in r.output
    assert read_model(entry.ws.show, Show).needs_review is True
    assert read_progress(batch_dir(root, lst)) == {}


def test_dry_run_prints_the_cost_summary_and_creates_no_batch(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    cfg = _cli(root)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst), "--dry-run")
    assert r.exit_code == 0
    assert "would: gratefuldead-1973-06-10 -> cleared" in r.output
    assert "summary: 1 rows, 0 already finished, 0 fresh briefs, 1 first-time downloads (~175 MB each, ~0.2 GB)" in r.output
    assert not (root / "reapply").exists()


def test_names_and_from_list_are_exclusive(tmp_path):
    from conftest import cli_invoke
    root, config, ledger, entry, _ = _env(tmp_path)
    r = cli_invoke(_cli(root), "reapply", HELD, "--from-list", str(tmp_path / "x.json"))
    assert r.exit_code != 0
```

- [ ] **Step 2: Run** — Expected: ImportError on `load_list`.

- [ ] **Step 3: Implement** per Interfaces. The pacing gate reuses `cli._meter`, `cli._meter_applies`, `decide`, `Progress`, `pace_options` as the show loop does; it never calls `pacing_state.record` (the EWMA fix is out of scope: spec "Next").

- [ ] **Step 4: Full suite green.**

- [ ] **Step 5: Commit** — `git commit -m "feat(reapply): --from-list batches with state, a pacing gate, stop rules and list checks"`

---

### Task 21: `fix --untitled` and triage `[u]`

Spec: "Slice 7 — Operator 'untitled' resolution", its acceptance.

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`fix`, `_resolve_prompt`, `_interactive_resolve`; new `_untitled_resolution`)
- Test: `packages/llama/tests/test_fix.py` (append), `packages/llama/tests/test_triage.py` (append)

**Interfaces:**
- Produces:
  - `cli._untitled_resolution(config, ia, ledger, entry, show: Show) -> Path | None`: prints `tracks on this tape (no resolved titles):` then one line per track `  {index:2d}  {filename}`, then `typer.confirm("Title every track 'Untitled (track N)', set narration vague, one set, and overrule any remaining flags?", default=False)`; on no → returns None without writing. On yes: `_edit_overrides(ws, set_titles={n: f"Untitled (track {n})" for n in 1..len(tracks)}, narration="vague", set_breaks=[])`, prints `{slug}: untitled resolution written`, then `pkg = _redo_show(config, ia, ledger, fresh_entry, "gather")`; if `pkg` is None: `_clear_hold(ws)`, prints `{slug}: remaining flags overruled`, `pkg = _redo_show(config, ia, ledger, fresh_entry, "brief")`; returns `pkg`.
  - `fix --untitled` (bool option): refuses with exit 1 and `--untitled cannot be combined with {flag}` when any of `--suggest-titles`, `--exclude`, `--unexclude`, `--include`, `--set-title`, `--set-breaks`, `--set-encore`, `--narration`, `--overrule`, `--no-run` is given (`--no-run` would stage a route that stops at the first hold with no overrule); refuses with `{slug}: --untitled applies only when every track is unresolved ({k} of {n} resolved)` otherwise; else calls `_untitled_resolution` and prints `packaged: {pkg}` / `still held: {slug}`. The confirmation prompt therefore always runs before anything is written.
  - triage: `_resolve_prompt(..., untitled: bool)` adds `[u]ntitled` before `[s]kip` only when every track is `unresolved`; the `u` branch calls `_untitled_resolution` and returns.

- [ ] **Step 1: Write the failing tests**

Append to `test_fix.py`:

```python
# --- slice 7: --untitled (spec "Slice 7") ---

def _all_unresolved_show(tmp_path, n=3):
    ws = _held_show(tmp_path)
    show = read_model(ws.show, Show)
    show.tracks = [Track(index=i, set="1", title=f"t{i:02d}.mp3", filename=f"t{i:02d}.mp3",
                         title_source="unresolved") for i in range(1, n + 1)]
    show.review_flags = ["unresolved track titles"]
    write_artifact(ws.show, show)
    return ws


def test_untitled_is_refused_when_any_track_is_resolved(tmp_path):
    cfg = _cfg(tmp_path)
    _held_show(tmp_path)          # its one track is tagged
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled")
    assert r.exit_code != 0 and "applies only when every track is unresolved (1 of 1 resolved)" in r.output


@pytest.mark.parametrize("flag", [["--suggest-titles"], ["--exclude", "x1"], ["--unexclude", "a"],
                                  ["--include", "x1"], ["--set-title", "1=A"], ["--set-breaks", "1"],
                                  ["--set-encore", "2"], ["--narration", "vague"], ["--overrule"], ["--no-run"]])
def test_untitled_refuses_every_combination(tmp_path, flag):
    cfg = _cfg(tmp_path)
    _all_unresolved_show(tmp_path)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", *flag)
    assert r.exit_code != 0 and "--untitled cannot be combined with" in r.output


def test_untitled_lists_filenames_and_declining_writes_nothing(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="n\n")
    assert "   1  t01.mp3" in r.output and "   3  t03.mp3" in r.output
    assert not ws.overrides.exists() and calls == []


def test_untitled_one_confirmation_writes_titles_narration_and_one_set_then_redoes(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path)
    calls = _stub_redo(monkeypatch, result=Path("/pkg"))
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.titles == {1: "Untitled (track 1)", 2: "Untitled (track 2)", 3: "Untitled (track 3)"}
    assert ov.narration == "vague" and ov.set_breaks == []
    assert calls == ["gather"] and "packaged: /pkg" in r.output


def test_untitled_overrules_remaining_flags_then_continues_from_brief(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _all_unresolved_show(tmp_path)
    outcomes = iter([None, Path("/pkg")])
    calls = []
    import llama.cli as cli
    def fake_redo(config, ia, ledger, e, stage, **kw):
        calls.append(stage)
        if stage == "gather":   # the re-gather raises a flag, as the spec expects
            s = read_model(e.ws.show, Show); s.needs_review = True
            s.review_flags = ["single-set structure for a long show (160 min)"]; write_artifact(e.ws.show, s)
        return next(outcomes)
    monkeypatch.setattr(cli, "_redo_show", fake_redo)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert calls == ["gather", "brief"]
    assert "remaining flags overruled" in r.output and "packaged: /pkg" in r.output
    assert read_model(ws.show, Show).needs_review is False


def test_untitled_gather_makes_no_align_structure_call(tmp_path):
    # the override path (set_breaks=[]) skips align(): run the real gather on gd73 with an align provider
    # that would fail if called
    from llama.stages.gather import compute_gather
    from test_stage_gather import StubIA, make_candidate, IDENT
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.overrides, Overrides(titles={i: f"Untitled (track {i})" for i in range(1, 7)},
                                           narration="vague", set_breaks=[]))
    class Boom:
        def complete(self, prompt): raise AssertionError("align_structure called")
    res = compute_gather(ws, StubIA(), FakeProvider(), make_candidate(), IDENT, align_provider=Boom())
    assert res.needs_llm == () and {t.set for t in res.show.tracks} == {"1"}
    assert [t.title for t in res.show.tracks][0] == "Untitled (track 1)"
```

Append to `test_triage.py`:

```python
def test_triage_offers_u_only_when_every_track_is_unresolved(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _held_show(tmp_path)
    r = cli_invoke(cfg, "triage", "gratefuldead", input="s\n")
    assert "[u]ntitled" not in r.output
    show = read_model(ws.show, Show)
    show.tracks = [t.model_copy(update={"title_source": "unresolved", "title": t.filename}) for t in show.tracks]
    write_artifact(ws.show, show)
    calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", "gratefuldead", input="u\ny\n")
    assert "[u]ntitled" in r.output and calls == ["gather"]
    assert read_overrides(ws).narration == "vague"
```

(Add the imports the snippets use: `Path`, `pytest`, `read_model`, `write_artifact`, `ShowWorkspace`, `Show`, `Track`, `Overrides`, `FakeProvider`.)

- [ ] **Step 2: Run** — Expected: `no such option: --untitled`.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Full suite green.**
- [ ] **Step 5: Commit** — `git commit -m "feat(fix): --untitled and triage [u], the operator route for tapes with no titles"`

---

### Task 22: Docs

**Files:** `CLAUDE.md` (Commands: `llama reapply`, `fix --untitled`/triage `[u]` with `eotoband-2007-10-09`'s route (`redo --from gather`, `fix --untitled`, `deliver`), `scripts/replay_holds.py`, `notes.json`; Architecture: one paragraph on the Tier 1 guards — 1a–1d, 2a–2c, 3a–3c, 4a–4c, 5a/5c — each one sentence, naming the predicate and the spec), `README.md` (operator-facing: the harness, `reapply`, `--untitled`).

- [ ] Write the docs; `./.venv/bin/python -m pytest -q` still green (no code change); commit `docs: Tier 1 held-backlog guards, replay harness, reapply, --untitled`.

---

## Checkpoint G (operator): final measurement, hand checks, dry run, cost, pilot, waves

Spec "Slice 6 — Procedure" and "Acceptance", "Settled by the operator" (the bulk cost is re-asked at apply time). Every command that writes under `~/.llama` is preceded by its own explicit go-ahead; the orchestrator never runs one on an earlier approval.

**G1 — final harness compare (read-only).** From the worktree head (every slice merged; the SHA the apply will run under; a clean tree, so `code_identity` carries no `-dirty`): measure per "Measuring at a checkpoint" with `X=G`, `PREV=tier1-cp-F`. The cand arms are `$H/G-cand-held.json` / `$H/G-cand-all.json`; the lists are in `$H/cmp-G-held/`.

Report: `summary.txt` (the combined clear count replaces every prototype estimate; expect roughly 240–280 minus needs-LLM), the needs-LLM count, the packaged-exposure list, and confirm the per-slice lists from Checkpoints B–F are unchanged where their slices were not touched since.

**G2 — hand-check lists.** Drawn from exactly the shows in `predicted_list.json`: `hand_check_sample.txt`, `closest_calls.txt`, `title_sources.txt` and `structure_changed.txt` (a structure-changed show joins `structure_changed_list.json` only once checked). Before the operator sees them, the orchestrator drops every row already approved at B–F (a mechanical diff: a row whose text appears verbatim in any `$H/approved-[B-F].txt`), then runs the Opus pre-screen (see "Operator time") over what remains, with the B–F rules for each list. The operator reads the flagged rows plus the 20-row sample per list. **Ask:** approval of the lists, and the slugs of any rejected rows. Stop. The orchestrator writes the rejected slugs to `$H/rejected.txt` (one per line) and drops them from every list the apply will read, before G3:

```bash
python3 - "$H/rejected.txt" "$H/cmp-G-held/predicted_list.json" "$H/cmp-G-held/structure_changed_list.json" "$H/cmp-G-held/pilot_list.json" <<'PY'
import json, sys
rejected = {l.strip() for l in open(sys.argv[1]) if l.strip()}
for path in sys.argv[2:]:
    data = json.load(open(path))
    data["rows"] = [r for r in data["rows"] if r["slug"] not in rejected]
    json.dump(data, open(path, "w"), indent=1)
PY
```

(Editing a list changes its bytes and so its batch directory; do it before any apply from that list. `sha` and `config_fingerprint` are untouched, so `load_list` still accepts it.)

**G3 — the same code, the same SHA.** The apply runs from the checkout whose `git rev-parse HEAD` equals `predicted_list.json`'s `sha` (the worktree head, or `main` after a fast-forward merge). If the operator merges first, re-run G1 from `main` so the list carries `main`'s SHA. Config fingerprint must match (`~/.llama/config.toml` unchanged since the harness ran).

**G4 — dry run (writes nothing).**

```bash
./.venv/bin/python -m llama reapply --from-list "$H/cmp-G-held/predicted_list.json" --dry-run
./.venv/bin/python -m llama reapply --from-list "$H/cmp-G-held/pilot_list.json" --dry-run
```

Report the summary line (rows, fresh briefs, first-time downloads and the GB estimate). **Bulk-cost re-ask:** state the exact counts (about 250 fresh Opus briefs and about 175 MB per cleared show on the prototype's numbers; use the dry run's figures) and **ask for a yes before any apply**. Stop.

**G5 — the 10-show pilot** (writes to `~/.llama`; one explicit go-ahead immediately before):

```bash
./.venv/bin/python -m llama reapply --from-list "$H/cmp-G-held/pilot_list.json"
```

Then re-run the harness on those 10 from the worktree (`run --slugs <the 10> --out "$H/pilot-after.json"`) and report per show, against `$H/G-cand-held.json`: predicted vs actual on the gather and vet legs (must be equal), the brief leg (reuse vs fresh, and a reused briefing's guard outcome), package-stage outcomes (duration mismatches, download failures), the meter delta per show (the real per-show cost), and `~/.llama/llm-failures/` unchanged except for any fresh-brief failure. Zero network outside package downloads and zero LLM calls outside fresh briefs are verified by the test suite's pins plus the pilot's log (`grep -c "brief" ...`). Any difference on a `clears` show is a defect to explain before G6. **Ask:** proceed to waves? Stop.

**G6 — waves** (each wave its own go-ahead): `llama reapply --from-list "$H/cmp-G-held/predicted_list.json"` resumes past the pilot's shows automatically (they are no longer held → `skipped: not held`, recorded finished). The pacing gate pauses at a window boundary and prints the resume command; the orchestrator reports at every pause and after every ~50 shows. Then `structure_changed_list.json` (after G2's edit) the same way.

**G7 — post-run harness.** `run --out "$H/post-held.json"` and `run --all --out "$H/post-all.json"`; list every show whose actual flags differ from `$H/G-cand-held.json`'s prediction; any difference on a `clears` show is a defect to explain. Delivered shows that were re-processed (the `re-deliver with` reminders in the apply log) are listed for the operator's `llama deliver`.

---

## Finish

After Checkpoint G (or earlier, if the operator stops at a checkpoint): `superpowers:finishing-a-development-branch`. The integration choice is the operator's; the whole-branch review on Opus is not optional. Before removing the worktree, copy the SDD ledger out of `.superpowers/` (it is gitignored) and keep `$H` (the harness arms are the measurement record; `docs/superpowers/2026-10-19-held-backlog-tier1-evidence.md` summarises the per-checkpoint numbers, written by the orchestrator at finish time).
