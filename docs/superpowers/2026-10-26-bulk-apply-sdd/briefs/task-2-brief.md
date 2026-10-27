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

