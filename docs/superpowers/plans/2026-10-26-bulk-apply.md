# Bulk apply of held-backlog pieces 1-4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tools that bring the existing library up to the pieces 1-4 code without voicing or airing anything on old data: persistent overrules, an `awaiting_fix` mark enforced by llama and emcee, `reapply` extended to every state with strict station audio reuse, and the campaign tooling (backfill, marking, lists, checks, snapshots, trial report, re-voice list).

**Architecture:** Library-side state is a new per-show `campaign.json` (marked / processed / cleared), written under the show lock and never digested. The station-side mark is one raw-JSON key, `awaiting_fix`, written by one llama writer (`llama/station_mark.py`) that marking, the clear command and the reversal share; emcee treats it as a state and refuses to spend on it. `reapply` keeps its replay computation and gains non-held states inside `show_unit`; `build_package` refuses to download audio the station holds. Operator tooling is one script, `scripts/bulk_apply.py`, over importable llama modules; the run itself (backfill, arm, marking, trial, waves, re-delivery) is the runbook in Appendix A, after the release.

**Gate ordering.** Tasks 1-2 overrules; 3-4 the campaign record and llama's view of it; 5-7 the station mark (writer, deliver, clear, emcee); 8-10 re-processing; 11-13 snapshots, gates, batch runner; 14 backfill (CHECKPOINT A); 15 marking (CHECKPOINT B); 16-17 lists and reports; 18 docs and acceptance (CHECKPOINT C). No task writes to `~/.llama` or the station.

**Tech Stack:** Python 3.11+, pydantic v2, typer, pytest; offline tests (`herder` fake backend, `tests/helpers.py` `build_ready`/`reuse_gd73`/`patch_fake_durations`/`stub_stages`, `tests/fixture_library.py` `library_show`/`build_library`, tmp station dirs).

**Spec:** `docs/superpowers/specs/2026-10-25-bulk-apply-design.md` (approved, review mode Opus). Every implementer reads the spec sections their task names, this task, Global Constraints, Contracts and Review Focus. Data (read-only): `~/.llama-harness/piece4/migration-post.json`, `migration-base.json`, `fw1/m3_changed-r1.json`, `~/.llama-harness/t3/verdicts/*.json`.

## Global Constraints

- **Untouched:** junk-filter constants and rule, `package.DURATION_TOLERANCE_S = 5.0`, `audio_reuse`'s pairing rule (index + title + `source.identifier`), `catalog.purge_package_audio`'s verification, every piece-3 fixed constant, `reapply.STOP_AFTER_LLM_FAILURES = 3`, `reapply.load_list`'s sha/fingerprint/`-dirty` gate, `briefing_reusable`. Code-quality review greps the diff for them.
- **llama's `Manifest` model gains no field.** `awaiting_fix` exists only in station manifests, written as raw JSON by `station_mark`; library packages never carry it.
- **New persisted fields, defaulted and permissive:** `Overrides.overrules: list[Overrule] = []`, `ShowNotes.brief: list[str] = []`, `<show>/campaign.json`, `<show>/reuse-anchor.json` (Contracts). Old show dirs read as "no record, no anchor, no overrules".
- **Lock order** run ⊃ show ⊃ ledger, unchanged. Station writes happen under the llama show lock. `process_show` stays lock-free. Nested `file_lock` on one show's `.lock` deadlocks: reapply's writes move into `show_unit`, which takes the lock itself.
- **Never** import emcee from llama or llama from emcee (`test_no_llama_imports.py`); transmitter is untouched.
- **Fixed strings** are in Contracts; tests assert them exactly.
- **Tests** run from the worktree root as `./.venv/bin/python -m pytest …` (CLAUDE.md worktree rule). Each task ends with the full suite green. A task that moves existing expectations does the **dry run** first: list every test whose expectation changes with its spec clause, report it, then edit; an unexplained change is BLOCKED.
- **Never write to `~/.llama` or `/Volumes/media/lma-radio/delivered/`.** Checkpoint dry runs read them; output goes under `~/.llama-harness/bulk/`. No task runs `reapply`, `deliver`, `fix`, `redo`, `clear-mark`, `emcee run/voice`, or any `--apply` against the live library or station.
- One commit per task, with the attribution trailer the orchestrating session specifies. Status reports to the parent list every dispatch since the last report with its model.

## Contracts

**`overrides.json` `overrules`** (Task 1): a list of `{"identifier", "kind", "subject", "flag", "source", "at"}`; `subject` is a list of strings or null; `source` is `fix` | `triage` | `untitled` | `backfill`; `at` UTC ISO-8601.

**Flag kinds** (Task 1, `overrules.flag_key`; first match wins; `norm(s)` = `" ".join(fold_curly_apostrophes(s).casefold().split())`):

| flag text | kind | subject |
|---|---|---|
| `research asserts unknown song: S` | `research-song` | `[norm(S)]` |
| `research asserts wrong date: D` / `research asserts D; item date … looks like a year-only placeholder` | `research-date` | `[D]` |
| `research asserts … sets but structure has …` | `research-sets` | null |
| `low-confidence structure alignment` | `alignment` | null |
| `single-set structure for a long show…` | `single-set` | null |
| `setlist evidence shows multiple sets…` | `sets-not-found` | null |
| `structure has N sets but jerrybase shows M` | `jerrybase-set-count` | null |
| `jerrybase set closer 'X' is not at a set break` (greedy `'(.*)'`) | `jerrybase-closer` | `[norm(X)]` |
| `low-confidence setlist` | `low-confidence-setlist` | null |
| `merged track(s) … span a set break` | `merged-tracks` | null |
| `unresolved track titles` | `titles` | sorted filenames of the show's `unresolved` tracks; matches when the new set ⊆ the recorded one |
| `venue mismatch: archive 'A' vs jerrybase 'B'` | `venue` | `[norm(A), norm(B)]` |
| `recordings of this date disagree on city: 'A' (selected) vs 'B'` | `city` | `[norm(A), norm(B)]` |
| `tape spans …` / `unassigned multi-event recordings` / `multi-event date: …` | `tape-spans` / `events-unassigned` / `multi-event` | null |
| `no playable tracks` | `no-tracks` | null |
| `briefing mentions unknown song: S` / `briefing references nonexistent set: S` | `briefing-song` / `briefing-set` | `[norm(S)]` |
| any other `briefing …` | `briefing-other` | `[re.sub(r"\d+", "N", norm(flag))]` |
| `duration mismatch on …` (package family) | not overrulable (`None`) | |
| anything else | `other` | `[norm(flag)]` |

A rule matches a flag when `rule.identifier == show.identifier`, the kinds are equal, and the subjects are equal (`titles`: subset). Records on another identifier (a re-selected show) are inert, never deleted.

**`<show>/campaign.json`** (Task 3): `{"marks": [{"at", "reason", "start_stage": "gather"|"select", "batch"}], "processed": {"at", "digests", "manifest_sha256": str|null} | null, "clears": [{"at", "outcome": "equal"|"change accepted"}]}`. **Awaiting fix** = `marks` non-empty and (`processed` null or `processed.at` < the last mark's `at`). The start stage is the last mark's.

**`<show>/reuse-anchor.json`** (Task 8): `{"identifier", "tracks": [{"filename", "title"}], "written_at"}`, the pre-commit `show.json` track list.

**Station manifest** (Task 5): top-level `"awaiting_fix": {"reason": "<one line>", "marked_at": "<UTC ISO>"}`; absent or null = not marked.

**`<root>/campaign/`** (Tasks 12-15): `pin.json` `{tag, sha, version, worktree, pinned_at}`; `needs-llm-frozen.json` `{arm_sha, arm_generated_at, slugs}`; `reselections.json` `{written_at, rows: [{slug, stored, pick}]}`; `station-backup/` (`index.json` + `<slug>/manifest.json`); `marking/<id>/` (`inputs.json`, `record.jsonl`, `before/<slug>.json`); `backfill/<stamp>/` (`snapshot/`, `record.jsonl`); `snapshots/<stamp>/`. A reapply batch's snapshot is `<root>/reapply/<hash>/snapshot/`.

**Fixed strings:**
- overrule note (notes.json): `overruled: <flag>`
- marking reasons: `changed by the held-backlog fixes: <fields, comma-joined from files, titles, sets, segues, set_breaks, venue, city, date>`; `replay needs an LLM call: <needs_llm, comma-joined>`; `stored briefing fails today's guard`; `recording re-selection: <stored> -> <pick>`; `newly held by today's checks: <flag kinds, comma-joined in first-seen order from gather_flags, vet_flags, brief_flags; package for a non-overrulable flag>`
- deliver: `refusing to deliver <slug>: awaiting fix (marked <marked_at>: <reason>)` then `  re-process it first: llama reapply <slug> --allow-structure-change` (start `gather`; ` --with-gather-llm` appended when the slug is on the frozen needs-LLM list) or `  re-process it first: llama redo <slug> --from select`; batch line suffix `  (refused: awaiting fix)`; `refusing to replace <slug>: the re-processed show equals the voiced station copy; keep the voicing with: llama clear-mark <slug>`
- campaign record: `<slug>: cannot read campaign.json (<error>); check it by hand`
- mark: `reselections.json predates the arm; re-run: bulk_apply.py reselect-check --write`
- reuse: `<slug>: station copy does not pair: <detail>`; `<slug>: station copy unreadable: <detail>`; details `no copy pairs`, `a different recording`, `<file> has no metadata length`, `<file> failed its length check`, `no delivery_path in config`; hint after either refusal on a by-name command `  if the station copy cannot be fixed: re-run this one show with --allow-download`; with a selector or list `--allow-download takes one named show`
- reapply outcomes (new): `label-only`, `unchanged`, `skipped: processed`, `skipped: re-selection (llama redo <slug> --from select)`
- clear: `mark cleared; the voicing is kept`
- emcee: status reason `awaiting fix from llama: <reason>`; run `skip <slug>: awaiting fix from llama`; voice/run refusal `awaiting fix from llama (<reason>); re-deliver from llama first`; a malformed mark (non-null, no usable `reason`): status reason `awaiting fix from llama`, refusal `awaiting fix from llama; re-deliver from llama first`
- rekey: `refusing to restore: the bulk apply retired this rollback at <at> (<by>); its writes postdate the snapshot: use scripts/bulk_apply.py restore`

## Review Focus

1. **emcee rewrites a station manifest while marking writes it** (emcee takes no lock). Expected: a change before the rename is caught by the byte re-read just before `os.replace` (temp removed, nothing written, retryable refusal); a change after the rename is caught by the post-write re-read (a key other than `awaiting_fix` changed), and the writer puts back what it read only if the file still holds its own bytes; either way the show is reported as not marked. Residual: a write landing between the last byte check and the rename is overwritten undetected (documented limitation); the primary guard is the `emcee_running()` check before each write. Tests: Task 5 `test_write_mark_detects_a_concurrent_rewrite` (before the rename), `test_write_mark_detects_a_rewrite_after_the_rename`.
2. **The station mount drops in the middle of a wave.** Expected: each show refuses retryably with `station copy unreadable`, nothing downloads, and the batch stops after the third in a row, printing its resume command. Test: Task 13 `test_batch_stops_after_three_unreadable_station_copies`.
3. **A delivered show whose fixed track list adds a newly kept short file.** Expected: every file the station holds is copied from it; only the new file downloads; the per-show line reads `audio reused N, downloaded 1`. Test: Task 8 `test_strict_downloads_only_files_the_station_never_held`.
4. **A marked, unvoiced delivered show that comes out of reapply unchanged.** Expected: it is still re-packaged (station audio copied back) so `deliver --fixed` can re-deliver it and clear the mark; it is not a `show.json`-only commit. Test: Task 9 `test_marked_unvoiced_unchanged_show_is_repackaged_for_redelivery`.
5. **A show whose `campaign.json` is unreadable.** Expected: `status` shows it awaiting fix, `deliver` refuses with the campaign-record string, `reapply` fails the row retryably; nothing treats it as "no record". Test: Task 4 `test_unreadable_campaign_record_counts_as_awaiting`.

---

### Task 0: Worktree venv and baseline (orchestrator, once)

- [ ] **Step 0:** The plan and the spec are committed on main before the worktree is cut: `git -C /Users/shawn/projects/llama ls-files --error-unmatch docs/superpowers/plans/2026-10-26-bulk-apply.md docs/superpowers/specs/2026-10-25-bulk-apply-design.md` exits 0 and `git status --porcelain` lists neither; otherwise stop and ask.
- [ ] **Step 1:** `W=/Users/shawn/projects/llama/.claude/worktrees/bulk-apply; git -C /Users/shawn/projects/llama worktree add -b bulk-apply "$W" main && cd "$W" && python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`.
- [ ] **Step 2:** `./.venv/bin/python -c "import llama, emcee; print(llama.__file__, emcee.__file__)"` prints paths under `$W/`.
- [ ] **Step 3:** `./.venv/bin/python -m pytest -q` passes; record the summary line in the SDD ledger as the baseline. `mkdir -p ~/.llama-harness/bulk`.

---

### Task 1: Overrule records and flag normalisation

**Spec:** "Overrules persist" (Matching). **Implementer: Sonnet.**

**Files:** Modify `packages/llama/src/llama/models.py`; Create `packages/llama/src/llama/overrules.py`, `packages/llama/tests/fixtures/arm_flags.json`; Test `packages/llama/tests/test_overrules.py` (new).

**Interfaces:**
- Produces in `models.py`: `class Overrule(BaseModel): identifier: str; kind: str; subject: list[str] | None = None; flag: str; source: str; at: str`; `Overrides.overrules: list[Overrule] = Field(default_factory=list)` (after `encore_after`).
- Produces in `overrules.py`:

```python
NOTE_PREFIX = "overruled: "
class FlagKey(NamedTuple):
    kind: str
    subject: tuple[str, ...] | None
def flag_key(flag: str, show: Show) -> FlagKey | None       # None: not overrulable (package family)
def rule_matches(rule: Overrule, key: FlagKey, identifier: str) -> bool
def split_overruled(flags: list[str], rules: Sequence[Overrule], show: Show
                    ) -> tuple[list[str], list[str]]          # (still holding, notes "overruled: <flag>")
def records_for(flags: list[str], show: Show, *, source: str, at: str) -> list[Overrule]
def merge_rules(existing: Sequence[Overrule], new: Sequence[Overrule]) -> list[Overrule]
    # appends new ones; one with the same (identifier, kind, subject) as an existing rule is dropped
```

- [ ] **Step 1: Build the fixture.** One read-only one-liner writes the sorted unique strings of `flags`, `gather_flags`, `vet_flags`, `brief_flags` and `stored_flags` over every row of `~/.llama-harness/piece4/migration-post.json` and `migration-base.json` to `arm_flags.json` (2,016 strings when written; record count and sha256 in the commit message).
- [ ] **Step 2: Write the failing tests:**
  - `test_every_arm_flag_has_a_kind`: for every fixture string, `flag_key(f, show)` is None exactly when `f.startswith("duration mismatch on ")`, and never has kind `other`.
  - `test_subjects`: `research asserts unknown song: Fixin’ to Die` → `("research-song", ("fixin' to die",))`; `jerrybase set closer 'Knockin' on Heaven's Door' is not at a set break` → subject `("knockin' on heaven's door",)`; the venue example in Contracts → two-item subject; `research asserts 1973-09-17; item date 1973-01-01 looks like a year-only placeholder` → `("research-date", ("1973-09-17",))`; `single-set structure for a long show (155 min)` and `(199 min)` give equal keys.
  - `test_titles_subject_is_a_subset_match`: a rule recorded with unresolved `{a.mp3, b.mp3}` matches a show whose unresolved set is `{a.mp3}` and not one with `{a.mp3, c.mp3}`.
  - `test_another_identifier_never_matches`.
  - `test_split_overruled`: two flags, one matching → `(["unmatched"], ["overruled: matched"])`; order of held flags preserved.
  - `test_records_for_skips_package_flags_and_merge_dedupes`.
  - `test_old_overrides_json_reads_no_overrules` **(pin)** and `test_overrules_round_trip_through_write_artifact`.
- [ ] **Step 3:** Run `./.venv/bin/python -m pytest packages/llama/tests/test_overrules.py -q` → FAIL (ImportError).
- [ ] **Step 4: Implement** per the Contracts table; `fold_curly_apostrophes` comes from `llama.structure`. `overrules.py` must not import `llama.replay` or any stage (gather imports it).
- [ ] **Step 5:** Full suite → PASS. Commit `feat(overrules): overrule records and per-family flag keys`.

---

### Task 2: Overrules take effect and are recorded

**Spec:** "Overrules persist" (Decision). **Implementer: Opus** (gather, vet, brief and the hold-clearing paths).

**Files:** Modify `stages/gather.py` (end of `compute_gather`), `stages/vet_research.py` (`apply_vet`, `run_vet_research`), `stages/brief.py` (`run_brief`), `replay.py` (`compute_legs`), `reapply.py` (fresh brief), `models.py` (`ShowNotes.brief`), `cli.py` (`_clear_hold`, `_edit_overrides`, its callers); Test `test_stage_gather.py`, `test_stage_vet.py`, `test_stage_brief.py`, `test_fix.py`, `test_triage.py`, `test_replay.py`.

**Interfaces:**
- Consumes: Task 1.
- Produces: `apply_vet(vetting, show, *, overrules: Sequence[Overrule] = ()) -> VetOutcome`; `ShowNotes.brief: list[str] = []`; `_clear_hold(show_ws, *, record: str | None = None)` (`record` is the `source` value; None records nothing); `_edit_overrides(..., add_overrules: Sequence[Overrule] = ())`.

- [ ] **Step 1: Write the failing tests:**
  - `test_gather_turns_an_overruled_flag_into_a_note`: a gather fixture that raises `low-confidence structure alignment`, with an `alignment` rule on its identifier → `review_flags == []`, `needs_review is False`, notes contain `overruled: low-confidence structure alignment`; with the rule on another identifier the flag holds.
  - `test_unresolved_titles_overrule_needs_a_subset`: the rule covers the show's unresolved files → note; one more unresolved file → still held.
  - `test_vet_overrule`: a `research-song` rule for `Golden` → `result.flags` lacks it, `VetOutcome.notes` has the note; another song still flags.
  - `test_brief_overrule_goes_to_notes_brief`: a fake brief whose guard reports `briefing mentions unknown song: X` with a matching rule → show not held, `notes.json` `brief == ["overruled: briefing mentions unknown song: X"]`.
  - `test_replay_sees_overrules`: `compute_legs` on a show whose overrides carry the rule reports no flag (the scratch copy carries `overrules`).
  - `test_fix_overrule_records_the_cleared_flags`: `fix <show> --overrule` on a held show with one gather flag and one `duration mismatch on …` flag → `overrides.json` gains exactly one rule (`source == "fix"`), the hold clears as today; `test_triage_overrule_records` (`[o]`, `source == "triage"`); `test_untitled_records_remaining_flags` (`source == "untitled"`).
  - `test_narration_vague_records_nothing` **(pin)**: `fix --narration vague` clears the hold and adds no rule.
  - `test_overrule_survives_a_regather`: after `fix --overrule`, `llama redo <show> --from gather` (stubbed providers) packages the show instead of re-holding it.
  - `test_edit_overrides_preserves_overrules` **(pin)**: `fix --set-venue X` on a show with rules keeps them byte-equal.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.** `compute_gather`: build `show`, then `held, noted = split_overruled(flags, overrides.overrules, show)`, `op_notes += noted`, rebuild `show` with `review_flags=held, needs_review=bool(held)`. `apply_vet`: split its own flags only (kept flags from other stages untouched). `run_vet_research` and `compute_legs` pass `read_overrides(ws).overrules`. `run_brief` and reapply's fresh brief split the guard's `problems` before writing flags and write `ShowNotes.brief` (read-modify-write of `notes.json`). `_clear_hold(show_ws, record=...)`: when `record`, `records_for(show.review_flags, show, source=record, at=now)` merged into `overrides.json` through `_edit_overrides(add_overrules=…)` before the flags are cleared. Callers: `fix --overrule` → `"fix"`, triage `[o]` → `"triage"`, `_untitled_resolution` → `"untitled"`; the two narration-vague callers pass nothing.
- [ ] **Step 4:** Dry run (Global Constraints), then full suite → PASS. Commit `feat(overrules): recorded overrules become notes on every re-gather`.

---

### Task 3: The campaign record and "processed"

**Spec:** "The library side", "Writing a mark" (campaign half). **Implementer: Sonnet.**

**Files:** Create `packages/llama/src/llama/campaign.py`; Modify `workspace.py` (`ShowWorkspace.campaign`, `.reuse_anchor`), `replay.py` (visible-change helpers), `cli.py` (`_redo_show_locked`), `stages/package.py` (`build_package` tail); Test `packages/llama/tests/test_campaign.py` (new), `test_replay.py`.

**Interfaces:**
- Produces in `campaign.py`:

```python
CAMPAIGN_FILE = "campaign.json"
class CampaignUnreadable(LlamaError): ...
class CampaignMark(BaseModel): at: str; reason: str; start_stage: Literal["gather", "select"]; batch: str
class CampaignProcessed(BaseModel): at: str; digests: dict[str, str | None]; manifest_sha256: str | None
class CampaignClear(BaseModel): at: str; outcome: Literal["equal", "change accepted"]
class CampaignRecord(BaseModel):
    marks: list[CampaignMark] = []; processed: CampaignProcessed | None = None; clears: list[CampaignClear] = []
def read_record(ws: ShowWorkspace) -> CampaignRecord | None          # None: no file; CampaignUnreadable otherwise
def awaiting_fix(rec: CampaignRecord | None) -> bool
def last_mark(rec: CampaignRecord | None) -> CampaignMark | None
def add_mark(ws, *, reason: str, start_stage: str, batch: str, at: str) -> None   # durable write
def remove_marks(ws, batch: str) -> int                              # the reversal; count removed
def mark_processed(ws, *, held: bool) -> bool                        # False (nothing written) without a record
def after_package(ws) -> None        # a processed record's manifest_sha256 refreshed from package/manifest.json
def add_clear(ws, outcome: str) -> None
def manifest_sha256(ws) -> str | None
```
- `ShowWorkspace.campaign = dir / "campaign.json"`, `ShowWorkspace.reuse_anchor = dir / "reuse-anchor.json"`; neither is in `show_stage_artifacts` nor in `replay.input_digests`.
- Produces in `replay.py`: `VISIBLE_FIELDS = ("files", "titles", "sets", "segues", "set_breaks", "venue", "city", "date")`; `visible_changes(stored: Show, new: Show) -> list[str]` (filenames compared, so a same-count file swap counts; titles by text only); `row_visible_changes(row: dict, stored: Show) -> list[str]` (arm row: `filenames`, `title_changes` old≠new, `set_changes`, `segue_changes`, `set_breaks`, `venue`, `city`, `date`); `row_label_only(row: dict, stored: Show) -> bool` (no visible change, and a `title_source` or `alignment` change).

- [ ] **Step 1: Write the failing tests:**
  - `test_awaiting_fix_follows_marks_and_processed`: no record → False; one mark → True; processed after it → False; a later mark → True.
  - `test_mark_processed_writes_digests_and_sha`: a packaged show → `manifest_sha256 == sha256(package/manifest.json)`, `digests == input_digests(ws)`; `held=True` → `manifest_sha256 is None`; no record → returns False, writes nothing.
  - `test_redo_from_the_recorded_stage_marks_processed`: a record with start `gather`; `_redo_show` from `gather` (stubbed stages) → processed; from `brief` → still awaiting; start `select` and redo from `gather` → still awaiting; a failing redo → the unit restores `campaign.json` byte-identical.
  - `test_redo_refuses_an_unreadable_record_before_any_stage`: a corrupt `campaign.json` → `CampaignUnreadable`, the stubbed stages and providers record zero calls.
  - `test_package_build_on_processed_show_refreshes_manifest_sha`: processed, then `redo --from package` producing a different manifest → `manifest_sha256` equals the new manifest's.
  - `test_unreadable_record_raises` and `test_record_is_not_an_input_digest` **(pin)**.
  - `test_visible_changes_and_label_only`: a filename swap with equal titles → `["files"]`; a title_source-only change → `[]` and `row_label_only` True; `row_visible_changes` on a `replay_show` row equals `visible_changes` on the same legs.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement.** Writes use `atomic_write_bytes` followed by `catalog._flush_to_disk` on the file. `_redo_show_locked`: `rec = read_record(ws)` BEFORE `process_show` (an unreadable record refuses before any spend); after `process_show` returns, when `rec` and `SHOW_STAGE_ORDER.index(from_stage) <= SHOW_STAGE_ORDER.index(last_mark(rec).start_stage)`, `mark_processed(ws, held=pkg is None)`. `build_package` calls `campaign.after_package(show_ws)` after the manifest write. `mark_processed` imports `input_digests` inside the function (`replay` imports the stages).
- [ ] **Step 4:** Full suite → PASS. Commit `feat(campaign): per-show campaign record, processed on a committed re-gather`.

---

### Task 4: Awaiting fix in `status` and `deliver`

**Spec:** "The library side" (Awaiting fix). **Implementer: Sonnet.**

**Files:** Modify `catalog.py` (`CatalogEntry`, `iter_shows`, `select_shows`), `campaign.py` (`frozen_slugs`), `cli_select.py` (`Selector`, `build_selector`, `selector_active`, `apply_selector`), `cli.py` (`status`, `_deliver_one`, `_deliver_batch`); Test `test_status_cmd.py`, `test_cli_select.py`, `test_deliver_cmd.py`.

**Interfaces:**
- Consumes: Task 3.
- Produces: `CatalogEntry.awaiting_fix: bool = False` (an unreadable record → True); `Selector.awaiting_fix: bool = False`; `build_selector(..., awaiting_fix: bool = False)`; `select_shows(..., awaiting_fix: bool = False)`; `status --awaiting-fix`; status row mark `awaiting-fix`; status JSON key `awaiting_fix`; `class _AwaitingFix(LlamaError)` in `cli.py`; in `campaign.py`, `FROZEN_FILE = "campaign/needs-llm-frozen.json"` and `frozen_slugs(root: Path) -> frozenset[str]` (the file's `slugs`; empty when missing or unreadable). The deliver `reapply` pointer adds ` --with-gather-llm` when the slug is in `frozen_slugs(config.root)`.

- [ ] **Step 1: Write the failing tests:**
  - `test_status_marks_and_selects_awaiting_fix`: two packaged shows, one with an awaiting record → its row carries `[awaiting-fix]`; `--awaiting-fix` lists only it; `--json` has `"awaiting_fix": true`.
  - `test_deliver_refuses_awaiting_fix_by_name`: exit 1, stderr is the deliver awaiting string and the `reapply` pointer; a `select` start prints the `redo --from select` pointer; nothing copied, no ledger row.
  - `test_deliver_pointer_names_with_gather_llm_for_a_frozen_show`: the slug in `<root>/campaign/needs-llm-frozen.json` → the pointer line ends `--allow-structure-change --with-gather-llm`; a corrupt frozen file → the plain pointer.
  - `test_deliver_batch_skips_awaiting_fix`: `deliver --packaged --yes` delivers the other show and prints the awaiting one with `  (refused: awaiting fix)`.
  - `test_processed_show_delivers` **(pin)**.
  - `test_unreadable_campaign_record_counts_as_awaiting` (Review Focus 5): `status` marks it, `deliver` refuses with the campaign-record string.
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement**; in `_deliver_one` the check is the first one under the show lock, before the voiced check. **Step 4:** Full suite → PASS. Commit `feat(cli): awaiting-fix shows in status, refused by deliver`.

---

### Task 5: The station mark writer and deliver over a marked copy

**Spec:** "The `awaiting_fix` contract" (Writing a mark, No concurrent emcee, It clears by re-delivery, the `--replace-voiced` paragraph), "Delivery after the fix" (selector). Strict surfaces 1-2. **Implementer: Opus.**

**Files:** Create `packages/llama/src/llama/station_mark.py`, `packages/llama/src/llama/campaign_gate.py` (`tool_processes` and `ps_lines` only; Task 12 adds the rest); Modify `cli.py` (`_deliver_one`, `_deliver_batch`, `deliver`); Test `packages/llama/tests/test_station_mark.py` (new), `packages/llama/tests/test_campaign_gate.py` (new), `test_deliver_cmd.py`.

**Interfaces:**
- Produces in `station_mark.py`:

```python
MARK_KEY = "awaiting_fix"
COMPARED = ("source.identifier", "show.venue", "show.city", "show.date", "tracks.filename",
            "tracks.duration_sec", "tracks.title", "tracks.set", "tracks.segue", "set_breaks")
class StationRefused(LlamaError): ...
class StationUnreadable(StationRefused): ...   # text "<slug>: station copy unreadable: <detail>"; the ONE
                                               # "unreadable" exception (Task 8 raises it, Task 13 counts it)
def read_station_manifest(out: Path) -> tuple[bytes, dict]   # StationUnreadable: dir or file missing, OSError, invalid JSON, not an object
def mark_of(manifest: dict) -> dict | None
def destination_voiced(out: Path) -> bool                    # StationUnreadable: dir or manifest missing or unreadable; call it for delivered shows only
def write_mark(out: Path, *, reason: str, marked_at: str) -> tuple[bytes, bytes]   # (before, after)
def clear_mark(out: Path) -> tuple[bytes, bytes]
def put_back(out: Path, *, expect_sha256: str, data: bytes) -> None   # the reversal: replace only when the file's sha256 equals expect_sha256
def manifest_differences(library: dict, station: dict) -> list[str]   # the COMPARED names that differ, raw JSON values
def emcee_running() -> list[str]   # campaign_gate.tool_processes(campaign_gate.ps_lines(), "emcee", self_pid=os.getpid())
```
- Produces in `campaign_gate.py`: `ps_lines() -> list[str]` (`ps -axo pid=,ppid=,command=`) and `tool_processes(ps_lines: Iterable[str], tool: str, *, self_pid: int) -> list[str]`, ported from `scripts/rekey_overrides.py` `llama_processes`/`_runs_llama` with the tool name a parameter (`self_pid` and its ancestors never match). The script is not changed here.
- The rewrite algorithm (spec, pinned): the caller holds the llama show lock; re-read the raw bytes and dict; add or remove only `MARK_KEY` (key order otherwise preserved; trailing newline kept as the original had it; `json.dumps(…, indent=2)`); write a unique temp in the same directory and flush it (`catalog._flush_to_disk`); re-read the station file's bytes immediately before the rename and, when they differ from the bytes read, remove the temp and raise `StationRefused` (retryable, nothing written); `os.replace`; re-read and require every other key equal to the dict read and `MARK_KEY` equal to what was written. On a mismatch after the rename: when the file still holds the bytes this call wrote, write `before` back; raise `StationRefused`. Never `Manifest`; `tracks`, `dj_notes`, `dj_audio` untouched by construction. A write landing between the last byte check and the rename is overwritten undetected (documented limitation, Review Focus 1); the per-write `emcee_running()` check is the primary guard.
- `deliver`: a destination whose manifest `mark_of(...)` is non-null always goes through `_replace_destination`; `--replace-voiced` on a marked destination whose `manifest_differences(library, station) == []` refuses with the fixed string; `deliver --fixed` (selector) keeps only shows that are not awaiting fix, whose record is processed, and whose station manifest is marked; it combines with the other selectors and refuses `--replace-voiced` like them.

- [ ] **Step 1: Write the failing tests** (`test_station_mark.py`, fixture station dirs under `tmp_path`):
  - `test_write_mark_adds_only_the_key`: every other key equal, `tracks` byte-for-byte in the re-read dict, `dj_audio` untouched, mtime changed; `clear_mark` returns a dict equal to the original.
  - `test_unreadable_or_malformed_manifest_is_refused_and_untouched` (missing file, missing dir, invalid JSON, a JSON list): `StationUnreadable` with the fixed text, bytes unchanged; `destination_voiced` on a missing dir or a dir without a manifest raises `StationUnreadable`.
  - `test_write_mark_detects_a_concurrent_rewrite` (Review Focus 1): monkeypatch the temp flush so another writer changes `dj_audio` after the read and before the rename → `StationRefused`, the file holds the other writer's bytes, no temp left in the directory.
  - `test_write_mark_detects_a_rewrite_after_the_rename`: monkeypatch `os.replace` so another writer changes `dj_audio` right after the rename → `StationRefused`, and the file holds the other writer's content (never `before` over it).
  - `test_put_back_requires_the_expected_sha`.
  - `test_manifest_differences`: equal manifests (differing only in `dj_*`, `awaiting_fix`, `briefing`) → `[]`; a moved set label → `["tracks.set"]`; a changed duration → `["tracks.duration_sec"]`.
  - `test_tool_processes` (`test_campaign_gate.py`): rekey's `llama_processes` cases re-run with `tool="llama"`; for `tool="emcee"`, `emcee run`, `/path/.venv/bin/emcee voice x`, `python -m emcee` match, `grep emcee`, `vim emcee.toml` and the caller's own pid and ancestors do not.
  - `test_emcee_running_reads_ps` (monkeypatched `ps_lines`).
- [ ] **Step 2:** Deliver tests (`test_deliver_cmd.py`): `test_marked_destination_is_always_replaced` (same track list, unvoiced, marked → the staged swap runs, the mark is gone, no `.old-*` left); `test_replace_voiced_refuses_an_equal_marked_copy`; `test_replace_voiced_replaces_a_changed_marked_copy` **(pin)**; `test_deliver_fixed_selects_marked_and_processed` (also a voiced, marked, processed show: the `--fixed` batch refuses it, its station manifest bytes and `dj_audio` unchanged); `test_unmarked_voiced_destination_keeps_todays_route` **(pin)**.
- [ ] **Step 3:** Run → FAIL. **Step 4: Implement.** **Step 5:** Full suite → PASS. Commit `feat(station): awaiting_fix writer; deliver replaces a marked copy, --fixed selector`.

---

### Task 6: `llama clear-mark`

**Spec:** "Clearing without re-delivery…" (all bullets). Strict surfaces 1, 3. **Implementer: Opus.**

**Files:** Modify `cli.py` (new command `clear-mark`); Test `packages/llama/tests/test_clear_mark.py` (new).

**Interfaces:**
- Consumes: Tasks 3, 5; `catalog.purge_package_audio`.
- Produces: `llama clear-mark <name> [--accept-change]` (panel "Fix & ship"). Under the show lock, in order, each refusal exiting 1 and writing nothing: station copy unreadable (`StationUnreadable` text); not marked (`<slug>: the station copy is not marked; nothing to clear`); unvoiced (`<slug>: unvoiced destination; re-deliver it instead: llama deliver <slug>`); not processed since the last mark (`<slug>: awaiting fix; re-process it first`); held (`<slug>: held for review`); library manifest sha ≠ record's (`<slug>: the library package changed since it was processed; re-process it`); differences without `--accept-change` (`<slug>: the station copy differs: <names>; pass --accept-change if the change is cosmetic`); `emcee_running()` non-empty (`refusing: emcee is running`). Then `clear_mark`, `add_clear(ws, "equal" | "change accepted")`, print `mark cleared; the voicing is kept` (plus `change accepted: <names>`), and purge: equal → `purge_package_audio(ws, out)` with deliver's three messages; accepted → `library audio kept (track lists differ)` when the purge skips.

- [ ] **Step 1: Write the failing tests:** one per refusal above (asserting the exact string and the station bytes unchanged); `test_equal_clears_and_purges` (station mark gone, `dj_audio` and audio files untouched, library `package/audio/` emptied, record `clears[-1].outcome == "equal"`); `test_accept_change_clears_and_keeps_library_audio`; `test_processed_then_overruled_still_clears` (Task 3's sha refresh: a `redo --from package` after processing still qualifies).
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(cli): clear-mark keeps a voicing when the re-processed show is unchanged`.

---

### Task 7: emcee honours `awaiting_fix`

**Spec:** "The `awaiting_fix` contract" (emcee). **Implementer: Sonnet.**

**Files:** Modify `packages/emcee/src/emcee/station.py` (`PackageStatus`, `package_status`), `cli.py` (`_STATUS_STATES`, `_echo_status_summary`, `run`, `_process_one`, `_status_json_row`); Test `packages/emcee/tests/test_station.py`, `test_status_cmd.py`, `test_run_cmd.py`, `test_voice_cmd.py`, `test_package_io.py`.

**Interfaces:**
- Produces: `station.AWAITING = "awaiting-fix"`; `station.awaiting_fix_reason(manifest: object) -> str | None`, mirroring transmitter's `awaiting_fix_reason` (None when absent or null; `awaiting fix from llama: <reason>` with the reason whitespace-collapsed and cut at 200 characters; plain `awaiting fix from llama` for any other non-null value, a string, list, number, bool or a dict without a usable `reason`; never raises); `PackageStatus.awaiting_fix: str | None = None` (that line); `package_status` returns `state == AWAITING` with reasons `[awaiting_fix_reason(manifest)]` whenever it is non-null (before the readiness legs decide ready/pending), keeping every `identity()` field (`voiced_by`, `tts`, profile fields) so the JSON row's `voiced_by`, `tts` and `tts_now` are filled as for any other state; `_STATUS_STATES` gains it; the summary gains an `awaiting fix` column (per profile and total); status JSON rows gain `"awaiting_fix"` (the line or null); `run` prints `skip <slug>: awaiting fix from llama` and does not count it as a failure; `_process_one` re-reads the manifest first and raises `EmceeError("awaiting fix from llama (<reason>); re-deliver from llama first")` (malformed mark: `awaiting fix from llama; re-deliver from llama first`) before `resolve_voicing`, preflight and any spend.

- [ ] **Step 1: Write the failing tests:** `test_marked_package_is_awaiting_fix` (a ready package plus the key → state `awaiting-fix`); `test_malformed_mark_is_awaiting_fix_without_raising` (`"awaiting_fix": "yes"` → state `awaiting-fix`, reason `awaiting fix from llama`; `voice` refuses with the malformed-mark string); `test_marked_voiced_package_json_row_keeps_identity` (a voiced package with a `tts` record plus the key → `--json` row has state `awaiting-fix` and non-null `voiced_by`, `tts`, `tts_now`); `test_summary_counts_awaiting_fix_per_profile`; `test_status_state_filter_accepts_awaiting_fix`; `test_run_skips_a_marked_package_and_spends_nothing` (fake TTS and LLM record zero calls; exit 0 when nothing else failed); `test_voice_refuses_a_marked_package_before_preflight` (the preflight stub is never called; exit 1; the manifest is byte-unchanged); `test_process_one_rereads_the_manifest` (a mark written after `run`'s scan but before `_process_one` refuses); `test_rewrite_manifest_preserves_awaiting_fix` **(pin)**.
- [ ] **Step 2:** Run `./.venv/bin/python -m pytest packages/emcee/tests -q` → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(emcee): awaiting-fix packages are a state, skipped by run, refused by voice`.

---

### Task 8: Strict station reuse and the held-outcome anchor

**Spec:** "Re-processing" (Audio reuse never silently falls back; Held outcomes keep a reuse anchor). Strict surface 5. **Implementer: Opus.**

**Files:** Modify `audio_reuse.py`, `stages/package.py` (`build_package`), `cli.py` (`_redo_show_locked`, `redo`, `fix`); Test `test_audio_reuse.py`, `test_redo_cmd.py`, `test_fix.py`; the dry run also reads `test_deliver_cmd.py` and `test_purge_audio.py`, which pin today's purged-show re-download route.

**Interfaces:**
- Consumes: Task 5 (`station_mark.StationUnreadable`, the one "unreadable" exception, raised here; no second class).
- Produces in `audio_reuse.py`:

```python
ANCHOR = "reuse-anchor.json"
class StationUnpaired(LlamaError): ...       # text "<slug>: station copy does not pair: <detail>"
@dataclass(frozen=True)
class ReusePlan:   # existing fields, plus
    strict: bool = False
    station_problem: str | None = None       # strict only: why the station copy cannot be read
def plan_reuse(show_ws, station_dir: Path | None, *, strict: bool = False) -> ReusePlan
    # station pairing: against show.json first; when that pairs nothing, against the anchor
    # (when the anchor's identifier equals the station manifest's source.identifier).
    # library pairing: against the library manifest first; when that pairs nothing and the
    # anchor's identifier equals show.json's, the anchor's track i (1-based) pairs its filename
    # with audio.packaged_filename(i, title, Path(filename).suffix) when that file is in
    # package/audio/ (a packaged show held by the apply, cleared later, reuses its own audio)
def check_pairs(plan: ReusePlan, show_ws) -> None
    # strict only: StationUnreadable(station_problem); StationUnpaired("no copy pairs") when
    # plan.station is empty and no plan.library file exists in package/audio/
def write_anchor_if_absent(show_ws) -> bool
def drop_anchor(show_ws) -> None
```
- `plan_reuse(strict=True)` with `station_dir is None` (`config.delivery_path` unset) sets `station_problem = "no delivery_path in config"`, so a delivered show refuses as unreadable.
- `build_package(..., tally: dict[str, int] | None = None)`: when `reuse.strict`, call `check_pairs` first; an identifier mismatch raises `StationUnpaired("a different recording")`; a source paired in the plan-time `library` or `station` map whose cached metadata has no length raises `StationUnpaired(f"{filename} has no metadata length")`, and one whose copy is not placed raises `StationUnpaired(f"{filename} failed its length check")`, instead of downloading; an unpaired source downloads. It increments `tally["reused"]`/`tally["downloaded"]`, logs one `detail(f"audio reused {r}, downloaded {d}")` line, and after the manifest write calls `drop_anchor` (then `campaign.after_package`, Task 3).
- `_redo_show_locked(..., allow_download: bool = False)`: `strict = <show delivered in the ledger> and from_stage != "select" and not allow_download`; before `drop_stage_artifacts`, `write_anchor_if_absent(show_ws)` when `package/manifest.json` exists or the show is delivered; `plan_reuse(..., strict=strict)`.
- `--allow-download` on `llama redo <name>` and `llama fix <name>` (by name only; with any batch selector it refuses before any write: `--allow-download takes one named show`): that one show's re-package is not strict, so it downloads whatever does not pair (today's route), for a delivered show whose station copy is gone or permanently unpaired. The CLI prints after either strict refusal the fixed hint line (Contracts).

- [ ] **Step 1: Dry run.** List the existing tests that expect a delivered show's `redo --from package` to re-download purged audio (CLAUDE.md's old route); each changes under the spec clause "Audio reuse never silently falls back".
- [ ] **Step 2: Write the failing tests:**
  - `test_strict_downloads_only_files_the_station_never_held` (Review Focus 3): delivered show, station copy pairs, the new list adds one unpaired file → `ia.download_file` called once (that file), `tally == {"reused": n, "downloaded": 1}`.
  - `test_strict_refuses_a_paired_copy_failing_its_length_check` (no download; the unit restores).
  - `test_strict_refuses_when_nothing_pairs` and `test_strict_refuses_a_missing_or_unreadable_station_copy` (exact strings; the unreadable case raises `station_mark.StationUnreadable`; each followed by the `--allow-download` hint line).
  - `test_strict_refuses_a_source_with_no_metadata_length` (`<file> has no metadata length`, no download) and `test_strict_refuses_without_a_delivery_path` (`config.delivery_path = None`, delivered show → `StationUnreadable`, detail `no delivery_path in config`).
  - `test_anchor_pairs_after_a_held_commit`: write the anchor, replace `show.json` with a retitled list (station no longer pairs with it), drop the library manifest → `plan_reuse` pairs the station through the anchor; a later package build removes the anchor.
  - `test_anchor_pairs_library_audio_of_a_packaged_show`: undelivered packaged show; write the anchor, replace `show.json` with a retitled list, drop the library manifest, leave `package/audio/` → `plan_reuse.library` maps every anchor filename to `packaged_filename(i, anchor title, ext)`; the package build reuses them with zero downloads and removes the anchor.
  - `test_allow_download_lets_one_named_show_download`: delivered show, station dir gone → `redo <slug> --from package --allow-download` downloads and packages; the same on `fix <slug> --set-venue X --allow-download`. `test_allow_download_refuses_a_selector`: `redo --held --from package --allow-download` exits 1 with the fixed string, nothing written.
  - `test_anchor_is_written_once`: a second `write_anchor_if_absent` leaves the first anchor byte-identical.
  - `test_reselection_redo_is_not_strict` **(pin)**: `redo --from select` on a delivered show downloads.
  - `test_undelivered_reuse_unchanged` **(pin)**.
- [ ] **Step 3:** Run → FAIL. **Step 4: Implement.** **Step 5:** Full suite → PASS. Commit `feat(reuse): strict station reuse for delivered shows, held-outcome anchor`.

---

### Task 9: `reapply` for packaged, briefed and delivered shows

**Spec:** "Re-processing" (reapply extended; purge; anchor; structure gate), "Known constraints" (show_unit), "The library side" (processed, skips). Strict surface 4. **Implementer: Opus.**

**Files:** Modify `reapply.py` (`reapply_show`, `ReapplyOutcome`), `cli.py` (`reapply` names form output, `--allow-download`); Test `test_reapply.py`.

**Interfaces:**
- Consumes: Tasks 2, 3, 5 (`destination_voiced`, `StationUnreadable`), 8.
- Produces: `ReapplyOutcome` gains `kind: str = "none"` (`fresh` | `reuse` | `needs-llm` | `label-only` | `none`), `audio: dict[str, int] = field(default_factory=dict)`, `align_reproduced: bool | None = None`. `reapply_show(..., with_gather_llm: bool = False, allow_download: bool = False, after_commit: Callable[[ShowWorkspace], None] | None = None)` (`with_gather_llm` is wired in Task 10; `after_commit` is Task 13's `record_after` hook). `llama reapply <name>... --allow-download` on the names form only (`--from-list` with it refuses: `--allow-download takes one named show`); it makes that show's reuse non-strict, as on `redo`/`fix` (Task 8); the names form prints the `--allow-download` hint line after a strict refusal.
- Flow (the order is the contract):
  1. Writes run inside `show_unit(ws, None)`; a dry run takes only `file_lock`. reapply's own audio/manifest undo and its `discard_aside`/`put_back` calls go (the unit does both).
  2. `rec = campaign.read_record(ws)` (`CampaignUnreadable` propagates). A last mark with start `select` → the re-selection skip string. For a non-held show only, a record that is not awaiting and has `processed` → `skipped: processed` (held shows keep today's behaviour). Then the existing digest check.
  3. Held shows keep today's `classify` path and outcomes.
  4. Non-held: `flags` → held commit (today's held writes, `drop:brief` rule included). No flags, no `visible_changes`, `legs.brief == "reuse"`, and NOT (the record is awaiting and the show is delivered and `destination_voiced(...) is False`) → `show.json`-only commit, outcome `label-only` when `shipped_diff` has any value else `unchanged`. Otherwise → brief (reuse or fresh) and package → `cleared`. Every station read before the commit (`destination_voiced`, the pairing check) raises `station_mark.StationUnreadable` for a missing or unreadable station dir or manifest; the voiced rider's purge after the commit keeps `purge_package_audio`'s own skip-and-warn.
  5. The structure gate (`_structure_changed(shipped_diff)` without `allow_structure_change` → `skipped: structure changed`) applies to every state.
  6. A delivered show that will package: `plan_reuse(..., strict=not allow_download)` and `check_pairs` BEFORE the fresh brief (in gather-LLM mode, before the recompute: Task 10).
  7. The first write of a packaged or delivered show is `write_anchor_if_absent`. `show.json` stays the commit marker; after it, `campaign.mark_processed(ws, held=bool(flags))`; then, for a cleared delivered show whose destination is voiced, `purge_package_audio(ws, station)` and an echo of its result; then `after_commit(ws)` when given, still inside the unit (a failure there restores the unit). `echo(f"{slug}: audio reused {r}, downloaded {d}")` after a package.
- [ ] **Step 1: Dry run** (existing tests asserting `skipped: not held` on a packaged show change under "reapply extended").
- [ ] **Step 2: Write the failing tests:**
  - `test_reapply_repackages_a_changed_delivered_show_from_the_station`: delivered unvoiced, changed title, fresh brief (fake) → `cleared`, audio copied from the station, no download, record processed with the new manifest's sha, anchor gone.
  - `test_label_only_commits_show_json_only`: no brief call, no package write, `package/manifest.json` byte-identical, outcome `label-only`.
  - `test_marked_unvoiced_unchanged_show_is_repackaged_for_redelivery` (Review Focus 4).
  - `test_voiced_unchanged_show_commits_show_json_only_and_clear_mark_then_works`.
  - `test_voiced_rider_purges_when_tracks_equal`: a cleared delivered show with a voiced destination whose tracks equal the station's → library audio emptied; tracks differ → kept.
  - `test_newly_held_delivered_show_keeps_an_anchor`: held commit, anchor present, `drop:brief` in `written`; a later `fix --overrule` re-packages from the station through the anchor.
  - `test_processed_and_reselection_rows_are_skipped`; `test_processed_held_show_is_not_skipped` (a held show with a processed record takes today's held path).
  - `test_after_commit_runs_inside_the_unit`: the hook sees the committed `show.json` while the show lock is held; a hook that raises restores every file and the outcome is a failure.
  - `test_reapply_allow_download_by_name_only`: a delivered show with no station dir → names form with `--allow-download` downloads and clears; `--from-list` with it exits 1 with the fixed string.
  - `test_failure_restores_every_file`: a package failure after the brief → every file outside `package/audio/` byte-identical (incl. `campaign.json`, no anchor), added audio gone.
  - `test_station_check_runs_before_the_brief`: unpaired delivered show → `StationUnpaired`, the fake brief provider has zero calls.
  - `test_held_show_behaviour_unchanged` **(pin)**: the existing held-path tests pass untouched apart from the dry-run list.
- [ ] **Step 3:** Run → FAIL. **Step 4: Implement.** **Step 5:** Full suite → PASS. Commit `feat(reapply): every state, inside show_unit, strict reuse, processed`.

---

### Task 10: `reapply` with gather's LLM touchpoints

**Spec:** "Re-processing" (Shows whose replay needs an LLM call), "The trial" (reproduction rate). **Implementer: Sonnet.**

**Files:** Modify `gather.py` (`compute_gather`), `replay.py` (`compute_legs`), `reapply.py`, `cli.py` (`reapply --with-gather-llm`); Test `test_gather.py`, `test_replay.py`, `test_reapply.py`.

**Interfaces:**
- Produces: `compute_legs(..., gather_providers: tuple[object, object] | None = None)` — `(extract_setlist provider, align_structure provider)` passed to `compute_gather`; when given, the `stored alignment llm` verdict is not appended (the alignment is computed fresh). `GATHER_LLM = frozenset({"extract_setlist", "align_structure", "stored alignment llm"})`. In `reapply_show`, when `legs.needs_llm` is non-empty, `with_gather_llm` and `set(legs.needs_llm) <= GATHER_LLM`: for a delivered show first run the strict `plan_reuse`/`check_pairs` (Task 9 step 6; its outcome is not known yet, so every delivered show is checked), so an unpaired or unreadable show spends no align call; then recompute the legs with `(providers["extract_setlist"], providers["align_structure"])` and `llm_failures_raise=True`, before any write, and continue as Task 9 with `kind = "needs-llm"`; `no vetting.json` stays `needs-llm`. `compute_gather(..., llm_failures_raise: bool = False)`: when True, a `TaskFailed`/`HerderError` from the `extract_setlist` or `align_structure` call (including herder's validation `TaskFailed`, raised above the provider) re-raises instead of degrading to `low-confidence structure alignment` and a held commit; the default keeps today's behaviour for every other caller (pin: `test_compute_gather_degrades_llm_failure_by_default`, `test_compute_gather_llm_failures_raise`). `compute_legs` passes it through. The exception escapes `reapply_show` before any write, so the list runner's `except (TaskFailed, HerderError)` arm records a retryable row failure counted toward `STOP_AFTER_LLM_FAILURES`. `RateLimited` passes through untouched (gather re-raises it; today's pause path). `align_reproduced` = the stored and new shows have equal filenames, set labels, segues and `set_breaks`, set only when the stored alignment was `llm` or `align_structure` was called. A dry run never calls an LLM (`dry-run: needs-llm`). `llama reapply --with-gather-llm` on both forms.
- [ ] **Step 1: Write the failing tests:** `test_needs_llm_show_is_reapplied_with_gather_llm` (fake align response; outcome `cleared`, kind `needs-llm`); `test_no_vetting_json_stays_needs_llm`; `test_without_the_flag_needs_llm_writes_nothing` **(pin)**; `test_align_reproduced_true_and_false`; `test_refusal_on_the_align_call_writes_nothing`; `test_dry_run_makes_no_llm_call`; `test_with_gather_llm_align_failure_is_a_retryable_row_failure` (the fake align provider raises `HerderError`: no commit, no `processed`, the row recorded retryable and counted; three such rows in a row stop the batch with today's LLM-failure line); `test_unpaired_delivered_show_spends_no_align_call` (station unpaired → `StationUnpaired`, the fake align provider has zero calls).
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(reapply): --with-gather-llm for shows whose replay needs an LLM call`.

---

### Task 11: Per-batch snapshots and restore

**Spec:** "Undo". Strict surface 4. **Implementer: Opus.**

**Files:** Create `packages/llama/src/llama/batch_snapshot.py`; Test `packages/llama/tests/test_batch_snapshot.py` (new).

**Interfaces:**

```python
def take(snap: Path, root: Path, slugs: list[str], *, station_root: Path | None) -> None
    # per slug under its show lock: copy every file outside package/audio/, .audio-aside/, .txn/
    # and the top-level .lock to snap/shows/<slug>/<rel>, sha256-verified and flushed; record the
    # station manifest's sha256 (None: no station copy); manifest.json written last
    # {created_at, slugs, files: {"<slug>/<rel>": sha}, station: {slug: sha|None}}; any failure
    # removes the partial directory and raises LlamaError
def verify(snap: Path) -> list[str]                           # [] = verifies
def record_after(snap: Path, slug: str, root: Path, *, station_root: Path | None) -> None
    # append {slug, files: {rel: sha}, station: sha|None, at} to snap/after.jsonl; takes no lock:
    # the caller holds the show lock (reapply's after_commit hook, the backfill's per-show unit)
def restore(snap: Path, root: Path, *, station_root: Path | None, apply: bool,
            slugs: set[str] | None = None, echo) -> list[tuple[str, str]]   # (slug, action or refusal)
def seal(snap: Path, root: Path, *, station_root: Path | None) -> None    # per slug, under its show lock: record_after
```
- `restore`, per slug, under its show lock: no after-record → `untouched` when files and station equal the snapshot, else refuse `changed, and this batch recorded no write for it`. With an after-record: files ≠ after → refuse `library files changed after the batch: <first rel>`; station sha ≠ after → refuse `station manifest changed after the batch (re-delivered or re-voiced): roll forward instead`. Else: when the snapshot's `package/manifest.json` bytes differ from the current file, empty `package/audio/` first (flushed); delete tracked files absent from the snapshot; write the snapshot's files back atomically. Without `apply` it only reports. It never writes the station.
- [ ] **Step 1: Write the failing tests:** `test_take_copies_metadata_only_and_verifies` (audio excluded, `campaign.json` and `reuse-anchor.json` included; a tampered copy fails `verify`); `test_partial_snapshot_is_removed_on_failure`; `test_restore_rewinds_a_batch_write` (after a reapply-style rewrite + `record_after` → files byte-identical to the snapshot, created files gone, audio emptied because the manifest differs); `test_restore_refuses_a_later_library_change`; `test_restore_refuses_a_changed_station_manifest`; `test_restore_dry_run_writes_nothing`; `test_untouched_show_is_left_alone`.
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement** (port the copy/flush/verify pattern of `scripts/rekey_overrides.py` `_write_copy`/`_sync_dir`/`verify_snapshot`; do not import the script or change it here). **Step 4:** Full suite → PASS. Commit `feat(snapshot): per-batch library snapshots with a guarded restore`.

---

### Task 12: Campaign gates, the pin, `bulk_apply.py` scaffold, rekey retirement

**Spec:** "Rollout" (version gate), "Known constraints" (pinned worktree, newer-installed refusal), "Undo" (rekey retired). **Implementer: Sonnet.**

**Files:** Create `scripts/bulk_apply.py`; Modify `packages/llama/src/llama/campaign_gate.py` (Task 5 created it with `tool_processes`/`ps_lines`), `scripts/rekey_overrides.py` (`_record_gate`); Test `packages/llama/tests/test_campaign_gate.py`, `scripts/test_bulk_apply_scaffold.py` (new), `scripts/test_rekey_overrides.py`.

**Interfaces:**
- Consumes: Task 5 (`campaign_gate.tool_processes`, `ps_lines`: the one process parser; no second one here).
- Produces in `campaign_gate.py` (beside Task 5's two functions):

```python
CAMPAIGN_MIN_VERSION = "2.19.0"       # the release this build ships in; confirm at release
class GateRefused(LlamaError): ...
def version_ok(text: str, minimum: str) -> bool        # rekey's rule, parameterised
def version_newer(text: str, than: str) -> bool
def tool_versions(tool: str) -> list[tuple[str, str]]  # `which -a <tool>` then `<path> --version`
def require_tools(echo, *, pin: dict | None) -> None
    # every llama and emcee on PATH >= CAMPAIGN_MIN_VERSION, and (with pin) no llama newer than pin["version"]
def read_pin(root: Path) -> dict | None
def write_pin(root: Path, *, tag: str, sha: str, version: str, worktree: str, replace: bool) -> dict
def require_pinned_code(root: Path) -> dict            # pin exists; replay.code_identity() == pin["sha"] (never -dirty)
def retire_rekey_restore(root: Path, *, by: str, at: str) -> bool
    # adds "retired": {at, by} to <root>/rekey-applied.json, durably; idempotent: True only when it
    # wrote, False when the file is absent or already retired (the first `retired` stays)
```
- `scripts/bulk_apply.py` (argparse, subcommands; exit 2 on a `GateRefused`/refusal, like `replay_holds.py`): `pin --tag vX.Y.Z [--replace]` (resolves `git rev-parse <tag>^{commit}`, requires it equal `code_identity()`); `arm --out <arm.json>` (`require_pinned_code` + `require_tools(pin=…)`, then `replay_holds.run` with `--all`); `snapshot --slugs <file>` → `<root>/campaign/snapshots/<stamp>/`; `seal <snap>`; `restore <snap> [--apply] [--slugs <file>]`. Later tasks add subcommands to this file.
- `rekey_overrides._record_gate` refuses with the rekey fixed string when the record has `retired`.
- `retire_rekey_restore` is called by whichever bulk write comes first, and harmlessly by every later one: backfill `--apply` (Task 14), `mark --apply` (Task 15), and a campaign list wave (Task 13).

- [ ] **Step 1: Write the failing tests:** `test_version_gate` (`2.19.0` ok, `2.18.0`/`0.1.0`/`2.19.0rc1` refused, for both tools; a pin of `2.19.0` and an installed `2.20.0` refused naming the path); `test_pin_requires_the_running_code` (a dirty tree and a mismatched tag refused; `--replace` needed to overwrite); `test_arm_refuses_without_a_pin`; `test_restore_cli_dry_run_reports`; `test_retired_record_refuses_restore` (scripts test: `_record_gate` raises with the fixed string; the rest of rekey's tests unchanged); `test_retire_is_idempotent` (a second call returns False and leaves `rekey-applied.json` byte-identical; absent file → False, nothing created).
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(campaign): version and pin gates, bulk_apply scaffold, rekey restore retired`.

---

### Task 13: The batch runner: snapshot, ceiling, trial stop, records

**Spec:** "Pacing, ordering and resumability", "The trial" (blocks), "Undo" (wave snapshot), "Re-processing" (stop after 3 unreadable). **Implementer: Sonnet.**

**Files:** Modify `cli.py` (`reapply`, `_reapply_list`), `reapply.py` (`record_progress`), `pacing.py` (`pace_options`); Test `test_reapply.py` (list form), `test_pacing.py`.

**Interfaces:**
- Consumes: Tasks 9-12.
- Produces: `pace_options(config, wait=None, max_wait=None, no_pacing=False, *, seven_day_ceiling: float | None = None)`; `record_progress(batch, slug, outcome, retryable, extra: dict | None = None)` (extra keys merged into the row); `reapply --from-list` options `--seven-day-ceiling PCT`, `--stop-at-points N` (`--with-gather-llm` on both forms is Task 10's); `STOP_AFTER_STATION_UNREADABLE = 3` in `reapply.py`.
- Behaviour: a list doc carrying `"campaign": {"version", "pin_sha"}` runs `campaign_gate.require_tools(pin=…)` first. A non-dry run whose batch has no `progress.jsonl` and no `snapshot/` takes `batch_snapshot.take` over the list's existing show dirs before the first show; a batch with progress but no snapshot prints `warning: no snapshot for this batch (started before snapshots)` and goes on. A campaign list's non-dry run then calls `retire_rekey_restore(by="bulk-apply wave <batch hash>")` before the first show (idempotent, Task 12). Every writing outcome (`cleared`, `held`, `label-only`, `unchanged`) is followed by `record_after`, called inside the show lock through `reapply_show(..., after_commit=…)` (Task 9), never after the unit returns. Progress rows carry `kind`, `meter: {"before": m, "after": m}` (each `{"five_hour": pct|null, "five_hour_resets": iso|null, "seven_day": pct|null, "seven_day_resets": iso|null}`), `audio`, `align_reproduced`. `station_mark.StationUnreadable` (the only exception counted here; it subclasses `StationRefused`/`LlamaError`) is caught above `LlamaError`: a retryable failure that increments a streak reset by any writing outcome; at 3 it prints `stopping after 3 consecutive unreadable station copies (is the station mounted?); <resume line>` and exits 1. `StationUnpaired` and any other `StationRefused` are ordinary retryable failures. **Retryability per outcome:** retryable: `needs-llm` (a row run without `--with-gather-llm`), station refusals (`StationUnpaired`, `StationUnreadable`, `StationRefused`), LLM failures (as today), `skipped: structure changed` (as today); not retryable: `skipped: processed`, `skipped: re-selection …`, and the committed outcomes `cleared`, `held`, `label-only`, `unchanged`; every other outcome keeps today's rule. `--stop-at-points N`: the block starts at the first `before` reading; after a show whose `after` reading has the same `five_hour_resets` and moved ≥ N points it prints `trial block done: 5h meter moved <d> points over <n> shows` and the resume line, exit 0; a show whose `after` reset differs prints `warning: this block crossed a 5-hour reset; discard it and re-run` and goes on.
- [ ] **Step 1: Write the failing tests:** `test_list_batch_takes_a_snapshot_before_the_first_write`; `test_after_records_follow_each_write`; `test_seven_day_ceiling_override_pauses` (a fake meter at 41% weekly with `--seven-day-ceiling 40` pauses before the first show and prints the resume line); `test_stop_at_points_ends_the_block`; `test_progress_rows_carry_meter_kind_audio`; `test_batch_stops_after_three_unreadable_station_copies` (Review Focus 2); `test_campaign_list_checks_installed_versions`; `test_campaign_list_retires_the_rekey_restore` (a fixture `rekey-applied.json` gains `retired` with `by` naming the batch); `test_retryability_per_outcome` (one row of each outcome above → its `retryable` value; a re-run retries exactly the retryable rows); `test_held_backlog_lists_still_run` **(pin)**.
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(reapply): wave snapshot, weekly ceiling override, trial stop, richer progress`.

---

### Task 14: The overrule backfill (CHECKPOINT A after it)

**Spec:** "Overrules persist" (Backfill), "Undo", "Rollout". Strict surface 4. **Implementer: Opus.**

**Files:** Modify `scripts/bulk_apply.py` (`backfill`); Test `scripts/test_bulk_apply_backfill.py` (new; verdict fixtures of both layouts written inline).

**Interfaces:**
- Consumes: Tasks 1, 11, 12.
- Produces: `bulk_apply.py backfill --base <migration-base.json> --verdicts <dir> [--apply]` (dry run by default) and, in the script, `plan_backfill(root: Path, base: dict, verdicts: Path, delivered: set[str]) -> list[BackfillShow]` with `BackfillShow(slug: str, record: list[Overrule], listed: list[tuple[str, str]], show_reason: str | None)`.
- Rule: shows whose base row has outcome `newly-held` and state ≠ `held`, and whose derived state today ≠ `held`. Base flags = `gather_flags + vet_flags + brief_flags` (the base arm has no `flags`). Verdict file `<verdicts>/<slug>.json`: layout A `flags[].{flag, verdict}`, recorded when `verdict == "spurious"`; layout B `claims[].{flag, verdict}`, recorded when `verdict == "flag-spurious"`; either layout's `action.overrule_if_reheld_on` (a list of flag texts) records the flags it names. Listed, never recorded, with these reasons: `no verdict` (show-level), `verdict never ruled on this flag`, `ruled <verdict>`, `only in other_flags (free text)`, `not overrulable (package flag)`, and for `unresolved track titles` when `show.json`'s track count differs from the base row's `title_sources` count, `cannot derive the unresolved files`. The `titles` subject = `show.json` filenames at the positions where the base row's `title_sources[i] == "unresolved"`. `identifier` = `show.json`'s.
- Dry run prints, per show, `record:` and `list:` lines, then totals: shows considered, shows with no verdict, flags recorded, flags listed, shows fully covered. `--apply`: `require_pinned_code`, `require_tools(pin)`, then `batch_snapshot.take` of the shows with records into `<root>/campaign/backfill/<stamp>/snapshot/`, then `retire_rekey_restore(by="bulk-apply overrule backfill <stamp>")`, then per show under the show lock: re-read `overrides.json`, `merge_rules`, `write_artifact`, `record_after`, append to `record.jsonl`. A re-run adds nothing already present.
- [ ] **Step 1: Write the failing tests:** `test_layout_a_spurious_is_recorded_real_is_listed`; `test_layout_b_flag_spurious_recorded_research_right_show_wrong_listed`; `test_overrule_if_reheld_on_records`; `test_no_verdict_lists_the_show`; `test_show_held_today_is_skipped`; `test_titles_subject_from_base_title_sources`; `test_apply_snapshots_retires_and_is_idempotent` (second `--apply` writes nothing; `rekey-applied.json` carries `retired`); `test_apply_refuses_without_gates`; `test_dry_run_writes_nothing`.
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(bulk): overrule backfill from the overnight verdicts`.

### CHECKPOINT A (orchestrator; stop and report to Shawn)

Run, from the worktree, read-only: `./.venv/bin/python scripts/bulk_apply.py backfill --base ~/.llama-harness/piece4/migration-base.json --verdicts ~/.llama-harness/t3/verdicts > ~/.llama-harness/bulk/backfill-dryrun.txt`. Report the totals and both lists. Measured while planning (a read-only query, same rule): 195 shows considered, 15 with no verdict (all delivered), 316 flags recorded, 62 listed (56 never ruled on, 4 `research-wrong`, 2 `research-right-show-wrong`), 141 of 180 fully covered. Ask Shawn: (1) the listed flags; (2) `~/.llama-harness/t3/rehold-verdicts/` (34 shows with `decision: overrule` and no per-flag ruling; the spec does not name it): does the backfill read them, or list them for him? The spec's old "false-hold" wording means the verdict values `spurious` (layout A) and `flag-spurious` (layout B), which is what Task 14 records. A ruling that changes the rule is a follow-up task before Task 15.

---

### Task 15: Marking, its inputs and its reversal (CHECKPOINT B after it)

**Spec:** "The `awaiting_fix` contract" (Who gets marked, Writing a mark, The marking batch, No concurrent emcee), "The library side" (Marking skips), "Re-processing" (GD re-selections). Strict surfaces 1, 4. **Implementer: Opus.**

**Files:** Modify `scripts/bulk_apply.py` (`freeze`, `reselect-check`, `mark`, `unmark`); Test `scripts/test_bulk_apply_mark.py` (new; fixture library + fixture station + a hand-built arm).

**Interfaces:**
- Consumes: Tasks 3, 5, 12; `replay.row_visible_changes`, `row_label_only`.
- Produces (script functions, each tested):

```python
def freeze(root: Path, arm: dict) -> Path            # <root>/campaign/needs-llm-frozen.json; refuses an existing file
def reselect_rows(root: Path, config, source: list[dict]) -> list[dict]
    # per source row: stored identifier (show.json), pick = run_select_recording into a scratch
    # ShowWorkspace under a tempfile.TemporaryDirectory (never under the library) with
    # CacheOnlyIA, force=True, config.selection, the assessment built as _redo_show_locked
    # builds it; voiced = destination_voiced(...) for a delivered show, False otherwise; returns
    # [{slug, stored, pick}] for rows not voiced and pick != stored
def mark_plan(root: Path, arm: dict, frozen: set[str], reselections: list[dict],
              delivered: set[str]) -> list[MarkItem]
    # MarkItem(slug, reason, start_stage, digests | None)
def mark_apply(root, items, *, station_root: Path, batch: Path, echo) -> int   # exit code
def unmark(root, batch: Path, *, station_root: Path, apply: bool, echo) -> int
```
- `mark_plan` rule, per arm row: reasons in priority order: re-selection (from the re-checked list, start `select`, whatever the arm says), visible change, on the frozen list and not processed, `outcome` not `needs-llm` and `stored_brief_guard` non-empty. A row whose outcome is `needs-llm` or `unreplayable` never gets the visible-change reason (its diff comes from the provider-less fallback alignment, an artefact): it is marked only by re-selection or by the frozen-list rule (not processed); an `unreplayable` row left unmarked is listed. For other rows, a show whose record is processed (not awaiting) is skipped unless `row_visible_changes` is non-empty; label-only rows are never marked. Every state gets a record; only delivered shows get a station mark.
- `freeze`, `reselect-check` and `mark` take `--campaign-dir DIR` (default `<root>/campaign`); Checkpoint B points it at a scratch directory.
- `mark` CLI: `mark --arm <arm.json> [--apply]`; the arm's `sha` must equal `code_identity()` and its fingerprint the running config's; the frozen list and `reselections.json` must exist, and `reselections.json`'s `written_at` must not be older than the arm's `generated_at` (else exit 2 with the fixed string naming `reselect-check --write`). Dry run prints counts by reason × (delivered unvoiced, delivered voiced, packaged, briefed, held), the voiced slugs, unreadable station manifests, and whether emcee is running. `--apply`: gates; `retire_rekey_restore(by="bulk-apply marking <batch id>")` (idempotent, Task 12); `<root>/campaign/station-backup/` taken (every top-level non-dot station dir's `manifest.json`, sha-verified, `index.json` last) when absent; batch dir `marking/<sha256(arm bytes + frozen bytes + reselections bytes)[:16]>/`; per item under the show lock: digests re-checked (`skipped: inputs changed`), `add_mark` (durable) unless the record is already awaiting, then for a delivered show with a station copy: `emcee_running()` non-empty stops the batch (every remaining item listed as not marked), an already-marked station copy records `already marked`, else `before/<slug>.json` saved and `write_mark`; one `record.jsonl` line per item `{slug, reason, start_stage, mark_added: bool, station: "marked"|"already marked"|"no station copy"|"not delivered"|"refused: <why>", before_sha256, after_sha256, at}` (`mark_added`: this batch's `add_mark` wrote a library mark). A re-run of the same batch skips items already recorded with a non-refused `station`. Exit 0 only when every delivered item is `marked` or `already marked`; 1 listing every delivered item that was not (`skipped: inputs changed`, `refused: …`, or left unmarked by an emcee stop), since the runbook's emcee rule depends on it; 2 on a gate.
- `unmark --batch <dir> [--apply]`: per record line with `mark_added` (whatever its `station`): the record processed since that mark → listed `processed since marked: re-deliver instead`, nothing changed; else, for a `marked` line only, station sha ≠ `after_sha256` → listed `station copy changed since marking`, nothing changed, otherwise `put_back(before)`; then `remove_marks(ws, batch_id)`. Station bytes are restored only for `marked` lines.
- [ ] **Step 1: Write the failing tests:** `test_plan_marks_visible_changes_frozen_guard_and_reselections` (a same-count file swap is marked; a label-only row is not; a processed show is skipped unless visibly changed); `test_apply_writes_record_before_station`; `test_rerun_skips_marked_items`; `test_unreadable_station_manifest_is_refused_and_listed_exit_1`; `test_emcee_running_stops_the_batch`; `test_station_backup_taken_once`; `test_inputs_changed_row_skipped` (a delivered inputs-changed row → exit 1 listing it; a packaged one → exit 0); `test_mark_plan_skips_processed_needs_llm_row_with_diff` (processed show, `needs-llm` row with set changes → not marked); `test_mark_plan_ignores_needs_llm_diff_off_frozen_list` (unprocessed, not on the frozen list, `needs-llm` row with a diff → not marked); `test_mark_refuses_reselections_older_than_the_arm` (exit 2, the fixed string); `test_mark_apply_retires_the_rekey_restore`; `test_reselect_rows_write_nothing_under_the_library` (the library tree's file list and mtimes unchanged); `test_reselect_rows_drop_voiced_and_already_reselected`; `test_unmark_restores_bytes_and_removes_the_batch_mark`; `test_unmark_removes_library_only_marks` (a packaged show's and a `refused` station's batch marks are removed, their station bytes untouched; a line with `mark_added: false` keeps the earlier mark); `test_unmark_refuses_a_manifest_changed_since_marking`; `test_unmark_lists_processed_shows`; `test_freeze_refuses_to_overwrite`.
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(bulk): marking batch, frozen needs-LLM list, re-selection check, reversal`.

### CHECKPOINT B (orchestrator; stop and report to Shawn)

Read-only, from the worktree at a clean HEAD: `./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/bulk/checkpoint-arm.json` (no pin exists yet; `arm` needs one), then, all with `--campaign-dir ~/.llama-harness/bulk/campaign`: `bulk_apply.py freeze --arm ~/.llama-harness/bulk/checkpoint-arm.json`, `bulk_apply.py reselect-check --source ~/.llama-harness/piece4/fw1/m3_changed-r1.json --write`, and the `mark --arm ~/.llama-harness/bulk/checkpoint-arm.json` dry run. Nothing is written under `~/.llama`. Report: counts by reason × state (the backfill has not run, so newly held is near the table's 220, not 29), voiced count and slugs, unreadable station manifests, the re-selection list (expected 17; the three voiced shows absent). Shawn confirms the rule before Task 16.

---

### Task 16: Wave lists, wave check, spot checks and the famous-shows packet

**Spec:** "Pacing, ordering and resumability" (selection), "Re-processing" (structure gate, spot checks, newly held), "Pacing" (free disk), "Known constraints". **Implementer: Sonnet.**

**Files:** Modify `scripts/bulk_apply.py` (`lists`, `wave-check`, `spot-check`); Test `scripts/test_bulk_apply_lists.py` (new).

**Interfaces:**
- `lists --arm <arm> --out <list.json> [--profile P]... [--state S]... [--slugs F] [--kind fresh|reuse|needs-llm|label-only|held]... [--include-voiced] [--famous F] [--limit N] [--counts]`. The arm's `sha` must equal the pin's `sha`; the doc is `{sha, config_fingerprint, written_at, campaign: {version, pin_sha}, rows: [{slug, outcome, briefing, kind, digests}]}`, rows in slug order. A row is listed when its show is awaiting fix with start `gather`, or the row is label-only (no record), or its outcome is `newly-held`; never when processed, a re-selection, voiced (destination `dj_audio` non-null) without `--include-voiced`, or on `--famous`. Kind from the row, first match: `needs-llm` (outcome), `held` (`briefing == "none"`), `label-only` (`row_label_only`), else `fresh`/`reuse` (`briefing`). `--profile` is exact on `provenance.profile`; `--state` the derived state. `--famous` writes `<out>.famous.txt`: per slug the before (`show.json`) and after (arm row `filenames`, `titles`, `sets`, `segues`) rendered by `render_side_by_side`. `--counts` prints JSON `{profile: {kind: {"unvoiced": n, "voiced": n}}}` over every awaiting, unprocessed show instead of writing a list (the trial projection's queue).
- `render_side_by_side(before: list[dict], after: list[dict]) -> list[str]` — rows of index, set (before→after), title (before→after), segue marks; a row whose values differ is starred.
- `wave-check --list <list.json>`: the station root is a readable directory; every delivered row's station manifest reads (`read_station_manifest`); needed bytes = sum of each delivered row's station `audio/*` sizes; refuse (exit 2) when `needed + WAVE_DISK_MARGIN_BYTES > shutil.disk_usage(config.root).free`, `WAVE_DISK_MARGIN_BYTES = 20 * 10**9`; prints needed, free, margin.
- `spot-check --batch <reapply batch dir> [--n 5] [--seed S]`: a seeded sample (seed printed) of the batch's `cleared`/`held` rows rendered before (the batch snapshot's `show.json`) and after (current `show.json`).
- [ ] **Step 1: Write the failing tests:** `test_lists_select_by_profile_state_kind_and_exclude_voiced_processed_reselection`; `test_lists_refuse_an_arm_not_at_the_pin`; `test_famous_shows_go_to_a_packet`; `test_counts_shape`; `test_kind_held_from_briefing_none` (a row with `briefing == "none"` and outcome `held` → kind `held`; a `needs-llm` row with `briefing == "none"` stays `needs-llm`); `test_wave_check_refuses_when_the_disk_is_short` (monkeypatched `disk_usage`); `test_wave_check_refuses_an_unreadable_station`; `test_spot_check_is_seeded_and_side_by_side`; `test_list_feeds_reapply` (a written list loads through `reapply.load_list` at the running code).
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(bulk): wave lists, wave check, spot checks, famous-shows packet`.

---

### Task 17: The ranked re-voice list and the trial report

**Spec:** "Delivery after the fix" (ranked re-voice list), "The trial". **Implementer: Sonnet.**

**Files:** Modify `scripts/bulk_apply.py` (`revoice-list`, `trial-report`); Test `scripts/test_bulk_apply_reports.py` (new).

**Interfaces:**
- `revoice-list --arm <arm> --emcee-status <emcee status --json file> [--backend voxtral|mlx_audio|elevenlabs]`: voiced shows (`voiced_by` non-null) that are awaiting fix; per show components from the arm row and `show.json`: `tracks` (+added/−removed by filename), `set moves` (tracks with the same filename whose set label changed), `titles` (title text changes), `segues`, `metadata` (venue, city, date changed). Ranked by `(tracks added+removed, set moves, titles, segues, metadata)` descending, then slug. Cost from `tts_now.backend`: `voxtral` → `1 Voxtral credit`, `mlx_audio` → `free (local)`, `elevenlabs` → `ElevenLabs`, missing/unresolved → `unknown`. Rows whose arm outcome is `needs-llm` print last under `unknown until re-processed`. Each row: rank, slug, presenter, backend, cost, every component.
- `trial-report --block <shape>-<kind>=<batch dir>... --queue <counts.json> --weekly-share PCT [--shape dead=dead,dead-family ...]`: per block, the applied rows of its kind; before = the first such row's `meter.before`, after = the last one's `meter.after`; `five_hour_resets` differing → `discarded: crossed a 5-hour reset; re-run`; delta5 < `MIN_BLOCK_POINTS = 5` → reports the error bound `±1/n` per show; per-show 5h cost = delta5 / n; the 7-day ratio = Σ delta7 / Σ delta5 over every kept block; per-show 7d cost = per-show 5h × ratio. Shapes whose per-kind costs differ by more than `MATERIAL_DIFFERENCE = 0.25` (relative) are kept apart and a profile outside every shape uses the higher measured cost; otherwise one pooled figure per kind. Projection: Σ over the queue of n × per-show 7d cost, in weeks at the weekly share, per profile and total; kinds `reuse`, `label-only` and `held` cost 0 (no LLM call), only `fresh` and `needs-llm` are measured. Also the `align_reproduced` rate of the needs-LLM blocks.
- [ ] **Step 1: Write the failing tests:** `test_ranking_is_lexicographic_and_explained`; `test_cost_from_tts_now`; `test_needs_llm_rows_last`; `test_block_cost_and_ratio` (two hand-built progress files: 20 shows moving 5h 30→40 and 7d 10→12 → 0.5 points per show 5h, ratio 0.2, 0.1 points per show 7d); `test_block_crossing_a_reset_is_discarded`; `test_small_block_reports_its_bound`; `test_projection_in_weeks` (queue rows of kind `reuse`, `label-only` and `held` add 0); `test_material_difference_keeps_shapes_apart`.
- [ ] **Step 2:** Run → FAIL. **Step 3: Implement.** **Step 4:** Full suite → PASS. Commit `feat(bulk): ranked re-voice list and trial cost report`.

---

### Task 18: CLAUDE.md, runbook check and final acceptance (CHECKPOINT C)

**Implementer: Sonnet** (docs); the orchestrator runs the acceptance.

**Files:** Modify `CLAUDE.md`; this plan's Appendix only if the build changed a command name.

- [ ] **Step 1:** CLAUDE.md: the `awaiting_fix` contract and `campaign.json` (Architecture), overrules (`overrides.json` bullet), strict station reuse (replaces "a purged show re-delivers via `redo --from package`, which re-downloads"), `reapply` for every state, `--allow-download` (by name on `reapply`/`redo`/`fix`), `clear-mark`, `deliver --fixed`, `status --awaiting-fix`, emcee's `awaiting-fix` state, `scripts/bulk_apply.py` subcommands (Commands), and the open gaps below.
- [ ] **Step 2:** Full suite green; `grep` the diff for the Global Constraints' untouched names (none changed); `./.venv/bin/python -c "import llama; print(llama.__file__)"` inside the worktree.
- [ ] **Step 3:** Whole-branch code review on Opus. Then CHECKPOINT C: report to Shawn with the release note (llama and emcee ship together at the version `CAMPAIGN_MIN_VERSION` names; correct the constant first if the release gets another number). Merge, tag, release and everything in Appendix A are the operator's.

---

## Open gaps (named, not closed by this plan)

- **A delivered show whose station copy is gone or permanently unpaired** refuses strict reuse every time; its only route is the by-name `--allow-download` (Tasks 8-9), which downloads whatever does not pair for that one show. Today no held show is delivered (measured), so no held-before-the-campaign show lacks an anchor.
- **A paired source whose cached metadata has no length** refuses (`<file> has no metadata length`) on every strict re-package, since its copy cannot be checked; the route is `--allow-download` for that show. How many such sources the library holds is unmeasured.
- **Newly held shows with no visible change** (1 delivered, 92 packaged in `migration-post.json`, before the backfill) are not marked by the spec's rule; Task 16 lists them (`kind == "held"`) so the apply writes their hold, but they get no campaign record and a delivered one keeps an unmarked station copy (its visible data is unchanged).
- **Raw-JSON duration equality** in `clear-mark` and `--replace-voiced`'s refusal: a re-packaged file whose re-read duration differs in the last digit reads as "differs" and needs `--accept-change`.
- **SMB/NFS rename atomicity** of the station mark is unmeasured (spec Limitation).
- **The station-mark residual window:** an emcee write landing between `write_mark`'s last byte check and its rename is overwritten undetected; the per-write `emcee_running()` check is the guard (Review Focus 1).
- The marking rule cannot reach processed needs-LLM shows after a later gather change (spec, documented limitation).

## Appendix A: the bulk-apply run (operator, after the release)

All campaign tools run from the pinned worktree by path, never with its venv activated (its dev `llama` reports `0.1.0`). `C=/Users/shawn/projects/llama/.claude/worktrees/campaign`, `B="$C/.venv/bin/python $C/scripts/bulk_apply.py"`, output under `~/.llama-harness/bulk/`. Nothing else spends while a step that needs quiet runs: no other Claude sessions, no sweep loop, no `emcee run`, no `scripts/backfill_*`.

1. Release llama and emcee together; install both; `llama --version` and `emcee --version` report the release on every PATH entry. Installing comes before step 3 (2.18.0's `fix` drops `overrules`; its `deliver` overlays a marked copy).
2. `git worktree add "$C" v<release>`; its own venv; `$B pin --tag v<release>`. Stop the sweep loop.
3. `$B backfill --base ~/.llama-harness/piece4/migration-base.json --verdicts ~/.llama-harness/t3/verdicts` (dry run); Shawn reads both lists; then `--apply`. Its restore (`$B restore <snapshot>`) works only until step 6 writes campaign records.
4. `$B arm --out ~/.llama-harness/bulk/arm-1.json`; `$B freeze --arm ~/.llama-harness/bulk/arm-1.json`.
5. `$B reselect-check --source ~/.llama-harness/piece4/fw1/m3_changed-r1.json --write` (expect 17).
6. `$B mark --arm …/arm-1.json` (dry run), Shawn approves the counts, then `--apply` (it backs up every station manifest first). Until a marking batch exits 0, no `emcee run` on a profile holding a show it could not mark (a killed batch prints no list: re-run until 0).
7. **Trial** (quiet): four block lists, e.g. `$B lists --arm …/arm-1.json --state delivered --profile dead --profile dead-family --kind fresh --limit 40 --out …/block-dead-fresh.json` (and `funk`, and `--kind needs-llm`, the Dead needs-LLM block drawing on both Dead profiles; merge with funk's if both pools are small); `$B wave-check --list <block>`; `"$C/.venv/bin/llama" reapply --from-list <block> --allow-structure-change [--with-gather-llm] --stop-at-points 5`; `$B spot-check --batch <batch dir>`; re-deliver the block's unvoiced shows (`llama deliver --fixed --state delivered --profile <p> --yes`). Then `$B lists --arm … --counts > …/queue.json` and `$B trial-report --block dead-fresh=<dir> … --queue …/queue.json --weekly-share <pct>`. The 3 held needs-brief shows can give an earlier sample with today's tooling.
8. Shawn sets the weekly ceiling from the projection. **Waves**, in the profile order Shawn picks: `$B lists --arm … --profile <p> [--state …] [--famous <file>] --out …/wave-<p>.json` (famous shows go to their packet and are hand-checked first), `$B wave-check`, `llama reapply --from-list … --allow-structure-change --with-gather-llm --seven-day-ceiling <pct>`, `$B spot-check`, then `llama deliver --fixed --profile <p> --yes` once the spot check passes (after that, the way back is forward). mlx voiced shows and the voiced needs-LLM shows may ride a wave with `--include-voiced --slugs <file>`. "Profile" is emcee's effective profile; today it equals llama's on every delivered show, so `--profile` selects it. Once moves or artist rules exist, build the slug file from `emcee status --json --profile <p>` and pass `--slugs`.
9. **Re-selections** in their wave: `$B snapshot --slugs <file>`; `llama redo <slug> --from select` each; for `gratefuldead-1970-05-06` and `-1985-11-10`, on the dangling-key refusal `llama fix <slug> --clear-<key> … --no-run`, then the redo again; `$B seal <snapshot>`; re-deliver.
10. Newly held shows wait for `llama triage` after their wave.
11. **Voiced shows:** `emcee status --json > …/emcee.json`; `$B revoice-list --arm … --emcee-status …/emcee.json`. When Shawn schedules one: `llama reapply <slug> --allow-structure-change [--with-gather-llm]`, then `llama clear-mark <slug>` (unchanged, or `--accept-change`) or `llama deliver <slug> --replace-voiced` and `emcee voice <slug>`. The 37 voiced-severe shows: `llama reapply <slug> --allow-structure-change [--with-gather-llm]` first, then piece-4 Appendix C (`short_keep_probe.py voiced-precheck`, then the named `deliver <slug> --replace-voiced`, then `emcee voice <slug>`).
12. **When the code or the library changes:** a new arm (`$B arm`), then `$B reselect-check --source ~/.llama-harness/piece4/fw1/m3_changed-r1.json --write` (`mark` refuses a `reselections.json` older than its arm), a new marking batch (marks are only added), new lists. At each llama release: a new worktree at the new tag, `$B pin --tag … --replace`, then a new arm; arms and waves refuse while an installed llama is newer than the pin.

## Appendix B: undo

- **Backfill:** `$B restore ~/.llama/campaign/backfill/<stamp>/snapshot` (dry run, then `--apply`), before step 6 only.
- **A wave:** `$B restore ~/.llama/reapply/<hash>/snapshot`, before its re-delivery; a show re-delivered or re-voiced since refuses (roll forward). A restore never rewinds a station mark (a show left marked is safe).
- **Marking:** `$B unmark --batch ~/.llama/campaign/marking/<id>` (dry run, then `--apply`); shows processed since their mark are listed, never unmarked.
- **The migration's `rekey_overrides.py --restore`** refuses from step 3 on (retired).
