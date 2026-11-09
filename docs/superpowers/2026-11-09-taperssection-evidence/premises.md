# Taper's Section premise probes (Task 0), measured 2026-11-09

## FIXTURE IDENTIFIERS (later tasks consume these)

- Phish PRIMARY: `phish1997-12-29.003886.newyork.mk41.cmc6.flac1644`
  (packages/llama/tests/fixtures/phish1997-12-29.003886.newyork.mk41.cmc6.flac1644.json). creator "Phish",
  date 1997-12-29, addeddate 2025-09-08 (older than 75 days), description has
  `Source: DFOB: Schoeps CMC6/MK41> Sonosax SX-M2> SV-MD1> CD` (an aud source line), title
  "Phish - 1997-12-29 - Madison Square Garden - New York, NY", no `source`/`lineage` metadata field.
  15 tracks, Flac + VBR MP3.
- Phish SECONDARY (documented "Recording Info:, no source line" case): `ph2017-07-30.139097.mk4.miller.flac2496`
  (packages/llama/tests/fixtures/ph2017-07-30.139097.mk4.miller.flac2496.json). Its gear sits under "Recording Info:"
  and a bare `Schoeps CMC6/MK4 > ...` line, which is not a Source/Src/Lineage/Transfer line, and it has no
  `source`/`lineage` field; `classify` for it can rest only on the identifier token `mk4`. Addeddate 2024-07-29.
- Which Phish fixture each consumer uses: Task 2 (classify) primary for the source-line path, secondary for the
  no-source-line/identifier-token path; Task 5 primary; Task 9 primary; Task 12 primary. **Task 12 must CONFIRM the primary
  fixture reaches `packaged` with no review flags (the 39-item setlist parse below contains duplicated/noise items); do not assume it.**
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

(a) setlist.fm name for JGB: **ANSWERED, PARENT-MEASURED** (the parent session ran it on the operator's direct approval; the Task 0 implementer did not, and no API key appears anywhere in the repo or evidence).
Query `GET https://api.setlist.fm/rest/1.0/search/setlists?artistName=<name>&year=1976`.
"Jerry Garcia": total 78; all 20 on page 1 are artist "Jerry Garcia Band" (mbid 3f7a73e5-cb7f-4488-bd7e-f5e26c87fe1b), e.g. 1976-12-23 Keystone Berkeley.
"Jerry Garcia Band": total 78, same artist and mbid.
Conclusion: setlist.fm files 1976 JGB dates under "Jerry Garcia Band", and artistName search is fuzzy (both names hit the same 78 setlists); a Garcia entry should set `setlistfm = "Jerry Garcia Band"` to be exact.

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

## Fix round 1: checks on the PRIMARY Phish fixture (`phish1997-12-29.003886.newyork.mk41.cmc6.flac1644`)

Command (run from the worktree root):
```
./.venv/bin/python scripts/capture_fixture.py phish1997-12-29.003886.newyork.mk41.cmc6.flac1644
./.venv/bin/python - <<'EOF'
import json
from llama.junk import filter_files, FORMAT_BY_AUDIO
from llama.setlist import parse_setlist
n='phish1997-12-29.003886.newyork.mk41.cmc6.flac1644'
d=json.load(open(f'packages/llama/tests/fixtures/{n}.json')); m=d['metadata']
for aud,fmts in FORMAT_BY_AUDIO.items():
    kept,exc,o=filter_files(d['files'],want_format=fmts)
    print(aud,'kept',len(kept),sorted({f['format'] for f in kept}),'excluded',len(exc))
ps=parse_setlist(m['description'])
print('conf',ps.confidence,'n',len(ps.items))
EOF
```
Output:
- (c) mp3 -> 15 kept, all `VBR MP3`, 0 excluded (first `phish1997-12-29s1t01.mp3`); flac -> 15 kept, all `Flac`, 0 excluded. PNG/JPEG/spectrogram files not kept. One format wins.
- (d) `parse_setlist`: confidence `high`, 39 items for a 15-track show (sets {1: 18, 2: 10, encore: 11}). The description carries the setlist twice: first as
  "s1t01 - NICU" track-file lines (titles keep the `sNtNN - ` prefix, segue flags set from ">"), then again as plain titles; the first block ends with
  noise lines parsed as encore songs ("Unfinished.", "----------", "original text file", "Phish 12-29-97", "Madison Square Garden", "New York", "NY"), and the plain list
  ends with "Uploaded to gdlive by ..." as an encore song; "Good Times Bad Times" is split into "Good Times" / "Bad Times"; "YEM" is a separate unresolved title.
  Net: HTML-free text parses with set markers but the setlist is duplicated and noisy while graded `high`. Same conclusion as for the secondary fixture.

## 3(f) date cross-check per artist

Command: `./.venv/bin/python scripts/taperssection_probe.py dates` (2026-11-09; scrape cached outside the repo; creator exact via `norm_creator`; "dates emptied" = dates whose every recording has `ts_rules.date_disagrees` true).

| artist | exact-creator items | dated | date_disagrees | rate | dates | dates emptied |
|---|---|---|---|---|---|---|
| Phish | 11133 | 11131 | 168 | 1.5% | 1881 | 95 |
| Jerry Garcia | 1648 | 1648 | 0 | 0.0% | 892 | 0 |
| Gov't Mule | 360 | 359 | 17 | 4.7% | 284 | 13 |
| Dave Matthews Band | 112 | 112 | 0 | 0.0% | 104 | 0 |
| Trey Anastasio | 111 | 111 | 3 | 2.7% | 68 | 2 |
| Trey Anastasio Band | 78 | 78 | 2 | 2.6% | 65 | 2 |
| Pavement | 107 | 107 | 0 | 0.0% | 100 | 0 |
| Medeski Martin & Wood | 101 | 101 | 1 | 1.0% | 90 | 1 |
| Allman Brothers Band | 85 | 85 | 0 | 0.0% | 76 | 0 |
| Black Crowes | 84 | 84 | 0 | 0.0% | 71 | 0 |
| Wilco | 74 | 74 | 2 | 2.7% | 70 | 1 |
| Warren Haynes | 51 | 51 | 1 | 2.0% | 39 | 1 |
| Neil Young & Crazy Horse | 47 | 47 | 0 | 0.0% | 29 | 0 |
| Sonic Youth | 44 | 44 | 0 | 0.0% | 44 | 0 |
| Primus | 43 | 43 | 0 | 0.0% | 37 | 0 |
| Bruce Hornsby | 44 | 44 | 2 | 4.5% | 41 | 2 |
| Pearl Jam | 34 | 34 | 0 | 0.0% | 34 | 0 |
| Mike Gordon | 41 | 41 | 0 | 0.0% | 27 | 0 |
| Nine Inch Nails | 5 | 5 | 1 | 20.0% | 5 | 1 |

## 3(g) title venue precision

Command: `./.venv/bin/python scripts/taperssection_probe.py venue > table.md` (2026-11-09; cached Phish scrape of 11,133 items, no live call; seeded sample `random.Random(7).sample` of 100 titles, parser `llama.ts_measure.parse_title_venue`).

Result, judged by reading each title:

- Parsed (venue found): **91 of 100**. Correct: **90**. Wrong: **1** ("Phish Live At Syracuse Armory-Syracuse, New York On 1992-05-09" gave venue "Syracuse Armory-Syracuse, New York": venue and city fused in the title, so the venue slot also carries the city; harmless for a fallback label).
- Faithful to a typo in the title (not counted wrong): "Northampton. MA", "Phileadelphia, PA".
- Not parsed: **9 of 100**. Two have no venue to find ("Phish 08.13.04", "Phish - Undated and Uncirculated - 1980s compilation"). Seven carry a venue with no separator, so the parser abstains rather than guess a venue/city split: "Phish 2025-09-19 Hampton Coliseum Hampton, VA ak40" and four like it ("Phish 2024-07-23 Mohegan Sun Arena ...", "... Forest Hills Stadium Forest Hills, NY ...", "... Dick's Sporting Goods Park mk4v 2496", "2025-09-21 Hampton Coliseum ..."), plus "Phish Live At Folsom Field Boulder, CO 2025-07-04" and "Phish Live At Ameris Bank Amphitheatre Alpharetta, GA 2025-09-16" (no " on ").
- Precision of parses: 90/91 = 99%. Recall on titles that name a venue: 91/98 = 93%. No date ever landed in a venue slot.
- Probe fix made along the way: the first run gave a wrong parse for "PHiSH 2009-08-08 @ The Gorge Amphitheatre - George, WA - Nakamichi CM700/CP702" (city "WA - Nakamichi CM700/CP702"); the `@` form now stops at the second " - " segment (pinned in `test_parse_title_venue_three_forms`).
