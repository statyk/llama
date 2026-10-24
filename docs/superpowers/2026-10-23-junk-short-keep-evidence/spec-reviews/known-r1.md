# Known findings after round 1 (issue -> how the spec now handles it)

## Migration (strict)
- Old binary silently ignores/erases re-keyed overrides (version skew) -> filename values stored under the LEGACY key names (`titles` filename keys, `set_breaks` filenames, `encore_after` filename); v2.17 model raises on them; test with the e37f670 model; mixed files refused (4.1).
- `set_breaks: []` lost -> presence semantics, `[]` preserved, `--untitled` writes `[]`, delmccoury test (4.1).
- Undo recomputed from mutable show.json -> backup, new file, sha256 sidecar (each temp + F_FULLFSYNC + rename); undo by recorded hash; "already undone"; needs the old binary; post-condition old-binary redo (4.3).
- Backup non-atomic / stale -> durable write; existing backup must equal a still-legacy file (4.3).
- Refused show has no way out; break check refused titles-only shows; no C1-equivalent check -> repair route via saved `llama-2.17.0`; break check only when a structure key is present; kept-list check under today's rule via the shared helper (`filter_files(short_keep=False)`), measured 0/606 differ (4.3).
- Ordering slips (base arm, apply lists, sweep loop, PATH binary) -> ordered runbook; script refuses unless PATH llama is new; base arm before migration; apply lists after (4.3, 5.1).
- Guard bypass by reapply / harness re-key -> guard in the resolver `compute_gather` uses; scratch re-key only in `replay_holds.py`, importing the migration's mapping (4.1, 4.2).
- Writers' numbering / staleness / combined fix / exclude of a keyed file -> show.json numbering; staleness vs overrides before this invocation's edits; one shared kept-list helper; `--exclude 3 --set-title 7=X` test; exclusion of a keyed file refuses up front (4.2).
- Dangling filename key after a cache refresh -> `--clear-title` accepts a filename; `--clear-*` skip the staleness check (4.2, AUTHOR'S CALL).

## Filter
- Count-match protection fragile / drops for nothing -> REMOVED (operator); ratdog-2007-08-12 an accepted limitation (2.4, 7).
- `short_kept` stamped too late (coverage clause inert) -> set in `resolve_titles` before align/LLM/taper; gather-level test (2.5, 6f).
- Tripwire reads the tag only -> filename stem + own and original title, word-bounded; 0 hits library and siblings; album/artist excluded (7 false hits, 0 true, measured); lying-tag limitation documented (2.3, 7).
- Vocabulary/separators ambiguous, empty parts -> rprime regexes normative verbatim; exact separators, no bare hyphen; empty cleaning not junk; corpus test (2.3, 6f).
- `radio`/`DJ` hit song titles -> broadcast qualifier required (incl. outro/ID/spots, AUTHOR'S CALL); 20/21 ruled examples drop, Consummation Station kept as band banter (2.3).
- Tag definition / count reconciliation -> fixed (2.2, 5.2).
- Later rung titles a short-kept file as junk -> notes.json note; limitation (2.5, 7).
- Claim wording vs harness outputs -> reworded (2.3, 6e).
- Interior test before dedupe/exclusion -> limitation (7).

## Apply
- `--replace-voiced` not confined -> one single-name call per slug from the 37-list with three pre-checks; `deliver` refuses it with a selector; unvoiced batch never passes it; reapply hint suppressed for voiced (5.5).
- `_destination_is_voiced` fails open -> only FileNotFoundError is unvoiced; other read errors and malformed manifests refuse (5.5).
- 28 minor voiced re-gathered for nothing; held-after-apply delivered shows -> 28 excluded from the apply; holds triaged before re-delivery (5.2, 5.5).
- Full re-download of purged shows -> station-copy reuse with a pre-regather index mapping and an ffprobe duration check; download fallback (5.4).
- `briefing_reusable` undefined for set breaks; 1,377 upper bound -> per-track tuples on matched non-short_kept tracks, each break keyed by the last non-short_kept file at or before it, show-level fields and guard unchanged; measured 1,017/1,415 (5.3).
- Transmitter horizon -> re-deliver outside the playout horizon first (5.5).

## Removed by revisions
- `titles_by_file` / `breaks_after` / `encore_after_file`; the count-match protection and `keep_untagged_short`; undo by recomputation; the 1,377 reuse figure.
