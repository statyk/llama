# Decisions for revision 1 of the adjudicator spec

Apply all of these. Spec: /Users/shawn/projects/llama/docs/superpowers/specs/2026-11-06-adjudicator-design.md.
"Shawn ruled" items are operator decisions made 2026-11-06 and must be written as his.

## A. Scope and operator class rulings (foundation)

A1. Fix the Intent/Goals framing. Measured 2026-11-06: 347 shows held; 316 already have a 2026-10-21
prototype verdict; 254 of those were escalated, not applied. Their verdicts' dominant classes: partial
tape ~69 (30 of them also have a better sibling), better sibling recording ~57, untitled or flags
echoing an untitled tape ~48, scrambled/shifted tags ~30, needs a listen ~23. So a re-judge alone cannot
reach "dozens"; it reaches dozens only with the class rulings below. State this plainly in Intent.

A2. Add a section "Operator class rulings" (Shawn ruled, 2026-11-06), which the prompt and the gate both
implement:
- Partial tape with no more complete sibling: **airs by default** (Shawn: "in most cases a partial show
  is worth keeping, and can be useful to the scheduler in plugging short gaps"). Not held merely for
  being partial; a note records it is partial. A song cut off at the tape's edge airs as is (author's
  call). Other bars still apply.
- Partial tape where a more complete sibling exists: handled as "better sibling" below.
- Better sibling recording: **switch automatically when the other recording is clearly better**
  (Shawn), else propose. See A3.
- Fully untitled tape (nothing names the songs): **hold** (Shawn). `--untitled` stays propose-only.
- Scrambled or shifted tags: **fix when confident** (Shawn), i.e. title edits at the title bar with
  code-verified taper-side evidence (B3, B6); else hold.
- Needs a listen: hold.
Pilot (B21) reports the projected queue per class against Shawn's tolerance (he can triage "dozens or
scores, maybe not hundreds", once the station has a solid base).

A3. New llama capability: a **recording pin**. `overrides.json` gains a recording field (identifier);
`llama fix <slug> --recording <identifier>` writes it; select honours it (the identifier must be one of
the performance's considered recordings). Verdict edit type "switch recording to <identifier>".
Auto-switch bar ("clearly better", author's call): the sibling's tracks cover at least the current
recording's songs and running time, it adds tracks or resolved titles, it passes winnow's normal quality
gate, evidence verified (B3), and the show is not delivered/station-marked (a switch on a delivered show
is propose-only, since it forces re-download and re-voice). After a switch the re-gathered show must
come out with no blocking flags; otherwise restore and keep it as a proposal. A switch is exempt from
the before/after "unnamed change" check (B1) because the whole track list is new by design; instead it
gets the coverage check above, compared against the pre-switch track list.

A4. Not doing: reusing the 2026-10-21 prototype verdicts (their evidence and schema are stale). Every
show is re-judged. One line under Non-goals.

## B. Mechanics (from the four reviews)

B1. Whole-show check replaces "verify the edits landed". Before writing, capture per track (filename,
position, title, title_source, set, segue) and the kept set. Predicted result = before + includes −
excludes, named titles changed, set labels as given by a structure edit (B7). After the redo: any
difference not predicted (an unnamed track's position, title, title_source or set; a kept set that is
not exactly the prediction, e.g. derivative swap, filename-order revert, desc-position switching on/off)
restores the snapshot and keeps the verdict as a proposal noting the diff. Segue loss from a structure
edit is expected and stated. The run report's track-list lines are built from this diff, not from the
edit list.

B2. Stale pre-flight: if the show fails llama's existing staleness check (show.json is not what gather
keeps now; `fix` refuses such shows), do not judge it; outcome `stale: reprocess first` (listed in the
report). Reprocessing is the campaign's/redo's job.

B3. Code-verified evidence. Each edit carries one or more evidence items {source kind, quote}. The gate
checks, after whitespace/case/curly-quote normalisation, that each quote is a substring of the bundle
section for its claimed source kind; for a >60 s include/exclude the quote must also name that file
(its tag title, filename stem or listed title); for a title edit the new title must appear in a quote.
A failed check makes the edit a proposal. Source kinds and the gate's wording use the same names (fix
"sibling item" vs "sibling's track list").

B4. Target validation before anything is written: exclude, title and structure targets must be current
tracks; include targets must be rows of excluded_files; a recording target must be a considered
recording; one file named by two conflicting edits, or any unknown filename, makes the verdict
malformed → held with the verdict stored. Write overrides through a filename-keyed path, not the
track-number-based writer, so no positional translation is reintroduced.

B5. Duration for the 60 s line: the duration of the row/track named, captured before the apply; where
both metadata and measured length are known, the larger; unknown → treated as >60 s. Cumulative cap:
if the verdict's short-bar track-list edits sum to more than 120 s, all of them need the long bar.
An exclude of a track with a resolved song title always takes the long bar, whatever its length (covers
short-song tapes). Re-admitting a row whose drop reason is duplicate listing, duplicate derivative or
spam-shaped is propose-only.

B6. Operator and taper state:
- Any edit that changes or removes an existing `overrides.json` entry (un-excluding an operator-excluded
  row, replacing an operator title, changing an operator venue/city/structure) is propose-only.
- Filling an unresolved or placeholder title: title bar (high + verified evidence).
- Replacing a title whose title_source is taper-derived (tags, desc-position, sibling-format/sibling
  rungs): needs taper-side evidence (the same item's description or original-file tag, or a sibling
  taper's tags); setlist.fm/JerryBase/reviews alone → proposal. This is the scrambled-tags path.
- Record each applied edit's source in adjudication.json (and keep `source: "adjudicate"` on overrules).

B7. Structure is one edit: {breaks_after: [files], encore_after: file|null}, the complete result, never
additive. The whole-show check compares the full set labelling to it. State that any structure override
drops segues and disables alignment checks (accepted: segues are loose).

B8. Flag-kind bars: a closed table keyed by llama's existing overrule flag kinds; any unmapped kind
defaults to never-auto. Never-auto: tape spans events, multi-event date, unassigned multi-event
recordings, no playable tracks, merged tracks across a set break, city conflict, the catch-all other
kinds, duration mismatch (which llama cannot record as an overrule anyway; drop "duration" from the
overrule row). research-sets → structure bar; research-song / research-date → title bar; venue
mismatch, other research claims, briefing cautions → medium. An overrule of a title- or structure-kind
flag needs verified evidence exactly like an edit (closes the "choose overrule to skip evidence" path).

B9. Verdict-level vetoes (kept from the prototype): auto-apply only when kind is fix or overrule,
show_correct_after_action = yes, and no flag is judged real-not-fixable or undecidable. A flag that an
edit silences as a side effect (a structure override silencing alignment, a venue override silencing
venue/city flags) counts as overruled: its own bar applies and its verdict must be spurious or
real-fixed-by-action.

B10. Re-hold rule: after a successful apply, auto-overrule only post-apply flags whose full key (kind
and subject) equals a pre-apply flag the verdict judged spurious at a passing bar. Never auto-overrule a
titles or alignment flag, or any subject-less structure kind, after a track-list or structure edit.
Never duration. Otherwise held with the proposal.

B11. Documented limitation (not a mechanism): an adjudicator overrule of a subject-less kind persists for
that recording like an operator overrule does today, so a later change that makes the problem real is
not re-flagged. One sentence under limitations.

B12. Locking and order: adjudication runs after the caller's lock / show_unit has been released. The
bundle is built with a captured show view; the apply runs in its own show_unit with that view as the
expected state, so a concurrent change raises ShowChanged → skip (re-judged next run). An adjudication
failure never touches the caller's committed result. Hook points are exactly: `get` (via the run
executor), `redo` (single and batch) and `run resume`. Not fix, triage, reapply, or the adjudicator's own
apply. Trigger: the show is held after processing (needs_review), which covers gather flags (reword
"holds come from vet, brief or package": gather raises flags too, checked after vet).

B13. Pacing: every adjudication call, pipeline or backlog, runs behind llama's existing pacing gate;
redo batches get the reapply-style gate before each adjudication. RateLimited during adjudication: the
show stays held and unjudged (no adjudication.json change), the run pauses the way it does for shows.
How adjudication spend feeds the per-show pacing estimate is the builder's call.

B14. adjudication.json: the applied record is written inside the unit (commits and restores with the
show); a held/failed proposal is written after the restore. The digest is computed from the final state
after the unit, over normalised inputs (flags, track table, excluded rows, overrides without timestamps,
identifier), excluding research and briefing text. Dry-run records are marked dry-run: never "current",
never offered as [a]. The pilot writes its per-model results to a pilot directory, not adjudication.json.

B15. Retryable outcome: a transient failure during apply (download error, station reuse refusal,
RateLimited inside the redo) restores the show and stores the verdict as `retry`; the next adjudicate run
re-applies it without a new LLM call if the digest is still current.

B16. Accepting proposals: [a] and `--accept` apply typed edits only (recording pin included), with the
same target validation, stored view as expected state (a changed show refuses), and the whole-show diff
reported — but not the gate and not the re-hold auto-overrule. Propose-only items (rm, set-date,
untitled, narration, redo from research) are printed as the commands to run; a proposal with only those
offers no [a]. `--accept` takes named slugs only and refuses selectors; it prints each proposal before
applying.

B17. Delivered / station-marked shows: the apply's redo stamps the campaign record processed, which makes
the show eligible for `deliver --fixed`; the run report lists those shows by name as "changed, needs
re-delivery (and re-voice if voiced)". Recording switches on such shows are propose-only (A3).

B18. Prompt rendering: bundle text containing `{{…}}` must not break rendering; a render or bundle error
is caught per show (show stays held, logged), never aborting a run.

B19. Update the ShowNotes model docstring ("a note can never reach an LLM") to say notes may appear in
the adjudicator's bundle; the ruling it records was about the briefing.

B20. Constraints: gate tests are mutation-checked at every bar boundary (60 s, 120 s cumulative, unknown
duration, each flag kind, evidence-check pass/fail).

B21. Pilot: 30 held shows stratified by the classes in A1; exact model pins (no tier escalation) so the
Opus and Sonnet arms stay what they claim; compare with the existing prototype verdicts for the same
shows; measure a few real applies' full cost (they re-run vet and brief); report projected
held-with-proposal count per class. Acceptance bar before the full sweep: an Opus reviewer finds zero
wrong auto-applied >60 s track-list edits, title replacements or recording switches in the pilot;
any class that fails becomes propose-only.

## Removed
- "Verify the edits landed" as written (replaced by B1).
- The gate row "overrule of title, structure or duration flags | high" (replaced by B8).
- The single "set break after file / encore after file" edits (replaced by B7).
