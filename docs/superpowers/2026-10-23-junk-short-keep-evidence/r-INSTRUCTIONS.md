# Rule R hand-check: keep or drop this short file?

Each row is ONE short audio file (under `floor_sec`, a quarter of that tape's median track length) that
llama's junk filter drops TODAY. Candidate rule R would KEEP it unless its tag says tuning / dead air /
silence / tape flip / fade / noise / soundcheck, or names a commercial, promo, station ID or house music.
An untagged short file is kept only when it sits between two kept tracks (`position: interior`).
`rule_R_would` says what R decides. You get the tag, its neighbours in play order, and the description.
Open `url` (archive.org) if needed; do not download audio.

Operator direction (Shawn, 2026-10-23): wrongly DROPPING something that belongs is worse than wrongly
including something. Short spoken segments are part of the show: a ~30 s band intro mid-set, or stage
announcements. About 60 s of tuning between songs is better dropped. A few seconds of junk barely hurts.

Answer per row, JSON lines `{"row": N, "decision": "keep"|"drop", "rule_R_right": true|false, "kind": ..., "confidence": ..., "why": "..."}`:
- `decision`: what SHOULD happen under the direction above.
- `rule_R_right`: does `rule_R_would` match your decision?
- `kind`: `song` / `segue-or-continuation` / `fragment` / `spoken-band` (band or crew talking, intros,
  announcements) / `spoken-broadcast` (radio DJ, interview) / `crowd` / `tuning` / `silence-or-tape-edge` /
  `non-performance` (commercial, promo, PA music, spam) / `unknown`.
- `confidence`: high / medium / low.
