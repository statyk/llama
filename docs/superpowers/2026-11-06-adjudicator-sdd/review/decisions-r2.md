# Decisions for revision 2 (simplify; circuit-breaker: evidence check drew findings two rounds running, spec grew >50%)

Spec: /Users/shawn/projects/llama/docs/superpowers/specs/2026-11-06-adjudicator-design.md. Prefer removing to adding.
Goal: the spec should SHRINK or stay level overall.

## Evidence: replace the generic substring check with a few anchored rules
C1. Keep the quote-is-a-substring-of-its-claimed-section check only as a hallucination filter for
medium/loose rows. For the strict and near-strict rows, use these rules instead (and say the
substring check alone is not sufficient there):
- Title from a sibling's track list (fills and the scrambled/shifted-tags replacements): the sibling
  file carrying that title must be within a stated tolerance of this file's duration (constant; author's
  call 2 s or 1 %, whichever is larger). Both durations are in the bundle.
- Title fill from the taper's description or an original-file tag of the same item: allowed at the
  title bar (the tag row is that file's own row; the description quote is substring-checked).
- Title fill or replacement from setlist.fm, JerryBase or reviews alone: propose-only.
- Exclude of a track with a resolved song title (any length): propose-only.
- Other > 60 s include/exclude: allowed only when the quote is from a section other than the file's own
  tag row and contains the filename stem or the track's position; otherwise propose-only.
C2. Overrule table: `titles` and `low-confidence-setlist` move to never-auto (unresolved tracks are fixed
by title edits; a fully untitled tape holds). Drop the sentence that overrules need verified evidence
like edits for those kinds; title-bar overrules left are research-song / research-date, which keep the
substring check.

## Recording switch
C3. Replace "passes winnow's normal quality gate" with per-recording tests read from select's existing
scores: the wanted format is present, the recording is not a complained-about one, and its lineage class
is no worse than the current recording's. A worse lineage → propose-only.
C4. Define coverage: every resolved pre-switch title (normalised with llama's existing song-name
canonicalisation) appears after the switch; total kept duration is at least the pre-switch total; added
duration on tracks with no resolved title or kept by the short-file rule is ≤ 60 s. Else propose-only.
C5. A switch auto-applies only when overrides.json has no filename-keyed entries (exclude, include,
titles, set breaks, encore) and the switch is the verdict's only track-list/title/structure edit;
otherwise propose-only. `fix --recording` (and [a] on a switch) refuses while such entries exist,
naming the commands that clear them.

## Gate simplifications
C6. Replace the "side-effect silenced flags count as overruled" map with a post-apply rule inside the
unit: any pre-apply flag key absent after the redo that the verdict did not judge `spurious` or
`real-fixed-by-action` at a passing bar restores the snapshot and becomes a proposal. Remove the
hand-written examples.
C7. Overrule timing: when a verdict has any track-list edit, the apply writes no subject-less
structure-kind overrules before its redo; those flags are judged only by the post-apply re-hold rule.
C8. Venue edits stay medium; city edits are propose-only (a city conflict can mean another performance;
`city` stays never-auto). Remove the contradiction.
C9. Title-row coverage: replacing a `setlist`/`setlist-gap`-sourced title goes under the title bar with
C1's rules; "placeholder" means llama's existing placeholder-title test; any edit case the table does not
match is never-auto.
C10. "Operator entry" → "any existing overrides.json entry" (entries carry no source, so every existing
entry is protected). Target validation adds: an exclude of a file that carries a title, break or encore
key is malformed (as `fix` refuses it).

## Remove / tighten
C11. Drop the `retry` outcome entirely. A transient apply failure restores and leaves the show held and
unjudged (re-judged next run); a station-reuse refusal becomes a proposal carrying the error.
C12. One staleness test: compute the digest at the end of the unit, after the redo (it is the final
state); store it with the record. Accept ([a] / --accept) refuses on digest mismatch, then captures a
fresh view as the unit's expected state. Remove the stored-byte-view wording.
C13. Whole-show check: compare the relative order of unnamed tracks (not absolute positions); an
included track's own title and set are not predicted (a structure edit may name its set), but if its
title is unresolved the usual titles flag holds the show.
C14. Delivered/marked wording: marked shows whose campaign record ends processed become eligible for
`deliver --fixed`; for every other changed delivered show the report prints the explicit
`llama deliver <slug> [--replace-voiced]` command.
C15. Pilot: (a) the auto-applies the pilot would make on strict surfaces (long track-list edits, title
replacements/fills, switches; expected under a dozen) are listed for Shawn to spot-check, not only an
Opus reviewer; (b) switches the pilot would auto-apply are actually applied and then restored, so the
coverage and no-blocking-flags checks are measured; (c) add title fills and structure edits to the
zero-wrong acceptance list.

## Open for Shawn (write as an open question in the rulings section, marked OPEN)
C16. A partial tape whose sibling fails the auto-switch bar: does it air under the partial-tape ruling
while the switch waits as a proposal, or stay held until he decides the switch?

Reply with: each decision and where it went; removals; anything not applied cleanly; line count before/after.
