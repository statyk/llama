# How llama works: the operator's guide

This is the user-facing map of the whole system: what the pipeline does, what
lands on disk where, the two different human gates and how they differ, every
command, every review flag, and a troubleshooting table from "message you saw"
to "what to do next." The design rationale lives in
`docs/superpowers/specs/`; this document is about *operating* it.

## The big picture

```
llama find "query"          llama profile run <name>
        │                           │
        ▼                           ▼
   interpret ──► search ──► winnow ──► [gate 1: shortlist approval]
                                              │
                              per approved show│
                                              ▼
             select-recording ──► gather ──► research ──► vet
                                              │
                            [gate 2: needs-review can halt here]
                                              │
                                  synthesize (default; --no-script skips)
                                              │
                                              ▼
                                          package ──► llama deliver
```

Every stage reads and writes plain files. Run-level artifacts (criteria,
candidates, shortlist) live in a per-run directory under `~/.llama/runs/`;
show-level artifacts live in a canonical **shows library** at
`~/.llama/shows/<slug>/` — one directory per performance, shared across
runs. Stages **skip work whose output file already exists**, so any command
that touches a run or show is cheap to re-execute — this is the core
mechanic behind resuming, and behind most of the answers in this guide.
Because the library is shared, a performance that surfaces again in a later
run lands on the same directory and reuses the expensive work (research,
package) already done.

Day to day, the workspace is show-centric: `llama status` is the triage
view (what's held, what's packaged and ready to deliver), and
`llama redo <show> --from <stage>` re-runs one show's pipeline tail without
touching its run or any other show.

There are two modes:

- **One-off:** `llama find "GD shows 73-74 with a china>rider"` — interprets
  the query, runs the whole pipeline.
- **Standing profiles:** `llama profile add` / `llama profile run` — a saved
  query re-run for recurring segments, deduplicated against the broadcast
  ledger so the same performance is never shipped twice.

## The on-disk workspace

Everything lives under `~/.llama/` (configurable as `root` in
`~/.llama/config.toml`):

```
~/.llama/
├── config.toml                  # optional; see README
├── ledger.jsonl                 # broadcast history (dedup + audit)
├── cache/                       # archive.org responses + artist index
├── profiles/<name>.toml         # standing profiles
├── runs/<run-name>/             # run-level artifacts only
│   ├── criteria.json            # interpreted query (interpret stage)
│   ├── candidates.json          # every performance found (search stage)
│   ├── shortlist.json           # ranked + scored top shows (winnow stage)
│   └── artists.json             # artist-less queries only: matched artists
└── shows/<slug>/                # canonical shows library: one dir per
    │                            # performance, slug = slugified performance id
    │                            # (gratefuldead-1973-06-10), shared across runs
    ├── provenance.json          # which run processed it, winnow dossier,
    │                            # script setting — what `redo` replays from
    ├── overrides.json           # hand-authored or `llama show`-edited, durable:
    │                            # excluded tracks, narration mode, and metadata
    │                            # corrections (venue/city/date/titles/set_breaks);
    │                            # read by gather/synthesize, survives every redo
    ├── selection.json           # which recording won and why
    ├── show.json                # tracks, sets, flags — THE show state file
    ├── reviews.json             # raw listener reviews
    ├── research.md              # deep-research output
    ├── vetting.json             # grounding-check results
    ├── dj-notes.md/.json        # verbatim DJ script (default; absent with --no-script)
    ├── llm-failure.txt          # raw LLM output if a task failed validation
    └── package/                 # the deliverable
        ├── manifest.json        # schema v2: tracks, sets, durations, context
        ├── playlist.m3u         # music-only play order
        ├── broadcast.m3u        # voiced shows only: DJ audio interleaved
        ├── audio/               # verified, tagged tracks
        ├── research.md
        ├── reviews.md
        ├── dj-notes.md          # absent only with --no-script
        └── dj-audio/            # opt-in TTS clips; present only when voiced
```

Run names default to `YYYY-MM-DD-<slugified-query>` for `find` and
`YYYY-MM-DD-<profile-name>` for profiles. Show slugs come from the
performance identity (artist + date), so they are stable across runs by
construction.

Three files deserve a callout:

- `show.json` carries `needs_review` and `review_flags`, and it is what
  gate 2 reads. When a show is held, this file says why.
- `provenance.json` is written every time a show is processed: which run
  caused it, the winnow dossier and quality assessment, and the script
  setting. It is what lets `llama redo` re-run a show standalone — the
  originating run directory doesn't even need to exist anymore.
- `overrides.json` is the opposite of both: it is never written by a stage,
  only by you (via `llama show`), and it is never derived away. It holds
  excluded source filenames, the narration mode (`full`/`vague`), and
  metadata corrections — `venue`, `city`, `date`, `titles` (track number →
  forced title), and `set_breaks` (track numbers a break falls after,
  numbered sets only). `gather` reads the exclude/titles/venue/city/date/
  set_breaks fields, `synthesize` reads `narration`, and it survives every
  `redo`, including ones that drop everything else downstream of a stage.

## Names and states: the catalog

Every command that takes a show or run accepts a **name, a unique
substring, or a path**: exact match wins, otherwise a substring that
matches exactly one candidate resolves to it, otherwise the command fails
loudly and lists the matches. `llama show 1973-06-10` is the typical form;
`llama run countryish` resolves `2026-07-16-countryish`.

A show's **state** is never stored — it is derived from which artifacts
exist plus the ledger, so it cannot go stale:

| State | Derived from | Meaning |
|---|---|---|
| `held` | `show.json` has `needs_review: true` | Gate 2 hold; sorts first in `llama status`, flags shown inline |
| `delivered` | ledger has a `delivered` entry for the performance | Shipped to the station |
| `packaged` | `package/manifest.json` exists | Ready to deliver |
| `scripted` / `vetted` / `researched` / `gathered` / `selected` | deepest stage artifact present | In-flight (or abandoned mid-pipeline) |

`llama status` is the triage table over these states; `llama runs`
summarizes per-run show counts. Both are in the command reference below.

## The stages

| Stage | LLM? | Writes | What it does |
|---|---|---|---|
| interpret | yes | `criteria.json` | Query → structured criteria (artist, era, count, constraints) |
| discover | yes | `artists.json` | Artist-less queries only: match style against the LMA artist index |
| search | no | `candidates.json` | Wide-net archive.org search via the cursor-paginated scrape API — every matching recording, uncapped; groups recordings by performance identity (artist + date + venue). Complete recording lists matter downstream: siblings feed set-structure recovery and recording selection |
| winnow | yes ×2 | `shortlist.json` | Ledger dedup → mechanical floors (rating/review count, setlist constraints) → LLM review scoring → quality floor (`min_quality_score`, default 6.0: lower-scored shows are dropped with a warning, so a thinning pool comes back short and loud instead of quietly mediocre) → light web research on the top 12+. When survivors exceed the review-fetch budget (`[winnow] max_metadata_fetch`, default 40), it samples the best-evidenced, bounded by `artist_cap`/`year_cap`. The shortlist cut is best-score-first with per-artist share capped at `artist_cap` (default 1/3) and per-year share capped at `year_cap` (default 1.0 = off — scores decide the year mix); equal scores tie-break on review evidence, not date |
| select-recording | no | `selection.json` | Picks the best *recording* of the performance: lineage (SBD > MTX > AUD, era-overridable — early-80s GD inverts to MTX > AUD > SBD), ratings, completeness (scales the score: fragments lose to fuller tapes), and `[selection.tapers]` reputation bonuses (miller/seamons for GD; newest revision of a taper preferred), sibling-relative download popularity, and embedded-title coverage (both small tie-breaker-sized terms) |
| gather | maybe | `show.json`, `reviews.json` | Junk-filters files, resolves track titles (tags → setlist → siblings), builds canonical set structure from all recordings + setlist.fm, aligns it onto tracks; LLM only as alignment/extraction fallback |
| research | yes | `research.md` | Deep web research on the specific performance |
| vet | yes | `vetting.json` | Extracts the research's factual claims; deterministic grounding check against the setlist and date |
| synthesize | yes | `dj-notes.*` | On by default (`--no-script` skips): verbatim DJ script, factually guarded against the manifest — spoken in the profile's presenter's persona when one is set, else the neutral house narrator |
| package | no | `package/` | Downloads audio (md5-verified), tags it, checks durations, writes manifest v2 + m3u + digests; if voice is active, also synthesizes `dj-audio/` clips (Voxtral by default, or ElevenLabs), adds the manifest's `dj_audio` block, and writes a `broadcast.m3u` with the DJ audio interleaved into play order |

Winnow's philosophy: the LMA archives everything, so mere presence means
nothing, and LMA reviews skew toward people who attended the show. The
scoring prompt demands merit-based praise, and light research looks for the
show's reputation *outside* the archive.

Quality earns the slots; caps only bound dominance. The shortlist cut and
the final auto-pick fill best-score-first with two optional bounds: while
other artists still have candidates, no artist may hold more than a share
of the batch (`--artist-cap` on `find`/`profile add`, default 1/3 — at
most ⌈n×cap⌉ slots), and `--year-cap` does the same per year (on
multi-artist runs, within each artist's own slots). `year_cap`
defaults to 1.0 (off): an unranged Dead query comes back 70s-heavy if
that's what the scores say. Set it for an era tour — `--year-cap 0.25`
keeps any year to a quarter of the batch; at or below 1/count it's strict
one-per-year rotation ("1969-1977" as a spread). Either cap at 1.0
restores pure top-N; a dominant artist or year is bounded, not rationed,
and if everything else runs out the cap relaxes rather than
under-delivering. The review-fetch sampling honors the same caps, and
equal scores tie-break on review evidence rather than date (score bands
cluster, and a date tie-break would quietly favor the earliest years).

Variety guarantees exist within a single batch only — nothing rotates
across runs, and the ledger's job is dedup, not rotation. Want no artist
repeated across your next N shows? Generate the N in one run. Explicit
`llama review` approvals are never capped; your picks are your picks.

## The two human gates (don't confuse them)

This is the single most confusing part of the system, so here it is plainly:

|  | Gate 1: shortlist approval | Gate 2: needs-review |
|---|---|---|
| **Question it asks** | "Which of these shows should we spend money processing?" | "Is this processed show clean enough to air?" |
| **Granularity** | The run's shortlist | One show |
| **Lives in** | `runs/<run>/shortlist.json` (`approved: true/false/null`) | `shows/<slug>/show.json` (`needs_review` + `review_flags`) |
| **Set by** | You (interactive prompt, or `llama review`) | The pipeline (gather/vet/synthesize/package flags) |
| **Cleared by** | `llama review <run>` | `llama show <show> --clear` (after you inspect) |
| **Surfaced by** | `Shortlist awaits review:` message | `llama status --held` |
| **What it blocks** | Processing starting at all | Packaging (or delivery, if flagged during packaging) |

**Gate 1** appears interactively during `llama find` ("Process which
ranks?"), or — for a `--human-gate` profile run with `--auto` — as the printed
message `Shortlist awaits review: llama review <run>`. `llama review`
records your picks and then offers to process them on the spot; decline and
it prints the resume command (`llama run <run>`) instead.

**Gate 2** fires per show, any time a stage records a review flag in
`show.json`. The pipeline checks it at three points (after vet, after
synthesize, after package) and prints `needs-review, skipped: <show>`. The
flags that can be set, and by which stage:

| Flag | Stage | Meaning |
|---|---|---|
| `unresolved track titles` | gather | Some filenames could not be mapped to song titles by any source |
| `low-confidence setlist` | gather | The best setlist parse is shaky |
| `low-confidence structure alignment` | gather | Setlist found, but it doesn't line up with the actual tracks (even after LLM fallback) |
| `setlist evidence shows multiple sets but alignment found none` | gather | Sources say multi-set; the aligned tracks came out flat |
| `single-set structure for a long show (N min)` | gather | 150+ minutes (configurable `guard_min_minutes`) with zero set breaks — past the plausible length of one uninterrupted set |
| `no playable tracks` | gather | Junk filtering left nothing |
| `research asserts unknown song: X` | vet | Most of the research's song assertions don't match this show's tracks (≥2 unknown and more than a third of all assertions — the wrong-show signal). Titles match loosely: segue chains ("A > B") check per-song, and prose variants ("Caution", "One More Saturday Night") match tracks by containment. One or two strays never block |
| `research asserts wrong date: X` | vet | Research names a date that isn't this show's date (year-less forms like "December 2" or "3/2" compare against the show's month and day) |
| ~~unparseable date~~ | vet | No longer blocks: a date the checker can't parse is recorded in `vetting.json` but can't-verify is not a contradiction |
| `dj notes mention unknown song / nonexistent set / missing set intros / break count mismatch` | synthesize | The DJ script contradicts the manifest |
| `duration mismatch on <file>` | package | Downloaded audio's real length disagrees with metadata |

**Clearing gate 2.** There is deliberately no `--force`-through-processing
flag: a flagged show stays held until a human looks. Looking means
`llama show <show>` — it prints the flags, state, a table of which stage
artifacts exist, and (if non-default) the current `overrides.json`. From
there you're choosing one of three resolutions:

| Resolution | When | Do | Clears the hold? |
|---|---|---|---|
| **Correct** | The flag is real and fixable — e.g. junk tracks slipped past the filter, or a setlist source is missing | `llama show <show> --tracks` to see the numbered track list, then `llama show <show> --exclude 9,10` (by track number or filename; `--include` to undo one) and `llama redo <show> --from gather` | No — a clean re-gather self-clears by producing structure with no flags |
| **Accept as vague** | The setlist genuinely can't be resolved, but the show is otherwise fine to air without naming songs | `llama show <show> --vague`, then `llama redo <show> --from synthesize` | Yes, immediately (narration mode also survives future redos) |
| **Overrule** | The flag is a false alarm | `llama show <show> --clear`, then `llama redo <show> --from package` | Yes, immediately |

Wrong non-track metadata — venue, city, date, a track's title, or where the
set breaks fall — is a variant of **Correct**, not a fourth resolution:
`llama show <show> --set-venue "..." --set-city "..." --set-date
YYYY-MM-DD --title N="..." --set-breaks "9,17"` force the corresponding
`overrides.json` field(s) the same way `--exclude` forces `overrides.exclude`,
and redo from `gather` the same way — see the `llama show` reference below
for the full flag set (`--clear-title`, `--clear-set-breaks`) and the
track-number lookup (`--tracks`).

Each resolution edits `overrides.json` (except overrule, which only clears
`show.json`'s flags) and by default just **prints** the follow-up `redo`
command rather than running it — add `--apply` to `llama show` to run that
redo inline instead of copy-pasting it (e.g. `llama show <show> --exclude
<file> --apply`). Stage precedence when multiple flags are set on
`--apply`/the printed command: an exclude or metadata edit redoes from
`gather`, a narration edit (with neither) redoes from `synthesize`, and
`--clear` alone redoes from `package`.

Deliver-time-only flags (`duration mismatch`) are a fourth, narrower case:
a package already exists, so `llama deliver <show> --force` overrides the
delivery refusal directly, with no `redo` needed.

## Voice (opt-in text-to-speech)

The DJ script can additionally be **spoken** during `package` — off by
default. The default backend is hosted Mistral Voxtral
(`voxtral-mini-tts-2603`); set `[tts] backend = "elevenlabs"` to speak via
ElevenLabs instead. Turn voice on globally (`[tts] enabled = true` +
`[tts] voice` in config), per invocation (`--voice` on `find`/`run`/
`review`/`redo`), or per profile by naming a **presenter** (below), which
opts that profile in even when `[tts] enabled` is false, so different
profiles can have different hosts and voices. `--no-voice` always turns it
off for that invocation. **Voice implies script**: turning voice on forces
the DJ script on even against `--no-script`, since there is nothing to
voice otherwise.

`[tts] voice` is the **house** voice — a preset name on Voxtral (or a
voice_id on ElevenLabs) — used whenever a run's profile names no
presenter. For a custom house voice, set `[tts] voice_clone` to a 3-25s
reference WAV instead — Voxtral clones it and ignores `voice`. (Voxtral's
open weights are CC BY-NC, but that only matters for self-hosting; llama's
non-commercial project only ever calls Mistral's hosted API, so the
license is irrelevant here. Self-hosting is deliberately out of scope.)

### Presenters: giving a show a host

A **presenter** is a reusable radio-show host — TTS voice + authored
character + on-air identity — defined by hand in
`~/.llama/presenters/<id>.toml`:

    name = "Casey"
    sex = "male"
    voice = "american-dj"          # or: voice_clone = "/path/to/casey-ref.wav"
    character = """
    Warm late-night FM veteran. Dry humor, deep tape-collector knowledge, gets
    audibly excited about big jams. Keeps it loose but never sloppy.
    """

A profile references one with `presenter = "<id>"` (`profile add
--presenter casey`) and names its show with `title = "..."`
(`--title "Sunday Morning Dead"`) — the host knows the title and drops it
on air occasionally. Naming a presenter fully owns that profile's voice:
`voice` XOR `voice_clone` on the presenter supplies the run's TTS voice
(and clone reference — the house `[tts] voice_clone` never bleeds into a
presenter's run), and the presenter is voiced even when `[tts] enabled` is
false. `voice_clone` on a presenter is Voxtral-only — it errors loudly if
`[tts] backend = "elevenlabs"`.

The presenter's character deliberately loosens `synthesize`'s grounding:
the host may voice opinions and adopt review/research sentiment as their
own (paraphrased, never quoted at length), but concert facts — dates,
venue, songs, set structure, personnel — still come only from the show
data, and the host never claims to have attended. `vet` and
`factual_guard` are unchanged and still hold a show for review if a script
strays. Character edits are live: edit the presenter's TOML, then `llama
redo <show> --from synthesize` re-scripts with the new persona — nothing
upstream needs to change.

Voiced shows gain `package/dj-audio/` (one MP3 per script segment) and the
manifest's `dj_audio` block — see [docs/station-brief.md](station-brief.md)
for the exact contract. Segments are cached per show by a hash of (text,
voice, model, chunk), so re-packaging with unchanged text doesn't re-spend
on the paid API.

**`[tts] chunk` (default off): sentence-level chunked synthesis.** Instead
of one TTS call per script segment, chunk mode splits the segment into
sentences, synthesizes each one separately (`fmt="wav"`), concatenates the
raw PCM with a short silence between sentences, and encodes a single MP3 at
the end via `lameenc`. This gives noticeably better prosody/pacing on
longer patter — a single long TTS call tends to rush or flatten out — at
the cost of more provider round-trips per segment. `chunk` is part of the
per-segment cache key, so flipping it re-renders affected clips on the next
`redo --from package --voice` (no `--force` needed). It requires the
`lameenc` dependency (installed by default). A too-short trailing sentence
fragment is folded back into the previous chunk so it isn't voiced as its
own tiny, context-free clip (which tends to come out as gibberish); and each
chunk is synthesized with its neighboring sentences as context — ElevenLabs
uses `previous_text`/`next_text` to keep prosody continuous across chunk
boundaries, while Voxtral has no such parameter and simply ignores it. The chunked encoder derives
its MP3 bitrate from the actual sample rate the provider returns (64kbps
for Voxtral's ~24kHz mono output, rather than a flat 128kbps) to avoid an
unusual bitrate/sample-rate combination that has been observed to trip up
some MP3 decoders with cosmetic `overread`/`enddists` warnings; this fix
hasn't been independently confirmed with `ffmpeg -v error` against a live
run (no network in the dev sandbox it was built in) — verify on a real
chunked show, and if warnings persist the documented next step is
resampling to 44.1/48kHz before encoding (not yet implemented).

**`[tts] bed`: instrumental bed under the DJ voice (default off).** A low
bed can play under every voiced clip: pre-roll (bed alone), bed-under-voice
for the duration of the speech, then a tail (bed alone), attenuated by
`[tts] bed_gain_db` (default **-20 dB**) with a short fade in/out. Set a
station-wide bed with `[tts] bed = "/path/to/bed.wav"`, or give a specific
host its own by setting `bed = "..."` in that presenter's
`presenters/<id>.toml` — a presenter's own bed overrides the station
default (the gain is always the station `bed_gain_db`, there's no
per-presenter gain). The bed file must be **24kHz mono 16-bit WAV**;
anything else, or a missing file, hard-fails that show's package rather
than shipping silently-wrong audio. Mixing is plain PCM math done with
`numpy` (a new dependency) — no `ffmpeg` is involved.

`llama` never converts audio, so prepare the bed in the required format once
with any external tool, e.g. `ffmpeg -i in.mp3 -ac 1 -ar 24000 -c:a pcm_s16le
bed.wav` (or `sox in.mp3 -r 24000 -c 1 -b 16 bed.wav`); these are one-time prep
tools, not runtime dependencies. Check with `ffprobe`/`soxi` that the result is
`pcm_s16le`, 1 channel, 24000 Hz before pointing config at it.

**Re-voicing an already-packaged show:** `llama redo <show> --from package
--voice` re-voices with the show's recorded voice (or, if it had none yet,
the current house `[tts] voice`, or the profile's presenter's voice).
`--voice`/`--no-voice` on `find`/`run`/`review`/`redo` only toggle voice on
or off — there's no per-invocation voice-id override; to actually switch to
a different voice, change `[tts] voice` (house shows) first. For a hosted
show it depends on what the presenter uses: editing `voice_clone` (or the
clip it points to) takes effect on the next `redo --from package --voice`,
since the clone reference is re-read live — but editing a preset `voice`
does **not**, because `redo` replays the voice *stamped* on the show at
process time; only a fresh `llama profile run` picks up a new preset voice.
`--force` re-renders
every clip instead of reusing the cache. A plain `llama run <run> --voice`
on a run whose shows are already packaged does **not** re-voice them — the
package stage is skipped because its output already exists — it prints a
note pointing at `redo --from package --voice`.

**Failure holds the show, not the batch.** If the TTS backend fails (bad
key, rate limit, missing key while voice is active), that show produces no
package (no manifest) and isn't delivered; llama prints `FAILED <show>: …`
and moves on to the rest of the batch. Retry with
`llama redo <show> --from package` once the API issue is resolved — the
cache means a retry only re-renders what didn't finish.

## Command reference

In every command below, `<show>` and `<run>` mean "name, unique substring,
or path" — see [Names and states](#names-and-states-the-catalog).

### `llama find "query" [--limit N] [--auto] [--no-script] [--voice/--no-voice] [--run-name NAME]`
One-off end-to-end run. Interactive by default: artist-less queries let you
prune the matched-artist list, and the shortlist prompt asks which ranks to
process (empty answer = top picks). `--auto` skips all prompts and takes the
top-ranked shows. The verbatim DJ script is generated by default (one extra
high-tier LLM call per show); `--no-script` skips it. `--voice` synthesizes
spoken DJ audio (Voxtral by default, or ElevenLabs; default follows
`[tts] enabled`; implies `--script`) — see
[Voice](#voice-opt-in-text-to-speech) above. Winnow knobs:
`--artist-cap`, `--year-cap`, `--min-score` (see the winnow discussion
above). `--full-rationale` prints each shortlisted show's complete
selection rationale instead of the first few lines (also available on
`run`, `review`, and `profile run`).

### `llama status [--held] [--packaged] [--voiced] [--unvoiced] [--broadcast-ready] [--state NAME] [--run NAME] [--artist SUBSTR] [--all] [--json]`
The triage table: every show in the library with its derived state, artist,
date, and originating run; held shows sort first with their flags indented
beneath. By default only the 5 most recently delivered shows are kept in
the listing — `--all` shows every delivered show. `--held` / `--packaged`
filter to one state ("what needs my judgment" / "what's ready to ship"),
`--voiced` / `--unvoiced` filter to packaged shows with or without DJ audio
(a show that isn't packaged yet is neither — it has no voiced status at
all), `--broadcast-ready` filters to shows that are actually airable right
now — packaged with every manifest track's audio file verified on disk, a
DJ script, DJ audio, a `broadcast.m3u`, and not held (positive-only; there's
no `--not-broadcast-ready`), `--state NAME` filters to one exact derived
state (e.g. `vetted`), `--run` filters to shows processed by that exact run
name, `--artist` substring-matches the artist, and `--json` emits the
records for scripting (each record now includes `voiced` — `true`/`false`/
`null` —, `broadcast_ready` — `true`/`false` —, and `overrides`, the show's
exclude list and narration mode). Text rows carry inline annotations for
anything non-default: `[broadcast-ready, voiced, vague, 3x-excl]`.

### `llama runs`
One line per run: name, show-state counts (via each show's provenance), and
the run's query. The run-side companion to `llama status`.

### `llama run <run> [--stage S --force] [--interactive] [--no-script] [--voice/--no-voice]`
**The resume/replay command.** Re-executes a run from its artifacts; every
stage skips work whose output already exists, so this is how you continue
after a crash, after `llama review`, or after fixing something by hand.
To re-run a stage for a *single show*, reach for `llama redo` instead —
`--stage --force` here applies to every show the run processes.

- `--stage <name> --force` deletes that stage's outputs **and everything
  downstream of it**, then re-runs — later stages can never reuse artifacts
  derived from the pre-force state. Deletion happens **per show, at process
  time, only for the shows chosen this run** — shows not selected for
  reprocessing keep their artifacts and packages intact. Valid stages:
  `search`, `winnow`, `select`, `gather`, `research`, `vet`, `synthesize`,
  `package`. Forcing `search` also drops the shortlist.
- Bare `--force` re-runs **everything**, including winnow — this rebuilds
  `shortlist.json`. If approvals were recorded on it, llama asks for
  confirmation before wiping them. Reach for `--stage X --force` first.
- Replays are faithful: the run's `criteria.json` carries the `count`,
  `script`, and `voice` settings it was created with (`find
  --limit/--no-script/--voice` and `profile run` stamp them), so `llama
  run` processes the same number of shows with the same script/voice
  settings. `--script`/`--no-script` and `--voice`/`--no-voice` explicitly
  override the persisted values.
- `--voice` only re-voices shows this invocation actually reprocesses. On an
  already-packaged show the package stage is skipped (its output already
  exists), so plain `llama run <run> --voice` is a no-op for it — llama
  prints a note pointing at `llama run <run> --stage package --force
  --voice` (forces just the package stage, for every show this run
  processes) or `llama redo <show> --from package --voice` (one show,
  standalone).
- Defaults to `--auto` (no prompts), unlike `find`.

### `llama review <run> [--script/--no-script] [--voice/--no-voice]`
Gate 1 only: prints the shortlist, asks which ranks to approve, and writes
the answer into `shortlist.json`. Ranks you don't name are left undecided
(once anything is approved, only approved entries are processed). It then
offers to process the approved shows immediately; decline and it prints the
`llama run` command to do it later. Empty input changes nothing. It has no
connection to needs-review (gate 2). `--script`/`--no-script` and
`--voice`/`--no-voice` override the run's persisted settings if you process
immediately.

### `llama show [<show>] [--tracks] [--exclude FILE|N] [--include FILE|N] [--vague] [--full] [--clear] [--apply] [--set-venue V] [--set-city C] [--set-date D] [--title N="..."] [--clear-title N] [--set-breaks "N,N"] [--clear-set-breaks] [--held/--packaged/--voiced/--unvoiced/--broadcast-ready/--state/--artist/--run]`
Gate 2's home command. Two forms:

- **Single-show form** (`llama show <show>`): prints artist/date/venue,
  chosen recording, derived state, a table of stage artifacts (present +
  age, or missing), the current `overrides:` line (only shown when
  non-default — narration and exclude list), the needs-review flags, and a
  `broadcast-ready: yes`/`no` line — when `no`, the reasons follow indented
  (e.g. `held for review`, `no DJ script`, `no DJ audio (unvoiced)`, `no
  broadcast.m3u`, `N of M audio files missing`, or just `not packaged` if
  there's no package at all). On a held show with no resolution flags
  given, and on a TTY, it drops straight into the same interactive
  walkthrough as the set form (below) for just that one show — pass a
  resolution flag to skip the prompt and act directly.
  - `--tracks` appends the numbered track table (index, set, title, title
    source, duration, filename) — the number to give
    `--exclude`/`--include`/`--title`/`--set-breaks`. `--tracks` is an explicit
    view request, so it prints and exits even for a held show on a terminal
    (it is *not* pre-empted by the interactive walkthrough; plain
    `llama show <show>` with no flag is what drops a held show into the
    walkthrough).
  - `--exclude FILE-or-N` (repeatable, comma-lists ok) adds a source
    filename to `overrides.exclude`; `--include FILE-or-N` (repeatable)
    removes one. Either also accepts **track numbers** (from `--tracks`)
    instead of filenames — numbers resolve against `show.json`'s track
    list, so they need `show.json` to already exist.
  - `--vague` sets `overrides.narration = "vague"` **and clears the hold**;
    `--full` resets narration to `"full"` (does not touch the hold).
  - `--clear` overrules the hold: clears `needs_review` and the flags,
    leaving `overrides.json` untouched.
  - `--set-venue`/`--set-city`/`--set-date` force
    `overrides.venue`/`overrides.city`/`overrides.date` (`--set-date`
    expects `YYYY-MM-DD`). `--title N="Song Title"` (repeatable) forces
    track N's title into `overrides.titles`; `--clear-title N` drops one.
    `--set-breaks "9,17"` sets `overrides.set_breaks` to those track
    numbers — the tracks a break falls *after* — replacing the computed
    structure alignment (the deterministic/LLM alignment ladder is skipped,
    so the `low-confidence structure alignment` flag can't fire); it's
    numbered-sets-only (labels come out `"1"`, `"2"`, ... — there's no way to
    mark an encore through this flag). Note: on a jerrybase-covered
    (Garcia-universe) show the jerrybase *cross-checks* still run against your
    breaks — the closer tripwire and the set-count guard — so manual breaks
    that contradict jerrybase's set closers or set count can still raise a
    flag rather than self-clearing; for non-jerrybase shows the override
    stands unchallenged. `--clear-set-breaks` removes the override.
  - By default any of the above just prints the follow-up
    (`next: llama redo <show> --from <stage>`, stage chosen by precedence —
    see [Clearing gate 2](#the-two-human-gates-dont-confuse-them) above —
    an exclude or metadata edit prints `--from gather`); `--apply` runs
    that redo immediately instead. A gather re-run recomputes
    `needs_review`/`review_flags` from scratch, so a hold **self-clears**
    whenever the correction removes the flag that caused it — no separate
    "clear" step needed for `--exclude`/metadata fixes.
- **Set form** (`llama show` with no name, or with any selector): walks
  every matching show. With no selector it defaults to `--held`. Selectors:
  `--held`, `--packaged`, `--voiced`, `--unvoiced`, `--broadcast-ready`,
  `--state NAME`, `--artist SUBSTR`, `--run NAME`. On a TTY, each held show
  in the walk gets an interactive prompt — `[e]xclude tracks / [v]ague /
  [c]lear / [s]kip / [q]uit` — `e` lists tracks and asks which numbers to
  exclude, then applies and redoes from `gather` right there; `v` and `c`
  clear the hold and redo from `synthesize`/`package` respectively; `s`
  leaves it and moves to the next show; `q` stops the walk. Non-held shows
  in the walk (e.g. from `--voiced`) are just printed, never prompted. Off a
  TTY (scripts, CI), the walk only prints each entry — no prompts, no edits.

### `llama redo <show>|<selectors> --from STAGE [--with-research] [--script/--no-script] [--voice/--no-voice] [--yes]`
Re-run show(s)' pipeline from a stage onward. `--from` is required; stages:
`select | gather | research | vet | synthesize | package`. For each show it
deletes that stage's artifacts **and everything downstream**, then re-runs
the tail using the show's `provenance.json` (candidate, winnow dossier,
script/voice settings) — the originating run directory is not needed.

- **Single-show form:** `llama redo <show> --from STAGE ...` — standalone,
  no run replay, no other show touched.
- **Batch form:** give selectors instead of a name —
  `--held`/`--packaged`/`--voiced`/`--unvoiced`/`--broadcast-ready`/
  `--state NAME`/`--artist SUBSTR`/`--run NAME` (same selectors as `llama
  show`'s set form). It prints the plan (every matching show) and asks
  `Proceed? [y/N]`; `--yes` skips the prompt for scripting. **Held shows are
  excluded from the batch unless `--held` is explicitly given** — a batch
  redo never processes a hold by accident. Each show's failure is isolated:
  a failing show prints `FAILED <slug>: <error>` and the rest of the batch
  continues. Giving a show name together with any selector is an error
  ("give a show OR selectors, not both").
- **`research.md` is kept by default** on `--from select`/`--from gather`:
  it's the expensive high-tier call and depends on performance identity,
  not recording choice; vet's grounding checks are the safety net if a
  structural fix leaves it slightly stale. `--with-research` drops it too;
  `--from research` redoes it by definition.
- The script setting recorded at process time is replayed;
  `--script`/`--no-script` overrides it (applied to every show in a batch).
- **`--from package --voice` is the standard way to (re-)voice show(s)**:
  `--voice` re-voices using the recorded (or given) voice, `--no-voice`
  strips voice from the package. Unchanged segments aren't re-synthesized
  (cached by text+voice+model) unless the recorded voice actually changed;
  there is no separate `--force` needed here since `redo` always rebuilds
  the stage it starts from. `llama redo --unvoiced --from package --voice`
  is the standard "voice everything that's silent" batch.
- A show without `provenance.json` (hand-built dir) errors — reprocess it
  via its run once; in a batch this fails just that show.

### `llama deliver <show>|<selectors> [--dest DIR] [--force] [--yes]`
Copies a show's `package/` into the station's watched folder
(`delivery_path` from config, or `--dest`) and records a `delivered` ledger
entry (run attribution from `provenance.json`). Refuses if the show is
marked needs-review; `--force` overrides.

- **Single-show form:** `llama deliver <show> ...`.
- **Batch form:** selectors instead of a name —
  `--held`/`--packaged`/`--voiced`/`--unvoiced`/`--broadcast-ready`/
  `--state NAME`/`--artist SUBSTR`/`--run NAME`. `llama deliver --packaged`
  is the standard ship-everything-ready command; `--broadcast-ready`
  narrows that to shows that are also scripted, voiced, and have a
  `broadcast.m3u` — the actually-airable subset. Same plan/`Proceed? [y/N]`/
  `--yes`, same held-excluded-unless-`--held` rule, same per-show
  `FAILED <slug>: ...` isolation, and the same "show OR selectors, not
  both" error as `redo`.
- `llama status --packaged` (or `llama deliver --packaged` itself, before
  confirming) lists what's ready to deliver.

### `llama config init [--stdout] [--config PATH]`
Seed `~/.llama/config.toml` (or `--config PATH`) with the baked-in
defaults as a fully-commented TOML file. Refuses to overwrite an existing
file; `--stdout` prints the template instead. Exists because config
values **replace** defaults rather than merging: any
`[selection.tapers.*]` or `[[selection.lineage_eras]]` you add replaces
the built-in GD tuning unless the defaults are restated — which the
seeded file does for you.

### `llama artists ["query"] [--limit N] [--all] [--refresh]`
Search the LMA artist index with a natural-language query, or with no query
list the deepest catalogs. `--all` bypasses the junk-filter floors.

This is the **test-drive** for a profile/find query: it calls the same LLM
matcher on the same request text with the same budget (20; `[artists]
max_matched` in config governs the pipeline side), so its list previews what
a run would search. The matcher is still an LLM — two calls can rank
differently — so when you've settled on a roster, pin it (below) and runs
stop consulting the matcher at all.

### `llama profile add <name> "query" [--count N] [--human-gate] [--no-script] [--presenter ID] [--title "..."] [--artists "..."]`
Interprets the query once and saves it as a standing profile.
`--human-gate` makes `profile run --auto` stop at gate 1 instead of
self-approving. `--presenter ID` gives this show a host
(`presenters/<id>.toml`; a typo'd id fails loudly right away), saved on the
profile; it voices every run of this profile even when `[tts] enabled` is
false globally, so different profiles can have different hosts and voices
(voice implies script). `--title "..."` names the show on-air (the host
knows it and drops it occasionally) — see
[Presenters](#presenters-giving-a-show-a-host) above. `--artists
"Galactic, Lettuce, ..."` pins the roster: names resolve against the
artist index at add time (typos and ambiguity fail immediately), and every
run of the profile searches exactly those artists — deterministic, no LLM
matching, no prune prompt. Edit the `artists` list under `[criteria]` in
the profile TOML to change it later.

### `llama profile run <name> [--auto]`
Runs the profile as a new dated run, skipping performances already in the
ledger. With `--human-gate` and `--auto`, stops at
`Shortlist awaits review: llama review <run>`; approve, then
`llama run <run>`.

### `llama presenter add <id> --name NAME --sex SEX (--voice ID | --voice-clone WAV) (--character "..." | --character-file PATH) [--bed WAV] [--force]`
Creates `presenters/<id>.toml` — the same file format described in
[Presenters](#presenters-giving-a-show-a-host) — without hand-editing TOML;
editing the file directly still works, `presenter add` is just the other
way in. Exactly one of `--voice`/`--voice-clone` and exactly one of
`--character`/`--character-file` are required; `--bed` sets this
presenter's own instrumental bed WAV (overrides `[tts] bed`, same station
`bed_gain_db`). Refuses to overwrite an existing id unless `--force`.

### `llama presenter list`
One line per `presenters/*.toml`: id, name, sex, and voice
(`clone:/path/to/ref.wav` for a voice-clone presenter). A presenter file
that fails to load is listed as `<id> (invalid: <error>)` instead of
raising.

### `llama presenter show <id>`
Prints one presenter's fields (name, sex, resolved voice, bed if set) and
its full character text.

### `llama profile artists <name> [--set "A, B, C"]`
View or re-pin a profile's pinned artist roster — the same `artists` list
under `[criteria]` in the profile TOML that `profile add --artists` writes.
With no `--set`, prints the current roster, or "no pinned roster (uses the
LLM matcher)" if unpinned. `--set "Galactic, Lettuce, Soulive"` resolves
each name against the local artist index (typos or ambiguity fail loudly,
same as `profile add --artists`) and re-pins it; `--set ""` clears the pin,
reverting future runs of the profile to the LLM artist matcher.

### `llama profile list` / `llama ledger list` / `llama ledger add` / `llama ledger remove`
Housekeeping. The ledger is the dedup memory: `selected` and `delivered`
entries suppress a performance in future winnows; `rejected` entries do too.
`ledger remove <performance-id>` un-suppresses one.

## Recipes

**What's the state of everything? / What came in overnight?**
`llama status` — held shows first with their flags, then packaged
(ready to deliver), then in-flight. `llama status --packaged` is the
ship-it worklist; `llama deliver <show>` each one (or `llama deliver
--packaged` to ship the whole worklist at once).

**What's actually ready to go on air right now?**
`--packaged` only means `package/manifest.json` exists — it doesn't check
that the audio files are still there, or that the show is scripted/voiced/
has a `broadcast.m3u`. `llama status --broadcast-ready` (or `llama show
<show>` for the reasons on one show) answers the stricter question;
`llama deliver --broadcast-ready` ships only that airable subset. No
inverse flag exists — a `no` shows its reasons on `llama show <show>`.

**Clear my overnight holds.**
`llama show --held` — walks every held show one at a time with the
interactive prompt (`[e]xclude tracks / [v]ague / [c]lear / [s]kip /
[q]uit`), resolving and re-processing each one on the spot as you answer.
`s` to leave one for later, `q` to stop the walk early.

**A run printed `needs-review, skipped` for a show I want.**
`llama show <show>` to read the flags. If a flag is a false alarm,
`llama show <show> --clear` and then `llama redo <show> --from package`.
If it's real (e.g. unresolved titles), fix the cause and
`llama redo <show> --from <stage>` — see the three resolutions in
[Clearing gate 2](#the-two-human-gates-dont-confuse-them) above.

**This show has junk announcement tracks.**
`llama show <show> --tracks` to see the numbered track list, then `llama
show <show> --exclude 9,10 --apply` (track numbers or filenames both work,
comma-lists ok, `--exclude` repeatable too) — adds them to
`overrides.exclude` and re-gathers immediately; gather drops them with
reason `operator-excluded` and warns if an entry doesn't match any source
file. A clean re-gather with the junk gone self-clears the hold.

**Wrong venue, city, date, a track title, or where a set break falls.**
`llama show <show> --set-venue "Winterland" --set-city "San Francisco, CA"
--set-date 1973-06-10 --title 4="Dark Star" --set-breaks "9,17" --apply` —
give only the flags you need; each forces the matching `overrides.json`
field and re-gathers. `--clear-title N` drops one forced title,
`--clear-set-breaks` drops the forced break list. `--set-breaks` takes the
track numbers a break falls *after*, numbered-sets-only (no way to name an
encore this way). Same self-clearing rule as excludes: a clean re-gather
drops the hold on its own.

**This show's setlist is unknowable.**
`llama show <show> --vague --apply` — sets `overrides.narration = "vague"`,
clears the hold, and re-synthesizes immediately; the script names no songs
and asserts no set structure, but is otherwise normal.

**I approved via `llama review` — now what?**
Say yes when it offers to process, or `llama run <run>` later.

**A stage failed with an LLM error.**
The raw output is in `shows/<slug>/llm-failure.txt`. Just re-run
`llama run <run>` — completed stages are skipped, the failed one retries.

**I want a different recording of the same show.**
`llama redo <show> --from select` — the drop cascades, so gather through
package rebuild from the newly picked recording. `research.md` is kept
(it's about the performance, not the recording); add `--with-research` if
you want it redone too.

**Re-research a show.**
`llama redo <show> --from research` — this also deletes `vetting.json`,
so the new research gets re-vetted.

**Voice every packaged-but-silent show.**
`llama redo --unvoiced --from package --voice` — batch-selects every
packaged show with no `dj-audio/` yet, prints the plan, and (after
confirming, or with `--yes`) re-packages each with speech. Each show uses
its recorded voice (house or presenter); a failure on one show doesn't
stop the rest.

**I want to add (or change) the spoken DJ voice on an already-packaged show.**
`llama redo <show> --from package --voice`. To switch to a *different*
voice, set `[tts] voice` (house shows) first. For a hosted show it depends
on what the presenter uses: edit `voice_clone` (or the clip it points to)
and the new clip takes effect, since the clone reference is re-read live;
editing a preset `voice` does **not** take effect this way, since `redo`
replays the voice stamped on the show at process time — re-run the show
fresh (`llama profile run`) to pick up a new preset voice. `--voice` itself
just turns voicing on, it replays the show's already-recorded voice
otherwise. Unchanged script segments aren't re-synthesized, so this is
cheap even against the paid API. `llama redo <show> --from package
--no-voice` strips voice audio back out.

**I edited a presenter's character — how do I hear the new persona?**
`llama redo <show> --from synthesize` re-scripts with the new persona
(deletes and rebuilds `dj-notes.*` and everything downstream, including
`dj-audio/` if the show is voiced). Swapping a presenter's `voice_clone`
with the character unchanged doesn't need a re-script either — `redo
<show> --from package --voice` is enough to re-render audio in the new
voice, since the clone reference is re-read live. Swapping a preset `voice`
needs a fresh `profile run` instead, same as above.

**I want a new host without hand-editing a TOML file.**
`llama presenter add casey --name Casey --sex male --voice american-dj
--character "Warm late-night FM veteran, dry humor, deep tape-collector
knowledge."` writes `presenters/casey.toml`; `llama presenter list` /
`llama presenter show casey` to check it. Then name it on a profile
(`llama profile add ... --presenter casey`, or edit an existing profile's
`presenter = "casey"`). Editing the TOML by hand afterward still works —
`presenter add` just gets you started without it; either way, `llama redo
<show> --from synthesize` re-scripts with any character change.

**Re-pin a profile's artist roster.**
`llama profile artists funky --set "Galactic, Lettuce, Soulive"` resolves
and re-pins the roster (typos/ambiguity fail loudly, same as `profile add
--artists`); `llama profile artists funky` alone shows the current roster;
`--set ""` clears it back to the LLM matcher.

**The same show keeps coming back in every profile run.**
It's not in the ledger. Deliver it, or `llama ledger add <performance-id>
--artist A --date D --status rejected` to suppress it.

**A search or winnow decision looks wrong (run-level, not one show).**
Stage forcing at the run level still exists:
`llama run <run> --stage winnow --force` rebuilds the shortlist
(confirming first if approvals would be lost); `--stage search --force`
re-searches and drops the shortlist with it.

## Troubleshooting: message → meaning → action

| You see | It means | Do |
|---|---|---|
| `Shortlist awaits review: llama review <run>` | Gate 1 is waiting (human-gate profile) | `llama review <run>` (it offers to process after) |
| `approved: [1]` (from review) | Picks recorded | Say yes at the process prompt, or `llama run <run>` later |
| `needs-review, skipped: <show>` | Gate 2: a flag was set during processing | `llama show <show>`; fix (`llama redo --from <stage>`) or `--clear`, then `llama redo <show> --from package` |
| `skipping <show>: needs review (…)` (log line) | Same as above, with the flags inline | Same |
| `holding <show>: flagged during packaging (…)` | Package built but audio verification flagged it | Inspect; `llama deliver --force` if acceptable |
| `refusing to deliver: … use --force` | Delivering a needs-review show | Inspect, then `--force` if intended |
| `FAILED <show>: …` | LLM/network failure mid-show | `llama run <run>` retries just the missing pieces; see `llm-failure.txt` |
| `FAILED <show>: …` (voice active) | TTS backend failed (bad key, rate limit, missing key — Voxtral needs `MISTRAL_API_KEY`, ElevenLabs needs `ELEVENLABS_API_KEY`) — show gets no package, batch continues | `llama redo <show> --from package` once the API issue clears; the segment cache means only the unfinished clips re-render |
| `note: already-packaged shows won't be re-voiced without --force …` | `llama run <run> --voice` on a run whose shows are already packaged is a no-op for them | `llama run <run> --stage package --force --voice`, or `llama redo <show> --from package --voice` for one show |
| `'x' is ambiguous` + a list | Substring matched several shows/runs | Use a longer substring or a full name from the list |
| `no show matches 'x'` / `no run matches 'x'` | Resolver found nothing | `llama status` / `llama runs` to see what exists |
| `no provenance.json in … - reprocess it via its run` | `redo` on a hand-built show with no provenance | Reprocess once via its run to write `provenance.json` |
| `No shows survived winnowing.` | Nothing passed dedup + mechanical floors + scoring | Broaden the query, lower floors, or check the ledger |
| `winnow: N of M scored shows fell below the quality floor` | LLM scores under `min_quality_score` (default 6.0) were dropped | Expected while a pool is healthy; if it recurs and runs come back short, the well is drying — broaden criteria, or lower `--min-score` if you'd rather ship marginal shows |
| `no matching artists found on the LMA` | Artist-less query matched nothing in the index | Name an artist or broaden the style terms |
| `winnow: sampling N of M survivors for review fetch` | More candidates than the review-fetch budget; the best-evidenced are scored, bounded by `artist_cap`/`year_cap` | Fine for most runs; raise `[winnow] max_metadata_fetch` in config to score more |
