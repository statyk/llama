# fw3 — `reapply`: a held outcome must not leave a briefing written against older titles

File: `packages/llama/src/llama/reapply.py` (`reapply_show`), tests in `packages/llama/tests/test_reapply.py`. Read final review I4 in the verdict file first.

## The defect (final review I4)
When `legs.brief == "none"` (the briefing leg is not run because gather/vet flags remain) and the replay changes shipped fields (titles, sets, segues, venue, city, date — whatever `compute_legs` / `classify` treat as shipped), `reapply_show` writes the new `show.json` (still held) and leaves the stored `briefing.json`/`briefing.md`, generated against the OLD titles. A later `llama fix --overrule` → `redo --from package` ships that briefing unchecked (package does not re-run `briefing_guard`). Before this branch a held show's show.json and briefing.json were always from the same gather.

## Required change
In `reapply_show`, on the path where `briefing is None` (no reuse, no fresh brief this run) AND the final outcome will be held AND a stored briefing exists AND the replayed show's shipped fields differ from the stored show's: drop the brief stage's artifacts before writing `show.json` — use the existing `workspace.drop_stage_artifacts(ws, "brief")` if (read it first) it drops exactly briefing.json/briefing.md (and whatever downstream package artifacts it already drops for a redo from brief — report what it drops). Record the drop in `written` (e.g. `"drop:brief"`) so the outcome lists it. Determine "shipped fields differ" with an existing helper if `replay.py` has one (the harness reports `title_changes`/`set_changes`/`segue_changes`/venue/city/date diffs — reuse that comparison rather than writing a new one; name the helper you used). If no stored briefing exists, or nothing shipped changed, behaviour is unchanged.

Keep the write order: vetting → notes → (drop) → show.json last. The drop happens under the lock, after every in-memory computation, immediately before the show.json commit marker, so a crash between the drop and show.json leaves a held show with no briefing (which `redo --from brief` regenerates) — say so in a comment.

Cases that must NOT drop (pin each with a test): (a) a fresh brief that failed its guard (the written briefing IS the new one — `briefing is not None`); (b) a reused briefing; (c) held with no shipped-field change (e.g. only a carried package flag); (d) cleared outcomes.

## Tests (add)
- held + shipped title change + stored briefing → briefing.json/.md gone after, `show.json` written with the new titles, `written` lists the drop.
- the four no-drop cases above.

## Mutants
- M1: never drop → predicted: the drop test.
- M2: drop whenever held (ignore the shipped-field diff) → predicted: case (c).
- M3: drop even when `briefing is not None` → predicted: case (a).

## Docs
One sentence in CLAUDE.md's reapply bullet ("Run (held-backlog tooling)"): a held outcome whose replay changed shipped fields drops the now-stale briefing, so the eventual overrule regenerates it.

## Done when
Full suite green; commit `fix(reapply): a held outcome drops a briefing written against older titles`; mutation table in the handback.
