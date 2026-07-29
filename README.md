# llama

Finds concerts on archive.org's Live Music Archive, vets them for quality,
researches the specific performance (fact-checking the research against the
setlist before it ships), and packages audio + notes for an automated radio
station. A verbatim DJ script is included by default (`--no-script`, or
`script = false` on a profile, opts out). A profile can name a **presenter**
(`presenters/<id>.toml`) as its on-air host — a persona-authored voice that
speaks in the first person and can hold opinions. The script can optionally
be **spoken** — per-segment MP3 clips synthesized via hosted Mistral Voxtral
by default (ElevenLabs is an opt-in alternative backend; presenter voice
clones are Voxtral-only) — opt-in and off by default (`--voice`, or naming a
presenter on the profile).

## Setup

This is a monorepo: `packages/llama` is the CLI described above, and
`packages/herder` is the shared LLM task layer underneath it (tiered
provider resolution, schema-validated task runners, retry escalation).
Install both editable together:

    python3 -m venv .venv && source .venv/bin/activate
    pip install -e packages/herder -e "packages/llama[dev]"

Optional config at `~/.llama/config.toml` — seed a fully-commented copy of
these defaults with `llama config init` (`--stdout` to print instead):

    root = "/path/to/workdir"        # default ~/.llama
    delivery_path = "/station/inbox" # for `llama deliver`
    audio_format = "mp3"             # or "flac"

    [setlistfm]
    api_key = "..."                  # or SETLISTFM_API_KEY env var; optional —
                                     # without it set-structure recovery is
                                     # best-effort from LMA descriptions only

    [tts]
    enabled = true                   # spoken DJ patter; default false. A profile
                                     # with a presenter is voiced even when
                                     # this is off. Voice implies --script.
    backend = "voxtral"              # hosted Mistral Voxtral (default); or
                                     # "elevenlabs"
    voice = "..."                    # HOUSE voxtral preset name (or elevenlabs
                                     # voice_id when backend="elevenlabs"), used
                                     # only when a profile names no presenter
                                     # (presenters/<id>.toml own their voice —
                                     # see Presenters below)
    # voice_clone = "/path/to/ref.wav" # 3-25s reference WAV; when set, voxtral
                                     # clones it instead and ignores `voice`
    # model = "..."                 # per-backend default when unset
                                     # (voxtral-mini-tts-2603 / eleven_multilingual_v2)
    api_key = "..."                  # or MISTRAL_API_KEY / ELEVENLABS_API_KEY env
                                     # var (env wins); no local/offline TTS option yet
    # chunk = true                   # sentence-by-sentence synthesis + concat
                                     # for better prosody; default false; needs lameenc

    [winnow]
    max_metadata_fetch = 40          # review-fetch budget; when survivors exceed it
                                     # the best-evidenced are sampled, bounded by
                                     # artist_cap/year_cap

    # Recording selection ships GD-tuned defaults (shown here); override per
    # collection. Taper bonuses match identifier substrings; among revisions
    # by the same taper the newest gets the full bonus. lineage_eras replace
    # the global sbd/matrix/aud base scores inside a date window.
    [selection.tapers.GratefulDead]
    miller = 2.0                     # Charlie Miller: community gold standard
    seamons = 1.0

    [[selection.lineage_eras]]       # early-80s boards are rough: MTX > AUD > SBD
    collection = "GratefulDead"
    date_from = "1980-01-01"
    date_to = "1987-12-31"
    scores = { matrix = 3.0, aud = 2.0, sbd = 1.0 }

    [llm.default]
    backend = "claude_cli"           # requires the `claude` CLI on PATH
    # backend = "openrouter"         # HTTP alternative; set OPENROUTER_API_KEY
    # Model tiers (low/medium/high): haiku/sonnet/opus on claude_cli;
    # gemini-2.5-flash / claude-sonnet-4.5 / claude-opus-4.1 on openrouter.
    # Defaults: medium for most tasks; high for deep_research and synthesize;
    # low for vet_research.
    # If a task's output fails validation twice, the final retry runs one
    # tier up (exact `model` pins never escalate).

    [llm.deep_research]
    # backend = "claude_cli"         # recommended when the default backend is
    # openrouter: openrouter research is single-shot web-search grounding,
    # weaker than the claude CLI's agentic multi-step research, and research
    # quality is audible on air. Mixing backends per task is supported.

    [llm.synthesize]
    # tier = "medium"                # example: cheaper synthesis
    # model = "claude-opus-4-8"      # example: exact pin, bypasses tiers

    [llm.tiers.openrouter]
    # medium = "deepseek/deepseek-chat-v3"  # retarget what a tier means per backend

Config values **replace** built-in defaults — nothing merges. Adding any
`[selection.tapers.<Band>]` table replaces the whole taper set (the
GratefulDead bonuses vanish unless restated), and any
`[[selection.lineage_eras]]` block replaces the built-in era list. One
level down, an era's `scores` map replaces the whole lineage table: an
omitted class (`sbd`/`matrix`/`aud`/`unknown`) scores 0.0, not its global
value. `llama config init` writes all defaults out explicitly so additive
edits keep them. The trap runs both ways: deleting a seeded table or block
restores its built-in default (absence = default) — to truly clear one, set
it empty (e.g. `lineage_eras = []` under `[selection]`).

### Presenters (optional on-air hosts)

A **presenter** is a reusable radio-show host — TTS voice + authored
character + on-air identity — created with `llama presenter add <id>
--name NAME --sex SEX (--voice ID | --voice-clone WAV) (--character "..." |
--character-file PATH)`, or defined by hand in
`~/.llama/presenters/<id>.toml` (both write/read the same file; `llama
presenter list` / `llama presenter show <id>` inspect what's there):

    name = "Casey"
    sex = "male"
    voice = "american-dj"          # or: voice_clone = "/path/to/casey-ref.wav"
    character = """
    Warm late-night FM veteran. Dry humor, deep tape-collector knowledge, gets
    audibly excited about big jams. Keeps it loose but never sloppy.
    """

A profile references one with `presenter = "<id>"` and names its show with
`title = "..."` (`llama profile add sunday-dead-hour "..." --presenter casey
--title "Sunday Morning Dead"`). Naming a presenter voices that profile's
runs even when `[tts] enabled` is false (`--no-voice` still strips audio for
one run); with no presenter, `[tts] voice`/`voice_clone` above is the house
default and the script stays in the neutral narrator voice. The host knows
the show's title and drops it on air occasionally, and speaks with
loosened-but-bounded grounding: opinions and paraphrased review/research
sentiment are the host's own, but concert facts (dates, venue, songs, set
structure) still come only from the show data, and the host never claims to
have been there — the same `vet`/`factual_guard` checks hold a show for
review either way. `voice_clone` on a presenter is Voxtral-only (errors
loudly on the ElevenLabs backend). Character edits are live: edit the TOML,
then `llama redo <show> --from synthesize` re-scripts with the new persona.

Release binaries (attached to each GitHub Release) are signed: the macOS build
is Developer ID-signed and notarized (Gatekeeper-clean; because it is a bare
executable it can't be stapled, so first run does an online notarization check),
and the Windows build is Authenticode-signed via Azure Trusted Signing. The
Linux builds are unsigned — verify them against `SHA256SUMS`.

## Use

    llama presenter add casey --name Casey --sex male --voice american-dj \
        --character "Warm late-night FM veteran, dry humor, deep tape-collector knowledge."
                                     # writes presenters/casey.toml; hand-editing it still works
    llama presenter list              # every presenter, one line each
    llama presenter show casey        # one presenter's full fields
    llama get "GD shows 73-74 with a china>rider"
    llama get "top 10 Grateful Dead shows of the 1980s" --auto
    llama get "well-known folk/acoustic performer, 1960s-70s, highly rated"
                                     # artist-less queries match artists against the index first
                                     # (interactive runs let you prune the list)
    llama get "GD 1972" --plan       # cheap preview: winnow + shortlist, nothing processed
                                     # (llama run approve <session-id> to actually process it)
    llama profile add sunday-dead-hour "classic Grateful Dead" --count 1 --human-gate
    llama profile add jazz "well-regarded jazz-adjacent live sets" --count 13 --artist-cap 0.25
                                     # multi-artist profiles: one artist may hold at most
                                     # ceil(count*cap) picks while others have candidates;
                                     # --year-cap does the same per year (default off:
                                     # scores decide the year mix; set it for an era tour);
                                     # --min-score (default 6.0) floors the LLM review score
                                     # so a thinning pool fails loudly, never fades quietly
    llama profile add funky "funk, soul, R&B" --count 13 \
        --artists "Galactic, Lettuce, Soulive, Dumpstaphunk"
                                     # pin the roster: runs skip the LLM artist matcher and
                                     # search exactly these (test-drive with `llama artists`,
                                     # freeze what you like; typos fail at add time)
    llama profile artists funky       # view a profile's pinned roster
    llama profile artists funky --set "Galactic, Lettuce, Soulive"
                                     # re-pin it (validated against the index); --set "" clears
    llama profile list                # every profile: name, count, presenter, query
    llama profile show sunday-dead-hour   # inspect one profile (read-only, no LLM call)
    llama get --profile sunday-dead-hour
    llama status                     # attention-list, then every show + its state
    llama status --held              # just the shows waiting on your judgment
    llama status --unvoiced          # packaged shows with no DJ audio yet
    llama status --broadcast-ready   # shows that are actually airable right now
    llama status --by-run            # sessions with per-state show counts
    llama run list                   # sessions awaiting approval or incomplete
    llama run approve countryish     # gate 1: approve a session's shortlist, optionally process it
    llama run resume countryish      # resume/replay a session; finished stages are skipped
    llama show 1973-06-10            # inspect one show (its state, artifacts, archive URL, flags)
    llama show 1973-06-10 --tracks   # numbered track list (index, title, filename, duration)
    llama fix 1973-06-10 --exclude 9,10       # exclude by track number (filenames work too);
                                     # auto-runs the redo from gather
    llama fix 1973-06-10 --set-venue "Winterland" --set-city "San Francisco, CA" \
        --set-date 1973-06-10 --set-title 4="Dark Star" --set-breaks "9,17"
                                     # metadata corrections; redoes from gather, hold self-clears
    llama triage                     # walk every held show and resolve each in turn
    llama redo 1973-06-10 --from vet # re-run one show's pipeline from a stage
    llama voice --unvoiced --yes     # voice every packaged-but-silent show
    llama deliver 1973-06-10         # copy package to the station inbox
    llama deliver --broadcast-ready  # deliver everything that's actually airable
    llama rm old-show --suppress     # delete a show and never offer it again
    llama history list                # broadcast history / dedup

Shows and sessions are addressed by **name or any unique substring** (paths
still work): `llama show 1973-06-10` finds `gratefuldead-1973-06-10`; an
ambiguous substring fails loudly and lists the candidates.
`status`, `triage`, `redo`, `voice`, `deliver`, and `rm` share one filter
vocabulary (`--held`/`--packaged`/`--voiced`/`--unvoiced`/`--broadcast-ready`/
`--state`/`--artist`/`--run`); `--broadcast-ready` is positive-only (no
inverse flag) and selects shows that are packaged with every track's audio
verified on disk, scripted, voiced, have a `broadcast.m3u`, and aren't held.
A batch action prints a plan and asks before running (`--yes` skips the
prompt); acting on held shows via a selector needs explicit `--held` opt-in.

Two different human gates, easy to conflate: `llama run approve` answers
"which shortlisted shows are worth processing" (gate 1) — sessions awaiting
it show up in `llama status`/`llama run list`'s attention-list. Separately,
a processed show can be held as **needs-review** when a stage flags
something suspicious (`needs-review, skipped: ...`, gate 2). A held show
has **three resolutions**, driven from `llama fix` (flag-by-flag, auto-runs
the redo) or `llama triage` (interactive walkthrough):

- **Correct the data** — `llama fix <s> --exclude <file-or-number>` drops
  junk tracks (e.g. between-set stage announcements; `llama show <s>
  --tracks` lists the numbers), and `--set-venue`/`--set-city`/`--set-date`/
  `--set-title N="..."`/`--set-breaks "9,17"` fix wrong venue, date, a track
  title, or where a set break falls. Either way it redoes from `gather` and
  the hold clears itself if that fixes it.
- **Accept an unknowable setlist** — `llama fix <s> --narration vague` tells
  the script writer to stay general (no song names, no set-structure
  claims), clears the hold, and redoes from `synthesize`.
- **Overrule a false alarm** — `llama fix <s> --overrule`, which redoes from
  `package`.

`llama triage` offers these as an interactive prompt over every held show
and runs your choice on the spot. See [docs/workflow.md](docs/workflow.md)
for the full pipeline map, every flag, and a troubleshooting table — start
there if a run didn't do what you expected.

**Running several jobs at once.** `llama` is safe to run as multiple
concurrent processes against the same `~/.llama/` on one machine — kick off
several `llama get`/profile runs (or a cron fan-out) in parallel. If two runs
pick the same performance, one builds it and the others wait and reuse the
result rather than duplicating the work; runs never idle behind each other
on shows they don't share. (Local filesystem only — a network/NFS-shared
workspace is not supported.)

### Explore artists

    llama artists "jangly 80s college rock"     # NL search, ranked with stats
    llama artists                               # deepest catalogs, no LLM call
    llama artists --include-junk "obscure tape scene"    # include the long tail
    llama artists --refresh                     # force an index rebuild

The first call builds a local artist index (one collections request plus
~30 scrape pages over all LMA items, about a minute); it auto-refreshes
after 30 days. Small collections are hidden unless they clear the
`[artists]` thresholds in config (defaults: 25 recordings or 50k
downloads); `--min-recordings` / `--min-downloads` / `--include-junk`
override per invocation.

## Tests

    pytest -q          # offline suite
    pytest -m live -q  # hits real archive.org (no LLM)

See `docs/superpowers/specs/2026-07-14-llama-design.md` for the design.

## Package format (v2)

A delivered show package contains:

- `audio/` — verified, tagged tracks (`01 - Morning Dew.mp3`, ...)
- `playlist.m3u` — music-only play order
- `broadcast.m3u` — voiced shows only: playlist with the `dj-audio/` clips
  interleaved (each set's lead-in before its first track, outro last)
- `manifest.json` — `schema_version: 2`; tracks, set breaks, durations,
  source lineage, `show.context`, pointers `research` / `reviews`, and
  `research_vetted`
- `research.md` — web-researched show notes, grounding-checked against the
  setlist (`vet` stage) before packaging
- `reviews.md` — trimmed listener-review digest (top 5, 800 chars each)
- `dj-notes.md` + `manifest.dj_notes` — verbatim DJ script (neutral house
  narrator, or a profile's presenter's persona when one is set), present by
  default; absent when the run opted out (`--no-script`, or `script = false`
  on a profile)
- `dj-audio/` + `manifest.dj_audio` — spoken DJ script (opt-in TTS), present
  only when voice was active for the show

### Script mode does not change the data

Whether a run generated a script has no effect on the content or quality of
anything else in the package. Research runs before the script decision is
consulted (same prompt, same inputs, same model tier), the vet grounding
check runs unconditionally right after it, and `reviews.md` and the
manifest's show data (including `show.context`, which comes from the vet
extraction) are built identically in both modes. `research.md` is the same
bytes either way.

The two modes differ only in scrutiny and availability, and both
differences err safe:

- **Script-on packages cleared one extra gate.** The generated script is
  cross-checked against the setlist (`factual_guard`), which occasionally
  catches prose-level research contamination that assertion-level vetting
  can't see — a wrong-show anecdote surfacing as a bad song name in the
  patter. A script-on run may therefore hold a subtly-bad show for review
  that a script-off run would ship.
- **Script-on runs have one extra failure point.** A synthesize call that
  exhausts its retries skips the show entirely — it affects whether a
  package is produced, never what's inside one.

Consumers can rely on `research.md`, `reviews.md`, and the manifest meaning
exactly the same thing regardless of mode; the script setting only
determines whether the script artifacts exist.

### Voice mode (opt-in TTS)

The DJ script can additionally be **spoken** — off by default, and
orthogonal to whether other shows in the same run are voiced. The default
backend is hosted Mistral Voxtral (`voxtral-mini-tts-2603`); set
`[tts] backend = "elevenlabs"` to use ElevenLabs instead.
Enable it globally (`[tts] enabled = true` + `[tts] voice`), per invocation
(`--voice` on `get`/`redo`, or the dedicated `llama voice` verb), or per
profile by naming a **presenter** (`profile add --presenter <id>`, see
[Presenters](#presenters-optional-on-air-hosts) above), which opts that
profile in even when `[tts] enabled` is false — different profiles can
have different hosts and voices. Voice always implies script: enabling
voice forces the DJ script on even against `--no-script`, since there is no
text to voice otherwise.

When a show is voiced, `package/dj-audio/` gains one MP3 per script
segment — one `set<key>-intro.mp3` per non-encore set (the first also opens
the show) and a closing `99-outro.mp3` — and the manifest gains a `dj_audio`
block of package-relative paths to them. There is one clip per gap between
music blocks, so nothing plays back-to-back: the encore has no lead-in (it
follows the final set), and the outro recaps it. See
[docs/station-brief.md](docs/station-brief.md) for the full contract.

Segments are cached per show by a hash of (text, voice, model), so
repackaging an unchanged script doesn't re-spend on the paid API; `llama
voice <show>` (sugar for `redo <show> --from package --voice`) re-voices a
previously-packaged show — it replays the show's recorded voice; to
actually switch voices, first set a new `[tts] voice` for a house show, or
edit the presenter's `voice`/`voice_clone` for a hosted show. Unchanged
segments are never re-rendered — only text/voice/model/chunk changes
invalidate the cache. Because Voxtral is non-deterministic (the same script
yields a different take each call), `llama voice <show> --fresh <clip-stem>`
(e.g. `set1-intro` or `99-outro`; repeatable) deletes just that clip so the
package re-render re-rolls only it — leaving the other cached takes
untouched — which is how you rescue a single janky read. A plain `llama run
resume <session>` on an
already-packaged session does **not** re-voice it — the package stage is
skipped — it prints a note pointing at `llama voice <show>`. A TTS failure
(bad key, rate limit, missing key while voice is active) fails only that
show — no package, no delivery — while the rest of the batch continues;
retry with `llama voice <show>` once resolved.

Voxtral is the default backend, ElevenLabs an opt-in alternative
(`fake` exists for offline tests). Voxtral's open weights carry a CC BY-NC
license, but that's irrelevant here: llama is strictly non-commercial, and
this integration only calls Mistral's hosted API (a paid commercial
service), not the weights directly. Self-hosting Voxtral, and any other
local/offline TTS backend, is deliberately deferred.

**Chunked synthesis (`[tts] chunk`, default off).** Instead of one TTS call
per script segment, `chunk = true` synthesizes each *sentence* separately
(via the provider's `fmt="wav"` path), concatenates the raw PCM with a short
inter-sentence silence, and encodes a single MP3 at the end — noticeably
better prosody and pacing on longer DJ patter than one long call, at the
cost of more provider round-trips per segment. It requires the `lameenc`
dependency (installed by default) and is part of the per-segment cache key,
so flipping it re-renders affected clips on the next `redo --from package`.
The chunked encoder picks its bitrate from the actual sample rate returned
by the provider (64kbps for a ~24kHz stream, matching Voxtral's real output)
rather than a fixed 128kbps, to avoid an unusual bitrate/sample-rate
combination; if `ffmpeg -v error` still reports anything on chunked clips,
the next step is resampling to 44.1/48kHz before encoding.

**Bed music (`[tts] bed`, default off).** A low instrumental bed can play
under each `dj-audio/` clip: pre-roll (music alone), then the bed continues
quietly under the voice, then a short tail (music alone) — attenuated by
`[tts] bed_gain_db` (default **-20 dB**) and faded in/out. Set a station
default with `[tts] bed = "/path/to/bed.wav"`, or override per host with
`bed = "..."` in a presenter's `presenters/<id>.toml` (a presenter's own bed
wins over the station default; the gain is always the station
`bed_gain_db`). The bed file **must be 24kHz mono 16-bit WAV** — anything
else (wrong sample rate, stereo, wrong bit depth) or a missing file
hard-fails the package for that show. Mixing is pure PCM math via `numpy`
(a new dependency); no `ffmpeg` is involved.

*Preparing a bed file.* `llama` never converts audio — produce the required
24kHz mono 16-bit WAV once with any external tool and point `[tts] bed` (or a
presenter's `bed`) at the result. For example, with ffmpeg:

```
ffmpeg -i your-track.mp3 -ac 1 -ar 24000 -c:a pcm_s16le bed.wav
```

or with sox: `sox your-track.mp3 -r 24000 -c 1 -b 16 bed.wav`
(`-ac 1`/`-c 1` = mono, `-ar 24000`/`-r 24000` = 24kHz, `pcm_s16le`/`-b 16` =
16-bit). These tools are only for this one-time prep — they are **not** runtime
dependencies of `llama`. Verify a file with
`ffprobe bed.wav` (or `soxi bed.wav`): it should report `pcm_s16le`, `1
channel`, `24000 Hz`.

### Downstream synthesis contract

If your DJ (human or LLM) writes its own spoken copy from this package, it
inherits the factual guard this pipeline applies to its own scripts:

- every song mentioned must match a track title in `manifest.tracks`
- set lead-ins must cover exactly the non-encore sets present in
  `manifest.tracks[].set` (the encore gets no lead-in)

Copy that names songs or sets not in the manifest must not air.

## Licensing

llama is licensed under **GPL-3.0-or-later**; see [LICENSE](LICENSE) for the
full text. `packages/llama/src/llama/data/set_breaks.csv` is vendored from the
[eichblatt/deadstream](https://github.com/eichblatt/deadstream) project
(also GPL-3.0) — see `packages/llama/src/llama/data/README.md` for vendoring details and
attribution.
