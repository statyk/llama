# Plan review round 1 decisions (2 Opus reviews). Apply all to docs/superpowers/plans/2026-10-22-taper-set-markers.md

D1 (Critical). Report 2 ("newly cleared") is redefined: held in the base arm, and in the candidate an outcome in `CLEARING` OR `structure-changed`. Task 7 (now 7b, see D24) emits it as its own file `taper_cleared.txt` (added to `OUTPUT_FILES`), with a test (`test_taper_cleared_includes_structure_changed_clears`). Task 9's report-2 pre-screen reads that file.

D2. Gate denominator fixed before the reader runs. In Task 3, the probe computes the in-scope set independently of the reader: `classified.jsonl` rows with `taper_explicit == "yes"`, `primary` in {`desc-set-header`, `desc-disc-with-set`, `desc-inline-marker`}, whose `marker_quote` matches a fixed worded-form regex written in the probe (the word `set` followed by 1–3/one–three/I–III, or an ordinal set word; documented in the task). Ownership ratio = owned / in-scope (all in-scope rows, renumbered or not: ownership is computed on the bundle's pre-adjudication tracks). Target match rate = owned rows that match / owned rows with a target and not `renum`. Rows with no target and `renum` rows are counted and listed separately. `gate_summary.txt` prints the in-scope row list. Stop rule: ownership ratio < 0.5.

D3. One pure ownership decision. Task 2 adds, in `taper.py`:
```python
@dataclass(frozen=True)
class TaperDecision:
    placement: TaperPlacement | None   # None when not owned
    taper: TaperText
    source: str                        # "description" | "notes" | "none"
    reason: str | None                 # why not owned (reader reason, "veto: track title",
                                       # "veto: encore-like text", or the placement decline)
def decide_taper(tracks: list[Track], meta: dict, *, aliases: dict[str, str],
                 today_sets: list[str]) -> TaperDecision: ...
```
It runs `taper_text_for`, `read_taper_structure`, both vetoes (`not taper.has_encore and (any(_ENCORE_MARKER.search(t.title) for t in tracks) or taper.encore_like)`) and `place_taper_structure`. `compute_gather` (Task 4) and the probe (Task 3) both call `decide_taper`, never the parts. The veto tests move to Task 2 (including `test_encore_like_does_not_veto_when_an_encore_is_marked`). Mutants (g), (h) target `decide_taper`.

D4. "Differs" is per-track labels, not break positions. Task 4: `alignment = "taper"` and the "was" op note when the shipped per-track labels of non-filler tracks differ from step 1's (so `1,2,3` → `1,2,encore` at the same positions counts). The note cites step 1's breaks and labels. Add test `test_label_rename_at_same_positions_is_recorded`. Report 3 (Task 7b) gains a `labels renamed` tier, pre-screened in full like `songs moved`.

D5. Harness-only fields allowed. Global Constraints: the new fields are `StructureInfo.taper_owned`, `GatherResult.taper_owned`, and on the harness record `ShowReplay` only: `taper_owned: bool`, `sets: list[str]` (replayed per-track labels), `filler: list[bool]` (per-track `is_filler`), `taper_source: str | None`, `taper_reason: str | None`, `step1_alignment: str | None`. Missing keys (base arms run base code) read as absent. Task 7a updates `test_show_replay_to_dict_has_the_contract_keys_plus_date` for the new keys. Report 3's "before" for a base row is the stored `show.json` labels with the base row's `set_changes` applied (base arms have no `sets`); its columns include the taper source, the first recognised header line (from `taper_reason`/source re-read is not needed: record `taper_source` and the overruled `step1_alignment`).

D6. Stripped arm from the candidate tree only (Task 9 Step 1: drop "for both"). Task 0 gains: a detached base worktree `.claude/worktrees/taper-base` at `a26c4d1` with its own venv, proven by `import llama` path.

D7. Mutants (Task 8) add: (n) jerrybase anchoring applied after the taper step on an owned show (predicted `test_taper_beats_jerrybase_anchoring`); (o) the `\b` dropped from the Set I–III form so `Set Intro` reads as set 1 (predicted `test_unrecognised_forms_are_not_markers`); (p) the merged-track-across-boundary rule removed (predicted `test_merged_track_spanning_the_boundary_is_unplaced`). Split (j) into (j1) relaxation removed (predicted `test_stored_llm_taper_owned_is_replayable`) and (j2) relaxation unconditional (predicted `test_stored_llm_alignment_is_needs_llm`).

D8. Task 5: factor the demotion into a pure helper in `gather.py` (or `taper.py`):
`demote_jerrybase_flags(hard: list[str], count_flag: str | None, event: JerrybaseEvent, taper: TaperText) -> tuple[list[str], str | None, list[str]]` (kept hard flags, kept count flag, op notes). Mapping: iterate `event.sets`; for each set whose closer string appears in a hard flag, map numbered set k to taper set k, jerrybase `encore` to the taper's encore; demote when the taper has no such set or its last song differs (`fuzzy_norm_title` then `fuzzy_title_eq`). Test `test_closer_flag_stays_hard_when_taper_text_agrees` with a synthetic hard flag against this helper (assert the input really contains the flag). Keep the gather-level tests for the note strings.

D9. "Exactly today" oracle: `test_not_owned_is_exactly_today` and the veto/override pins compare against the same candidate with `llama.taper.decide_taper` monkeypatched to return not-owned. Task 9 adds: every replayable row whose candidate `taper_owned` is false must have zero base/candidate differences in shipped fields and flags; any difference is a defect.

D10. Task 2 `test_merged_track_spanning_the_boundary_is_unplaced`: a < b, b is the merged track `Space > Scarlet Begonias` where `Space` is in the taper's set A and `Scarlet Begonias` opens set B (a is A's last song on its own track) → unplaced. Update Review Focus 2 to match.

D11. Add real-case tests: Task 2 placement declines for `moe-1997-02-21` (encore boundary unplaced: Head and Interstellar between) and `darkstarorchestra-2005-11-16` (repeated `NFA`); Task 1 `lotus-2005-10-15` (set-and-encore disc line, later `e:`); Task 4 `test_umphreys_2004_04_14_taper_owned_identical_to_today`.

D12. Task 4 test `test_owned_show_drops_merge_conflicts_not_owned_keeps_them` (same merged track, owned vs decide_taper patched to not-owned).

D13. Low-confidence on owned shows: `canonical.items and no anchoring and step1 coverage < threshold and reader coverage < threshold`. On an owned show `StructureInfo.coverage` records the reader's coverage (the alignment of what shipped). Test both. Update the Global Constraint on fields (no new field for coverage).

D14. Veto precedence pinned (in D3). Global Constraints' encore list adds the existing `E1:`/`E2:` (`_ENCORE_LINE`'s `e\d?`). Task 1 adds positive tests for decorated headers (`[Set One]`, `~Set One~`, `-Set I-`, own-line `(Set 2)`) and a negative test for a mid-line `Song (set II)`.

D15. Note group: Task 7b adds a `taper` group to `NOTE_GROUPS`, checked before 5c.1, matching the three fixed strings (`set breaks from the taper's markers`, `… (taper's markers)` set-count and closer notes).

D16. Global Constraints: `git diff main -- packages/llama/src/llama/setlist.py` must be empty (code-quality reviewers check it every task).

D17. Task 4 Step adds: grep that no reader outside llama (emcee, transmitter, antenna) switches on `structure.alignment`; record the result in the commit message.

D18. Task 9 adds Measurement 4: list every newly held show (base not held, candidate held) with its added flags; each needs an explanation in `acceptance.md`.

D19. Header note: the gate runs after Tasks 1–2 build the pure reader and placement (nothing wired into gather), a deliberate reading of the spec's "before any build task": Tasks 1–2 are the prototype. Say it in the header and at Checkpoint A.

D20. `taper_probe.py` options: `--root` (library, default `~/.llama`), `--bundles` (default `~/.llama-harness/t3/bundles`), `--evidence` (default the repo evidence dir), `--out`. `replay_holds.py compare` gains `--config` (to read `delivery_path` for the voiced check; default as `run`). Task 7a/7b Files lists name `scripts/taper_probe.py` and `scripts/test_taper_probe.py` where they change them.

D21. Wording: "Set 4–9" → "set 4 or higher"; empty set = a numbered or encore header with no song items before the next numbered/encore header (continuation headers and header lines carrying inline songs are not empty); matching = `fuzzy_title_eq(fuzzy_norm_title(a, aliases), fuzzy_norm_title(b, aliases))` (check the real signatures in structure.py and state them exactly).

D22. Task 9: a pre-screen or acceptance finding that is a rule defect goes back to the owning task (fix on the branch, re-run the arms from Step 1); only then Checkpoint B.

D23. Task 6 `test_cross_check_failure_keeps_stored_llm_needs_llm` uses the `set 3, disc 2` form (paf2007-10-12 excerpt).

D24. Split Task 7: 7a "record fields, override stripping and scoring" (ShowReplay fields D5, `--strip-structure-overrides`, compare refusals, `taper_probe.py score`); 7b "reports" (`taper_cleared.txt`, `taper_changes.txt` with tiers incl. `labels renamed`, voiced via `--config`'s `delivery_path` and `cli._destination_is_voiced`, unreplayable/slfm-miss section, needs-LLM split, stored-llm moved shows with segue changes, the `taper` note group). Renumber later tasks' references accordingly (keep Task 8/9 numbers; 7a/7b are fine).
