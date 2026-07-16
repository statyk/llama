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

`llama deliver <show-dir>` copies the package directory into a
**watched folder** (`delivery_path` in llama's config, or `--dest`), named
by the slugified performance id, then records the delivery in its ledger:

```
<delivery_path>/gratefuldead-1973-06-10/
├── manifest.json
├── playlist.m3u
├── audio/
│   ├── 01 - Morning Dew.mp3
│   ├── 02 - Beat It On Down the Line.mp3
│   └── ...
├── research.md
├── reviews.md
└── dj-notes.md          (only when a DJ script was requested)
```

The copy is a plain recursive copy — **not atomic**, and there is no
completion sentinel today. If the station ingests on a filesystem watcher,
tell us; see question 1.

## Package format — `manifest.json`, schema_version 2

The manifest is the machine-readable contract; everything else is
supporting material. Field-by-field:

```jsonc
{
  "schema_version": 2,
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
    { "after_track": 8, "note_index": 0 }  // break falls after play-order index 8;
  ],                                       // note_index → dj_notes.set_break_notes[i],
                                           // null when no script exists
  "dj_notes": {                            // null unless a script was requested
    "context": "one-line era context",
    "intro": "verbatim show intro …",
    "set_intros": { "1": "…", "2": "…", "encore": "…" },
    "set_break_notes": ["read during break 1", "…"],
    "outro": "verbatim sign-off …",
    "mentioned_songs": ["Morning Dew", "..."]  // every song the script names
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
  play order. Convenience only; the manifest is authoritative (the m3u has
  no set-break or segue information).
- **`research.md`** — web-researched show notes in four fixed sections:
  `## Reputation`, `## Performance highlights`, `## Context`,
  `## Recording notes`. Grounding-checked before packaging; `research_vetted`
  in the manifest tells you whether it passed with zero flags.
- **`reviews.md`** — trimmed listener-review digest (top 5 reviews,
  ≤800 chars each) from the source archive.org item.
- **`dj-notes.md`** — human-readable rendering of `dj_notes`; present only
  when the run requested a script.

### Contract details worth knowing

- **Scripts are opt-in and their absence changes nothing else.** Research,
  vetting, reviews, and all structural data are identical whether or not
  `dj_notes` exists. If the station generates its own on-air speech from
  `research.md`/`reviews.md`, it inherits the obligation to stay grounded
  in them — llama vets its research against the setlist, and a downstream
  generator should not reintroduce hallucinated claims.
- **Segues matter on air.** `segue: true` means the audio flows directly
  into the next track (Dead notation "China Cat > Rider"); insertions
  between segued tracks will sound broken.
- **Set breaks are real intermissions.** `set_breaks` is where a station
  can insert station IDs, ads, or the corresponding `set_break_notes`
  entry. Typical Dead shows have 1–2 breaks plus an encore boundary.
- **`show.context`** is a vetted one-liner designed for quick on-air
  framing when there's no script.
- Filenames are filesystem-safe (unsafe characters replaced), zero-padded,
  and unique within a package.

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
   Do you want additive changes flagged too (minor version), and should we
   pin a version negotiation somewhere?

Format changes are cheap on our side — the packaging stage is one module
and everything is covered by offline tests. Happy to adapt to whatever
makes RadioDJ ingestion boring and reliable.
