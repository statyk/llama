# Taper set/encore markers: classification evidence (2026-10-22)

Input to `specs/2026-10-22-taper-set-markers-design.md`. Population: the 394 verdicts in
`~/.llama-harness/t3/verdicts/` tagged `set-source-precedence` (the 2026-10-21 overnight
adjudication; see `../2026-10-21-held-backlog-adjudication/`).

- `sort1.py` / `sort1.json`: deterministic pass (run with the repo venv at `a26c4d1`). Per show:
  shipped `structure.source`/`alignment` and breaks (from the bundle's show.json), the
  adjudicator's target breaks (parsed from its `llama fix` command), llama's own
  `parse_setlist` of the selected description, and that parse aligned onto the tape.
- `classify-brief.md`: the brief four Sonnet agents followed (about 99 shows each; per-show packets
  were built from the verdict, the bundle and the cached item metadata; packets stay in
  `~/.llama-harness/piece2/packets/`).
- `classified.jsonl`: their output, one row per show (`primary`, `also`, `taper_explicit`,
  `marker_quote`, `lost_to`, `target_matches_marker`, `note`).

These are model classifications of free-text verdicts: good for sizing and for picking examples,
not ground truth. The spec's acceptance is measured by the replay harness, not by this file.
