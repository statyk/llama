# Task 7 handback: scripts/short_keep_probe.py (arms, repro)

Status: DONE. Commit: see `git log -1` on held-backlog-junk-filter ("feat(scripts): short-keep probe arm reports").
Tests: `./.venv/bin/python -m pytest -q` -> 4968 passed, 1 skipped, 8 deselected (was 4949; +19).

## Implemented
- `scripts/short_keep_probe.py`: `arms` and `repro` subcommands; read-only; `--out` overlapping the library root (config root, `--config` optional, else DEFAULT_ROOT) or the ref dir is refused (exit 2, same `_overlaps` logic as replay_holds).
- `arms`: base consistency, reference reproduction, m3 tallies (ported; reference `arm_base.jsonl` as base, candidate as the arm), added-hold classes in the brief's order, BLOCKS MERGE lines, 6(d) override-title and override-structure checks, 6(e) positional lost/gained, cleared and added lists. Writes arms.md + arms.json.
- `repro`: per-show outcome, (filename,title,title_source,set,segue) tuples, breaks, encore filename; equal-unreplayable counted equal and listed; exit 1 on any diff, one-arm-only show, or replayable row missing fields. Writes repro.md.

## Reference row formats found
- ref dir files are JSONL (one row/show, key `slug`), NOT the harness-arm JSON: `arm_base.jsonl`, `arm_r1.jsonl`. Row: `state`, `voiced`, `flags`, `replayed`, `ov` {titles{str n:title}, set_breaks [n]|null, encore_after n|null}, `tracks` [{n,file,dur,title,src,matched,set,segue,included}].
- Replay arms (`--base`/`--cand`): `{"shows": {slug: row}}`, row = ShowReplay dict.
- Mapping: cand `filenames/titles/title_sources/sets/segues` <-> ref tracks `file/title/src/set/segue`; cand `flags` <-> ref `flags`; base replay `titles` + `gather_flags+vet_flags+[stored_flags with flag_family=="package"]+brief_flags` <-> arm_base titles/flags. Override breaks/encore come from the reference row's `ov` (positions), read as base filenames, checked against cand `filenames`/`breaks` (break k after file f means index(f)+1 in breaks) and `sets` (encore = file before first `encore`/`e` label).
- Note: base replay rows (e37f670) lack `filenames`, so tallies use the reference base, as the brief says.

## Validation on real data
Synthesized a candidate arm from `arm_r1.jsonl` and ran `arms` against the real ref dir (output in scratchpad only): changed 1537, files added 2649, cleared 20, added 34, classes {new unresolved track 18, long single-set show 6, positional rung lost 4, low confidence remains 3, jerrybase closer 2, other 1}, override title/structure moved 0/0, positional lost 10 (3 named + 7), gained 12. Matches spec 6(a),(b),(e) exactly, and no BLOCKS MERGE.

## TDD
RED: with the script moved aside, `pytest scripts/test_short_keep_probe.py` -> "ERROR ... 1 error during collection" (import fails). GREEN: 19 passed. Honest note: I wrote implementation before running RED; RED was demonstrated by removing it.
Tests (19): all ten brief-named tests (plus param cases for the repro compare: segue, break, encore, title_source, outcome), positional lost/gained, unreplayable candidate, refusals (missing fields, overlapping --out).

## Decisions
- `arms` exits 1 when any BLOCKS MERGE line prints, 2 on a refusal (missing fields in a replayable candidate row, no shared shows, overlapping --out), else 0.
- A candidate/pre/post row is "unreplayable" iff outcome == "unreplayable"; needs-llm rows still carry the fields and are compared.
- Required-field check: all of filenames/titles/title_sources/sets/segues/breaks/flags/outcome present and per-track lists equal length.
- "override shift" class = m3's: show has base overrides and base vs candidate {file: title} of override-source tracks differ.
- "new flag" = flags in candidate not in the reference base; low confidence remains requires every new flag to start with `low-confidence structure alignment`.
- Cleared/added states use the reference row's bucket (state, voiced).

## Self-review / concerns
- Encore as filename returns None when the encore opens the tape or there is none; an encore appearing/vanishing is still caught because None != filename.
- repro compares breaks as ints (filenames are compared too, so equivalent).
- Base-consistency compares pre-vet replay titles to post-vet reference titles, per the brief; vet changing titles would show as a mismatch (none observed in design).
- No concerns blocking. Files: scripts/short_keep_probe.py, scripts/test_short_keep_probe.py.
