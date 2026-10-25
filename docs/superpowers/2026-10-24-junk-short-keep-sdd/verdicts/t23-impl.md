# t23-impl handback (Task 23)

Status: DONE. Commits: eac1a07 (CLAUDE.md + spec), 04f68b4 (SDD record). Worktree clean. No code or tests changed (git diff 4dd0ea6 -- packages scripts antenna is empty).
Suite (`./.venv/bin/python -m pytest -q -p no:cacheprovider`, llama.__file__ inside worktree, run before the first commit; docs-only afterwards): 5468 passed, 1 skipped, 8 deselected, 26 warnings in 50.41s.

## Files changed
- CLAUDE.md
- docs/superpowers/specs/2026-10-23-junk-short-keep-design.md
- docs/superpowers/2026-10-24-junk-short-keep-sdd/ (README.md, 6 ledgers, orch-r5/checkpoint-c.md, orch-r4/fw1-rulings.md, 90 verdicts/*.md; mutation.md untouched)

## Batch items
(a) spec: 2.3 NONPERF measurement reworded (no more vacuous line), 2.3 "Measured" now 685 -> 691 with the 3 music-kind rows; zero-duration cross-references in section 1, 2.1 and 2.5; section 7 "Non-performance false-positive class" (K/W abbreviation next to a qualifier, `<x> music` incl. `Exit Music (For a Film)`).
(b) spec 5.3: "restored-file gate" block (15a, ruling "2", 15b vocabulary and normalised-window design, FW2 additions, 100% regeneration, 1,017/1,415 marked superseded); premise 4 result recorded in section 8.
(c) spec 5.4: "Identifier gating" bullet.
(d) spec section 7: crowd-chant ruling verbatim + pin test name.
(e) spec section 7: manifest-less destination merges ("Leave it, low risk and unlikely.").
(f) CLAUDE.md: deliver bullet (stale "marks or counts" replaced; one named show, never a selector; unreadable destinations; changed track list replaces; hint suppression), "(single name only)" in What this is; process-check limitation in the piece-4 bullet and spec 4.3.
(g) spec new 2.6 + section 7, CLAUDE.md FORMAT_BY_AUDIO sentence rewritten (running-time choice, ties by order, fallback kept) and piece-4 bullet.
(h) spec 2.6 (derivative dedupe, PREFER_VBR_DERIVATIVE, copy order, measured basis, operator exclude/include, no flip), section 7 bullet replaced (supersedes Checkpoint A ruling 5), CLAUDE.md piece-4 bullet.
(i) spec 5.3 vocabulary list (lacks, not recorded, cut from the recording, lists no, too/implausibly window, apostrophe separator copy, U+02BB/U+02B9).
(j) spec 4.3: wrong-snapshot refusal paragraph (+ unreadable record, record renamed on success), repro refusals; CLAUDE.md piece-4 bullet.
(k)(l) spec new 2.7 (segue-bearing donor; G5; donor_segues with the add guard on SHIPPED sets; measured numbers; unfreezes blend_segues pooling), CLAUDE.md piece-4 bullet.
(m) spec 4.3 "what restore does not revert" (mtime listing; no --replace-voiced needed), CLAUDE.md piece-4 bullet.
Plan Step 1: Domain-gotchas paragraph (rule, tripwire reason, short_kept, coverage, 239 includes), piece-4 Architecture bullet, Commands entry (short_keep_probe subcommands, replay_holds --rekey-overrides, rekey_overrides.py), overrides.json bullet amended, deliver bullet amended. Filed follow-ups: CLAUDE.md bullet (brief) and README (full).

## SDD record
99 files before the README (100 with it), 900,003 bytes before README; none over 256 KB, none skipped. 90 verdicts copied. Task dir without handback: tfw2-rev (dead claim; work is tfw2-rev2). orch-r5/ledger.md copied as it stood; README says the orchestrator re-syncs it.

## Concerns / conflicts with the brief
- The brief calls `Exit Music (For a Film)` a call-sign false positive; in the code it matches the `<x> music` (exit music) alternative, not the call-sign one. The spec text describes both classes separately as the code behaves.
- The brief's "G5 23 false marks removed, 0 real lost" and "adds ~2,000" are quoted as given (cand-g vs cand-d); I did not re-measure. The ledger's per-round figures differ slightly (e.g. 1,055 shows at first build); the spec says "about 1,050 shows (as first built)".
- Spec 5.2's counts (1,537 shows, 2,649 files, etc.) were left as the original measurements; acceptance.md carries the later ones.
- Reapply's extended path for packaged/delivered shows is not built; CLAUDE.md and the README say so.

# t23-fix1 report
Status DONE, commit 9ecaeb9 docs: Task 23 review fixes (fix without show.json, brief budget, runbook, reapply hint). Suite: 5468 passed, 1 skipped, 8 deselected, 26 warnings in 51.59s. Docs only; SDD record untouched.
Fixed: Important 1 (CLAUDE.md fix-without-show.json sentence rewritten per cli.py refuse_no_show_json); Important 2 (spec 5.3 budget ~1,110+13+34+371 = ~1,530); Minors 1 (runbook step 1 in spec x2 and plan Appendix A/B), 2 (restore: destinations whose manifest changed since), 3 (reapply hint exceptions, verified cli.py _echo_redeliver_hint), 4 (--include placement mentions derivative dedupe); optional spec 2.7 G5 reopens warrenzevon-1994-02-07 #16, spec 5.2 pointer to acceptance.md.
