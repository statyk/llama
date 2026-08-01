# m3u → single mp3 stitcher — design

Date: 2026-07-31
Status: approved

## Problem

A show package holds many audio files and an m3u naming their play order
(`package/playlist.m3u` from llama, `broadcast.m3u` from emcee). Some uses —
archiving an aired broadcast, handing someone a single file, auditioning a
whole show — want one mp3 instead of a directory plus a playlist.

## Scope

One standalone script, `scripts/stitch_m3u.py`, that reads an m3u and writes a
single mp3 of its entries concatenated in order, with per-entry ID3 chapters
and file-level tags. Stdlib only; no packaging, no new dependencies, no
integration into the `llama` or `emcee` CLIs. It is a *generic* m3u tool that
merely knows how to take advantage of a llama `manifest.json` when one is
present.

Out of scope: crossfades, gap insertion, loudness normalization, output
formats other than mp3, remote (`http://`) playlist entries, nested m3u
references.

## Interface

```
python3 scripts/stitch_m3u.py PLAYLIST.m3u
        [-o OUT.mp3] [--title T] [--artist A] [--album AL]
        [--bitrate 192k] [--reencode] [--force]
        [--ffmpeg PATH] [--ffprobe PATH]
```

- `-o/--output` defaults to `<playlist-stem>.mp3` beside the playlist.
- The script refuses to overwrite an existing output without `--force`.
- `--title/--artist/--album` override any derived metadata.
- `--bitrate` (default `192k`) applies only on the re-encode path.
- `--reencode` forces the re-encode path even when stream-copy is eligible.
- `--ffmpeg`/`--ffprobe` name the binaries. Each defaults to a PATH lookup.
  If `--ffmpeg` is given without `--ffprobe`, `ffprobe` is looked for in the
  same directory first, then on PATH. A binary that is missing or not
  executable is a startup error naming the flag that would fix it.

Exit status is 0 on success, non-zero on any error; errors print to stderr.

## Pipeline

### 1. Parse the playlist

Read as UTF-8, tolerating a BOM. Skip blank lines and `#` comment lines,
except `#EXTINF:<seconds>,<title>` — its title applies to the next entry.
Entries are file paths: absolute paths are used as-is, relative paths resolve
against the playlist file's own directory. A remote URL, or a playlist with
no entries, is an error.

### 2. Probe every entry

One `ffprobe -v error -print_format json -show_format -show_streams` per
entry, collecting duration, `codec_name`, `sample_rate`, `channels`, and the
embedded `title`/`artist` tags. A missing file, a probe failure, a file with
no audio stream, or a missing duration is a hard error that names the
offending entry.

All probing happens before any encoding: the run either produces a complete
output or produces nothing. A silently shortened broadcast is worse than no
file at all.

### 3. Resolve metadata

If `manifest.json` sits in the playlist's directory and parses as a manifest
with `schema_version >= 3`, derive:

- artist ← `show.artist`
- album ← `"<show.date> — <show.venue>"` (empty parts omitted)
- title ← `"<show.artist> — <show.date>"` (empty parts omitted)
- a map from track basename → `tracks[].title`

Explicit CLI flags always win over derived values. With no manifest and no
flags, title falls back to the playlist's filename stem and artist/album are
omitted.

Per-chapter titles use the first hit in this cascade:

1. the manifest track title for that entry's basename
2. the entry's own embedded `title` tag
3. the `#EXTINF` title
4. the filename stem

Entries absent from `manifest.tracks` — emcee's `dj-audio/` clips in a
`broadcast.m3u` — therefore chapter under their stem (`set-1-intro`).

### 4. Choose a route

Stream-copy is used when every entry is `codec_name == "mp3"` with an
identical sample rate and channel count across all entries; otherwise the
script re-encodes. `--reencode` forces re-encoding. The chosen route is
printed so the operator knows whether the output is a lossless splice.

Copy route:

```
ffmpeg -i <concat-list> -i <metadata> -map_metadata 1 -c copy -id3v2_version 3 OUT
```

with `-f concat -safe 0` on the list input. The list file uses ffmpeg's
`file '<path>'` syntax with single quotes escaped.

Re-encode route: each entry is a separate `-i`, and a `filter_complex` runs
`aformat=sample_rates=44100:channel_layouts=stereo` on each stream before
`concat=n=N:v=0:a=1`, encoded with `libmp3lame -b:a <bitrate>`. Normalizing
per-stream first is what lets the concat filter accept heterogeneous inputs.

### 5. Chapters and tags

An FFMETADATA1 file carries the file-level tags and one `[CHAPTER]` block per
entry, `TIMEBASE=1/1000`, with start/end from the cumulative probed durations.
It is passed as an extra input with `-map_metadata 1`, identically on both
routes, and written with `-id3v2_version 3` for player compatibility.

### 6. Write atomically

ffmpeg writes `<output>.partial-<pid>` in the output directory; the script
renames it over the destination only after ffmpeg exits 0. On failure the
partial file is removed and ffmpeg's stderr tail is surfaced. Temporary
concat-list and metadata files live in a `TemporaryDirectory` and never in
the output directory.

## Known limitations (documented in the script)

- mp3 stream-copy concatenation is not gapless: encoder delay and padding at
  each join are inherent to the format. The re-encode route removes the
  interior joins but re-encodes already-lossy audio.
- Chapter offsets derive from probed durations, so on the re-encode route they
  can drift a few milliseconds from true positions.

## Structure

A single file, with the pure logic factored into functions that take data and
return data — `parse_m3u`, `can_stream_copy`, `resolve_metadata`,
`build_ffmetadata`, `build_concat_list` — and a thin `main` that wires
argument parsing, probing, subprocess invocation, and the atomic rename. The
pure functions are what the tests exercise directly.

## Testing

`scripts/test_stitch_m3u.py`, with `scripts` appended to `testpaths` in
`pytest.ini` so it runs under the root `pytest -q`.

- Unit: playlist parsing (comments, `#EXTINF` titles, relative/absolute paths,
  BOM, empty playlist, URL rejection); the stream-copy eligibility check
  (uniform mp3 → yes; mixed sample rate, mixed channels, non-mp3 → no);
  metadata resolution (manifest present/absent, flag overrides, the chapter
  title cascade); FFMETADATA rendering (timebase, cumulative offsets,
  escaping); concat-list quoting.
- Binary resolution: `--ffmpeg` given alone finds a sibling `ffprobe`; a
  missing binary raises a clear error.
- End-to-end, `skipif shutil.which("ffmpeg") is None`: generate two `lavfi`
  sine mp3s at *different* sample rates, stitch them, and probe the result —
  duration ≈ sum of inputs, two chapters with the expected titles, tags
  present. A second case with two matching-format mp3s asserts the
  stream-copy route is taken.
