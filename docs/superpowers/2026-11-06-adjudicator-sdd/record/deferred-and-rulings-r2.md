Ruling: ⚠️ RED-on-BASE resolved by log order (RED r1-impl.log:123 precedes GREEN :125, mutants :206, suite :294) — single atomic commit is acceptable — cost: none if the log is honest.
Task R1: minor (deferred): non-empty-created-dir test has no explicit is_dir asserts.
Task R1: minor (deferred): _dirs os.walk swallows errors — an unreadable subtree at snapshot time drops its pre-existing subdirs from 'dirs' (fix: onerror re-raise in the snapshot walk). Strict-surface hardening; candidate to ride with the next show_unit change.
Task R1: minor (deferred): show_unit.py:206 comment implies put_back ordering matters (equivalent by construction).
Task R1: minor (deferred): a pre-existing empty dir deleted by the unit body is not recreated (unreachable today: no in-unit dir removal).
Task R1: minor (deferred): no test of a created empty dir nested in a pre-existing dir (research/new/).
Ruling: R1b also makes the _tracked_files SNAPSHOT walk strict — same cause, and it fails open worse (a pre-existing file in an unreadable-at-snapshot subtree is unlinked by restore step (a)); restore-time walks stay tolerant (safe direction); refusal as LlamaError 'cannot snapshot' — cost: a show with an unreadable subdir refuses every unit until permissions are fixed (correct for a strict surface).
Task R1b: minor (deferred): test regex r"s: cannot snapshot .*private" does not pin the slug (anchor ^s:).
Task R1b: minor (deferred): an unreadable FILE refuses as bare PermissionError (data-safe; auto apply records failed not proposal; reapply-by-name/resolve/fix/redo show a traceback). Fix: wrap OSError in the same LlamaError + chmod-file test. Offered to parent.
Task R1b: minor (deferred): message repeats the path; _walk has no return annotation.
Task R1c: minor (deferred, parent ruling): capture_view at unit entry raises bare PermissionError for unreadable overrides.json/show.json — writes nothing, pre-existing, needs a manual permission fault.
Task R1c: minor (deferred): ruling (b) unpinned — no test of a non-EACCES OSError (FileNotFoundError) on the snapshot read (mutant a survived).
Task R1c: minor (deferred): pre-existing Py3.14 hole — package/audio at 0o600 (readable, not searchable): is_file() swallows EACCES, snapshot records audio [] without refusing; data-safe today (restore cannot unlink without search perm). Fix: scandir/stat in snapshot listing.
Task R1c: minor (deferred): message repeats path (sanctioned).
Ruling: R2-R5 sequential (all touch gate.py/validator); replay harness at $W/replay/ (git-ignored), reused by R3 — cost: none.
13:29 Parent: R2 count-base mismatch is a REQUIRED fix (current from selection.json kept_tracks; current unknown -> veto + mutation row) in fix round 1 regardless of reviewers; tolerance stays 60 s pending Shawn. Ruling: F1b duration like-with-like too (current kept duration via the same filter over the current recording's metadata) — same fail-open class — cost: one more metadata-derived value; unknown skips the clause. Findings file $W/task-R2-fix1-findings.md; waiting for r2-spec before sending.
Ruling: tolerance Important is parked on Shawn's pending decision, not a fix-round item — parent directed keep 60 s — cost: one fix round if he picks (b)/(c).
Ruling: no prompt change for the coverage veto — it is a deterministic veto, not a bar, and the prompt already asks the model to name a fuller sibling with a switch — cost: the model may still emit no-switch verdicts that the veto demotes (safe).
Task R2: minor (deferred): corrupt selection.json makes build_bundle raise (fails closed via failed outcome); no R2 test.
Task R2: minor (deferred): considered = scores minus show.identifier vs recording_info's selection identifier (fail-safe).
Ruling: fold r2-quality Minor 1 (flac-config parity test) and Minor 2 (current identifier defined once; show/selection disagreement -> veto) into fix round 1 — both touch F1's code and Minor 2 is fail-open-adjacent — cost: slightly larger fix round.
Task R2: minor (deferred): one veto per sibling is noisy (gd1982 9 vetoes) — consider fullest + count.
Task R2: minor (deferred): NaN lengths skip the duration clause silently (safe direction).
Task R2: minor (deferred): non-dict selection.json crashes validate_targets (pre-existing; failed outcome).
Task R2: minor (deferred): runner e2e veto has both sides 0 s (RigIA no format) — duration clause unit-tested only.
Task R2: minor (deferred): kept_tracks reflects audio_format at select time, durations at adjudication time.
Task R2: minor (deferred): over-long spec line design.md:212.
Task R2: parked — SIBLING_COVERAGE_TOL_S=60 s (spec Important Extra) — Ruling: pending Shawn; parent directed keep (a) — cost: one fix round if (b)/(c).
Task R2: complete (commits cb0e081c..2a7a4937, 1 parked pending operator)
Ruling: R3 strict — no set_title exception (a mixed verdict with title fills + research-song overrules lands as a proposal) — cost: one keystroke per such show.
Ruling: R3 counts missing/empty/unresolved titles as placeholders (fail closed) — cost: fewer auto overrules on partly-titled shows.
Task R3: minor (deferred): prompt adds two sentences where the brief asked one (+ a bar-section sentence, justified).
Task R3: minor (deferred, operator note): [a]/--accept applies a placeholder-vetoed overrule with no gate (pre-existing accept semantics).
Ruling: fold the include-re-admit known-limit spec line (Minor) into fix round 1 — one line, strict-surface transparency — cost: none.
Task R3: minor (deferred, operator note): a real title restored as 'Track 9' keeps the placeholder veto on that show (fail-closed).
Task R3: minor (deferred): veto reason outranks 'not judged spurious' (display only).
Ruling: interpret as the UNION — veto if any current shipped title is a placeholder (strict, unchanged) OR any predicted post-verdict title is (set_title applied) — keeps the earlier strict no-set_title-exception ruling — cost: a verdict that fixes all placeholders still lands as a proposal. Amendment sent to r3-impl.
Task R2: parked tolerance finding — resolved by Shawn's ruling (c) -> Task R2b. Brief $W/task-R2b-brief.md written.
Task R3: minor (deferred): predict included titles via clean_tag_titles (number strip parity).
Task R3: minor (deferred -> carry to R4): add an included-file title check to whole_show_diff (apply.py:223) once include-then-title is valid.
Task R3: minor (deferred): no test of an excluded current track with a placeholder set_title (over-veto only).
14:10 Parent: R4 must add the included-file title check to whole_show_diff (required, not deferred) + include-lands-title-does-not test + mutation row. Brief $W/task-R45-brief.md written (R4+R5 batched). Ruling: R5 = bundle lists distinct flags; validator collapses IDENTICAL repeated judgements, differing repeats stay malformed — cost: a model that judges a duplicate two different ways is still malformed (correct).
Task R2b: minor (deferred): fewer-tracks-more-duration test only covers 0 vs 1 tracks (add 1 vs 2).
Task R2b: minor (deferred): over-long design.md line in the Sibling-coverage paragraph.
Ruling: ⚠️ replay ran on a tree identical to f3c52d44 (HEAD clean) — accepted; the final whole-branch replay re-runs at HEAD anyway — cost: none.
Ruling: R5 collapses repeated judgements that agree on (verdict, confidence), keeping the first (its why is displayed) — the gate never reads why; my earlier 'identical' rule was over-strict vs Shawn's 'dedupe' and the pilot-review's 'accept repeated judgments that agree' — cost: a differing why on the duplicate is dropped from display.
Task R4+R5: minor (deferred -> final): prompt adjudicate.md:134-135 still says an include of a placeholder-tag file holds even with a real set_title (over-cautious, safe).
Ruling: ⚠️ replay at ~commit time on the R5 tree accepted; the final whole-branch review re-runs the replay at HEAD — cost: none.
Ruling: I1 option (a) — structure naming an included file is propose-only in the gate (validation stays valid) — fail-closed, few lines; option (b) position prediction rejected as larger and guess-prone — cost: such verdicts (e.g. waynehancock) land as proposals.
Ruling: fold M6 breaks_after test and the stale prompt sentence (+ one I1 prompt sentence) into fix round 1 — cost: none.
Task R4+R5: minor (deferred): gate.py:176 '& excluded' only dedupes a reason line — do not simplify.
