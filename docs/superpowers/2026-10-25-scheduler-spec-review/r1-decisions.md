# Round-1 decisions for the scheduler spec (apply exactly)

Source: three reviews (S = strict Opus, F = breadth Fable, O = breadth Opus). All Foundation SOUND.

## A. Frozen prefix and re-planning (S1, F1, O1, F16) — class L
A1. Add a definition in "Planning" (new first bullet, "The frontier") and reference it from Stakes:
  - Let R = max(`PublishState.listed_bound()`, the highest segment index with a file in `render/seg/<epoch>/`). Publish deletes a local segment file once its horizon is confirmed, so files alone are not evidence; `listed_bound` covers those.
  - A row is **frozen** when it overlaps any segment at or below R. A row spanning the boundary is frozen whole. Encode presence is irrelevant (an ID clip's encode is shared by many rows).
  - Every plan step truncates the plan to the frozen rows and re-plans everything after them from the current clock, library and history. So a clock edit needs no detection; it takes effect at the next plan step for every row not yet frozen.
  - The first new row starts exactly at last-frozen.end + gap (or at the run start for a fresh run), as `replan_from` does today. A re-plan may never start earlier than that.
  - `plan_step`'s early return ("plan already covers until_frame") must not skip the truncate-and-re-plan; the builder decides how often a plan step runs, but a step that runs re-plans the unfrozen tail.
  - The frozen-prefix tests include a state where published segments' local files have been deleted, and a state where rendered segments are unpublished (publish stopped: guard trip, budget).
A2. Replace "Clock edits reach air after the frozen prefix, so within about one lead (24 h). This is phase 1's existing property and does not change." with: "Rows after the frontier are re-planned at every plan step, so a clock edit reaches air once the frozen prefix (at most about one lead) has aired. Phase 1 never re-plans persisted rows; this is new."
A3. Persistence bullet: drop the "except a block committed with its announcement" clause (see D1).

## B. Gap layout invariant (S3, O6) — class L
B1. In "Planning", pin the layout: every non-run_start row starts at the previous row's end + `gap_frames` (the configured inter-show gap), interstitials included. A boundary with an interstitial is therefore show, gap, clip, gap, show. Asserted whenever new rows are written (not on load, so plans written under an earlier `show_gap_seconds` still load). Replace the Stakes wording "Every gap is the configured inter-show gap, plus an interstitial when one is placed" with a pointer to this rule.

## C. Estimates vs exact (F2, O4, F8, O7) — class P
C1. Replace the "Exact timing" bullets with:
  - Each piece carries its exact frame count when its analysis is cached, else an **estimate**: the manifest's `total_duration_sec` plus each DJ clip's length from its file size at emcee's 64 kbps, (the sizes `file_set_key` already stats); for `--library delivered` on unvoiced packages, a flat 4-minute clip allowance. Estimates are cached by file-set key and marked as estimates.
  - The scheduler is pure **for given lengths**: preview and live agree when they see the same cache state.
  - A plan step: run the scheduler on best-known lengths; analyse the pieces whose rows it is about to write (those up to `until_frame`); substitute exact counts; run the scheduler **once more** with them; write. No further iteration: if exact counts now push a block outside its window, that is a miss. Written rows always carry exact frame counts, never estimates.
  - Analysis per step stays bounded by the rows written (the service's existing `max_new` pacing stands). Analysing the rest of the eligible library to replace estimates is background work whose pacing is the builder's call; the watchdog keeps being fed.
  - `total_duration_sec` counts an unmeasured track as 0; such a show is under-estimated until analysed. Accepted.
C2. Unverified premise to record (test in the plan's first task, on hugo): estimates land within seconds of decoded counts (compare `~/.transmitter/cache/` analyses with the estimate), and one cold analysis's duration on hugo.

## D. Announcements (O2, F9, F10, O10) — class P / D
D1. REMOVE the "Locked with its block" bullet and every trace of commitment (persisting a block past the lead, "committed rows", commit in the same plan step, `plan.jsonl` past the lead). Replace with:
  - "**A promise kept where possible** (operator ruling 2026-10-25: a promise, not a guarantee). Every block is already planned to land the next block in its window, which is exactly what an announcement promises, so no lock is needed: the block the announcement names is re-planned like any other until frozen, and the scheduler's own objective keeps the promise unless the library or clock changes. An announcement whose promise breaks anyway (the named block starts outside its window or degrades to open time) is logged `announcement-broken` and recorded in history, not alerted."
D2. Placement and wording. Two templates replace `one`/`two`:
  - `next` (at the boundary into block X): names X as starting now and, when it qualifies, the block after it with its nominal time. Default: "Coming up next, {title}. Then at {next_time}, {next_title}." and a one-block form "Coming up next, {title}.".
  - `later` (at a show boundary inside the block before X, when there is one): names X with its nominal time and, when it qualifies, the block after. Default: "Stay tuned for {title} at {time}, followed by {next_title} at {next_time}." and a one-block form.
  - Selection: X untitled → no announcement there (a station ID). The block after X untitled or degraded to open time → the one-block form. A two-block form failing only on the second block → the one-block form, not an ID.
  - Truthful at placement: X (and the second block when named) must, in the plan being written, start within its window and on its own profile. The second block's profile is a prediction made when the announcement is placed (accepted limitation, counted under `announcement-broken`).
  - The finite-set and hashing text stays (both templates, both forms).

## E. Rotation precedence and noise (O3, O13, F14) — class P
E1. Add to "Selection score and rotation rules": "**The compromise order outranks every rotation rule.** Rotation rules only rank options within the same tier: a block filled from its own profile always beats one that keeps a rotation rule by using fill."
E2. Replace "Rules a block's own pool makes impossible don't count as bends" bullet with: "A bend is counted only when an option that kept the rule existed in the same tier and was passed over. A rule the pool makes impossible (a single-artist Dead pool cannot avoid the same artist twice a day or in a pair) is not applied within that pool at all, and is not a bend. The same holds for the concert gap when the pool's eligible airtime is shorter than the gap: least recently aired first still applies."
E3. Fix the soft-launch figure: "roughly 80/20 Dead/funk" → "roughly 60/34 Dead/funk by voiced airtime (about 22 days of audio in all)".
E4. Goals 3 wording: make step 1 the primary objective, not a compromise: "Within the block's own profile, choose shows so the next block starts inside its wiggle room (closest to nominal is best). When that is impossible, compromise in this order: ..." with the remaining two steps (fill from the open pool; a miss).
E5. Fill reporting: `schedule`/`status` report fill minutes split by cause: "pool short" (the block's own pool could not fill it) and "longer than max_shows" (structural: the block is longer than `max_shows` of its shows can fill). Only "pool short" is a compromise.
E6. Empty pools (S5): an empty open pool bends `[open] exclude_profiles` last; `PlanError` only when nothing at all is eligible.

## F. Compatibility (F3, O8, F4, S6, O5, F15) — class P
F1. Keep `[planner] seed`: it becomes the scheduler's deterministic tie-break (`shuffle_rank(seed, slug)`, as phase 1). Retiring `choose_next`/`extend` must not remove the config key. Also `start_delay_minutes` stays.
F2. Plan rows: `PlanRow.from_json` ignores unknown keys (the project's permissive-persisted-state idiom). This lands in the plan's first deployable task, deployed to hugo before the scheduler, so a later rollback lands on a reader that tolerates scheduler rows. The runbook names that commit as the oldest safe rollback target, and says never to truncate `plan.jsonl` by hand.
F3. Rows carry what history needs at decision time (O F12): at least `kind`, `block`, `nominal_start`, `miss`, `bends`. (Name them as the minimum; field detail is the plan's.)

## G. Interstitials below the scheduler (S2, F6, O6, F7, F13) — class L/P
G1. In "Program pieces", list the package-shaped touch points as required work: render-time re-validation (looks rows up in the station scan by slug), `service.row_analysis` (re-evaluates `root/row.dir`), the publisher's per-slug notes/page loop, `build_timeline`'s `recent`, and `PlanRow.dir`'s meaning.
G2. Interstitial rows re-validate against the interstitials folder (file present, same file-set key, past the quiet period). A failing clip is removed from the interstitial pool for the rest of that call and its boundary re-planned without it. One `render_step` call has a hard cap on re-plans (a re-plan that writes no segment cannot repeat without bound); exceeding it fails the step (alerted).
G3. Timeline: interstitial entries carry `kind: "interstitial"`, are excluded from the notes/page publishing loop and from `recent`, and the player treats them as a break showing the station name (a small `antenna/public/` change). R2 writes stay as phase 1's.
G4. Folder: default `<station root>/interstitials/` (no `manifest.json`), configurable. Verified invisible to all three scanners: transmitter `station.py:226`, emcee `station.py:323-326`, llama deliver touches only `<dest>/<slug>` and never lists the root (`cli.py:2300-2385`); also `scripts/backfill_voiced_by.py:42`. Remove "The builder verifies this and records it" and the "outside every scanner's view / both can reach" uncertainty; keep "transmitter only reads this folder". Remove the "move them to the Mac" step if the export can target the folder directly; keep `--export DIR` as an explicit operator write.
G5. Frame model for single-clip pieces: unverified premise; the plan tests `planned_frames` against a real encode of an ID clip.

## H. History (F11, O-aired) — class P
H1. `aired.jsonl` rows are appended only for rows that were published: end at or before the end of segment `PublishState.last`, and at or before now. A row cut by recovery records its cut end. Identity is (epoch id, start_frame); the appender adds only rows not already present, so restarts never double-append. Backfill uses the same rule.
H2. `plan.jsonl` trimming is the builder's call, constrained: never trim a row the timeline's 24 h window or the frozen prefix still needs.

## I. Clock file handling (S4, O9) — class P
I1. The clock is read at every plan step (not only at start). An invalid `clock.toml` fails the step with an alert and leaves the plan untouched; the published lead carries the station while the operator fixes it. `schedule --clock <file>` is the way to check an edit before moving it into place (runbook). `status` says "no clock: open all week" when the file is absent.

## J. Status cost (O14) — class P
J1. `status`'s next-24 h figures come from persisted plan rows only; `status` never runs the scheduler or scans the library.

## K. DST (O15) — class P
K1. A block occurrence that resolves to zero length (spring-forward collapsing two starts) is dropped; tested.

## L. Measurement (F5, O12) — class P
L1. Replace the baseline bullets: the parent's `feasibility-sim.py` needs edits before it can serve: station root as an argument; separate "overran" and "not fillable" counts (it currently folds overruns in as a ×1000 weight and prints one figure); the same length estimate the scheduler uses; its fill exclusion (`dead`, `funk`, `dead-family`) expressed in clock (a) as `[open] exclude_profiles`. Commit the edited script beside the evidence doc. Run the scheduler over at least 50 consecutive weeks with history accumulating (one week is 22 block starts, too coarse), against the naive script's 50 seeds.
L2. Note the parent's two-column table came from a variant not in the repo; the baseline is re-derived, not copied.

## M. Calls list
M1. Update "Calls made in this document": remove the announcement-lock call; add: frontier definition; one exact-count re-pass; `next`/`later` templates; bends counted only when a keeping option existed; seed kept as tie-break; tolerant row reader shipped first; interstitials folder inside the station root; clock read per step, fail-the-step on invalid.

## Rejected / not taken
- S4's "keep planning with the last good clock": rejected for simplicity; fail-the-step + alert + the lead is enough (I1).
- Sidecar file for new row fields: rejected; tolerant reader (F2) is simpler.
