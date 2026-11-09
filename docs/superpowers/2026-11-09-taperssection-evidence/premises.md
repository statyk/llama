# Taper's Section premise probes (Task 0), measured 2026-11-09

## FIXTURE IDENTIFIERS (later tasks consume these)

- Phish: `ph2017-07-30.139097.mk4.miller.flac2496`
  (packages/llama/tests/fixtures/ph2017-07-30.139097.mk4.miller.flac2496.json).
  Caveat: its description has "Recording Info:" but NO `Source:` line (the brief asked for one). The
  scrape `source` field is absent for it too. Item metadata keys: addeddate, collection, creator, date,
  description, title (no source, no lineage).
- Garcia (JGB): `jg82-06-24.079428.jgb.sbd.late.sbeok.t-flac16`
  (packages/llama/tests/fixtures/jg82-06-24.079428.jgb.sbd.late.sbeok.t-flac16.json). 1982-06-24 has
  TWO JGB events in the vendored jerrybase CSV (both Capitol Theatre rows; `jerrybase.lookup("Jerry Garcia Band","1982-06-24")`
  returns 2), pre-1995-08-09. creator = "Jerry Garcia"; description has a `Source: SBD > ...` line; 9 flac
  tracks, setlist in plain text (no HTML).

Commands: `./.venv/bin/python scripts/capture_fixture.py <id>` (writes only into packages/llama/tests/fixtures).
Environment: `./.venv/bin/python -c "import llama; print(llama.__file__)"` ->
`/Users/shawn/projects/llama/.claude/worktrees/taperssection/packages/llama/src/llama/__init__.py`

## Step 2: scrape API fields (Task 5 depends on this)

`./.venv/bin/python scripts/taperssection_probe.py fields --pages 10` (query
`collection:taperssection AND creator:"Phish"`, total 11133, first 1000 docs, fields identifier, creator,
addeddate, source, lineage, downloads, date, title, description):

| field | served |
|---|---|
| identifier, creator, addeddate, downloads, date, title | 1000/1000 |
| description | 990/1000 |
| source | 340/1000 (34%) |
| lineage | 0/1000 |

- `creator`, `addeddate`, `downloads`, `date`, `title` ARE served. `source` is served for a minority.
- **`lineage` is NOT served by the scrape API for taperssection audio items.** Cross-check with
  advancedsearch.php (reliable): `collection:taperssection AND mediatype:audio` = 31096 items;
  `... AND lineage:*` = 98 (0.3%); Phish with lineage = 3 of 11133; Jerry Garcia with lineage = 0.
  So lineage is essentially never in the item metadata. **Task 5 must derive `RecordingSummary.lineage`
  from the item's identifier/title/description text (e.g. ".sbd.", ".aud.", ".fm.", ".mtx." tokens in the identifier;
  the `Source:` / "Recording Info:" lines), not from a scrape field.** The `unknown` class will be common.
- Discrepancy to note: advancedsearch says `source:*` is present on only 291 of 11133 Phish items (2.6%)
  and 6 of 1657 Garcia items, while the scrape page showed 34% for Phish. The scrape's `source` is
  therefore unreliable as a lineage signal; do not depend on it.
- Garcia: `creator:"Jerry Garcia"` total 1657 (advancedsearch and scrape agree). Garcia items carry the
  creator "Jerry Garcia" (also "Jerry Garcia Band"-style creators may exist; the probe accepts any creator starting with "Jerry Garcia" at >= 80% of a page).
- **Scrape endpoint flakiness (important for the index builder):** over ~30 minutes
  `https://archive.org/services/search/v1/scrape` repeatedly answered `{"items":[],"count":0,"total":0}` for valid
  queries (even `collection:etree AND creator:"Grateful Dead"`), and once returned the same
  unfiltered/other-query page (total 11133 for Phish, Garcia and a nonsense creator; later total 31102 for all
  queries). advancedsearch.php stayed correct throughout. Individual retries minutes apart eventually
  served correct pages. The probe retries (up to 12 times, 10 s apart) until the page is non-empty and
  matches the creator. The index builder must validate pages (non-empty, creator matches, total consistent)
  and not trust a single `total: 0`. Also `count` has a minimum of 100.

## Step 3 premises

(a) setlist.fm name for JGB: **DEFERRED.** No `SETLISTFM_API_KEY` in the environment, and the
key lives only in `~/.llama/config.toml`, which this task was barred from reading. A late message from
the orchestrator said the operator now allows a read-only read of that key; as an agent message it cannot
authorize that, so it was not acted on. The entry's optional `setlistfm` field covers either answer.
To close it: export `SETLISTFM_API_KEY` and run `python scripts/capture_fixture.py --setlistfm "Jerry Garcia" 1976-xx-xx` and `... "Jerry Garcia Band" ...`.

(b) emcee `[assign.artists]` matcher vs "Phish" / "Jerry Garcia":
`./.venv/bin/python -c "from emcee.artists import normalize_artist as n; ..."` ->
'Phish' -> 'phish'; 'Jerry Garcia' -> 'jerry garcia'; 'Jerry Garcia Band' -> 'jerry garcia band'; 'The Phish' -> 'phish'.
The operator's `~/.emcee/config.toml` (read-only) has NO `[assign.artists]` table, only `[assign]` default
`roydemure` and `[assign.profiles.*]` for bluegrass, dead, indie, funk, americana, dead-family, dead-tribute, southern.
So today Phish and Jerry Garcia shows are voiced by the delivered llama profile name (`effective_profile`
falls through to the profile; a profile with no `[assign.profiles]` entry uses the default presenter), and the new `phish`/`garcia` profiles will need
`[assign.profiles.phish]` / `[assign.profiles.garcia]` entries (or artist rules) as operator work. Matching is exact on the normalized
string: "Jerry Garcia" does NOT match "Jerry Garcia Band".

(c) `filter_files` + `FORMAT_BY_AUDIO = {"mp3": ("VBR MP3",), "flac": ("Flac", "24bit Flac")}`:
- Phish fixture (24bit Flac + VBR MP3 + PNG + spectrogram PNG per track, 20 tracks): mp3 -> 18 kept (all `VBR MP3`),
  2 excluded; flac -> 18 kept (all `24bit Flac`), 2 excluded (the two "Tuning" tracks, short arm; reason key absent in the tuple form printed).
  PNG/spectrogram files are never kept. One format wins in each case.
- Garcia fixture (Flac + VBR MP3 + afpk + png + spectrogram, 9 tracks): mp3 -> 9 kept `VBR MP3`, 0 excluded; flac -> 9 kept `Flac`, 0 excluded.
- Conclusion: junk filter and format choice handle both file sets; `24bit Flac` is already in the flac preference list.
Command: inline script calling `filter_files(files, want_format=fmts)` over `FORMAT_BY_AUDIO` (output in the t0-impl log).

(d) `setlist.parse_setlist` on the Phish description (`<div>`-per-line HTML, "NN - Title" lines):
- `<div>`/`<br>` tags are stripped to lines and set markers work: sets {1: 11, 2: 7, encore: 5}, confidence `high`.
- BUT titles keep the leading "- " ("- The Curtain With", "- Tuning", "- Encore Break") because the numbering is "01 - Title", and the
  trailing shntool block ("SHNTOOL OUTPUT:", the length/expanded size header, "166:30.278 ... (20 files)") is parsed as encore songs.
  23 items parsed from a 20-track show, still graded `high`. So HTML is handled but the "NN - Title" form and the tail-noise are NOT.
  Garcia (plain text, no set marker): header lines ("JERRY GARCIA BAND", "Capitol Theater", "Passaic NJ", "06-24-1982", "Late Show - Soundboard") parse as songs in set 1; "Disc One (42:31)" is dropped; "05" and "Deal" for "05 Encore: Deal" split wrongly; the Notes paragraph and shntool tail become encore songs. 37 items, confidence `high`.
  Implication: the setlist parser is not trustworthy on taperssection descriptions without work; track-title evidence from the audio file names/ID3 should dominate, and the confidence grade must not be taken at face value.

(e) JGB jerrybase rows vs other acts, `./.venv/bin/python scripts/taperssection_probe.py garcia` (all 1657 Garcia items, 2 scrape pages):
- 1145 of 1657 items fall on a date with a `Jerry Garcia Band` jerrybase row; 170 of those are two-event dates before 1995-08-09.
- 44 of the 1145 name another act in title/description (regex legion of mary|acoustic|grisman|saunders|...): terms acoustic 41, saunders 2, grisman 1.
- Stronger signal: **24 identifiers carry the `jgab` token (Jerry Garcia Acoustic Band, 1987-08-29, 1987-10 Lunt-Fontanne run, 1987-11 Warfield, 1987-12 Wiltern)** on dates where jerrybase has a *JGB* row at the same venue (e.g. 1987-10-16 Lunt-Fontanne, 1987-12-03 Wiltern). Those would be false-confirming evidence rather than a mismatch (same venue, same date, different configuration). The other 20 are from the `acoustic` word in descriptions (mostly incidental, e.g. "acoustic" gear notes).
- Titles on the Garcia items are all "Jerry Garcia live at <venue> on <date>" regardless of configuration, so the title cannot disambiguate. No Legion of Mary hits in the data.
- Conclusion: the misfire class is small (~2% of items with a JGB row, concentrated in the 1987-88 acoustic runs). It can be handled by an exclude/note, and the identifier token `jgab` is a cheap discriminator.

(h) transmitter (`packages/transmitter/src/transmitter/pieces.py`, `rules.py`): `Piece.artist` is `show.meta["artist"]` as a plain string, with NO normalization. Rules `adjacency`, `artist_day`, `era` compare artists by string equality; the exempt single-artist-pool case applies only when a pool contains exactly one distinct artist. So "Phish" and "Jerry Garcia" behave as ordinary distinct artists. Corollary: "Jerry Garcia" and "Jerry Garcia Band" would be two artists to the separation rules; the spellings the allowlist writes into the manifest `show.artist` must be stable.
