# Plan revision decisions (from two Opus plan reviews)

Plan: /Users/shawn/projects/llama/docs/superpowers/plans/2026-11-06-adjudicator.md. Spec (authoritative):
docs/superpowers/specs/2026-11-06-adjudicator-design.md. Keep the plan proportionate: signatures, test
names and assertions, not bodies. Add each new rule's test to its owning task.

## Strict surface
P1. Switch bar (Task 5): add the part "`overrides.recording` is None", else propose-only ("changes an
existing overrides.json entry"); add `break_it="existing_pin"`.
P2. "Adds tracks or titles" moves into post-switch coverage (Task 6): the post show has more tracks or
more resolved titles than the pre show. Drop the selection.json `kept_tracks`/`title_fraction`
comparison (it compares different measures).
P3. Coverage "added duration" formula (Task 6): post sum of durations of tracks that are unresolved or
short_kept, minus the pre sum of the same, ≤ COVERAGE_ADDED_MAX_S (60). Pin 60 / 60.01.
P4. Long bar (Task 5): drop the "track position" alternative entirely (per-disc numbering makes it
collide); require the normalized filename stem as a token-bounded match (not an unanchored substring);
tests for the `d1t1` vs `d1t10` collision. Record under Ambiguities as "stricter than the spec".
P5. Filler exemption (Task 5): a title counts as filler only when every segue component (split on `>`
and `->`) is filler; test "Tuning > Promised Land" stays propose-only.
P6. Title- and structure-kind overrules (Task 5) use the same evidence-kind rules as `set_title` /
`structure` (taper-side for structure; sibling-with-match, taper description, or own tag for titles).
`flag_passes` for title/structure kinds requires a passing `overrule` edit for that flag; a bare
judgement fails. This feeds re-hold and silenced-flags.
P7. Apply the silenced-flags check to switches too (spec gives no exemption); scope the subject-less
structure overrule deferral to verdicts with a track-list edit (as the spec says), not structure-only.

## Accept
P8. Accept mode (Tasks 6/7): silenced flags count as accounted for when the verdict judged them
`spurious` or `real-fixed-by-action` at any confidence (Shawn's acceptance replaces the bar).
P9. Accept staleness (Task 7): capture the view first and compute the digest from that same state; the
unit gets that view as `expect`. Race test: the show changes between the check and the write → refuse.
P10. Accepted switch (Task 7): runs coverage's title and duration rules (not the held rule); on failure
restore and print `llama fix <slug> --recording <id>` as the deliberate override. Replace Ambiguity 8.
P11. Accept outcome table (Task 7): define the outcome for restored (diff / silenced / coverage),
refused (station), transient, ShowChanged and RateLimited; on any non-commit the stored proposal record
is left unchanged.
P12. Applied-but-still-held (Tasks 6/7/8/10): the record stores the remaining flags with the verdict's
judgements as a proposal (overrules of the leftover flags); triage renders it and offers [a]; the
run report lists these shows under held-with-proposal.

## Pilot and rollout
P13. Task 7: `adjudicate_show` takes `trial_policy: Callable[[Verdict, GateResult], bool] | None`,
decided after `evaluate`: dry-run record otherwise, trial apply-and-restore when the policy says so. Task
11 uses it (one LLM call per show).
P14. Task 11: the meter reader is injected; tests monkeypatch it and one test asserts it is never called
unpatched (scripts/ tests don't get the llama conftest).
P15. Checkpoints: an operator checkpoint after Task 7 (core done, before CLI wiring) and a final one after
Task 11: the pilot runs from the worktree against ~/.llama only with Shawn's go (it performs trial
applies), then the acceptance bar, Shawn's model decision and any propose-only demotions, all before
merge/release/install. Implementers never run the pilot.

## Hooks, reporting, interfaces
P16. `redo --run --from search|winnow` passes `redo`'s own `--adjudicate/--no-adjudicate`. `run approve`
keeps following the config value; list it under Ambiguities as "hook point beyond the spec's list, for
Shawn's sign-off".
P17. `delivered_changed` = delivered and the pre-apply digest differs from the post-apply digest (covers
venue edits and overrules). The report lists marked shows whose campaign record ends processed under
"eligible for `llama deliver --fixed`", and the rest with `llama deliver <slug> [--replace-voiced]`.
P18. Adjudication pause inside `_execute`: track adjudication-pending shows separately and re-adjudicate
them on resume without re-running `_process` (no double count). RateLimited in adjudication under
`--no-pacing`: the show counts as held, unjudged (not failed). State the exit code on a pause (same as
reapply's).
P19. `--dry-run` does not overwrite a proposal or applied record unless `--force`.
P20. Mutation lists (Tasks 5, 6): add, each with its predicted red test: `quote_ok` removed/always true;
quote checked against any section instead of the claimed kind; the existing-overrides propose-only rule;
REFUSED_INCLUDE_REASONS; the structure taper-side requirement; the venue existing-override rule; the
existing-pin switch rule; kept-set exactness; coverage missing-title; coverage total-duration; coverage
added-duration.

## Small fixes
P21. Task 3: `escape_braces` uses a regex that breaks every adjacent brace pair (`\{(?=\{)` and
`\}(?=\})`); add a triple-brace case; `quote_ok` normalises the same way. Expected track values come from
the fixture (d1t01 is 664 s), not literals like 612; don't assert `matched=True` without a setlist.
P22. Task 4 prompt: "copy each flag verbatim from the review-flags section"; the prompt test checks the
phrase.
P23. Interfaces: `field(default_factory=list)` for list defaults; `_adjudicate_after` return type
includes None; `write_outside_unit` returning False → outcome CHANGED; lineage lookup uses `.get`, an
unknown class counts as worse (propose-only); `_sets_from_breaks` takes 1-based positions; `_execute`
resolves the CatalogEntry via `_resolve_show(config, ledger, slugify(pid))`; import the two
`read_record`s under aliases; Task 8 tests use the full `fake_providers` (the apply's redo needs every
stage key).
P24. Accepted limitation (one line, Task 6): a restore after a successful package leaves a ledger
`selected` row (outside the snapshot; pre-existing behaviour); the pilot's byte-identical claim excludes
the ledger.

Reply with: each decision and where it went; anything not applied cleanly; new line count.
