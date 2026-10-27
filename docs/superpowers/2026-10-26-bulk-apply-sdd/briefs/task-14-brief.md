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

