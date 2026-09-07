# Code-quality review — branch `overrides-include` (18 commits, base `e1fecb9`)

Baseline reproduced: 1968 passed, 7 deselected at HEAD. Tree restored, `git status
--porcelain` empty, suite green at 1968 after all mutation work.

VERDICT: one Important finding, seven Minor. No Critical. 37 mutants run, 34 caught by the
test named before running, 3 survivors (all cosmetic or inert).

## 1. Critical
None.

## 2. Important

### I1. `--suggest-titles` / triage `[t]` permanently unusable on any show with an effective
`overrides.include`, with a false diagnosis and a looping remedy.

`packages/llama/src/llama/cli.py:2284`

    kept, _, _ = filter_files(ia.metadata(show.identifier).get("files", []), want_format=want)
    if entry.overrides.exclude:
        drop = set(entry.overrides.exclude)
        kept = [f for f in kept if f["name"] not in drop]

`_suggest_titles_for` recomputes `kept` from `ia.metadata` + `overrides.exclude` and does NOT
pass `readmit`. It then hard-declines on any disagreement with `show.tracks`
(cli.py:2304-2311) -- deliberately a hard decline per the C1 comment. Once gather re-admits a
file, show.tracks has N+1 and this recomputation has N, so the guard fires forever.

Reproduced end to end (gd73 fixture, Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"]), real
run_gather, then `llama fix ... --suggest-titles`):

    gratefuldead-1973-06-10: show.json is stale relative to overrides.json
    (6 files kept, 7 tracks on disk) - run `llama redo gratefuldead-1973-06-10 --from gather` first

Both halves are wrong. show.json is not stale, and the recommended redo reproduces the same 7
tracks, so the operator loops. The `fix` guard at cli.py:2452 refuses --include +
--suggest-titles in one INVOCATION; nobody guarded the later separate invocation that guard's
own message tells the operator to run.

Matters more than the narrow repro suggests: --include and --suggest-titles target the same
population, and a re-admitted file is by construction title_source="unresolved" -- precisely
the hold flag that makes triage's `[t] suggest titles` appear.

FIX: one line -- `readmit=frozenset(entry.overrides.include)` at cli.py:2284. Passing it also
reproduces gather's play-order fallback, so the filename-list comparison stays valid.

This is the only one of six `filter_files` call sites that gets it wrong. Verified correct:
gather.py:195 and correspondence.py:305 (donor-side), gather.py:340 (lossless sibling),
select_recording.py:63 (pre-gather).

## 3. Minor

M1. `_dedupe_duplicate_listings`' new `duration_sec` unpinned. junk.py:173-174, 182-183.
Mutant M13 set both to None -> 1968 passed. test_excluded_entries_carry_a_duration runs on
gd73 (no duplicate listings); test_readmit_of_a_duplicate_listing_ships_the_track_twice
asserts `excluded == []`. Symptom: a `?` in the show --tracks excluded column for a file whose
duration IS known -- what test_operator_excluded_entry_carries_duration_sec prevents on the
other branch.

M2. The new echo gate made a pre-existing --exclude no-op silent. cli.py:2564
`if add or rm or undo:`. On main the exclude echo was unconditional. Measured: `llama fix X
--exclude ,` now prints only `packaged: /pkg` and still redoes from gather. Mutant M20
(`if True:`) also survived, so the gate is unpinned in both directions.

M3. Dead guard. junk.py:252 `f.get("format") == matched` in `by_name`. Mutant M16 dropped it:
green. Provably inert -- `excluded` only ever names winning-format files (docstring
junk.py:203-205). The comment above reads as if this clause enforces that; `excluded`'s scope
does.

M4. Two different enumeration votes for the same tape two lines apart. gather.py:944
`title_fraction(clean_tag_titles(kept))` (no gate_basis) vs :953-955 `gate_basis=
tag_gate_basis`. The fetch_siblings carve-out is justified for the FRACTION, but the side
effect is the track-number STRIP is decided one way there and the other way in
resolve_titles. Nearly always inert (is_real_title counts letters); reachable for a bare
numeric title like "01 2001".

M5. A test docstring claims a kill it does not make.
test_stage_gather.py::test_gather_leaves_ordinary_tracks_unmarked claims it catches both the
whole-block deletion and forced-True. Measured: forced-True (M23) caught; whole-block
deletion (M24) NOT caught by this test -- only by its sibling
test_gather_readmits_an_operator_included_file.

M6. The triage `[e]` picker shows xN handles it cannot act on. `_pick_excludes`
(cli.py:1362-1367) renders `_format_tracks`, now including the `excluded (N):` block with
handles; `_parse_ranks` (cli.py:135) silently drops non-numeric tokens, so typing `x1` gives
"nothing selected; skipping". The re-admit hint is deliberately withheld there. For the spec
reviewer: shows handles / ignores handles / explains nothing is the worst of three options.

M7 (editorial). `included` stamps on the request. gather.py:1183-1187 uses
`overrides.include`; correct and honest (legend wording fixed in eb1e278, documented at
models.py:167-172) -- but gather.py:872-875 says in capitals "Filter on what filter_files
ACTUALLY re-admitted, never on the raw overrides.include request." One cross-reference
("display, not standing") settles it.

## 4. Answers to the specific questions

CORRECTNESS OF THE NAMED SITES -- all correct as far as measurable.
- filter_files' block sits after both junk passes and dedupe, before ordering; all three
  positions individually pinned (M1, M12, M36). ordering["readmitted"] is the ACTUAL set:
  M2 (substituting `readmit`) fails test_readmit_of_an_unknown_filename_changes_nothing AND
  test_including_a_file_that_was_never_dropped_keeps_its_vote. Commit 6a4c573 is real and
  pinned twice.
- recovery_basis (pre-exclusion) vs tag_gate_basis (post-exclusion) is RIGHT at each site and
  pinned in both directions: M35 (recovery post-exclusion) fails
  test_gather_recovery_survives_an_operator_exclusion; M5 (tag_gate_basis = recovery_basis --
  the "simplification" the comment warns about) fails
  test_readmission_does_not_stop_the_track_number_strip. With empty include, recovery_basis is
  byte-identical to main's kept at that point.
- clean_tag_titles' gate_basis: `is None`, not falsy, so gate_basis=[] correctly means "vote
  on nothing"; len(voters)==0 cannot divide by zero because numbered < _ENUMERATED_MIN_FILES
  short-circuits. M6 caught at unit and stage level.
- fullmatch is used at both handle sites and EACH is independently killed (M10a ->
  test_resolve_include_tokens_needs_show_json; M10b ->
  test_a_filename_that_merely_starts_like_a_handle_is_a_filename). 542d690's claim holds.
  Clash check, both _edit_overrides purge clauses and the was_operator routing are each killed
  by exactly one test (M19, M7, M8, M9).

BOUNDARY CASES -- all checked.
- Empty lists: readmit=frozenset() skips the block; include=[] skips the stamp;
  _edit_overrides with both defaults is a no-op on both lists (triage's other callers safe).
- Both lists: exclude wins, warned, tested (M33).
- Out-of-range handle: clear message with count, pinned verbatim.
- Pre-feature show.json: e.get("reasons", []) / e.get("duration_sec") at both the rendering
  site and was_operator; both pinned (M26, M26b, M27). Show/Overrides stay permissive.
- fix CANNOT reach the new unconditional read_model(sws.show, Show) at cli.py:2552 without a
  show.json -- cli.py:2531 guards first. Probed specifically; safe.
- A re-admitted file with NO duration does not break package: ManifestTrack.duration_sec is
  float|None and package.py:52-57 re-probes, so cli.py:1321-1324's claim is accurate.
- ROUND-TRIP CLOSES: --include f (junk) -> --exclude f -> re-gather stamps operator-excluded
  -> --include f routes through was_operator to --unexclude, leaving BOTH lists empty and f
  back under the junk filter's own verdict. No --uninclude needed.

DO THE TESTS PIN WHAT THEY SAY -- mostly yes, measurably. 37 mutants, PYTHONPYCACHEPREFIX=
$(mktemp -d) per mutant, restored from a byte copy (never git checkout), expected failing test
named before each run. 34 caught, every one by the predicted test. Survivors M13/M16/M20 =
Minor M1/M3/M2. No fifth instance of the four-assertion problem. Two tests that LOOK like the
flagged patterns are sound: test_readmit_of_an_unknown_filename_changes_nothing compares two
calls to the same function but its `order == base_order` half is exactly what kills M2; and
test_clean_tag_titles_gate_basis_none_votes_with_the_files_themselves was already rewritten to
a concrete value for that reason.

BONUS: test_readmit_does_not_move_the_duration_floor is the ONLY test in the 1968-test suite
that catches breaking _keep_and_exclude's two-pass invariant (M36: floor over all audio).

UNIFY THE TWO RESOLVERS? NO, with one exception. They differ in four places: predicate
(p.isdigit() vs _HANDLE.fullmatch), lookup table and key type ({int: filename} from
show.tracks vs {str: filename} from _excluded_handles), and two operator-facing error strings
pinned verbatim. A unified helper needs four parameters for a 14-line body and puts a callback
between each flag and the wording an operator reads. Negative trade.

Worth extracting: the one byte-identical line that must never diverge --

    def _split_tokens(tokens) -> list[str]:
        """Comma groups, whitespace-stripped, empties dropped. Shared so
        `--exclude a, b` and `--include a, b` can never split differently."""
        return [p.strip() for tok in tokens for p in str(tok).split(",") if p.strip()]

One line, no parameters; removes the only duplication with a real failure mode, and
incidentally removes the byte-identical mutation anchor.

NEW WHOLE-OUTPUT NEGATIVE ASSERTIONS: NONE. Grepped the test diff for `not in *.output`; the
only three hits are two COMMENTS explaining why the author did not write one, plus
`assert "excluded" not in json.loads(r.output)` (a dict-key check). Every new negative is
line-scoped or an exact whole-line equality. The branch makes no pre-existing
test_show_cmd.py / test_triage.py whole-output negative newly reachable -- the new output
(`excluded (N):`, `+ = ...`, `re-admit one with:`) contains none of the negated strings.

SEAMS BETWEEN COMMITS. Read every consumer of `kept` in run_gather (gather.py:840-955) and
every filter_files call in the tree.
- Task 1 -> 2: ordering["readmitted"] is the contract; the 6a4c573 fix to consume it rather
  than overrides.include is correct and double-pinned.
- Task 2 -> 3: Show.excluded_files grew duration_sec and Task 3 reads it defensively -- but
  the operator-excluded producer (gather.py:892-893) and the dedupe producer (junk.py:173/182)
  were treated unequally; only the former got a test (Minor M1).
- Task 3 -> 4: _excluded_handles as single producer is right; M11 (start=0) fails 15 tests
  across three files, which is what one-producer looks like when it works.
- Task 4 -> the pre-existing --suggest-titles consumer: MISSED (Important I1). The only reader
  of `kept` outside gather that must know about re-admission, and the one place a per-task
  diff review structurally could not see.

## Method
- ./.venv/bin/python -m pytest -q from repo root throughout; never a .venv/bin/* console
  script.
- Every mutant: PYTHONPYCACHEPREFIX=$(mktemp -d), source touched after edit, restored by cp
  from a pre-run byte copy. No git checkout/stash/commit/push/merge/tag at any point.
- Two temporary probe test files created under packages/llama/tests/ and deleted; both
  untracked. Final: git status --porcelain empty, git diff --stat empty, 1968 passed.
- Full command log: sdd/wbr-qual/wbr-qual.log
