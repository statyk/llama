# Taper preferences & era lineage overrides in recording selection

Date: 2026-07-15. Status: approved (conversation, 2026-07-15).

## Problem

Recording selection scores lineage, ratings, format, completeness, and
complaints — but the Grateful Dead taping community carries knowledge the
generic signals miss: certain transferists' tapes (Charlie Miller above all,
Kevin Seamons next) are reliably excellent, a newer transfer by the same
person usually supersedes the older one, and for roughly 1980–1987 the
soundboards are often poor while matrixes and audience tapes shine.

## Design

Two data-driven rules resolved per candidate (collection + date) at
select-recording time, with Grateful Dead defaults baked into config and
everything overridable via a `[selection]` table in `config.toml`.

### Taper preference

```toml
[selection.tapers.GratefulDead]
miller = 2.0
seamons = 1.0
```

- A recording whose identifier contains the pattern (case-insensitive) gets
  the bonus added to its base score — alongside lineage, before the
  completeness multiplier, so a favored-taper *fragment* still loses to a
  complete tape unless ratings justify it.
- **Newest revision preferred:** when several recordings of one performance
  match the same pattern, only the newest gets the full bonus; the rest get
  half. Newness = the shnid (largest integer token in the identifier:
  `miller.32350` > `miller.32273`), with `addeddate` metadata as tiebreak
  only — verified live that upload date misorders revisions (the older
  1969-11-02 miller transfer was uploaded a year after the newer one).
- A recording matching multiple patterns takes the largest applicable bonus.
- Magnitude rationale: +2.0 is two-thirds of the SBD-over-AUD lineage gap —
  decisive between comparable tapes, but a 5-star/80-review alternative can
  still win.

### Era lineage override

```toml
[[selection.lineage_eras]]
collection = "GratefulDead"
date_from = "1980-01-01"
date_to = "1987-12-31"
scores = { matrix = 3.0, aud = 2.0, sbd = 1.0 }
```

For shows in the window, this map replaces the global
`sbd 3.0 / matrix 2.5 / aud 1.0` base scores: a strict MTX > AUD > SBD
inversion. First matching era wins; everything else in the score is
unchanged. The table above ships as the baked-in default.

## Plumbing

- `config.py`: `SelectionConfig` (`tapers`, `lineage_eras`) with the GD
  defaults; `Config.selection`.
- `scoring.py`: `score_recording` gains `taper_bonus: float = 0.0` and
  `lineage_scores: dict | None = None` (None = global table).
- `select_recording.py`: resolves era scores and per-recording taper bonuses
  (with the newest-revision split) from `candidate.collection` +
  `candidate.date`; captures `addeddate` while fetching metadata.
- `pipeline.process_show` / `cli._execute`: pass `config.selection` through;
  `None` means `SelectionConfig()` defaults, so direct callers and tests get
  GD behavior without wiring.

## Testing

- scoring: bonus adds; era map inverts sbd/aud.
- config: GD defaults present; TOML overrides both tables.
- selection stage: miller beats an equal non-miller; the newer of two
  millers (by addeddate) wins; a 1982 GD aud beats an equal sbd; a
  non-GD collection is untouched by the defaults.
- docs: README `[selection]` example; workflow.md select-recording row.

## Out of scope

LLM-assisted selection; per-taper date windows; venue/city rules; any
change to winnow (show-level merit) — this is recording-level only.
