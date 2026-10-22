# t7a-rev: Task 7a review (63c4a4b..a8950fa). Status: DONE (verdict: Needs fixes)

### Spec Compliance

- ❌ Issues found (2):
  1. **Renumbered rows are never graded, but strip mode exists to grade them.** `scripts/taper_probe.py:695-696` puts every `renum` row in "owned, renumbered target (not graded)". That copies the gate, but the gate read pre-adjudication track tables. Strip mode does not have that limitation. Spec Measurement 1: strip mode "strips only `overrides.set_breaks`/`encore_after`, keeping excludes, includes and titles, since the adjudicator's targets are in post-exclusion numbering". Keeping the includes and excludes is what lets these rows be graded. I read the library's `overrides.json` for the yes/partial rows (read-only). Of the 73 `renum` yes/partial rows, **55 (45 yes, 10 partial) hold the adjudicator's applied fix**: the include/exclude, plus `set_breaks`/`encore_after` equal to `sort1`'s `t_breaks`/`t_enc`. The stripped replay of those 55 is in the target's own numbering. As written, about 55 rows the spec expects graded drop out of match/miss without notice.
  2. **Four of the 8 known disagreements can never be UNEXPECTED, though the spec text is stricter for three of them.** See `scripts/taper_probe.py:625-635` (table) and `:663-665` (the `ships` branch, always "as expected"). The spec paragraph (lines 96-99) says: "with no taper encore marker its last set runs to the end of the tape unless section 2's veto applies". That holds for all 8, but the checker applies it only to the three `no-encore` slugs. The evidence shows:
     - `stevekimockband-2003-03-11`: `desc_labels` is `['1','2']` and the description has no encore marker. If it is owned with an `encore` label, that breaks the spec, yet it scores "as expected".
     - `deadandcompany-2018-06-16` (`Disc II 1st Set Con't | Encore:`) and `ekoostikhookah-2009-12-31` (`Set I:|E:`): one numbered set plus an encore. §2 says "A single numbered set, or an encore marker alone, asserts nothing", so if either is **owned**, that is a reader defect. Both score "as expected".
     - Only `gratefuldead-1981-12-31` (`Encore aka Electric-3:`) is ambiguous enough for the lenient check.

     Fix: give each of the four slugs its own kind (`no-encore` for stevekimock; a new `not-asserted` kind for the two single-set rows, owned → UNEXPECTED). Keep `ships` only for 1981-12-31.
- ⚠️ Cannot verify from diff:
  - That Task 4's `GatherResult.taper`/`step1_alignment` are set the way the brief assumes. The test exercises them end to end, which is enough here.
  - Whether Task 9's run will use `--all` or `--slugs` covering the 394 rows. With the default `--held` scope, non-held rows read "absent from arm".

### Checks run (named risk → check)
- Writes into the live show dir or `~/.llama` in strip mode → read `_shadow` (`scripts/replay_holds.py:103-126`), `compute_legs`/`replay_show` (`packages/llama/src/llama/replay.py:297-363, 447-482`) and `derive_state`.
  - The shadow lives under `<scratch>/.shadow/<slug>`, and `run` already refuses a `--scratch` that overlaps the library root.
  - `d` is only read, with `copyfile` and `read_text`. `compute_legs` writes only into `show_scratch`, which is a sibling of `.shadow`, so `compute_legs`' shows-dir refusal does not trip.
  - The test hashes the live overrides file before and after.
  - Verdict: safe.
- Is the shadow a faithful copy → listed every file the replay reads:
  - `compute_legs` reads overrides, provenance, show, vetting, briefing.json and `read_overrides`. `replay_show` reads the same set. All of them are copied, or rewritten in the case of overrides.
  - Not copied: `research.md`, which is only digested and never read, and `package/manifest.json` plus the stage files, which `derive_state` reads.
  - `notes.json`, reviews and the ledger are not read by the replay.
  - The one dependent value is the shadow's `derive_state`. It feeds `classify` before the reset, but `classify` only tests `== "held"`, and that comes from the copied `show.json` (`catalog.py:120-123`). Outcome is therefore unaffected.
  - Verdict: faithful.
- Is resetting `state` and `digests` to the real show's sound → yes, and nothing is masked.
  - The strip transform is a deterministic function of the real `overrides.json`, so the real digest still identifies the input.
  - `research.md` is not a replay input.
  - The docstring's stated purpose ("comparable with an unstripped base", `replay_holds.py:132-133`) is moot, because `_gates` refuses mixed arms (`:311-312`). See Minor 1.
- Can a stripped arm reach `reapply --from-list` → no.
  - Lists are written only when `cand` is unstripped (`:851-857`), and a mixed pair is refused before that.
  - The existing `OUTPUT_FILES` unlink (`:808`) removes stale lists, and the test pins this.
  - The digests matter only to `_gates` and to `_list_row`'s `input_digests`, and the latter is never written for stripped arms.
- Grading against `sort1` →
  - `compare_filler` matches the gate's `compare` (filler flags from the arm instead of `is_filler(title)`).
  - `target_labels` and `breaks_of` are reused.
  - `apply_vet` never changes `Track.set` (`vet_research.py:308-321`), so pre-vet `sets` equal the shipped labels.
  - `OUT_OF_SCOPE_PRIMARY` strings match the `classified.jsonl` values.
  - `gratefuldead-1970-05-15-spans`: the library flag really is `tape spans 2 events` and the row is held, so the check is right.
- Base-arm compatibility → `_gates` reads `bool(.get(...))`, so a missing key counts as unstripped (tested). `score` refuses an unstamped arm, and no compare code reads the new row keys. Correct.
- Global constraints → `git diff main -- packages/llama/src/llama/setlist.py` is empty. A grep of the diff for the protected names and the do-not-retune constants found no hits. The only existing test changed is `test_show_replay_to_dict_has_the_contract_keys_plus_date`. No new `llama` flags or config keys.

### Strengths
- Strip mode works as the spec describes: a script-side scratch transform, stamped in the arm, never a `compute_legs` parameter. `test_strip_mode_removes_only_structure_overrides` spies on the real `replay_show` input and checks the shadow's location, the live file's bytes, the stamp and the digests.
- The compare refusal is tested in both directions, plus the base-code (missing key) case and stale-list deletion.
- `score` refuses an unstamped arm and an `--out` that overlaps the arm's root. It keeps the known disagreements out of the headline numbers and lists every miss, decline and ungraded row.
- The `replay.py` change is purely additive: six fields with defaults, filled only on the success path, so an unreplayable row keeps the defaults.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. `scripts/taper_probe.py:695-696`: renumbered rows are never graded (spec issue 1 above). Fix:
   - Have the stripped run record what it stripped on the row, e.g. `stripped: {"set_breaks": [...], "encore_after": N}` in `_replay_stripped`. That is also useful audit data behind the stamp.
   - In `score`, grade a `renum` row when the stripped values equal `sort1`'s `t_breaks`/`t_enc`, meaning the adjudicator's fix with its renumbering edits is applied. Keep "not graded" for the other 18.
   - Test both branches.
2. `scripts/taper_probe.py:625-635, 663-665`: the known-disagreement encoding is weaker than the spec for stevekimockband-2003-03-11, deadandcompany-2018-06-16 and ekoostikhookah-2009-12-31 (spec issue 2 above). A reader defect on these rows would score "as expected" in an acceptance measurement.

#### Minor (Nice to Have)
1. `scripts/replay_holds.py:132-133` and the implementer's rationale: "so arms stay comparable with an unstripped base" can never happen, because `_gates` refuses a mixed pair. Reword it as "the row carries the real show's state and input identity". The behaviour is fine.
2. `scripts/replay_holds.py:131-144, 271`: `_shadow` runs outside `replay_show`'s never-raises guarantee. An `OSError` on one show's copy or read aborts the whole run, where an unstripped run would record that show unreplayable. If `derive_state(real)` or `input_digests(real)` raises, the swallowed exception leaves the shadow's state or digests on the row without notice. Catch per show and record `unreplayable`.
3. `scripts/taper_probe.py:718-725`: the summary's "in scope (not filename / track-tag)" uses a different definition from the `in_scope` field on every row (the gate's yes ∧ worded ∧ desc primary), which is computed and never summarised.
   - The headline mixes yes and partial rows, plus the 41 encore-only rows that are expected to decline.
   - The spec's check is "most in-scope `yes` rows match", so add a headline over `row["in_scope"]` and a yes/partial split, or rename the label.
4. `packages/llama/tests/test_replay.py` `test_record_carries_taper_fields` pins neither the `filler` derivation (it only checks `isinstance(bool)`; `[False]*n` passes) nor the `state` reset in strip mode. The only stripped show tested is held, where shadow and real state agree. Add a filler title to the fixture, and a packaged show to the strip test.

### Assessment

**Task quality:** Needs fixes

**Reasoning:**
- Strip mode, the arm stamp, the compare refusals and the record fields are correct and safe. Nothing can write into the library or feed an apply list.
- `score` as written does not fully deliver Measurement 1:
  - It drops the roughly 55 renumbered rows that strip mode keeps excludes and includes precisely to grade.
  - Its known-disagreement checks are weaker than the spec for 3 of the 8.

Commits: none (reviewer). Tests: none run; read-only library inspection only (`overrides.json` and `show.json` of the 394 yes/partial slugs, nothing written). Log: $D/t7a-rev/t7a-rev.log.
