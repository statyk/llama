# llama

Finds concerts on archive.org's Live Music Archive, vets them for quality,
researches the specific performance (fact-checking the research against the
setlist before it ships), and packages audio + notes for an automated radio
station. A verbatim DJ script is included by default (`--no-script`, or
`script = false` on a profile, opts out). The script can optionally be
**spoken** — per-segment MP3 clips synthesized via hosted Mistral Voxtral by
default (ElevenLabs is an opt-in alternative backend) — opt-in and off by
default (`--voice`, or a profile's own `voice`).

## Setup

    python3 -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev]"

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
                                     # with its own `voice` is voiced even when
                                     # this is off. Voice implies --script.
    backend = "voxtral"              # hosted Mistral Voxtral (default); or
                                     # "elevenlabs"
    voice = "..."                    # station-default voxtral preset name (or
                                     # elevenlabs voice_id when backend="elevenlabs")
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

Release binaries (attached to each GitHub Release) are signed: the macOS build
is Developer ID-signed and notarized (Gatekeeper-clean; because it is a bare
executable it can't be stapled, so first run does an online notarization check),
and the Windows build is Authenticode-signed via Azure Trusted Signing. The
Linux builds are unsigned — verify them against `SHA256SUMS`.

## Use

    llama find "GD shows 73-74 with a china>rider"
    llama find "top 10 Grateful Dead shows of the 1980s" --auto
    llama find "well-known folk/acoustic performer, 1960s-70s, highly rated"
                                     # artist-less queries match artists against the index first
                                     # (interactive runs let you prune the list)
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
    llama profile run sunday-dead-hour
    llama status                     # every show + its state, held-for-review first
    llama runs                       # runs with per-state show counts
    llama review countryish          # approve a run's shortlist, optionally process it
    llama run countryish             # resume/replay a run; finished stages are skipped
    llama show 1973-06-10 [--clear]  # inspect (or overrule) a needs-review hold
    llama redo 1973-06-10 --from vet # re-run one show's pipeline from a stage
    llama deliver 1973-06-10         # copy package to the station inbox
    llama ledger list                # broadcast history / dedup

Shows and runs are addressed by **name or any unique substring** (paths
still work): `llama show 1973-06-10` finds `gratefuldead-1973-06-10`; an
ambiguous substring fails loudly and lists the candidates.

Two different human gates, easy to conflate: `llama review` answers "which
shortlisted shows are worth processing" (gate 1). Separately, a processed
show can be held as **needs-review** when a stage flags something suspicious
(`needs-review, skipped: ...`, gate 2) — `llama status --held` lists those,
`llama show` inspects and clears one, and `llama redo` re-runs it from the
flagged stage. See [docs/workflow.md](docs/workflow.md) for the full
pipeline map, every flag, and a troubleshooting table — start there if a
run didn't do what you expected.

### Explore artists

    llama artists "jangly 80s college rock"     # NL search, ranked with stats
    llama artists                               # deepest catalogs, no LLM call
    llama artists --all "obscure tape scene"    # include the long tail
    llama artists --refresh                     # force an index rebuild

The first call builds a local artist index (one collections request plus
~30 scrape pages over all LMA items, about a minute); it auto-refreshes
after 30 days. Small collections are hidden unless they clear the
`[artists]` thresholds in config (defaults: 25 recordings or 50k
downloads); `--min-recordings` / `--min-downloads` / `--all` override
per invocation.

## Tests

    pytest -q          # offline suite
    pytest -m live -q  # hits real archive.org (no LLM)

See `docs/superpowers/specs/2026-07-14-llama-design.md` for the design.

## Package format (v2)

A delivered show package contains:

- `audio/` — verified, tagged tracks (`01 - Morning Dew.mp3`, ...)
- `playlist.m3u`
- `manifest.json` — `schema_version: 2`; tracks, set breaks, durations,
  source lineage, `show.context`, pointers `research` / `reviews`, and
  `research_vetted`
- `research.md` — web-researched show notes, grounding-checked against the
  setlist (`vet` stage) before packaging
- `reviews.md` — trimmed listener-review digest (top 5, 800 chars each)
- `dj-notes.md` + `manifest.dj_notes` — verbatim DJ script, present by
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
(`--voice` on `find`/`run`/`review`/`redo`), or per profile (`--voice
VOICE_ID` on `profile add`, which opts that profile in even when `[tts]
enabled` is false — different profiles can speak in different voices).
Voice always implies script: enabling voice forces the DJ script on even
against `--no-script`, since there is no text to voice otherwise.

When a show is voiced, `package/dj-audio/` gains one MP3 per script
segment (`00-intro.mp3`, one `set<key>-intro.mp3` per set, one
`break<N>.mp3` per set-break note, `99-outro.mp3`), and the manifest gains
a `dj_audio` block of package-relative paths to them (each `set_breaks`
entry also gets an `audio` path). See
[docs/station-brief.md](docs/station-brief.md) for the full contract.

Segments are cached per show by a hash of (text, voice, model), so
repackaging an unchanged script doesn't re-spend on the paid API; `llama
redo <show> --from package --voice` re-voices a previously-packaged show
(it replays the show's recorded voice — set a new `[tts] voice`/profile
voice first to actually switch voices), and `--force` re-renders
everything instead of reusing the cache. A plain `llama run <run> --voice`
on an already-packaged run does **not** re-voice it — the package stage is
skipped — it prints a note pointing at `redo --from package --voice`. A
TTS failure (bad key, rate limit, missing key while voice is active) fails
only that show — no package, no delivery — while the rest of the batch
continues; retry with `redo --from package` once resolved.

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

### Downstream synthesis contract

If your DJ (human or LLM) writes its own spoken copy from this package, it
inherits the factual guard this pipeline applies to its own scripts:

- every song mentioned must match a track title in `manifest.tracks`
- set intros must cover exactly the sets present in `manifest.tracks[].set`
- one break note per entry in `manifest.set_breaks`

Copy that names songs or sets not in the manifest must not air.

## Licensing

llama is licensed under **GPL-3.0-or-later**; see [LICENSE](LICENSE) for the
full text. `src/llama/data/set_breaks.csv` is vendored from the
[eichblatt/deadstream](https://github.com/eichblatt/deadstream) project
(also GPL-3.0) — see `src/llama/data/README.md` for vendoring details and
attribution.
