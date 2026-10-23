### Spec Compliance
- ✅ Spec compliant. The brief's Task 13 list and the three alternatives the orchestrator added are all present. Details:
  - CLI and output: `dump [--config] [--slugs] [--jobs] --out`, `_meta` first line (title_hygiene_probe.py:886-898). `_meta` carries one extra key, `align_coverage_threshold`, which is harmless.
  - Two views, built as the brief says (582-625, 806-813):
    - fresh view: `_shadow` with `("titles","set_breaks","encore_after")`;
    - as-is view: the show dir itself.
  - Capture wrappers wrap `accept_short_tags` and `_sibling_transfer` only, armed only while `compute_legs` runs (359-385, 525-542).
  - Inputs come from `title_inputs` with `build` calling `build_canonical(provider=None, setlistfm=CacheOnlySetlistFM)` (498-512).
  - Arms are none / all / all-<slice> on the fresh view and none on the as-is view, with `cosmetic_strip` applied last on every slice5 arm and a `+5` suffix (348-349, 564-572).
  - `--jobs` workers install the wrappers through the Pool initializer (393-401, 907-909). Start method here is `spawn`, and the jobs-1 vs jobs-2 test passes.
  - Every row field the brief lists is present (785-858).
  - gate0 / gate0_as_is compare titles, sources, op notes and struct notes, and report the first difference (545-561).
  - All nine `alt_*` fields are present (658-769).
  - Refusals (exit 2) come from `replay_holds._check_identity`/`_overlaps` (873-880, 937-941).
- Global Constraints: the diff only adds `scripts/title_hygiene_probe.py` and its test. No protected name is defined or edited. `fuzzy_norm_title`, `fuzzy_title_eq`, `is_filler` and `gap_span` are imported and called only. No library module is touched.
- ⚠️ Cannot verify from the diff alone, so I checked these on disk:
  - **Gate 0 on the library.** The implementer's dump has 3983/3983 `gate0` true and 3983/3983 `gate0_as_is` true. There are 0 probe errors and 0 unreplayable rows.
  - **Wider gate 0 (named risk: Task 16 deletes compute_gather's duplicate code on the strength of gate 0, which compares only titles, sources and notes).**
    - I ran the probe through a scratch driver, with `--jobs 1` over all 3983 shows, both views (`~/.llama-harness/piece3/scratch/t13-rev/widegate.py`, output under `.../wall/`).
    - It widened gate 0 to whole-`Track` `model_dump` equality, plus compute_gather's `kept`, `excluded`, `ordering`, `metadata_norms`, `family_aliases`, `format_titles`, `recovery_basis` and `tag_gate_basis` against `title_inputs`, plus `cb.setlist`, `source`, `corroboration` and `needs_llm`.
    - Result: no difference anywhere except `cb.notes`. That one is explained by aliasing: compute_gather binds `notes = cb.notes` and later extends it in place with the jerrybase-anchoring and sibling notes. A recheck on 40 of those shows confirms `title_inputs`' `cb.notes` is an exact prefix (0 differences).
    - So the prelude and the title block reproduce today on every field Task 16 will consume.
  - **Read-only.** `find ~/.llama -newer <marker>` after my two probe runs: 0 files.
  - **Two reconstructions in the probe, cross-checked against the cascade's own record over the whole dump:**
    - R15's candidate set and failures equal `d.failed`'s `hygiene:*` entries on all 78 rows where D ran; D's open positions are a subset of the candidates.
    - `s_candidates`' judge verdicts match the `gated` S plan's fills and per-track decline notes on all 581 gated shows.
    - 0 mismatches.
  - **`alt_check2_cleaned` really captures calls.** It recorded 576 S, 78 D and 1 S-deferred calls, so the spy is live. The value "would decline: 0" is real, not an empty capture.

### Strengths
- The capture is armed only inside `compute_legs`, so the cascade's own `accept_short_tags` call (gather.py:1273) is never recorded as "today" (title_hygiene_probe.py:366, 528-536).
- A probe that gets a show wrong cannot stop the run (`_safe_one`, 861-867). The output is written atomically through a pid-named temp file and `os.replace` (892-913).
- The gate-0 test shows that gate 0 can fail: `test_gate0_reports_the_first_difference` bends the `none` arm and asserts `track 2 title:` (test:149-162).
- The non-vacuity assertions in `test_gate0_parity_on_fixtures` cover sibling-align, setlist and D (test:141-146).
- `test_strips_titles_and_structure_overrides_in_the_shadow` checks that the live overrides file's hash is unchanged and that the as-is view keeps the override (test:165-180).
- `structure_override` uses gather's own rule (`is not None`, so `set_breaks: []` counts), at 809-810 versus gather.py:1694.
- Per-run `left`/`right` in `alt_bracketed_s` and `containment`/`ratio` in `alt_c2_containment` keep the raw evidence next to the derived verdicts.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **`alt_c2_containment.containment_only` does not use the definition the dispatch asked for** (title_hygiene_probe.py:485-493, 760-762).
   - The dispatch asked for C2 replacements "whose agreement holds only through `loosely_same_title`'s containment arm". The code computes `not strict`, where `strict` = core equality or `fuzzy_title_eq`. `fuzzy_title_eq` is not one of `loosely_same_title`'s arms (structure.py:241-245: equality, containment, ratio). Two errors follow:
     - a multi-word subphrase that agrees only by containment (e.g. `dark star` inside a long title, ratio below 0.8) is marked strict and **omitted**;
     - a ratio-only agreement is **included**.
   - On this dump the error has no effect. I recomputed all 118 C2 rows: 0 agree only by containment (`containment and ratio < 0.8`), 0 agree only by ratio, and 0 have `agrees` false. Task 14's R-row value is 0 under either definition.
   - Fix before any re-run of the dump: `containment_only = containment and na != nb and ratio < LOOSE_TITLE_RATIO` (cores of 3+ letters).
2. **`alt_bracketed_s` follows `gap_span` literally, including its leading-edge branch** (461-482).
   - A run starting at position 0 with only a right anchor counts as `closed` and its S fills `remain`. The plan and spec text say "bracketed on **both sides** … (`gap_span`'s rule)", and `gap_span` itself is one-sided at the leading edge (structure.py:1350).
   - The implementer disclosed this as judgement call 4. On the library it changes 2 runs: `beneventorusso-2005-08-27` and `umphreysmcgee-2005-02-27`, each lo=hi=0, left false, right true.
   - Task 14 may not compute alternatives itself. So either add a `remain_both_sides` list for it to tabulate, or list the reading as a Checkpoint-A question.
3. **`inputs_for` leaves process-global state set** (515-522).
   - `_init` calls `logging.disable(logging.CRITICAL)` and fills `_W`. `inputs_for` undoes only the wrappers.
   - In the test process, every test after `test_arms_present_and_slice5_applied_last` therefore runs with logging disabled, which would silently blind any later `caplog` assertion.
   - Today this is latent: this file is the last in `testpaths` and has no `caplog` tests. Fix: save and restore `logging.root.manager.disable` in the `finally`, as `dump` does at 895/912.
4. **The capture depends on a local variable name in its caller** (368).
   - `sys._getframe(1).f_locals["op_notes"]` ties the probe to compute_gather's local name and to it being the direct caller.
   - If the name changes, the `KeyError` is raised inside `compute_legs`, recorded as `unreplayable`, and leaves `cap` None, so `gate0` becomes **None**, not False.
   - `_write`'s progress counter counts only `is False` (922). A broken capture would therefore print "gate0 false: 0".
   - Count `gate0 is not True` (on rows that are replayable) in the summary line, and Task 14 should treat None as not passing.
5. **`_s_candidates` re-implements `_s_check`'s cleaning and `judge` call** (637-655) instead of using a recorded result, so it can drift from title_hygiene.py:472-504. It agrees today (581/581 gated shows, checked above). A comment naming the function it mirrors, or a test pinning the equality, would catch future drift.
6. **Tests check only that the `alt_*` keys exist, not their values**, on the end-to-end rows (test:213-221). The three unit tests cover only the check-2 cleaned, bracketed and C2 arm helpers. These have no test: `via_c_where_ab_disagreed`, `exemption_decided`, `alt_filler_confirm` and R15's candidate set. My dump-wide cross-checks cover R15 and S, but not the first three.
7. **Gate 0's scope is what the brief specifies, but narrower than the contract Task 16 relies on.** I measured the wider equality as clean (see the gate 0 checks above), so no action is needed for this dump. If the probe is re-run after later tasks, consider adding whole-`Track` equality to `first_difference`. It is cheap, and it is the property Task 16 actually depends on.
8. Style: `from difflib import SequenceMatcher` is imported inside `c2_arms` (489).

### Assessment
**Task quality:** Approved
**Reasoning:** The probe meets the brief and the three added alternatives, stays read-only, and refuses correctly. Gate 0 holds on every row. I independently confirmed it holds even when widened to whole tracks and the full prelude, and that the probe's reconstructed alternatives agree with the cascade's own record. The remaining findings are a mis-labelled field whose current value I verified, a disclosed R4 reading for Checkpoint A, and latent test or robustness issues.
