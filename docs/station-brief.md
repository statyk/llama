# llama → radio station: show-package handoff brief

*Prepared 2026-07-16 to open a coordination conversation between `llama`
(the show-sourcing pipeline) and the downstream radio-station app
(custom Claude-written scheduler layered on RadioDJ). Questions for the
station team are at the end.*

## What llama is

`llama` is a Python CLI that turns archive.org's Live Music Archive (LMA)
into broadcast-ready concert packages. For each request ("well-regarded
Grateful Dead shows 1969–1977", a standing "jazz" profile, etc.) it:

1. **Searches wide** — every matching recording via the uncapped scrape API.
2. **Winnows hard** — the LMA is a completist archive, so mere presence
   means nothing. An LLM scores listener reviews with attendance bias
   discounted (merit-based praise from people who *weren't* there counts
   most), a quality floor drops weak scores, and no single artist or year
   may monopolize a batch.
3. **Selects the best recording** of the chosen performance (soundboard vs
   audience lineage, taper reputation, completeness, revision recency).
4. **Recovers set structure** — canonical setlist from every sibling
   recording's description plus setlist.fm, aligned onto the chosen
   recording's tracks. Track titles come from a resolution cascade
   (embedded tags → parsed setlist → sibling recordings); titles are never
   guessed.
5. **Researches the specific performance** on the open web, then runs a
   deterministic **grounding check** (does the research assert songs or
   dates that don't belong to this show?).
6. **Packages**: downloads audio with md5 verification, filters junk files
   (the LMA contains spam MP3s that would otherwise go to air), tags every
   file, cross-checks real durations against metadata, and emits the
   package described below.

Anything suspicious at any stage (unresolved titles, duration mismatches,
setlist/DJ-notes contradictions, ungrounded research) marks the show
**needs-review** and holds it before delivery until a human clears it.
What reaches the station has passed every gate.

**Dedup:** llama keeps a ledger keyed by performance identity
(artist + date + venue, not archive.org item id) and will not process or
deliver the same performance twice. Replay/rotation policy is entirely the
station's concern — llama assumes a delivered package may be aired many
times.

## Delivery mechanics (current)

`llama deliver <name>` (name or unique substring; a path still works) copies
the package directory into a **watched folder** (`delivery_path` in llama's
config, or `--dest`), named by the slugified performance id, then records
the delivery in its ledger. `llama status --packaged` shows what's ready to
hand off:

```
<delivery_path>/gratefuldead-1973-06-10/
├── manifest.json
├── playlist.m3u
├── broadcast.m3u        # voiced shows only: playlist with DJ audio interleaved
├── audio/
│   ├── 01 - Morning Dew.mp3
│   ├── 02 - Beat It On Down the Line.mp3
│   └── ...
├── research.md
├── reviews.md
├── briefing.md            # neutral vetted briefing (always present, manifest v3)
├── briefing.json          # same content, structured
├── dj-notes.md           (default; absent only if the run opted out)
└── dj-audio/             (opt-in TTS; present only when the show was voiced)
    ├── set1-intro.mp3    (also opens the show)
    ├── set2-intro.mp3
    ├── ...               (one per non-encore set; the encore has none)
    └── 99-outro.mp3      (recaps the encore when there is one)
```

The copy is a plain recursive copy — **not atomic**, and there is no
completion sentinel today. If the station ingests on a filesystem watcher,
tell us; see question 1.

## Package format — `manifest.json`, schema_version 3

The manifest is the machine-readable contract; everything else is
supporting material. Field-by-field:

```jsonc
{
  "schema_version": 3,
  "show": {
    "artist": "Grateful Dead",
    "date": "1973-06-10",                  // ISO, always YYYY-MM-DD
    "venue": "RFK Stadium",                // may be null
    "city": "Washington, DC",              // may be null
    "context": "Peak 1973, RFK weekend"    // one-line era/tour context, vetted
  },
  "source": {
    "performance_id": "GratefulDead/1973-06-10",
    "identifier": "gd73-06-10.sbd.hollister.174.sbeok.shnf",  // archive.org item
    "url": "https://archive.org/details/gd73-06-10.sbd.hollister.174.sbeok.shnf",
    "lineage": "SBD > Master Reel > ..."   // recording lineage when known, may be null
  },
  "tracks": [
    {
      "index": 1,                          // play order, 1-based
      "set": "1",                          // "1" | "2" | "3" | "encore"
      "title": "Morning Dew",
      "filename": "01 - Morning Dew.mp3",  // relative to audio/
      "duration_sec": 733.4,               // measured from the delivered file
                                           // (source metadata only as fallback)
      "segue": true                        // runs directly into the NEXT track —
    },                                     // do not talk or crossfade over it
    ...
  ],
  "set_breaks": [
    { "after_track": 8 }                   // physical set boundary only: set 1
  ],                                       // ends after track 8. The DJ talk for
                                           // that gap rides the NEXT set's lead-in
                                           // (set_intros["2"]), not the break.
  "briefing": {              // llama's scriptwriter-facing text deliverable
    "file": "briefing.md",   // neutral vetted briefing (prose)
    "json": "briefing.json", // same content, structured (per-set talking points, cautions)
    "narration": "full",     // "vague": assert no songs/set structure downstream
    "vetted": true           // research passed the grounding check
  },
  "dj_notes": {                            // present by default; null only when
                                           // the run opted out (--no-script)
    "context": "one-line era context",
    "set_intros": { "1": "…", "2": "…" },  // one combined lead-in per non-encore
                                           // set; the encore has none
    "outro": "verbatim sign-off …",        // recaps the encore when there is one
    "mentioned_songs": ["Morning Dew", "..."]  // every song the script names
  },
  "dj_audio": {                             // opt-in TTS; present ONLY when the
                                           // show was voiced, otherwise null
    "set_intros": { "1": "dj-audio/set1-intro.mp3",
                    "2": "dj-audio/set2-intro.mp3" },
    "outro": "dj-audio/99-outro.mp3"
  },
  "research": "research.md",               // relative pointer, null if absent
  "reviews": "reviews.md",
  "research_vetted": true,                 // grounding check passed with zero flags
  "total_duration_sec": 10231.7,
  "set_durations_sec": { "1": 4110.2, "2": 5390.1, "encore": 731.4 }
}
```

### The other files

- **`audio/`** — `NN - Title.mp3` (or `.flac`; format is per-run config,
  mp3 default). Every file is md5-verified against archive.org, then tagged:
  ID3v2.3 for mp3 (`TIT2` title, `TPE1` artist, `TALB` album =
  `"<date> <venue>, <city>"`, `TRCK` track number, `TDRC` date, `COMM` =
  source archive.org identifier) or the equivalent Vorbis comments for FLAC.
  Durations in the manifest are measured from the actual files; a >5 s
  disagreement with source metadata blocks delivery instead of shipping.
- **`playlist.m3u`** — minimal `#EXTM3U` with relative `audio/…` paths in
  play order. Music only. Convenience only; the manifest is authoritative
  (the m3u has no set-break or segue information).
- **`broadcast.m3u`** — present only for voiced shows: the same `#EXTM3U`
  format, but with the `dj-audio/…` clips interleaved into play order (each
  set's lead-in before that set's first track, the outro last), so it can be
  played top-to-bottom without reconstructing the sequence from the manifest.
  This is exactly the interleaving described under "Spoken DJ audio" below.
- **`research.md`** — web-researched show notes in four fixed sections:
  `## Reputation`, `## Performance highlights`, `## Context`,
  `## Recording notes`. Grounding-checked before packaging; `research_vetted`
  in the manifest tells you whether it passed with zero flags.
- **`reviews.md`** — trimmed listener-review digest (top 5 reviews,
  ≤800 chars each) from the source archive.org item.
- **`briefing.md`** / **`briefing.json`** — the always-neutral, vetted
  briefing: era/tour/venue context, why the show is worth airing, per-set
  talking points, notable moments, review sentiment, and cautions for
  whoever writes on-air copy. Always present (manifest v3, no opt-out) and
  factually guarded against the setlist the same way `dj_notes` is; under
  `narration: "vague"` it names no songs and asserts no set structure, same
  as the script path. `briefing.md` is a deterministic render of
  `briefing.json` — the two can never disagree. This is now **the**
  recommended text source for a station-side scriptwriter: it is neutral
  (no in-house persona baked in) and structured for programmatic
  consumption.
- **`dj-notes.md`** — human-readable rendering of `dj_notes`: llama's own
  verbatim, ready-to-air DJ script (neutral house narrator, or a profile's
  presenter persona). Present by default, absent only when the run opted
  out with `--no-script`. This is llama's in-house scripting path,
  transitional — a downstream persona tool is planned to take over
  scriptwriting from the briefing after llama's split into separate
  projects completes; `dj-notes.md`/`dj_notes` keep working unchanged in
  the meantime.
- **`dj-audio/`** — spoken-word MP3 clips of the DJ script (opt-in TTS,
  hosted Mistral Voxtral by default or ElevenLabs as an alternative
  backend), present only when the show was voiced. When the show's profile
  names a **presenter** (a reusable host: voice + authored character,
  `presenters/<id>.toml`), `dj-notes`/`dj-audio` speak in that host's persona
  rather than a neutral narrator — concert facts stay grounded either way.
  One file per `dj_audio` path in the manifest; a `segments.json` sidecar in
  the same directory is llama's internal render cache and can be ignored.
  When a station default `[tts] bed` (or the host's own `bed` in
  `presenters/<id>.toml`) is configured, each clip already has a low
  instrumental bed mixed in underneath — pre-roll, then the bed continues
  quietly under the voice at `[tts] bed_gain_db` (default -20 dB), then a
  short tail — so there's nothing further for the station to layer on. Bed
  WAVs must be 24kHz mono 16-bit; a mismatched or missing bed file
  hard-fails that show's package. Mixing is pure PCM math via `numpy`; no
  `ffmpeg` involved. Because mixing needs PCM, bed-active clips are
  re-encoded to MP3 (24kHz mono, ~64 kbps via `lameenc`) rather than
  shipping the provider's native MP3 like unbedded clips do — a small,
  expected bitrate difference.

### Contract details worth knowing

- **The `narration` directive is binding on any downstream scriptwriter.**
  `briefing.narration` (and `manifest.briefing.narration`) is `"full"` or
  `"vague"` — under `"vague"` the setlist genuinely couldn't be resolved,
  and the briefing itself names no songs and asserts no set structure
  (`briefing.per_set` is empty). Any script generated from the briefing
  must honor the same constraint: no song names, no set-structure claims,
  under `"vague"`. `manifest.briefing.vetted` mirrors `research_vetted` at
  package time.
- **Scripts ship by default; opting out changes nothing else.** Runs can
  skip the script with `--no-script`, so consumers should still handle a
  null `dj_notes`. Research,
  vetting, reviews, and all structural data are identical whether or not
  `dj_notes` exists. If the station generates its own on-air speech from
  `briefing.md`/`briefing.json` (recommended) or `research.md`/`reviews.md`
  directly, it inherits the obligation to stay grounded in them — llama
  vets its research against the setlist and factually guards the briefing
  the same way, and a downstream generator should not reintroduce
  hallucinated claims.
- **Segues matter on air.** `segue: true` means the audio flows directly
  into the next track (Dead notation "China Cat > Rider"); insertions
  between segued tracks will sound broken.
- **Set breaks are real intermissions.** `set_breaks` marks where a station
  can insert station IDs or ads; the DJ's own between-set talk is already
  voiced as the next set's lead-in. Typical Dead shows have 1–2 breaks plus
  an encore boundary.
- **`show.context`** is a vetted one-liner designed for quick on-air
  framing when there's no script.
- Filenames are filesystem-safe (unsafe characters replaced), zero-padded,
  and unique within a package.
- **Spoken DJ audio is opt-in and additive.** `dj_audio` (and `dj-audio/`)
  exist only for shows llama voiced; a show can have `dj_notes` (text)
  without `dj_audio` (speech), but never the reverse. There is exactly one
  spoken clip per gap between music blocks, so nothing plays back-to-back:
  slot each `dj_audio.set_intros["<key>"]` before that set's first track
  (the first set's lead-in also opens the show), and `dj_audio.outro` after
  the last track. An **encore has no lead-in** — it plays straight after the
  final set, and the outro (which recaps it) is the only talk after it. A
  `set_breaks` entry is a physical marker (`after_track`) only; it carries no
  audio, because the between-set talk lives in the next set's lead-in.

## Questions for the station team

1. **Ingestion handshake** — is a watched folder right, and do you need
   atomicity (temp-dir + rename) or a completion sentinel
   (e.g. `manifest.json` written last, or a `.done` file)?
2. **RadioDJ import** — what does your scheduler actually consume? Is m3u
   useful, or should we emit a RadioDJ-native playlist/cart format, cue
   sheets, or a direct DB import file? Should set breaks/segues be encoded
   in the playlist rather than only the manifest?
3. **Audio spec** — preferred codec/bitrate/sample rate? Should we
   transcode (source material is mixed mp3/flac/shn) and/or
   loudness-normalize (e.g. EBU R128 / ReplayGain tags) before delivery?
   Live tapes vary wildly in level.
4. **Tagging** — do you key anything off ID3? We can adjust the tag scheme
   (grouping, catalog ids, custom TXXX frames) if RadioDJ's library
   ingestion needs it.
5. **Metadata gaps** — anything missing from the manifest for scheduling?
   Candidates: per-track intro/outro talk-over points, explicit
   total-with-breaks runtime, genre/era tags, suggested airdate,
   content advisories.
6. **Feedback channel** — if a package fails your ingestion or QA, how do
   you tell llama? A reject file dropped back in the folder, an HTTP
   callback, or manual? (llama's ledger marks the show `delivered`; a
   reject status could reopen it.)
7. **Schema evolution** — `schema_version` is bumped on breaking changes.
   v3 (the required `briefing` block) is the worked example: no migration,
   no back-compat window, old packages regenerate via `llama redo`. Do you
   want additive changes flagged too (minor version), and should we pin a
   version negotiation somewhere?

Format changes are cheap on our side — the packaging stage is one module
and everything is covered by offline tests. Happy to adapt to whatever
makes RadioDJ ingestion boring and reliable.
