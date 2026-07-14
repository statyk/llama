# llama — Live Music Archive → Radio Station Pipeline

**Date:** 2026-07-14
**Status:** Approved design, pending implementation plan

## Purpose

A Python CLI tool that finds concerts on archive.org's Live Music Archive (LMA)
matching given criteria, synthesizes metadata and commentary about the specific
performance (from LMA data plus internet research), and produces a self-contained
"show package" — verified audio, playlist, track/set metadata, and LLM-distilled
DJ notes — for handoff to an automated, AI-dependent in-house radio station.

Primary use tilts toward Grateful Dead and similar acts: two sets plus encore,
rich fan commentary available online. The DJ must be able to introduce the show,
describe each set, and know in advance where the set break falls for a check-in
or station break.

## Decisions made during brainstorming

- **Operation:** Phased. Human-driven CLI first; every piece designed so the same
  pipeline runs unattended on a schedule later (`--auto`).
- **Handoff:** We define our own show-package format; the station side adapts.
  The station's ingest details (and any existing AI integration layer) are
  unknown — treated as an open question, isolated behind the package format and
  an optional `deliver` step.
- **Audio:** Downloaded locally, verified, and re-tagged. Airtime must not depend
  on archive.org uptime. (Note: LMA soundboards are officially stream-only;
  private in-house use accepted by the user.)
- **Stack:** Python. `internetarchive`/HTTP for archive.org, `mutagen` for tags,
  `typer` for CLI, `pydantic` for schemas.
- **AI layer:** Provider abstraction. Dev backend is headless `claude -p`
  (subprocess); OpenRouter backend later with no pipeline changes. Headless
  claude also supplies web search for research tasks.
- **Architecture:** Staged pipeline over an on-disk workspace (chosen over
  single-shot script and agent-orchestrated alternatives) — resumable,
  inspectable, human-editable between stages, LLM calls isolated at stage
  boundaries.

## Operating modes

- **One-off:** "Find me one (or a few) shows fitting this criteria" — run the
  pipeline once, produce 1–k packages.
- **Standing criteria:** A named, saved criteria profile for a recurring segment
  (e.g. "Sunday Dead Hour"). Each run finds and fully processes the next N
  qualifying shows, consulting a persistent **history ledger** to avoid
  duplicates. The ledger records every show selected (and explicit rejections,
  so they aren't re-winnowed).

## Pipeline stages

Each stage reads files written by earlier stages and writes its own artifacts;
stages only write outputs on success, skip work whose outputs exist unless
`--force`, and are individually re-runnable.

1. **interpret** — LLM parses a natural-language query ("GD '73–'74 with a
   China>Rider", "top 10 GD shows of the '80s", "well-known folk/acoustic
   performer, '60s–'70s, highly rated") into `criteria.json`: hard filters
   (collection/artist, date range), soft preferences (style, mood), setlist
   constraints (song sequences), quality thresholds, and count N. A standing
   profile stores exactly this object, skipping the stage.

2. **search (wide net)** — Query archive.org with only the hard filters,
   deliberately over-fetching (potentially hundreds of items); group recordings
   by performance. Bulk-fetch cheap winnowing inputs per candidate: description
   (setlist), ratings, review counts, review texts. Writes `candidates.json`.

3. **winnow** — The quality gate, escalating in cost:
   - *Mechanical filters:* parse setlists from descriptions; enforce setlist
     constraints (e.g. china>rider), completeness, plausible length.
   - *Review-quality scoring (LLM over cached data):* assess LMA reviews with
     explicit skepticism of "I was there" nostalgia — weight reviews evaluating
     the recording/performance on merit, discount attendance bias, note
     recording-quality complaints. The LMA is completist; the bar is evidence
     the show is well received by people who were **not** there.
   - *Light web research* on the surviving shortlist only (~top 10–15):
     external reputation — best-of lists, blog writeups, fan-poll rankings.
   - Consults the ledger to exclude past selections before ranking.
   - Output: `shortlist.json` — ranked, with a per-show quality dossier
     (one paragraph of rationale each).
   - **Optional human gate:** in interactive mode, or when a profile mandates
     it, the shortlist is presented for approval/pruning before any expensive
     processing. "Best-of top 10" queries are a winnow that keeps 10.

4. **select-recording** — For each approved show, pick the best recording of it
   (purely recording quality; show merit was settled by winnowing). Writes
   `selection.json` including scores of rejected siblings.

5. **gather** — Full metadata for the chosen item: files, tags, durations,
   setlist parsed to tracks, set boundaries mapped to track indices, junk-file
   flagging, track-title resolution. Writes `show.json`, `reviews.json`.

6. **research (deep)** — LLM with web search digs into this specific
   performance, seeded with the winnow dossier. Writes `research.md` with
   citations.

7. **synthesize** — Distill show model + reviews + research into DJ material:
   show intro, per-set intros, set-break talking points, encore/outro. Writes
   `dj-notes.md` + structured `dj-notes.json`.

8. **package** — Download audio, verify, tag, emit `package/`; optional
   delivery to a watched folder. On success, record the show in the ledger.

Stages 4–8 loop per approved show when N > 1. Expensive work (deep research,
synthesis, downloads) happens only after winnowing.

## Workspace layout and ledger

Configurable root (default `~/.llama/`); the repo stays code-only.

```
<root>/
  config.toml                    # LLM backend/models per task class, delivery path, defaults
  profiles/
    sunday-dead-hour.toml        # saved criteria + N, human-gate flag, schedule hints
  ledger.jsonl                   # one line per show selected/rejected
  runs/
    2026-07-14-china-rider/
      criteria.json
      candidates.json
      shortlist.json
      shows/
        gd1973-06-10/            # canonical performance id
          selection.json
          show.json
          reviews.json
          research.md
          dj-notes.md
          dj-notes.json
          package/               # the only thing the station sees
```

**Ledger:** append-only JSONL (not a DB). Human-readable and hand-editable;
dedup is an in-memory set. Entries record performance identity
(artist + date + venue), not item id, so a different recording of an
already-played show still counts as a duplicate. Statuses: selected, delivered,
rejected.

## Show package format

Self-contained; no references back into the workspace.

```
package/
  manifest.json
  playlist.m3u                   # relative paths, play order
  dj-notes.md
  audio/
    01 - Morning Dew.mp3
    ...
```

`manifest.json` (versioned via `schema_version`):

- **show:** artist, date, venue, city, era/tour context line
- **source:** archive.org item id + URL, recording lineage, transfer credit
- **tracks:** ordered `{index, set: "1"|"2"|"encore", title, filename,
  duration_sec, segue: bool}` — segues marked so the DJ system doesn't talk
  over China Cat > Rider
- **set_breaks:** explicit positions ("after track 8"), each pointing at the
  DJ-notes segment for the check-in
- **dj_notes:** structured intro / per-set intros / set-break talking points /
  outro (inline, plus the `.md`)
- **total_duration_sec** and per-set durations for station clock planning

Audio files renamed `NN - Title.ext` and re-tagged (artist, title,
album = "YYYY-MM-DD Venue, City", track number, comment = source item id).

## LMA data handling (deterministic core)

- **Search:** `advancedsearch.php` over `mediatype:etree`; hard filters map to
  indexed fields (`collection`, `date` range, `avg_rating`, `num_reviews`,
  `venue`); lightweight field list in bulk. Item detail via
  `archive.org/metadata/<id>` (files + description + reviews in one call),
  rate-limited and cached on disk.
- **Performance grouping:** normalized `(collection, date, venue)`; canonical
  id like `gd1973-06-10`. Early/late same-day shows disambiguated by venue
  string matching. Identifier patterns are *not* trusted for parsing.
- **Setlist parsing:** defensive parser over conventional description layouts
  ("Set 1:", "Set II", "E:", "d1t01 - ..."); extracts ordered songs with set
  assignments and segue markers (`>`), reports confidence. LLM
  `extract-setlist` fallback when parsing fails. Song-name normalizer with a
  shipped, editable alias table (GD-heavy initially) for setlist-constraint
  matching.
- **Track-title cascade:** embedded tags → filename-position alignment against
  parsed setlist (count-sanity-checked) → sibling recordings with better tags.
  Resolution method recorded per track; unresolved tracks flagged, never
  guessed; human fix offered in interactive mode.
- **Recording selection score:** lineage class (sbd/matrix > aud > unknown)
  + avg_rating weighted by log(review count) + mp3 derivatives available
  + completeness vs consensus setlist − recording-quality complaints from
  review analysis. Deterministic and explainable.
- **Junk filtering:** keep only files that are `source: original` (or
  derivatives of originals) AND match the item's dominant filename convention
  AND have plausible duration. Kills spam mp3s (e.g. `FOLLOW-ME @BYPIKENO.mp3`
  present in the gd73-06-10 item), stray text/checksum files, truncated
  uploads. Exclusions logged in `show.json`.
- **Download & verify:** prefer VBR mp3 derivatives (FLAC configurable);
  verify size/md5 against item metadata; resume on retry; post-download real
  durations (mutagen) reconciled with manifest — >5s mismatch flags
  needs-review instead of shipping.

## LLM layer

Two provider capabilities, kept separate:

- `complete(task, input)` → validated JSON or markdown; no tools.
- `research(brief)` → markdown with citations; requires web search. Backends
  without it raise a clear error, never degrade silently.

**Backends:** v1 ships `claude_cli` (subprocess `claude -p
--output-format json`; tool permissions locked to the call's needs — none for
`complete`, WebSearch only for `research`). Later: `openrouter`
(OpenAI-compatible HTTP + search-enabled models). Config maps task classes to
backend+model so cheap models handle mechanical extraction and stronger models
handle research/synthesis. A `fake` backend serves tests.

**Six touchpoints**, each a named task with its own prompt template and output
schema:

1. `interpret` — NL query → criteria.json
2. `score-reviews` — candidate's LMA reviews → attendance-bias-aware quality
   assessment (batched several candidates per call)
3. `light-research` — shortlist survivor → external-reputation check *(research)*
4. `extract-setlist` — description text → setlist JSON (parser fallback)
5. `deep-research` — approved show + dossier → research.md *(research)*
6. `synthesize` — show model + reviews + research → DJ notes (md + json)

**Prompts** are versioned template files in-repo (`prompts/*.md`).

**Validation:** every structured output validated with Pydantic; on failure the
error is fed back for up to 2 retries, then the stage fails loudly with raw
output preserved. Failed stages never write downstream artifacts. `synthesize`
gets a factual guard: song names and set structure in DJ notes cross-checked
against `show.json` (no misnamed encores on air).

## CLI surface

```
llama find "GD shows 73-74 with a china>rider" [--limit 3] [--auto]
llama profile add sunday-dead-hour "criteria..." --count 1 --human-gate
llama profile run sunday-dead-hour           # standing mode: next N, dedup vs ledger
llama run <run-dir> --stage winnow --force   # re-run one stage of an existing run
llama review <run-dir>                       # human gate: approve/prune shortlist
llama ledger list | add | remove
llama deliver <show-dir> [--dest PATH]
```

`--auto` suppresses all interactive prompts (top-ranked candidates taken, human
gate skipped unless the profile mandates it). Phase-2 scheduling is just
`llama profile run X --auto` from cron.

## Error handling posture

- Stages idempotent; outputs written only on success; any failure resumable
  via `--stage`.
- archive.org calls: retries with backoff + on-disk cache; mid-run outages
  leave a resumable run.
- Anything suspicious — unresolved titles, duration mismatches, low-confidence
  setlist parse, factual-guard failure — marks the show `needs-review` rather
  than silently shipping. `--auto` runs skip needs-review shows and report it.

## Testing strategy

1. **Unit tests, real fixtures:** captured archive.org responses for canonical
   shows (gd73-06-10 RFK included — it exhibits the spam-file problem).
   Table-style tests for setlist parser, song normalizer, performance grouping,
   junk filter, recording scorer, manifest generation.
2. **Pipeline tests, fake LLM:** canned schema-valid responses; full pipeline
   runs offline and deterministically in CI, including validation-retry and
   failure paths.
3. **Live smoke test (manual, opt-in):** one real end-to-end run against
   archive.org + real claude backend on a known show. Not in CI.

## Open questions / future work

- **Station ingest:** the radio system's actual ingest mechanism and whether it
  has an existing AI integration layer are unknown. Isolated behind
  `manifest.json` (versioned) and the `deliver` step; revisit when details
  arrive.
- **OpenRouter backend:** planned second provider; interface already shaped
  for it.
- **Scheduling:** phase 2; cron + `--auto` requires no code changes.
- **LMA stream-only policy:** downloads are for private in-house use; if this
  ever changes scope, revisit.
