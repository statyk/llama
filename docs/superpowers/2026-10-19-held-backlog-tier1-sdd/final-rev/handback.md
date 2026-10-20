# Final whole-branch review: held-backlog-tier1 (f1744ad..030caa7)

Reviewer: final-rev (Fable). Read-only; no commits, HEAD untouched, nothing written under `~/.llama`.

## Method

Reviewed in passes over the package diff (15,986 lines): (1) plan Global Constraints / Contracts / Recorded-at-B..F blocks, spec Stakes/Rulings/Slices 1-7/Constants/Testing, all four ledgers' "minor (deferred" / "Ruling:" lines and HANDOFF sections; (2) the apply surface — `reapply.py`, `cli.py` (reapply names + list forms, `--untitled`, triage `[u]`), `replay.py`; (3) the guard code — `gather.py`, `vet_research.py`, `brief.py`, `structure.py`, `titles.py`, `placeholders.py`, `jerrybase.py`, `siblings.py`, `package.py`, `workspace.py`, `models.py`; (4) `scripts/replay_holds.py`, `test_reapply.py` in full, test names of every other test file, CLAUDE.md/README diffs. Code outside the diff inspected only for named risks: `ia_client._cached` (cache immutability), `pipeline.process_show` (gather call parity), `workspace.drop_stage_artifacts`, `catalog.derive_state`, `cli._edit_overrides`/`_clear_hold`/`_redo_show`/deliver's `copytree`, `package.build_package`'s download loop.

Independent verification run from the worktree venv (`llama.__file__` resolves inside the worktree): `./.venv/bin/python -m pytest -q -p no:cacheprovider` → **3761 passed, 1 skipped, 8 deselected** (matches the orchestrator's count at 030caa7). Tree clean after. Live probes (in a scratch dir, nothing in the tree) of `_claim_counts`, `_sets_from_breaks`, `shipped_short_tag`, `is_placeholder_text`, `venues_equivalent`, `cities_compatible`, `normalize_date`/`day_unknown_date`, and a partial-write-then-rerun of `reapply_show` with a list row (see I4 and Strengths).

Do-not-retune constants: grepped every `+`/`-` line of the diff for `_RECOVER_BELOW`, `_RECOVER_SIBLING_ABOVE`, the tail-guard trio, the junk-duration trio, `align_coverage_threshold`, `_ENUMERATED_MIN_*`, `_STRUCTURE_PREFIX`, `_FOOTNOTE_TAIL`, `_TRACK_NUM_PREFIX`, `is_real_title`, `title_fraction`, `normalize_song`, `DEFAULT_ALIASES`, `GD_SHORTHAND`, the sibling-transfer four, `lookahead=8`. **None moves.** `junk.py`, `songs.py`, `correspondence.py`, `config.py` are untouched. Only brief-local / titles-local new names appear (`_BRIEF_STRUCTURE_PREFIX`, `_GLUED_FOOTNOTE_TAIL`).

## Strengths

- **The apply is genuinely the harness's computation.** `reapply_show` calls `compute_legs` + `classify` and nothing else decides; the same `CacheOnlyIA`/`setlistfm_client(config)` choice; `load_list` pins SHA (refusing `-dirty` on either side) and config fingerprint. I checked the one way prediction and apply could still diverge — the archive.org/setlist.fm caches — and `ia_client._cached` never rewrites an existing file, so a cache that produced the arm produces the apply.
- **Write order and partial-failure contract are right and pinned.** `vetting.json`, `notes.json`, `briefing.*`, package, `show.json` last; lock held from the still-held check through the last write (`test_reapply_holds_the_show_lock_throughout`, `test_the_show_lock_is_held_when_the_row_digests_are_checked`). My probe: after a fresh brief + a package download failure, `input_digests(ws) == row["digests"]` still holds (vetting.extraction hashes only the extraction) and the list re-run completes the show by **reusing the just-written briefing** — one Opus call total, not two. The spec's resumability claim is true, not just asserted.
- **Nothing is written on needs-LLM, dry-run, refusal, not-held or changed-digests**, pinned with byte snapshots (`_snapshot`/`_stale`).
- **Narrow-beside discipline is real.** `_venues_equivalent_pre1b` is a frozen copy with its own tables; `_GLUED_NUM_PREFIX`, `_BRIEF_STRUCTURE_PREFIX`, `_ENCORE_MARKER`, `_CORE_TAIL`/`_SHIPPED_TAIL` all sit beside the protected predicates. `resolve_titles` demotes placeholders before the positional `setlist` rung and the rung itself refuses placeholder items (11b).
- **Ruling 6 (notes never reach the LLM) is structurally enforced**: `op_notes` is a separate list from `notes` (structure.conflicts) in `compute_gather`; `filler_tail_closers` is a separate producer from `closer_contradictions`' soft list; `ShowNotes` is read only by `cli._read_show_notes`.
- **5c.2 removal is clean** (grep shows no residue), and the plan records it.
- The harness's IO discipline (`_check_identity`, overlap refusals, `OUTPUT_FILES` clearing, exit 2/3 gates, read-only-root test) is exactly what a tool that runs beside a live library needs.
- Checkpoint rulings are recorded in the plan with the measured numbers; the rejected-D/E lists are the operator's and G drops them mechanically.

## Issues

### Critical (Must Fix)

None found. No finding would make the Checkpoint G apply write a wrong title/venue/date/structure from the *predicted lists*, lose operator data, or move a do-not-retune constant.

### Important (Should Fix)

**I1. `_SCOPE_AFTER` crosses the briefing-field boundary (loosening; on the strict surface for fresh briefs).**
`packages/llama/src/llama/stages/brief.py`, `_SCOPE_AFTER = re.compile(r"^\s*(?:each|every|a|per)\s+(?:night|day|weekend|tour)\b", re.I)` used in `_qualified`. `\s*` matches the `\n` that `_guard_prose` uses as the field boundary, so a count/ordinal claim at the END of one field is suppressed when the NEXT field starts with `A night…`, `A day…`, `A tour-…`, `Each night…`. Probe: `_claim_counts("The band played two sets\nA night to remember")` → `(set(), {})`; with a period instead of the newline → `({2}, {})`. This is the exact mirror of the negation-window bug fixed in Task 14 round 1 (`_CLAUSE_BREAK` includes `\n`; `_SCOPE_AFTER` does not). Direction is *fewer* holds: a fresh briefing claiming "two sets" on a three-set show passes the guard if the following field happens to start that way, and the pre-branch guard would have caught it (spec Stakes: "wrong … set structure that the old guard would have caught").
Fix: `r"^[^\S\n]*(?:each|every|a|per)\s+(?:night|day|weekend|tour)\b"` plus one test row.
**LOAD-BEARING FOR THE APPLY: borderline — yes in kind, low in probability.** Stored briefings reused at G were hand-read at D and every 3c suppression was listed in `briefings.txt`, so reuse rows are covered. The ~250 FRESH briefs at G are "checked by guard, not read", and this hole is live in that guard. The phrase shape is uncommon but not contrived (`per_set` points and `notable_moments` are short sentences; "A tour-closing…" matches via `\btour\b`). A one-character fix plus a G1 re-measure costs minutes (the F2 arms took ~2 min); I recommend fixing before the waves rather than after. The executor rules.

**I2. `fix --untitled` / triage `[u]` can ship a fabricated encore.** `cli._untitled_resolution` calls `_edit_overrides(ws, set_titles=…, narration="vague", set_breaks=[])` and leaves a pre-existing `overrides.encore_after` in place. Probe: `_sets_from_breaks(5, [], 3)` → `['1','1','1','encore','encore']`. The confirmation text promises "one set"; the manifest then carries two labels on a tape with no titles. Rare (an encore override on a wholly unresolved tape), but it is operator data producing a wrong structure after a prompt that said otherwise. Fix: pass `clear_encore=True` in that call (the flag `--clear-encore` is already refused, so clearing internally is consistent) and assert `ov.encore_after is None` in `test_untitled_one_confirmation_writes_titles_narration_and_one_set_then_redoes`. Not load-bearing for the apply.

**I3. Names-form `llama reapply <show>` applies a structure-changed show silently as `-> cleared`.** `reapply.py` `_PREDICTED["structure-changed"]` is used only for `--dry-run`; the real apply treats it like `clears`. Spec slice 6: a structure-changed show "joins the apply only once checked". The list form is safe (predicted_list carries only clears/needs-brief; structure_changed_list is a deliberate operator choice), but an operator naming a show gets no signal that sets/segues/breaks moved. Fix: print `reapplied: {slug} -> cleared (structure changed: set_breaks …)` or refuse without `--allow-structure-change`. Not load-bearing for the apply (G is list-driven; the orchestrator excluded structure_changed_list from the waves).

**I4. A `held` outcome rewrites `show.json` but leaves a now-stale `briefing.json` beside it.** When `legs.brief == "none"` (flags remain) and shipped fields changed (e.g. a 2a/2b title), `reapply` writes the new show.json and leaves the stored briefing (generated against the old titles). A later `llama fix --overrule` → `redo --from package` ships that briefing unchecked (package does not re-run `briefing_guard`). Before this branch a held show's show.json and briefing.json were always from the same gather. Fix options: on `held` with a shipped-field diff and a stored briefing, `drop_stage_artifacts(ws, "brief")` (costs one Opus call at the eventual overrule) — or at minimum document it in CLAUDE.md's reapply bullet. **Not load-bearing for G**: the only `held` outcomes G can produce from predicted_list rows are a fresh brief that failed its guard (the written briefing IS the new one) or a carried/new package flag (briefing consistent); any show whose inputs moved is skipped by the digest check.

**I5. `vet_research._date_flags(..., day_unknown: dict | None = None)` defaults to None.** (Deferred from 16b.) Both callers pass it today; a third caller that omits it silently drops every day-00 hold — the Checkpoint E decision. Make it a required keyword. Trivial; not load-bearing.

### Minor (Nice to Have)

- **siblings.py:88 (11b):** the placeholder refusal tests `is_placeholder_text(t.strip())` but adoption strips a trailing `>`; a donor title `tmp >` bypasses and could be adopted as `tmp`. Check the same stripped form the adoption uses. Cheap; title surface; should go in the fix wave.
- **`_reapply_list` catch-all arm prints `FAILED {slug}: {exc}` without the type**; a `RuntimeError("")` prints a blank reason. Use `f"{type(exc).__name__}: {exc}"` as `replay_show` does.
- **`reapply_show` ignores `row["outcome"]`/`row["briefing"]`.** With immutable caches this cannot diverge, but a one-line `skipped: prediction changed` when `classify` disagrees with the row would make the "prediction and apply cannot disagree" guarantee self-checking instead of argued.
- **Dry-run download count** uses "no manifest" — a delivered+held show (audio purged, manifest present) is undercounted; count rows whose `package/audio` lacks any manifest track instead. Affects the GB estimate only.
- `cities_compatible("York, PA", "New York")` → True (spec-mandated containment when one side is regionless); `("Austin, TX-USA", "Austin, TX")` → False (conservative). Both known from Task 12; leave, but the first is the loosening direction and worth a line in the operator notes.
- `_SHIPPED_TAIL` leaves `-`/`@`/`^`/`~` on a shipped 2a title (spec text), e.g. `Jam -` would ship as-is if it ever reached 2a (it does not: it passes `is_real_title`). Fine as ruled.
- `encore_lost` uses whole-tape membership (an encore repeating an earlier song reads as matched); conservative only in the sense of fewer flags — watch in G7's post-run diff.
- `_filler_excused` re-implements `closer_contradictions`' loop; `_second_closer_candidates` / `_short_track_arm` re-walk the set tail. One helper returning hard/soft/excused would remove the drift risk.
- `right_show_gate` recomputes `tape_known`/`unknown` that `grounding_flags` already has; pass them in.
- `run_vet_research` reads `notes.json` strictly (a malformed file fails vet); consistent with show.json, so acceptable.
- Docs (Task 22 deferred): pacing gate is list-form only; 1c needs a single-event date; needs-LLM also covers stored `alignment == "llm"`; README "its only LLM call" is up to two attempts; `OUTPUT_FILES` already includes the three lists. All accuracy, all cheap.
- `_date_flags` ordering / `('0/5/08' → '2008-05-00')` pin, first-surface-text de-dup of day-00 entries untested (16b deferred).
- Test hygiene carried from the ledgers (mid-file imports, `test_cities_not_compatible` one-direction asserts, `_two_arms` positional args, `logging.disable` restore in the harness): leave for the fix wave.

## Deferred-minor triage (every "minor (deferred" line in the four ledgers)

**Fix before merge (fold into the post-apply fix wave):** T14 `_SCOPE_AFTER` field boundary (I1 — and consider before the waves); T21 `encore_after` survives `--untitled` (I2); T19 names-form structure-changed message (I3); T16b `day_unknown` required (I5); T11b siblings `tmp >` bypass; T20 catch-all exception type; T22 docs accuracy lines; T21 `_untitled_resolution` return a status instead of the byte-snapshot trick (both call sites duplicate it) and add the untested decline/zero-track rows.

**Can wait (no behaviour change on the strict surface, or ruled residuals):** T1 (extract-with-provider negative pinned later in T4; unreachable tuple; strict notes read), T2 (fingerprint/capture test gaps; version fallback), T3 (dead `show` param — kept for brief-mandated signature), T4 (both-kinds held precedence untested), T5 (`--slugs` missing file traceback; herder not identity-checked; mtime-based helper test), T6 (hc_rows duplication, E731, non-dict arm row, untested report bodies, exit-2-removes-nothing test), T7 (state filter test, triple show.json read, unused params), T8 (docstring scoping, shared `{}` default), T9 (near-duplicate format loop, positions computed twice, `blind_tag_gapfill.py` drift), T10 (whole-core vetoes, docstring), T11 (comments, long import line, `52Nd Street` class), T11b (`.`/`!`/`?` endings; `\d+` footnote year strip), T12 (university strip pairs — 0 library pairs; containment — see Minor), T13 (notes survive an override; signature computed twice), T13b (live-`venues_equivalent` V residual — 0 pairs, operator chose; vacuous companion assert), T13c (summary wording), T14 (`_BRIEF_TRAILING` lacks `→`; `_suppressed_claims` not digest-gated; comment omissions), T15 (unused `y`, over-promising test name, NYE spill case hand-read at E), T16 (duplicated counts), T17 (`encore_lost` membership; `Encore Break` filler fires — conservative), T18 (helper duplication; 5c subsections read stored show.json — F readers were told), T18b (commit subject), T20 (concurrent writers of one list; `-dirty` stamped unconditionally by the harness — refused at load, so safe).

## Rulings I would question

- **"Fix wave not committed until the apply is finished" (orch-r3) vs I1.** Correct in general (moving HEAD invalidates the list), but I1 is a one-character guard fix whose re-measure is a few minutes of arms plus a re-pre-screen diff that should be empty. Applying ~250 fresh briefs through a guard with a known hole, to save minutes, is the wrong trade on the strict surface. Recommend: fix I1, re-tag, re-run G1, then pilot.
- **Task 20 fix-r1 catch-all `except Exception` → retryable FAILED.** Right call for the batch, but it also hides programming errors as "row failures" with no type name; add the type and keep a `--debug`/`LLAMA_DEBUG` re-raise path. Minor.
- **M8 (Opus pre-screen + 20-row sample instead of full hand reads)** was operator-ratified; I note only that the spec's strict-surface clause ("every briefing that ships by reuse is read whole") was in fact honoured at D (27 read, 5 rejected), so nothing is owed here.
- Every other `Ruling:` line I read (B1-B6, M1-M9, T4/T6/T8/T9/T10/T13/T13b/T14/T15/T16/16b/T18/T19/T20/T21 deviations, the F2/G1 PREV choices) is sound and conservative; none needs reversing.

## Declined to judge

- `_edit_overrides`/`_clear_hold` running outside the per-show lock in `fix`/triage — pre-existing pattern across every `fix` path, not introduced here.
- Old-titled audio left in `package/audio` after a title change and copied by `deliver`'s `copytree` (T19 C3) — pre-existing `redo --from package` behaviour; disk waste only (manifest, emcee and transmitter never read strays).
- `redo` sharing the llm-failures capture gap — outside the branch's scope (Task 20 fixed `reapply`).
- openrouter 429 arriving as a plain `HerderError` (counts toward the 3-failure stop, never pauses) — documented boundary (b) in CLAUDE.md, unchanged by this branch.
- `correspondence.propose_titles` (`--suggest-titles`/`[t]`) has no placeholder veto — operator-confirmed path, outside the slices (11b deferred to the operator).
- The known false demotion of the real song `2:22` and the `Master`/`Matrix` residue limitation — ruled at B, resolved by `fix --set-title`.
- `Cornell University` vs `Cornell College` / `Capitol` vs `Capital` under V — ruled at C with 0 library pairs.
- The names form continuing past a `RateLimited` (T19 C1) — ruled; each later fresh brief fails before any write, so it is noise, not damage.
- Pacing-state EWMA not learned by `reapply` (`test_the_gate_reads_the_meter…never_records_pacing_state`) — a deliberate spec choice ("Next").
- The spec's `4d` prompt change being unmeasurable offline — by design.
- 5c.2's description still present in the spec — the plan records the drop; the orchestrator chose to leave the approved spec text.

## Recommendations

1. Before the waves: fix I1 (one character + one test), re-run G1 from the new SHA, confirm the compare diff against the current G arms is empty except the new test, then pilot. Everything else in this review can land after the apply as ruled.
2. Fix wave after the apply: I2-I5, the siblings `tmp >` strip, the catch-all type name, the docs lines, and the `_untitled_resolution` status return.
3. G7 reading: watch the `structure` family for `encore_lost` false matches (repeated-song encores) and the `briefing` family on fresh briefs for any `two sets` claim that slipped (I1) if the apply runs before the fix.
4. Consider making `reapply_show` compare `classify`'s outcome with `row["outcome"]` and skip on disagreement — cheap insurance that turns an argued invariant into a checked one.

## Assessment

**Ready to merge?** With fixes.

**Reasoning:** The apply surface (lock span, write order, show.json-last, nothing written on needs-LLM/dry-run/refusal/skip, SHA+config+digest pinning, cache immutability) is correct and well pinned, every do-not-retune constant is byte-identical, and the guard slices sit beside the protected predicates as the spec requires. Five Important findings remain, all small: one (I1, a `\s*` that crosses the field boundary in `_SCOPE_AFTER`) is a live loosening of `briefing_guard` for fresh briefs and is the only finding I would fix before `reapply` touches the live library; I2-I5 are merge-blocking in the ordinary sense and can land in the post-apply fix wave.
