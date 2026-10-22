# t7b-rev: Task 7b review (spec + quality), 4e17576..86e9886. Status: DONE

### Spec Compliance

- ✅ Spec compliant. All brief items are present: `compare --config` (scripts/replay_holds.py:1070), `taper_cleared.txt` and `taper_changes.txt` added to `OUTPUT_FILES` (:243) and unlinked as stale outputs, and a `taper` NOTE_GROUP placed before `5c.1` (:236) with the suffix rule (:548, `_is_taper_note`). The seven brief tests exist, plus one stripped-arm test. One tiering gap is raised as Important below: it is a spec-shape issue, not a missing item.
- The four fixed strings match the code. I checked them against gather.py:108 (`{count_flag} (taper's markers)`), :127-128 (closer note) and :1407 (`set breaks from the taper's markers (was …`). The plain 5c.1 closer note stays in `5c.1` (tested). Moving it out of `5c.1` does not touch `_closest`, which reads only the `1c`/`2a`/`4a` groups (:711-733).
- Global constraints:
  - `git diff main --stat -- packages/llama/src/llama/setlist.py` is empty.
  - The diff touches only `scripts/replay_holds.py` and `scripts/test_replay_holds.py`, so no protected name is touched.
  - The test file diff has no `-` lines, so no existing test changed.
  - There is no new `llama` flag or config key; the new option is on the harness only.
  - Nothing writes to `~/.llama`: `_is_voiced` calls `cli._destination_is_voiced`, which is a raw `read_text` + `json.loads` (cli.py:2300-2309).
- Judgement on the implementer's four calls:
  1. **Stripped pairs get no reports.** Agreed. Spec item 1 is the only consumer of the override-ignoring mode. Items 2 and 3 are about the shipped library, and their "stored" column comes from the unstripped `show.json`. The summary says so, and stale files are unlinked by the `OUTPUT_FILES` loop.
  2. **Label-derived breaks.** Agreed. They include encore boundaries, which `Show.set_breaks` (numbered sets only) would hide. They are also computable for the stored and base sides, where no `set_breaks` list exists per row. But see Important 1: breaks alone cannot express a relabel.
  3. **Tiers.** Mostly sound:
     - Non-filler comparison uses the candidate's `filler`, which is the post-gather `is_filler`, the same predicate gather uses at :1405.
     - A count mismatch counted as `songs moved` over-reports, which is the safe direction.
     - `provenance only` = labels equal, candidate owned, base not. That matches the spec. Base rows read `taper_owned` as absent, so every owned-but-unchanged shipped show lands here, as intended.
  4. **Stored-llm section.** Agreed in substance: the base `needs_llm` contains `"stored alignment llm"`, any state, and the string matches main's replay.py:330 exactly. See Minor 1 for the unreplayable case.
- "Before" fallback chain (`_before_labels`, :601-607):
  - base needs-LLM → stored labels;
  - else base `sets`;
  - else stored labels with base `set_changes` applied.

  It is correct against `replay.shipped_diff` (replay.py:185-226). On equal track counts only the changed indices are listed. On a count change every index is listed, with `new=None` past the replay's end, and `_apply_set_changes` drops those (probe: `['1','1','1']` with `[1→1, 2→2, 3→None]` gives `['1','2']`).

  Pre-vet `sets` against the post-vet `set_changes` is not a mismatch: `apply_vet` (vet_research.py:308-320) never touches track labels.

  Both fallbacks are tested: `test_taper_changes_before_is_stored_labels_with_base_set_changes` checks `before [2]`/`stored []`, and `test_taper_changes_counts_not_owned_needs_llm_rows` checks needs-LLM base → stored.
- Voiced check:
  - It is read-only.
  - Its destination matches `deliver`: `delivery_path / <show dir name>` (cli.py:2364-2367, :2430).
  - The `--config` default is `DEFAULT_ROOT / "config.toml"`, the same as `run` (:155).
  - A missing explicit `--config` gives the same `Refusal` text as `run`.
- ⚠️ Cannot verify from the diff: whether `classify`'s outcome set for held shows has any non-held outcome besides `CLEARING` + `structure-changed`. Spec item 2 says "held in base and not held in candidate", and the brief narrows it to those three outcomes. The controller should check that `classify` emits no other non-held outcome for a held show.

### Strengths

- The reports reuse the row fields Task 7a built (`sets`, `filler`, `taper_*`, `step1_alignment`) rather than re-deriving them, and treat base-arm absence correctly (`bool(b.get("taper_owned"))`).
- The voiced read is lazy: only a delivered row that reaches a tier triggers it, so tests never touch the home config.
- The before/after/stored triple on every row lets old-code drift be told apart from this piece's effect, as the spec asks.
- The unreplayable/slfm-miss section covers shipped shows in either arm, so nothing the rule could touch is silently absent.
- The summary lines give the operator per-tier counts at a glance.

### Issues

#### Critical (Must Fix)
(none)

#### Important (Should Fix)

1. **A set↔encore relabel at an existing boundary is tiered `labels renamed`, and the row cannot show it.** At scripts/replay_holds.py:616-625 and :666-670, `_tier` returns `labels renamed` whenever non-filler break positions are equal. A probe (read-only, importing the worktree module) confirmed:
   - `_tier(['1','1','2'], ['1','1','E'], …)` → `labels renamed`, the same tier as `['1','1','2']`→`['1','1','3']`.
   - The row prints only break positions, so before and after are identical (`before [2] after [2]`) and nothing on it says what changed.

   Why it matters: "set 2 becomes the encore" moves songs out of a set into the encore. That changes what the briefing says, and it is the "encore folded or added" kind the spec's gate singles out. Spec item 3's pre-screen covers every `songs moved` row but only a stratified sample of the rest, so these rows can escape review. At Checkpoint B the operator cannot tell a cosmetic renumber from a set-to-encore change.

   Fix:
   - Print the labels on each row, e.g. a compact run form `1x3 2x5 Ex1` for before/after/stored.
   - Either tier a change that crosses between a numbered label and the encore label as `songs moved`, or give it its own tier.
   - Add a test for the `2`→`E` same-position case.

#### Minor (Nice to Have)

1. **The stored-llm section can mislabel a broken show.** At scripts/replay_holds.py:690, any candidate outcome other than `needs-llm` counts as "now replayable", including `unreplayable`. A candidate-side exception, such as a bug in the new taper code, on a base stored-llm show would be listed as "now replayable" with `segue changes: []`. Fix: also exclude `outcome == "unreplayable"`, or print the outcome on the row.
2. **The voiced check can be absent or fail without saying so:**
   - At :628-638, when `delivery_path` is None every delivered row silently reads `[delivered]`.
   - A typo'd `--config` is refused only lazily, when a delivered row first reaches a tier. That happens after several reports are written and before `summary.txt`, so the run exits 2 with a partial output dir. Validate eagerly, as `run` does at :156.
   - Consider a summary line naming the delivery path used for the voiced check, or saying the check is off.
3. **The unreplayable section prints `[delivered]` without the voiced check** (:685). The spec's state triple applies to tier rows, so this is optional.
4. **`provenance only` rows print `overruled: <step1_alignment>`** (:670), though nothing was overruled when the labels are equal. Print it only when before != after, or rename the field `step1:`.
5. **Test hygiene in scripts/test_replay_holds.py:**
   - `_clone_slugs` (:963) takes an unused `arms_fn`, and its docstring claims cloning it does not do.
   - `cfg` at :973 is unused.
   - No test covers a delivered row without `dj_audio` reading `[delivered]` and not voiced, or the default-`--config` path.
6. **`_delivery_path` (:635-638) repeats `run`'s default-and-refuse logic** (:155-157). A shared `_config_path(arg)` helper would keep the two defaults from drifting.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The reports are correct, read-only and well tested against the spec's before/after/stored contract, and all four of the implementer's calls hold up. However, the `labels renamed` tier folds a set-to-encore change into a tier the pre-screen only samples, and its rows carry no labels, so report 3 is not yet trustworthy for the operator at Checkpoint B (Important 1).

Checks run (read-only):
- `git diff main --stat -- setlist.py`: empty.
- `git diff 4e17576..86e9886 -- scripts/test_replay_holds.py | grep '^-'`: no removed lines.
- Probe of `_tier`/`_apply_set_changes` from a scratch cwd, with `llama.__file__` resolving into the worktree; output is in t7b-rev.log.

No commits, no repo edits.
