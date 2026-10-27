# t4-review handback: Task 4 (awaiting fix in status and deliver), 79049ca6..c45936ff

### Spec Compliance

- ✅ Spec compliant. Every interface named in the brief is present: `CatalogEntry.awaiting_fix` (catalog.py:45, set from `campaign.is_awaiting` at catalog.py:313, unreadable record -> True at campaign.py:68-74); `select_shows(..., awaiting_fix)` (catalog.py:321-324); `Selector.awaiting_fix` / `build_selector` / `selector_active` / `apply_selector` (cli_select.py:35,41,54,59,67); `status --awaiting-fix`, row mark `awaiting-fix` (cli.py:4342), JSON key `awaiting_fix` (cli.py:4330); `class _AwaitingFix(LlamaError)` (cli.py:2579); `FROZEN_FILE = "campaign/needs-llm-frozen.json"` and `frozen_slugs` empty on missing/unreadable (campaign.py:24,57-65).
- Fixed strings checked against Contracts: `refusing to deliver <slug>: awaiting fix (marked <at>: <reason>)` + `  re-process it first: llama reapply <slug> --allow-structure-change[ --with-gather-llm]` / `  re-process it first: llama redo <slug> --from select` (cli.py:2584-2598) match character for character; batch suffix `  (refused: awaiting fix)` matches; the campaign-record string comes from Task 3's `_unreadable` unchanged.
- "First check under the show lock, before the voiced check": cli.py:2623 is the first statement inside `with file_lock(show_ws.lock)`, ahead of `_read_destination_manifest`/voiced. ✅
- Spec "refused by llama deliver by name and in every selector": by name via `_deliver_one`; every existing deliver selector goes through `_deliver_batch` (cli.py:2794), which marks and refuses. ✅
- Review Focus 5 (library part): `status` marks an unreadable record (is_awaiting -> True) and `deliver` refuses with the campaign-record string (CampaignUnreadable propagates as LlamaError from cli.py:2623 to the by-name handler, exit 1). Pinned by test_deliver_cmd.py:915. ✅
- Named risk checked: `status --awaiting-fix` hiding delivered shows behind the RECENT_DELIVERED trim. Checked cli.py status body: the trim runs only when `not filtering`, and `selector_active` now includes `awaiting_fix`, so `--awaiting-fix` lists every awaiting delivered show. ✅
- Named risk checked: `read_record` raising something other than `CampaignUnreadable` from inside `iter_shows` (would crash every catalog reader). campaign.py:87-97 wraps OSError and Validation/ValueError; FileNotFoundError -> None. ✅
- No extras: no deliver `--awaiting-fix` selector was added (not requested). ✅
- ⚠️ Cannot verify from diff: reapply builds its own `CatalogEntry` at cli.py:3947 without `awaiting_fix` (default False). Harmless for this task (nothing there reads the field), but Review Focus 5's reapply leg ("reapply fails the row retryably" on an unreadable record) belongs to a later task and the controller should check it there. Task 5's `--fixed` selector and marked-destination route are also out of scope here.

### Strengths

- The by-name refusal re-reads `campaign.json` under the show lock rather than trusting the scan-time `entry.awaiting_fix`, so a show marked between scan and delivery is still refused (cli.py:2623).
- An unreadable record is never treated as "no record" in either place: `is_awaiting` returns True for the catalog, and `_awaiting_fix_check` lets `CampaignUnreadable` surface with its own text.
- `frozen_slugs` fails soft only for what it controls, the hint's wording (campaign.py:57-65). The corrupt-file case is pinned (test_deliver_cmd.py, `test_deliver_pointer_names_with_gather_llm_for_a_frozen_show`).
- The tests build real show dirs, add real campaign marks through `campaign.add_mark`/`mark_processed` and invoke the real CLI. They assert the full fixed strings, "nothing copied", and the absence of a ledger row.
- Targeted run: `./.venv/bin/python -m pytest test_status_cmd.py test_cli_select.py test_deliver_cmd.py -q` gave 101 passed, and `llama.__file__` resolves inside the worktree.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. cli.py:2713-2720: the batch's per-show awaiting re-check duplicates `_deliver_one`'s own first check (cli.py:2623). The `except LlamaError` arm at the `_deliver_one` call already prints the same `_AwaitingFix`/`CampaignUnreadable` text. As written it takes the show lock twice. And if the show gets processed between the scan and this point, the check passes and the code falls through to deliver it, though the confirmation plan said `(refused: awaiting fix)`. That outcome is correct, but it disagrees with the plan. Fix: drop the block and let `_deliver_one` refuse; the plan mark stays. A mutation reasoned from the code (not run): deleting this block leaves every test green, which confirms it is redundant.
2. No test pins the ordering the brief mandates ("before the voiced check"). Neither test gives an awaiting show a voiced destination and expects the awaiting refusal instead of `_VoicedDestination`. Swapping cli.py:2623 below the voiced check would pass every test. Add one test: a delivered, voiced destination plus a mark, deliver by name, and expect the awaiting string.
3. test_deliver_cmd.py:891 `test_deliver_batch_skips_awaiting_fix` asserts the plan mark and the copy results. It does not assert that the refused show's refusal and pointer reach stderr ("naming the route" in every selector), and it does not assert that the refused show has no ledger row. Add both assertions.
4. cli_select.py:59 is 106 characters, longer than the surrounding style. Wrap it.
5. Observation, not a defect: `_deliver_batch` still exits 0 when shows are refused. That matches the existing voiced and unreadable-destination refusals, and the brief specifies no exit code.

Untouched-names grep: the diff mentions none of SHORT_FRACTION/MIN_PLAUSIBLE/MIN_MEDIAN, DURATION_TOLERANCE_S, audio_reuse, purge_package_audio, STOP_AFTER_LLM_FAILURES, load_list, briefing_reusable, AGREEMENT_FLOOR, _apply_short_rule, emcee or transmitter. No `Manifest` model field was added. ✅

### Assessment

**Task quality:** Approved

**Reasoning:** The refusal is enforced at the right place (first under the show lock), every fixed string matches the Contracts, and the unreadable record is treated as awaiting on both the status and the deliver side. The remaining items are a redundant batch block and gaps in test pinning, all Minor.
