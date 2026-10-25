# Piece 4 hand-check: did the junk filter drop real music?

Each row is ONE audio file that llama's junk filter dropped from the show it ships (reason in
`drop_reason`; `implausibly short` means under `floor_sec`, 25% of that tape's median track length).
You get the file's own tag, its neighbours in filename order (with their tags and whether they were
dropped too), the taper's description, the canonical setlist, and, where available, how the file's
duration lines up against another taper's recording of the same show (`sibling_duration_evidence`:
`alone` = this file pairs one-to-one with the sibling's track(s) listed; `merged` = this file plus a
neighbour together match one sibling track, i.e. it is part of a song split across files; `skipped` =
the sibling has nothing here). Open `url` (archive.org) if you need more; do not download audio.

Answer per row, as JSON lines `{"row": N, "verdict": ..., "kind": ..., "hole": ..., "confidence": ..., "why": "..."}`:
- `verdict`: `music` (belongs in the broadcast), `junk` (tuning, crowd, banter, spoken intro, tape
  noise, spam), or `unsure`.
- `kind` (if music): `whole-song` (a complete short song), `continuation` (part of a song split across
  files, a reprise, the tail after a tape flip), `segue-piece` (jam/prelude/drums/space bridge between
  songs), `fragment` (a cut, false start, aborted song or tease that is not continuous with anything).
- `hole`: true if dropping it leaves an audible gap inside continuous music (the tags say `->`/`>`
  into or out of it, or the sibling shows it is part of a longer song).
- `confidence`: high / medium / low.
Tape notes are presumed correct: if the taper names it as a song in the set list, that counts, but a
taper listing "tuning", "banter" or a spoken bit by name does NOT make it music.
