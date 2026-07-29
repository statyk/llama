# How llama works: the operator's guide

This is the user-facing map of the whole system: what the pipeline does, what
lands on disk where, the two different human gates and how they differ, every
command, every review flag, and a troubleshooting table from "message you saw"
to "what to do next." The design rationale lives in
`docs/superpowers/specs/`; this document is about *operating* it.

## The big picture

```
llama get "query"          llama get --profile <name>
        │                           │
        ▼                           ▼
   interpret ──► search ──► winnow ──► [gate 1: llama run approve]
                                              │
                              per approved show│
                                              ▼
             select-recording ──► gather ──► research ──► vet
                                              │
                            [gate 2: needs-review can halt here]
                                              │
                                     brief (always on) ──► synthesize (default; --no-script skips)
                                              │
                                              ▼
                                          package ──► llama deliver
```

`llama pipeline` prints this same flow (plus the derived states and a redo
cheat-sheet) as a static teaching command — reach for it any time you want a
refresher without leaving the terminal.

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

There are two modes, both under the one `get` verb:

- **One-off:** `llama get "GD shows 73-74 with a china>rider"` — interprets
  the query, runs the whole pipeline.
- **Standing profiles:** `llama profile add` then `llama get --profile
  <name>` — a saved query re-run for recurring segments, deduplicated
  against the library and the history ledger so the same performance is
  never offered (or shipped) twice.

## The on-disk workspace

Everything lives under `~/.llama/` (configurable as `root` in
`~/.llama/config.toml`):

```
~/.llama/
├── config.toml                  # optional; see README
├── ledger.jsonl                 # broadcast history (dedup + audit)
├── cache/                       # archive.org responses + artist index
├── profiles/<name>.toml         # standing profiles
├── runs/<session-id>/            # session-level artifacts only
│   ├── criteria.json            # interpreted query (interpret stage)
│   ├── candidates.json          # every performance found (search stage)
│   ├── shortlist.json           # ranked + scored top shows (winnow stage)
│   ├── session.json             # lifecycle marker: awaiting-approval | complete
│   │                            # (missing/other = incomplete) — read by
│   │                            # `llama run list`/`status`'s attention-list
│   └── artists.json             # artist-less queries only: matched artists
└── shows/<slug>/                # canonical shows library: one dir per
    │                            # performance, slug = slugified performance id
    │                            # (gratefuldead-1973-06-10), shared across runs
    ├── provenance.json          # which run processed it, winnow dossier,
    │                            # script setting — what `redo` replays from
    ├── overrides.json           # hand-authored or `llama show`-edited, durable:
    │                            # excluded tracks, narration mode, and metadata
    │                            # corrections (venue/city/date/titles/set_breaks);
    │                            # read by gather/brief/synthesize, survives every redo
    ├── selection.json           # which recording won and why
    ├── show.json                # tracks, sets, flags — THE show state file
    ├── reviews.json             # raw listener reviews
    ├── research.md              # deep-research output
    ├── vetting.json             # grounding-check results
    ├── briefing.md/.json        # neutral vetted briefing (always on) — brief stage
    ├── dj-notes.md/.json        # verbatim DJ script (default; absent with --no-script)
    ├── llm-failure.txt          # raw LLM output if a task failed validation
    └── package/                 # the deliverable
        ├── manifest.json        # schema v3: tracks, sets, durations, context, briefing
        ├── playlist.m3u         # music-only play order
        ├── broadcast.m3u        # voiced shows only: DJ audio interleaved
        ├── audio/               # verified, tagged tracks
        ├── research.md
        ├── reviews.md
        ├── briefing.md/.json    # always present (manifest v3)
        ├── dj-notes.md          # absent only with --no-script
        └── dj-audio/            # opt-in TTS clips; present only when voiced
```

Session ids default to `YYYY-MM-DD-<slugified-query>` for a one-off `get`
and `YYYY-MM-DD-<profile-name>` for `get --profile`, with `-2`, `-3`, …
appended on same-day collisions (`--name` overrides it explicitly). Show
slugs come from the performance identity (artist + date), so they are
stable across runs by construction.

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
  set_breaks fields; `brief` and `synthesize` both read `narration` and
  stamp it onto their own output (the LLM's own opinion of it is never
  trusted); it survives every `redo`, including ones that drop everything
  else downstream of a stage.

## Names and states: the catalog

Every command that takes a show or session accepts a **name, a unique
substring, or a path**: exact match wins, otherwise a substring that
matches exactly one candidate resolves to it, otherwise the command fails
loudly and lists the matches. `llama show 1973-06-10` is the typical form;
`llama run resume countryish` resolves `2026-07-16-countryish`.

A show's **state** is never stored — it is derived from which artifacts
exist plus the ledger, so it cannot go stale:

| State | Derived from | Meaning |
|---|---|---|
| `held` | `show.json` has `needs_review: true` | Gate 2 hold; sorts first in `llama status`, flags shown inline |
| `delivered` | ledger has a `delivered` entry for the performance | Shipped to the station |
| `packaged` | `package/manifest.json` exists | Ready to deliver |
| `scripted` / `briefed` / `vetted` / `researched` / `gathered` / `selected` | deepest stage artifact present | In-flight (or abandoned mid-pipeline) |

`llama status` is the triage table over these states; `llama status
--by-run` summarizes per-session show counts. Both are in the command
reference below.

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
| brief | yes | `briefing.*` | Neutral vetted briefing for scriptwriters, factually guarded (always on, no flag/config gate) |
| synthesize | yes | `dj-notes.*` | On by default (`--no-script` skips): verbatim DJ script, factually guarded against the manifest — spoken in the profile's presenter's persona when one is set, else the neutral house narrator. Transitional: this is llama's in-house script/voice path; a downstream persona tool is planned to take over scriptwriting from the briefing |
| package | no | `package/` | Downloads audio (md5-verified), tags it, checks durations, writes manifest v3 + m3u + digests (hard-fails if `briefing.*` is missing); if voice is active, also synthesizes `dj-audio/` clips (Voxtral by default, or ElevenLabs), adds the manifest's `dj_audio` block, and writes a `broadcast.m3u` with the DJ audio interleaved into play order |

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
across runs, and the history ledger's job is dedup, not rotation. Want no
artist repeated across your next N shows? Generate the N in one run.
Explicit `llama run approve` picks are never capped; your picks are your
picks.

## The two human gates (don't confuse them)

This is the single most confusing part of the system, so here it is plainly:

|  | Gate 1: shortlist approval | Gate 2: needs-review |
|---|---|---|
| **Question it asks** | "Which of these shows should we spend money processing?" | "Is this processed show clean enough to air?" |
| **Granularity** | The session's shortlist | One show |
| **Lives in** | `runs/<session>/shortlist.json` (`approved: true/false/null`) | `shows/<slug>/show.json` (`needs_review` + `review_flags`) |
| **Set by** | You (interactive prompt, or `llama run approve`) | The pipeline (gather/vet/synthesize/package flags) |
| **Cleared by** | `llama run approve <session>` | `llama fix`/`llama triage` (after you inspect) |
| **Surfaced by** | `llama run list` (the attention-list), also fronting `llama status` | `llama status --held` |
| **What it blocks** | Processing starting at all | Packaging (or delivery, if flagged during packaging) |

**Gate 1** appears interactively during `llama get` ("Process which
ranks?"), or — with `--plan`, or a `--human-gate` profile run with `--auto`
— as a parked session showing up in `llama run list`/`llama status`'s
attention-list with a `llama run approve <session-id>` hint. `llama run
approve` records your picks and then offers to process them on the spot;
decline and it prints the resume command (`llama run resume <session-id>`)
instead.

**Gate 2** fires per show, any time a stage records a review flag in
`show.json`. The pipeline checks it at four points (after vet, after brief,
after synthesize, after package) and prints `needs-review, skipped: <show>`
during first-time processing (`llama get`), or `still held: <show>` when a
`redo`/`voice`/`fix`/`triage` re-run comes back held. The flags that can be
set, and by which stage:

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
| `briefing mentions unknown song` / `references nonexistent set` / claims the wrong set count / vague-narration violation (names songs or asserts set structure under `narration: vague`) / has no per-set talking points under `full` | brief | The briefing contradicts the setlist, the real set structure, or the vague-narration contract; retried once with feedback before holding |
| `dj notes mention unknown song / nonexistent set / missing set intros / break count mismatch` | synthesize | The DJ script contradicts the manifest |
| `duration mismatch on <file>` | package | Downloaded audio's real length disagrees with metadata |

**Clearing gate 2.** There is deliberately no bypass anywhere else: a
flagged show stays held until `llama fix` or `llama triage` resolves it —
`llama deliver` has no hold override at all (§ below). Looking means
`llama show <show>` — strictly read-only: it prints the flags, state, a
table of which stage artifacts exist, the archive URL, and (if non-default)
the current `overrides.json`, plus a hint pointing at `llama fix <show>
--overrule` if it looks like a false alarm. From there you're choosing one
of three resolutions, either flag-by-flag with `llama fix <show> <flags>`
(auto-runs the correct redo) or interactively with `llama triage` (walks
every held show with an `[e]xclude / [m]etadata / [v]ague / [o]verrule /
[s]kip / [q]uit` prompt):

| Resolution | When | Do (`fix`) | Do (`triage`) | Clears the hold? |
|---|---|---|---|---|
| **Correct** | The flag is real and fixable — e.g. junk tracks slipped past the filter, a setlist source is missing, or the venue/date/a title/a set break is wrong | `llama fix <show> --exclude 9,10` (track numbers or filenames; `--unexclude` to undo one) or `--set-venue`/`--set-city`/`--set-date`/`--set-title N="..."`/`--set-breaks "9,17"` | `[e]xclude` or `[m]etadata` | No — a clean re-gather self-clears by producing structure with no flags |
| **Accept as vague** | The setlist genuinely can't be resolved, but the show is otherwise fine to air without naming songs | `llama fix <show> --narration vague` | `[v]ague` | Yes, immediately (narration mode also survives future redos) |
| **Overrule** | The flag is a false alarm | `llama fix <show> --overrule` | `[o]verrule` | Yes, immediately |

`llama show <show> --tracks` lists the numbered track table first if you
need the numbers for `--exclude`/`--set-breaks`/`--set-title`.

Each resolution edits `overrides.json` (except overrule, which only clears
`show.json`'s flags) and, on `fix`, runs the correct redo automatically —
`--no-run` stages the edit and prints `next: llama redo <show> --from
<stage>` instead, for batching several edits before one redo. Stage
precedence when multiple flags are combined on one `fix` call: an exclude
or metadata edit redoes from `gather`, a narration edit (with neither)
redoes from `brief` (regenerating the briefing, script, and package too),
and `--overrule` alone redoes from `package`.

## Voice (opt-in text-to-speech)

The DJ script can additionally be **spoken** during `package` — off by
default. The default backend is hosted Mistral Voxtral
(`voxtral-mini-tts-2603`); set `[tts] backend = "elevenlabs"` to speak via
ElevenLabs instead. Turn voice on globally (`[tts] enabled = true` +
`[tts] voice` in config), per invocation (`--voice` on `get`/`redo`/`voice`),
or per profile by naming a **presenter** (below), which
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

**Re-voicing an already-packaged show:** `llama voice <show>` (sugar for
`llama redo <show> --from package --voice`) re-voices with the show's
recorded voice (or, if it had none yet, the current house `[tts] voice`, or
the profile's presenter's voice); `llama voice --off <show>` strips voice
back out. `--voice`/`--no-voice` on `get`/`redo` (and `voice`'s own `--off`)
only toggle voice on or off — there's no per-invocation voice-id override;
to actually switch to a different voice, change `[tts] voice` (house shows)
first. For a hosted show it depends on what the presenter uses: editing
`voice_clone` (or the clip it points to) takes effect on the next `voice
<show>`/`redo <show> --from package --voice`, since the clone reference is
re-read live — but editing a preset `voice` does **not**, because a redo
replays the voice *stamped* on the show at process time; only a fresh
`llama get --profile <name>` picks up a new preset voice. Unchanged
segments aren't re-synthesized — the per-segment cache (keyed on
text+voice+model+chunk[+bed]) means a redo only re-renders what actually
changed. Voxtral is non-deterministic, though — the same script gives a
different take each call — so when one clip comes out janky, `llama voice
<show> --fresh <clip>` deletes just that clip (a DJ-audio filename stem,
e.g. `set1-intro` or `99-outro`; repeatable) and the package re-render
re-rolls only it, leaving the cached good takes untouched. It's single-show,
voice-on; an unknown stem lists the show's actual clips. A plain `llama run resume <session>` on a session whose shows are
already packaged does **not** re-voice them — the package stage is skipped
because its output already exists — it prints `note: already-packaged shows
won't be re-voiced by a plain replay; use 'llama redo <show> --from package
--voice' to re-voice one show` (or `llama voice <show>` as the equivalent
sugar).

**Failure holds the show, not the batch.** If the TTS backend fails (bad
key, rate limit, missing key while voice is active), that show produces no
package (no manifest) and isn't delivered; llama prints `FAILED <show>: …`
and moves on to the rest of the batch. Retry with
`llama redo <show> --from package` once the API issue is resolved — the
cache means a retry only re-renders what didn't finish.

## Command reference

In every command below, `<show>` and `<session>` mean "name, unique
substring, or path" — see [Names and states](#names-and-states-the-catalog).

### The shared selector vocabulary

`status`, `triage`, `redo`, `voice`, `deliver`, and `rm` all accept the same
filter flags, reconciled by one implementation (`llama.cli_select`):

```
--held                 selector: shows in state held
--packaged             selector: packaged, undelivered shows
--voiced / --unvoiced  selector: packaged shows with / without DJ audio
                       (pre-package shows match neither)
--broadcast-ready      selector: broadcast-ready shows (positive-only, no
                       inverse)
--state NAME           selector: one derived state (repeatable; validated
                       enum: held|selected|gathered|researched|vetted|
                       briefed|scripted|packaged|delivered)
--artist SUBSTR        selector: case-insensitive substring on artist
--run NAME             selector: shows processed by this session
```

All filters AND together; repeated `--state` values OR together. A
positional show name and any selector flag are mutually exclusive ("give a
show OR selectors, not both"). Neither given is an error naming an example
selector, except `status` (defaults to every show) and `triage` (defaults
to `--held`). A batch action (`triage`/`redo`/`voice`/`deliver`/`rm`) prints
a plan and asks `Proceed? [y/N]` (`--yes` skips); per-show failures print
`FAILED <slug>: …` and the sweep continues.

**The held opt-in rule:** for an *acting* command (`triage`, `redo`,
`voice`, `deliver`, `rm` — not the read-only `status`/`show`), a selector's
matches in state `held` are dropped unless the selector explicitly included
held (`--held` or `--state held`); when any are dropped the plan prints
`note: N held show(s) excluded (add --held to include them)`. `triage`'s
default selector *is* held, so no opt-in applies there. Naming a single
show positionally is itself explicit opt-in — `redo gd73 --from gather` on
a held show runs (that's how holds self-clear); `deliver gd73` on a held
show reaches the per-show gate and is refused there with the reason.

### `llama get "query" [--limit N] [--auto] [--plan] [--name NAME] [--script/--no-script] [--voice/--no-voice] [--artist-cap F] [--min-score F] [--year-cap F] [--full-rationale]`
### `llama get --profile NAME [--auto] [--plan] [--full-rationale]`
One verb replaces `find` + `profile run`; honest that it spends. Exactly
one of `"query"` / `--profile` is required.

- **Query mode** interprets the query, prunes artist-less matches
  interactively (discovery path), searches, winnows, prints the shortlist,
  and prompts which ranks to process (empty answer = top picks); `--auto`
  skips all prompts and takes the top-ranked shows. The verbatim DJ script
  is generated by default (one extra high-tier LLM call per show);
  `--no-script` skips it. `--voice` synthesizes spoken DJ audio (Voxtral by
  default, or ElevenLabs; default follows `[tts] enabled`; implies
  `--script`) — see [Voice](#voice-opt-in-text-to-speech) above. Winnow
  knobs: `--artist-cap`, `--year-cap`, `--min-score` (see the winnow
  discussion above). `--full-rationale` prints each shortlisted show's
  complete selection rationale instead of the first few lines (also
  available on `run approve`/`run resume`). Query-mode-only flags error on
  profile mode ("set these on the profile").
- **Profile mode** (`--profile NAME`) loads the profile and runs it as a new
  session, stamping its count/script/voice/presenter/title; only `--auto`,
  `--plan`, `--full-rationale` apply.
- **`--plan`** stops after the shortlist prints — winnow's LLM scoring and
  light research still spend (that's what produces the shortlist), but
  nothing is downloaded, researched further, or packaged. The session parks
  `awaiting-approval` and llama prints:

  ```
  shortlist ready — nothing processed.
  to approve & process:  llama run approve <session-id>
  to discard:            llama run rm <session-id>
  ```

  `--plan` composes with `--auto` (`--auto --plan` = "spend on winnow,
  never prompt, park it").
- `--name` gives the session an explicit id instead of the auto-unique
  `YYYY-MM-DD-<slug>` (mainly for tests/scripting).
- The winnow pool now also excludes every show already in the library, not
  just the ledger (§ [Dedup](#dedup-library--history) below).

### `llama artists ["query"] [--limit N] [--include-junk] [--min-recordings N] [--min-downloads N] [--refresh]`
Search the LMA artist index with a natural-language query, or with no query
list the deepest catalogs. `--include-junk` skips the junk-filter floors
entirely (`--min-recordings`/`--min-downloads` override them instead).

This is the **test-drive** for a `get`/profile query: it calls the same LLM
matcher on the same request text with the same budget (20; `[artists]
max_matched` in config governs the pipeline side), so its list previews what
a run would search. The matcher is still an LLM — two calls can rank
differently — so when you've settled on a roster, pin it (`profile
artists --set`) and runs stop consulting the matcher at all.

### `llama status [SELECTOR] [--all] [--by-run] [--json]`
Global triage view: the session **attention-list** first, then the show
table. Read-only — never prompts, never writes.

- **Attention-list:** whenever any session is awaiting approval or
  incomplete, prints before the show table:

  ```
  sessions needing attention:
    2026-07-27-sunday-dead-hour-2       awaiting approval   llama run approve sunday-dead-hour-2
    2026-07-27-china-rider              incomplete          llama run resume china-rider
  ```

  Complete sessions never appear. In `--json` this becomes the `sessions`
  key alongside `shows` (or `runs` with `--by-run`).
- **Selectors:** the shared vocabulary above (read-only class — no held
  opt-in needed; every show is shown). `--all` includes every delivered
  show instead of the recent-5 tail.
- **`--by-run`** replaces the deleted `runs` command: one row per session —
  id, per-state show counts, query. Exclusive with selectors/`--all`.
- Show rows: state, artist, date, session, held-for-review first, flags
  indented beneath; inline annotations for anything non-default
  (`[broadcast-ready, voiced, vague, 3x-excl]`).

### `llama show <show> [--tracks] [--json]`
Inspect one show. **Strictly read-only — never prompts, never edits.** Use
`llama fix` to edit overrides or resolve a hold, and `llama triage` for the
interactive walkthrough.

Prints artist/date/venue, the chosen recording **with its archive.org URL**,
a `considered:` block of every other recording weighed (identifier + score,
descending — omitted when there was only one candidate), derived state, a
table of stage artifacts (present + age, or missing), the current
`overrides:` line (only shown when non-default), the needs-review flags,
and a `broadcast-ready: yes`/`no` line — when `no`, the reasons follow
indented (e.g. `held for review`, `no DJ script`, `no DJ audio (unvoiced)`,
`no broadcast.m3u`, `N of M audio files missing`, or `not packaged`). On a
held show it also prints `to overrule after inspecting: llama fix <slug>
--overrule`. `--tracks` appends the numbered track table (index, set,
title, title source, duration, filename) — the numbers `fix`'s
`--exclude`/`--set-title`/`--set-breaks` take. `--json` emits the full
machine-readable record (`archive_url`, `considered`, `stages`, `overrides`,
`broadcast_reasons`, etc.). A show that hasn't reached `gather` yet
(state `selected`) still prints what exists instead of erroring.

### `llama pipeline`
Teaching command: prints the stage flow with both gates marked, the nine
derived `--state` values (plus the `voiced`/`broadcast-ready` annotations),
and a redo cheat-sheet (which `fix` flag redoes from which stage). Static
text, read-only — no config, no I/O, never prompts, never writes. Reach for
it as a refresher any time.

### `llama triage [<show>|SELECTOR]`
The interactive resolution walkthrough — always interactive, requires a
TTY (`triage is interactive; use status/show for scripted reads` off a
TTY). Default selector `--held`; a broader selector walks held shows for
resolution and just prints-and-skips non-held matches. Per held show,
prints the full inspection block (as `show <name>`, including the archive
URL) then prompts:

```
[e]xclude tracks / [m]etadata / [v]ague / [o]verrule / [s]kip / [q]uit
```

- **`[e]xclude`** — numbered track list, pick indices to add to
  `overrides.exclude`, redo from `gather`.
- **`[m]etadata`** — a mini-editor over `venue`, `city`, `date
  (YYYY-MM-DD)`, `title overrides (N=Title, comma-separated)`, `set breaks
  after tracks (e.g. 9,17)` — each shows the current effective value, empty
  input keeps it; any change writes the overrides and redoes from `gather`.
- **`[v]ague`** — sets `overrides.narration = "vague"`, clears the hold,
  redoes from `brief` (regenerating the briefing, script, and package too).
- **`[o]verrule`** — clears the hold, redoes from `package`.
- **`[s]kip`** / **`[q]uit`** — next show / stop the walk.

After each action it reports `packaged: <path>` or `still held: <slug>`
before advancing to the next show.

### `llama fix <show> <edit-flags...> [--no-run]`
The flag-driven editor for `overrides.json` and hold resolution — **runs
the correct redo automatically** by default (earliest-affected stage wins
when flags are combined: `gather` < `brief` < `package`); `--no-run`
stages the edit and prints `staged; next: llama redo <show> --from <stage>`
instead, for batching several edits before one redo. At least one flag is
required (bare `fix <show>` errors, pointing at `show`/`triage`). Works on
non-held shows too — overrides are general inputs, not hold-only.

| Flag | Effect | Redo stage |
|---|---|---|
| `--exclude FILE\|N` (repeatable, comma groups) | add to `overrides.exclude` (filename or track number) | gather |
| `--unexclude FILE\|N` | remove from `overrides.exclude` | gather |
| `--set-venue V` / `--set-city C` / `--set-date YYYY-MM-DD` | force the field | gather |
| `--set-title N="Song"` / `--clear-title N` | force/drop a track title | gather |
| `--set-breaks "9,17"` / `--clear-set-breaks` | force/drop set breaks (the track numbers a break falls *after*; numbered-sets-only) | gather |
| `--narration vague\|full` | set `overrides.narration`; `vague` also clears the hold | brief |
| `--overrule` | clear `needs_review`/`review_flags`: "I've reviewed it, ship it" | package |

Excludes/metadata do **not** pre-clear a hold (the re-gather decides,
self-clearing only if the derivation comes out clean); `--narration vague`
and `--overrule` clear immediately. On a jerrybase-covered (Garcia-universe)
show, `--set-breaks` still runs the jerrybase cross-checks against your
breaks (closer tripwire, set-count guard), so a manual break that
contradicts jerrybase can still raise a flag rather than self-clearing.
`--overrule` on a non-held show is a no-op + note. Single-show only — bulk
blind edits to per-show overrides are a foot-gun, so batch resolution is
`triage`, not `fix`.

### `llama redo <show> | --run SESSION | SELECTOR --from STAGE [--redo-research] [--script/--no-script] [--voice/--no-voice] [--yes]`
The single re-execution verb. `--from` is required. Three addressing forms
(exactly one):

1. **Single show:** `llama redo <show> --from STAGE` — drops that stage's
   artifacts and everything downstream, then re-runs the tail using
   `provenance.json` (candidate, winnow dossier, script/voice settings) —
   the originating session doesn't need to exist anymore. Stage ∈
   `select | gather | research | vet | brief | synthesize | package`. A
   show without `provenance.json` errors — reprocess it via its session
   once.
2. **Selector batch:** `llama redo SELECTOR --from STAGE` — shared
   vocabulary above, acting class (held opt-in), plan + confirm + per-show
   `FAILED <slug>: …` isolation. `llama redo --unvoiced --from package
   --voice` is the standard "voice everything that's silent" batch.
3. **Session scope (`--run`, the new home for the old whole-run force):**
   `llama redo --run <session> --from STAGE`.
   - `STAGE ∈ {search, winnow}` (valid **only** with `--run`): rebuilds the
     session's shortlist from that stage — deletes the stale downstream
     artifacts (`candidates.json`+`shortlist.json` for `search`,
     `shortlist.json` for `winnow`), then replays `get`'s processing tail
     with the session's own criteria. If the doomed shortlist carries
     approvals, confirms first ("this rebuilds the shortlist and discards
     the approvals recorded on it"). This is the old `run --stage X --force`
     for the whole run.
   - Any show-level stage: batch-redo the session's shows — identical to
     the selector form with `--run` as the only filter.

`--redo-research` (renamed from `--with-research`, which *sounded* additive
but deletes `research.md`) also drops research when redoing from
`select`/`gather` — kept by default otherwise (it's the expensive
performance-level call; vet's grounding check is the safety net if a
structural fix leaves it slightly stale). `--script`/`--no-script` and
`--voice`/`--no-voice` override the replayed setting (unset defers to the
provenance stamp). Result per show: `packaged: <path>` or `still held:
<slug>`.

### `llama voice <show> | SELECTOR [--off] [--yes]`
TTS as a first-class verb — pure sugar over `redo --from package
--voice`/`--no-voice`:

- `llama voice <show>` ≡ `redo <show> --from package --voice`
- `llama voice --off <show>` ≡ `redo <show> --from package --no-voice`
  (strips DJ audio + `broadcast.m3u` from the rebuilt package)
- `llama voice --unvoiced --yes` replaces the old four-flag incantation
  `redo --unvoiced --from package --voice --yes`.
- Selector form uses the shared vocabulary (acting class, held opt-in). No
  default selector — bare `voice` errors with `give a show or a selector
  (e.g. --unvoiced)`.
- Re-voicing replays the voice **stamped** at process time when one exists
  (a presenter's clone edits are live — the stamp *is* the clone path — but
  a preset change needs a fresh stamp: reprocess via `get --profile` to
  pick it up); with no stamp, the house `[tts]` voice applies. `--off`
  always wins over any stamp.

### `llama deliver <show> | SELECTOR [--dest DIR] [--allow-unvoiced] [--yes]`
Copies a show's `package/` into the station's watched folder
(`delivery_path` from config, or `--dest`) and records a `delivered`
history row.

**Requires broadcast-ready by default** (packaged, file-complete, not
held, scripted, voiced, has `broadcast.m3u`). `--allow-unvoiced` is the
**sole** override — it ships an otherwise-ready music-only show anyway (no
extra confirmation beyond the normal batch plan; the flag itself is the
consent). Held shows and shows with missing audio files are **never**
overridable — resolve via `fix`/`triage`, or re-package
(`redo --from package`), first. **There is no `--force`** — the old
`needs-review + --force` delivery bypass is gone entirely. Refusals print
the failing reasons and a pointer, e.g. `refusing to deliver <slug>: held
for review — resolve with llama triage`.

- **Single-show form:** `llama deliver <show> ...`.
- **Batch form:** the shared selector vocabulary. `llama deliver --packaged`
  is the ship-everything-ready sweep; `llama deliver --broadcast-ready`
  narrows that to the actually-airable subset. Same plan/`Proceed? [y/N]`/
  `--yes`, same held-opt-in rule, same per-show `FAILED <slug>: …`
  isolation.
- `llama status --packaged` (or `llama deliver --packaged` itself, before
  confirming) lists what's ready to deliver.

### `llama rm <show> | SELECTOR [--forget | --suppress] [--yes]`
Deletes `shows/<slug>/` — the one irreversible local operation, so it
confirms by default (`--yes` skips). Leaves history in an intentional,
*stated* state rather than a stale row:

| Mode | Ledger effect | Net effect |
|---|---|---|
| default (no flag) | untouched | held/pre-package show (no ledger row): **re-eligible**. Packaged/delivered show: **stays excluded** (history dedup) |
| `--forget` | purge all history rows for this performance | fully re-eligible, a clean slate |
| `--suppress` | additionally append a `rejected` row (`run="manual"`) | guaranteed out, reversibly (`llama unsuppress`) — the only way to keep a *held* show (which has no keep-out row) from returning |

Echoes what it did to history, e.g. `removed shows/gd1972-08-27 — no
history rows; this show can be re-offered` / `… — history kept (selected,
delivered): stays excluded from future gets` / `… — forgot 2 history rows:
re-eligible` / `… — suppressed: will not be offered again (undo: llama
unsuppress …)`. Selector form: shared vocabulary, acting class (`rm --held`
is the legitimate "purge my junk holds" sweep, and must be spelled
explicitly). Delivered copies already at the station are out of scope —
`rm` only touches the workspace.

### `llama suppress <show-or-performance-id>` / `llama unsuppress <show-or-performance-id>`
The standalone deliberate reject / undo. `suppress` appends a `rejected`
history row (repeats are harmless); the show, if on disk, is left
untouched. `unsuppress` removes this performance's `rejected` rows only
(0 removed is a clean no-op message). Both resolve an on-disk show like
other acting commands, or accept a raw performance id
(`collection/date[/eN]`) for a performance that isn't (or is no longer) on
disk — the only way to keep "never offer me this again" usable for shows
long gone. No confirmation prompts (reversible by construction).

### `llama config init [--stdout] [--config PATH]`
Seed `~/.llama/config.toml` (or `--config PATH`) with the baked-in
defaults as a fully-commented TOML file. Refuses to overwrite an existing
file; `--stdout` prints the template instead. Exists because config
values **replace** defaults rather than merging: any
`[selection.tapers.*]` or `[[selection.lineage_eras]]` you add replaces
the built-in GD tuning unless the defaults are restated — which the
seeded file does for you. (This is the one `--config` that means *target
file to write*, not *config to load* — the app-wide `llama --config PATH
<command>` spelling is unaffected.)

### `llama run list [--json]`
The session **attention-list**: sessions awaiting approval or incomplete,
newest first (complete sessions never show here — their dirs remain on
disk harmlessly). Columns: session id, state, age (from the
`session.json` marker, else dir mtime), criteria (`profile: <name>` or the
truncated query).

### `llama run approve <session> [--full-rationale]`
Gate 1: prints the session's persisted shortlist, prompts `Approve which
ranks?` (unnamed ranks stay undecided), then confirms `Process approved
shows now? [Y/n]`. Declining keeps `awaiting-approval` and prints `next:
llama run resume <session-id>`. The shortlist approval **persists**
(winnow is non-deterministic — a deferred approval must approve the exact
list shown).

### `llama run resume <session> [--auto/--interactive] [--full-rationale]`
Resume a crashed or incomplete session from its artifacts — stages skip
work already done. To force a stage re-run (run-wide or per-show), use
`llama redo --run` instead; there's no `--stage`/`--force` here anymore.
The persisted criteria fully determine script/voice/presenter — post-hoc
voice changes are `llama voice`'s job. Defaults to `--auto` (no prompts).

### `llama run rm <session> [--yes]`
Discard a session directory (`runs/<id>/`, after a y/N confirmation showing
the id and state). Shows it already processed are untouched — they live in
`shows/` and carry `provenance.json`; sessions have no ledger history of
their own.

### `llama profile add <name> "query" [--count N] [--human-gate] [--no-script] [--presenter ID] [--title "..."] [--artists "..."]`
Interprets the query once and saves it as a standing profile.
`--human-gate` makes `get --profile --auto` stop at gate 1 instead of
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

### `llama profile list`
One line per profile: name, count, presenter (or `-`), query (truncated).

### `llama profile show <name>`
Inspect one profile's fields — query, count, human_gate, script, presenter,
title, pinned roster, and the interpreted criteria highlights. Strictly
read-only — never prompts, never edits, no LLM call.

### `llama profile remove <name> [--yes]`
Delete `profiles/<name>.toml` with a y/N confirmation. Sessions and shows
already created are untouched.

### `llama profile artists <name> [--set "A, B, C"]`
View or re-pin a profile's pinned artist roster — the same `artists` list
under `[criteria]` in the profile TOML that `profile add --artists` writes.
With no `--set`, prints the current roster, or "no pinned roster (uses the
LLM matcher)" if unpinned. `--set "Galactic, Lettuce, Soulive"` resolves
each name against the local artist index (typos or ambiguity fail loudly,
same as `profile add --artists`) and re-pins it; `--set ""` clears the pin,
reverting future runs of the profile to the LLM artist matcher.

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

### `llama presenter remove <id> [--yes] [--force]`
Delete `presenters/<id>.toml` with a y/N confirmation. Refuses if any
profile still names this presenter (lists which); `--force` removes it
anyway (the next run of that profile then fails fast at load time, same as
today for a missing id).

### `llama history list [--log] [--json]`
Dispositions for shows no longer on disk — the library covers what's on
disk. Renamed from `ledger`; `add`/`remove` are gone (`suppress` covers
reject, `unsuppress`/`rm --forget` cover removal). Default: one row per
performance, its latest disposition:

```
2026-07-25  delivered  GratefulDead/1977-06-09      (2026-07-20-china-rider)
2026-07-26  rejected   DelMcCouryBand/2003-04-19    (manual)
```

`--log` prints the full append-only trail instead. `--json` emits the
corresponding rows.

## Dedup: library ∪ history

A performance is excluded from future `get`s if it's **in the library**
(any show currently on disk, in any state — held, mid-pipeline, packaged,
delivered) **or** it has a `played`/`delivered`/`rejected` row in the
history ledger. This closes a gap the old ledger-only check had: a held
show (no ledger row until it clears both gates) used to re-surface in every
future run. `redo`/`fix`/`triage`/`voice`/`deliver`/`rm` don't run winnow,
so none of them are affected — only `get` and a `redo --run --from
search|winnow` re-winnow. Gone from *both* the library and the ledger (the
`rm` default for a held show) is genuinely re-eligible — that's deliberate.

## Recipes

**What's the state of everything? / What came in overnight?**
`llama status` — the attention-list first (sessions awaiting approval or
incomplete), then held shows with their flags, then packaged (ready to
deliver), then in-flight. `llama status --packaged` is the ship-it
worklist; `llama deliver <show>` each one (or `llama deliver --packaged` to
ship the whole worklist at once).

**What's actually ready to go on air right now?**
`--packaged` only means `package/manifest.json` exists — it doesn't check
that the audio files are still there, or that the show is scripted/voiced/
has a `broadcast.m3u`. `llama status --broadcast-ready` (or `llama show
<show>` for the reasons on one show) answers the stricter question;
`llama deliver --broadcast-ready` ships only that airable subset. No
inverse flag exists — a `no` shows its reasons on `llama show <show>`.

**Clear my overnight holds.**
`llama triage` — walks every held show one at a time with the interactive
prompt (`[e]xclude tracks / [m]etadata / [v]ague / [o]verrule / [s]kip /
[q]uit`), resolving and re-processing each one on the spot as you answer.
`s` to leave one for later, `q` to stop the walk early.

**A run printed `needs-review, skipped` for a show I want.**
`llama show <show>` to read the flags (strictly read-only). If a flag is a
false alarm, `llama fix <show> --overrule`. If it's real (e.g. unresolved
titles), fix the cause with the matching `llama fix` flag (it auto-runs the
redo) — see the three resolutions in
[Clearing gate 2](#the-two-human-gates-dont-confuse-them) above, or drive
it interactively with `llama triage`.

**This show has junk announcement tracks.**
`llama show <show> --tracks` to see the numbered track list, then `llama
fix <show> --exclude 9,10` (track numbers or filenames both work,
comma-lists ok, repeatable too) — adds them to `overrides.exclude` and
re-gathers immediately; gather drops them with reason `operator-excluded`
and warns if an entry doesn't match any source file. A clean re-gather with
the junk gone self-clears the hold.

**Wrong venue, city, date, a track title, or where a set break falls.**
`llama fix <show> --set-venue "Winterland" --set-city "San Francisco, CA"
--set-date 1973-06-10 --set-title 4="Dark Star" --set-breaks "9,17"` — give
only the flags you need; each forces the matching `overrides.json` field
and (once, for the combined edit) re-gathers. `--clear-title N` drops one
forced title, `--clear-set-breaks` drops the forced break list.
`--set-breaks` takes the track numbers a break falls *after*,
numbered-sets-only (no way to name an encore this way). Same self-clearing
rule as excludes: a clean re-gather drops the hold on its own.

**This show's setlist is unknowable.**
`llama fix <show> --narration vague` — sets `overrides.narration =
"vague"`, clears the hold, and redoes from `brief` immediately (regenerating
the briefing, script, and package); neither the briefing nor the script
names songs or asserts set structure, but both are otherwise normal.

**I ran `get --plan` (or a human-gate profile) — now what?**
`llama run list` (or `llama status`) shows it in the attention-list with a
`llama run approve <session-id>` hint. Approve, say yes when it offers to
process, or `llama run resume <session-id>` later if you decline.

**A stage failed with an LLM error.**
The raw output is in `shows/<slug>/llm-failure.txt`. Just
`llama run resume <session>` — completed stages are skipped, the failed one
retries.

**I want a different recording of the same show.**
`llama redo <show> --from select` — the drop cascades, so gather through
package rebuild from the newly picked recording. `research.md` is kept
(it's about the performance, not the recording); add `--redo-research` if
you want it redone too.

**Re-research a show.**
`llama redo <show> --from research` — this also deletes `vetting.json`,
so the new research gets re-vetted.

**Voice every packaged-but-silent show.**
`llama voice --unvoiced --yes` (or `llama redo --unvoiced --from package
--voice`) — batch-selects every packaged show with no `dj-audio/` yet,
prints the plan, and re-packages each with speech. Each show uses its
recorded voice (house or presenter); a failure on one show doesn't stop the
rest.

**I want to add (or change) the spoken DJ voice on an already-packaged show.**
`llama voice <show>`. To switch to a *different* voice, set `[tts] voice`
(house shows) first. For a hosted show it depends on what the presenter
uses: edit `voice_clone` (or the clip it points to) and the new clip takes
effect, since the clone reference is re-read live; editing a preset
`voice` does **not** take effect this way, since a redo replays the voice
stamped on the show at process time — re-run the show fresh (`llama get
--profile <name>`) to pick up a new preset voice. Unchanged script segments
aren't re-synthesized, so this is cheap even against the paid API. `llama
voice --off <show>` strips voice audio back out.

**I edited a presenter's character — how do I hear the new persona?**
`llama redo <show> --from synthesize` re-scripts with the new persona
(deletes and rebuilds `dj-notes.*` and everything downstream, including
`dj-audio/` if the show is voiced). Swapping a presenter's `voice_clone`
with the character unchanged doesn't need a re-script either — `llama voice
<show>` is enough to re-render audio in the new voice, since the clone
reference is re-read live. Swapping a preset `voice` needs a fresh `get
--profile` instead, same as above.

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

**The same show keeps coming back in every `get`.**
It's neither in the library nor the history ledger. Deliver it, or `llama
suppress <performance-id>` to reject it without touching disk (works even
for a show that's no longer on disk, given a raw `collection/date[/eN]`
id).

**A search or winnow decision looks wrong (session-level, not one show).**
`llama redo --run <session> --from winnow` rebuilds the shortlist
(confirming first if approvals would be lost); `--from search` re-searches
and drops the shortlist with it.

**I want to clean up a stale or abandoned session.**
`llama run list` to see what's awaiting attention; `llama run rm <session>`
discards the session directory (shows it already processed live on in
`shows/`, untouched).

## Troubleshooting: message → meaning → action

| You see | It means | Do |
|---|---|---|
| `shortlist ready — nothing processed.` (`get --plan`) | Session parked awaiting approval | `llama run approve <session-id>`, or `llama run rm <session-id>` to discard |
| `sessions needing attention:` (on `status`/`run list`) | A session is awaiting approval or incomplete | Follow the printed `llama run approve`/`llama run resume` hint |
| `needs-review, skipped: <show>` | Gate 2: a flag was set during first-time processing | `llama show <show>` to read the flags; `llama fix <show> --overrule` if a false alarm, or the matching `fix` flag if real, or `llama triage` interactively |
| `still held: <slug>` (from `redo`/`voice`/`fix`/`triage`) | Gate 2: the show came back held after a re-run | Same as above |
| `skipping <show>: needs review (…)` (log line) | Same as above, with the flags inline | Same |
| `holding <show>: flagged during packaging (…)` | Package built but audio verification flagged it | `llama show <show>`; `llama fix <show> --overrule` if acceptable |
| `refusing to deliver <slug>: held for review — resolve with llama triage` | Delivering a held show | `llama triage`/`llama fix <slug> --overrule`, then `llama deliver` again — there is no delivery-time override |
| `FAILED <show>: …` | LLM/network failure mid-show | `llama run resume <session>` retries just the missing pieces; see `llm-failure.txt` |
| `FAILED <show>: …` (voice active) | TTS backend failed (bad key, rate limit, missing key — Voxtral needs `MISTRAL_API_KEY`, ElevenLabs needs `ELEVENLABS_API_KEY`) — show gets no package, batch continues | `llama voice <show>` (or `llama redo <show> --from package`) once the API issue clears; the segment cache means only the unfinished clips re-render |
| `note: already-packaged shows won't be re-voiced by a plain replay; …` | `llama run resume <session>` on a session whose shows are already packaged is a no-op for them | `llama voice <show>` (one show), or `llama redo --run <session> --from package --voice` (the whole session) |
| `'x' is ambiguous` + a list | Substring matched several shows/sessions | Use a longer substring or a full name from the list |
| `no show matches 'x'` / `no session matches 'x'` | Resolver found nothing | `llama status` / `llama run list` (or `llama status --by-run`) to see what exists |
| `no provenance.json in … - reprocess it via its run` | `redo`/`voice` on a hand-built show with no provenance | Reprocess once via its session to write `provenance.json` |
| `No shows survived winnowing.` | Nothing passed dedup + mechanical floors + scoring | Broaden the query, lower floors, or check the library/history |
| `winnow: N candidates -> M after library+ledger -> K after mechanical` | Dedup + mechanical-floor progression | Informational; a big drop at the first arrow means most candidates are already on disk or in history |
| `winnow: N of M scored shows fell below the quality floor` | LLM scores under `min_quality_score` (default 6.0) were dropped | Expected while a pool is healthy; if it recurs and runs come back short, the well is drying — broaden criteria, or lower `--min-score` if you'd rather ship marginal shows |
| `no matching artists found on the LMA` | Artist-less query matched nothing in the index | Name an artist or broaden the style terms |
| `winnow: sampling N of M survivors for review fetch` | More candidates than the review-fetch budget; the best-evidenced are scored, bounded by `artist_cap`/`year_cap` | Fine for most runs; raise `[winnow] max_metadata_fetch` in config to score more |
