# Tier-A title defects — design

Date: 2026-08-04. Status: approved, not yet implemented.

Three defects in llama's title-resolution path, all of which put wrong or
missing track titles into `manifest.json` and therefore in front of emcee's
scriptwriter and the robot DJ. They are specified together because A3 cannot
be built without the format fix, and the A1 cleaner has to run over A3's
recovered titles.

Companion backlog entries: items **A1** and **A3** of the 2026-08-04 Tier-A
list. **A2 (the setlist parser splitting titles on commas) is deliberately
NOT in this spec** — the comma is load-bearing for a documented real class of
descriptions, so telling a separator comma from a title comma needs its own
measurement pass and its own spec.

## Evidence base

All numbers below were measured on 2026-08-04 against the 2,095 cached
archive.org metadata responses in
`/Users/shawn/projects/llama-setlist-analysis/iacache/`, by calling llama's
**real** `junk.filter_files`, `titles.clean_tag_title`, `titles.is_real_title`
and `jerrybase.is_family_artist` — not a reimplementation. Scripts and raw
JSON are preserved outside the repo under the measuring session's scratchpad
(`work/measure/a1_leading_numbers.py`, `a3_mp3_vs_flac_titles.py`,
`a3_stem_match.py`).

**Standing caveat, applies to every figure here.** That cache is a
`random.shuffle(seed=7)` decade-stratified sample of archive.org *items*,
built by `build_corpus.py`, which does **not** run `select_recording` or any
scoring. Sibling recordings of one performance appear as unrelated rows.
So these are rates over *cached items*, not over *shows llama would actually
pick*, and nothing here describes llama's tape-selection behaviour.

## Part 1 — A1: track-number prefixes reach the DJ

### Problem

`titles.clean_tag_title` strips an identifier prefix (`gd73-06-10d1t04 `) and
a file extension, but nothing strips a bare leading track number. Shipped
examples seen in production: `01 Intro - Ramona`, `02 Two Points For
Honesty`, and the double-numbered `10. 10 Satellite`. These land in
`manifest.json` verbatim and are read aloud.

Measured: **201 of 2,053 items (9.8%) and 1,831 of 39,009 tracks (4.7%)**
still carry a leading number after today's `clean_tag_title`.

### Why it cannot be fixed at the string level

`01 Intro - Ramona` and `100 Years` are indistinguishable in isolation. What
separates them is the recording they sit in: an enumerated tape numbers
essentially every track, whereas a real numeric title is one lone numbered
file among unnumbered ones.

The corpus splits almost perfectly along that line:

| shape | items | prefixed tracks |
|---|---|---|
| enumerated tape (>=3 numbered, >=80% coverage) | 94 | 1,708 |
| **exactly one** numbered file | 99 | 99 |
| everything else (the ambiguous band) | 8 | 24 |
| **total** | **201** | **1,831** |

The 99 lone cases are real song titles without exception — `100 Years`
(ten separate Bruce Hornsby items), `200 More Miles`, `300 Pounds Of Joy`,
`20 Eyes`, `2 x 4`, `40 Miles From Denver`, `18 Wheels Of Love`,
`3 Dimes Down`.

**A rejected classifier, recorded so it is not re-derived.** The measuring
pass first classified items by whether their numbers form a `1..k` run, then
relaxed that to "any internally-consecutive run" and found it reclassified
**all 162** strict failures as clean numbering. That relaxation is invalid: a
run of *one* number is trivially consecutive, so the check passes exactly the
population it needed to reject. It is the metric-blind-at-its-own-boundary
shape this project has hit before. Coverage fraction, not run-consecutiveness,
is the discriminator.

### Design

`clean_tag_title(raw)` is unchanged — it stays pure and per-string. Add a
list-level sibling in `titles.py`:

```python
clean_tag_titles(kept_files: list[dict]) -> list[str]
```

It applies `clean_tag_title` to each file's tag title as today, then decides
whether the recording is an **enumerated tape** and strips leading numbers
only if it is.

- **Leading track number**: `^(\d{1,3})(?!\d)([.)\-:]?)\s+(?=\S)`. The 1–3
  digit bound with `(?!\d)` is load-bearing — it is what makes
  `1952 Vincent Black Lightning` and a bare `2001` unreachable by this rule at
  all, and it must not be widened to `\d+` without re-measuring.
- **Enumerated-tape gate**: at least **3** kept files carry a leading number
  **and** at least **80%** of kept files do. Both arms required.
- **Double numbering** (`10. 10 Satellite`): strip a *repeated identical*
  leading number as one unit. Do **not** loop the single strip — a second pass
  would take a legitimate `10 Satellite` down to `Satellite`.

All four call sites already hold the kept file list, so this needs no new
plumbing: `gather.py:78`, `gather.py:522`, `select_recording.py:70`, and
`resolve_titles` in `titles.py`.

### Measured outcome

Of the 201 affected items, 96 (1,719 tracks) are genuine enumerated tapes and
105 (112 tracks) carry a real numeric title.

- **Cleans 94 of the 96 enumerated tapes** — 1,708 of their 1,719 tracks.
- **Protects all 105 real-title items** — the 99 lone-number ones plus 6 of
  the 8 in the ambiguous band. Among them `52 Vincent Black Lightning`, a
  taper's `1952` with the `19` dropped, which any unconditional strip would
  mutilate.
- **Misses 2 enumerated tapes** (11 tracks): `Fishbone1992-09-18.Warfield_SF`
  (disc 2 numbered 8–16, 9 of 15 files = 0.60 coverage) and `gd2024-06-20`
  (2 of 18). Both are **false negatives** — the prefix survives, which is
  today's behaviour. The gate mutilates no real title anywhere in the corpus.

That asymmetry is deliberate and matches the project's standing bias: a
surviving prefix is visible and ugly, a mutilated title is silent and ships.

### Not observed, designed for anyway

`A1.4` searched the whole corpus for the `10. 10 Satellite` shape and found
**zero** instances. The handling above exists because the shape was seen in
production, not because this corpus supports it. Record it as *not observed
here*, never as *does not happen*.

## Part 2 — the `FORMAT_BY_AUDIO` exact-match gap

### Problem

```python
FORMAT_BY_AUDIO = {"mp3": "VBR MP3", "flac": "Flac"}
```

`filter_files` matches this by **exact string equality** (`junk.py:32`). The
real format strings on audio files across the corpus are:

| format string | files |
|---|---|
| `VBR MP3` | 41,386 |
| `Ogg Vorbis` | 30,367 |
| `Flac` | 29,084 |
| `24bit Flac` | 7,971 |
| `Shorten` | 4,086 |
| `WAVE` | 696 |
| `192Kbps MP3` | 1 |

So `24bit Flac` and `Shorten` are invisible to llama. Two consequences:

1. **A live defect independent of A3**: a user who sets
   `audio_format = "flac"` gets **zero** kept files on a 24-bit-only item
   (385 such items in the corpus), so `has_format` is false, scoring
   penalises the recording, and llama effectively cannot select it. Masked
   today only because the default is `mp3`.
2. It is why `gd1971-02-23` — one of the five known-affected identifiers —
   did not flag during measurement: its lossless files are `24bit Flac`, so
   `filter_files` never saw a FLAC sibling at all. **382 of the 609
   corpus-wide "no FLAC available" items actually have lossless** under that
   other string.

### Design

`filter_files` takes `want_format: str | Sequence[str]` and treats a sequence
as an **ordered preference list**: try each format in turn, first one yielding
a non-empty audio set wins.

```python
FORMAT_BY_AUDIO = {"mp3": ("VBR MP3",), "flac": ("Flac", "24bit Flac")}
```

**Preference-ordered, never a union.** 5 corpus items carry both `Flac` and
`24bit Flac`; a union would keep every track of those items twice. A bare
string must keep working, since `filter_files`'s default and its existing
callers pass one.

`Shorten` is deliberately **not** added to the delivery formats. It is a
different codec with a different extension, and adding it changes what llama
downloads and ships — beyond the scope of this defect. It *is* used as a
title-recovery source in Part 3, where nothing is downloaded.

`192Kbps MP3` (one file corpus-wide) is not worth handling.

## Part 3 — A3: recover titles from the lossless sibling

### Problem

On the default `audio_format = "mp3"`, the chosen VBR MP3 derivative
sometimes carries **zero** embedded titles while the sibling lossless files of
the *same item*, for the *same tracks*, are fully tagged. `resolve_titles`
then falls through to `unresolved track titles` and the show is held.

Measured: **166 of 1,444 items (11.5%)** that have both formats kept show mp3
title coverage below 0.5 with lossless coverage at or above 0.9.

Worth stating precisely, because it changes how much to trust the fix: llama
reads **no tags itself**. Every `title` comes from archive.org's metadata API,
where archive.org extracted it server-side. (`mutagen` is a dependency but is
used only in `audio.py:tag_audio` to *write* tags onto packaged files.) So
"the mp3 has no titles" is a fact about archive.org's derivative pipeline —
it built the VBR MP3 from the lossless original and did not carry the tags
across — not about the bytes. The lossless sibling is genuinely the better
source.

### Design

A title-recovery step in `gather`. When the delivered-format kept set has poor
title coverage and a lossless sibling set **in the same item** has good
coverage and a filename-stem bijection with it, lift the titles across.

**Trigger, stated explicitly so it is not re-guessed at implementation time.**
Let `title_fraction` be the fraction of a kept set whose `clean_tag_title`
passes `is_real_title` — the same quantity `select_recording.py:70` already
computes. Recover when the delivered set's `title_fraction < 0.5` **and** the
lossless sibling's `>= 0.9`. Recovery is all-or-nothing per recording: either
every track's title comes from the sibling or none does, so a manifest never
interleaves two tag sources.

Those two thresholds are the ones the measurement was run at and were **not
independently swept**; the 166-item population and therefore the 100% figures
below are defined by them. They are a reasonable starting point, not a tuned
optimum — if the implementation wants different values, re-measure rather than
carrying these results across.

- **Source set for recovery** is broader than the delivery set — `Flac`,
  `24bit Flac`, `Shorten` — because recovery reads only metadata strings and
  never downloads those files.
- **Matching is by filename stem** (basename minus extension), not by
  position, and requires a **bijection**: same kept-file count, same stem set.
  Anything short of that declines recovery rather than guessing.
- Recovered titles get `title_source="sibling-format"`, alongside the existing
  `tags` / `setlist` / `sibling` / `unresolved`, so the provenance is visible
  in the manifest rather than laundered into `tags`.
- **A1's cleaner runs over recovered titles too.** Measured: 5 of 2,928
  recovered titles (0.17%) carry a leading number, and all five are genuine
  song titles (`200 More Miles`, `40 Acres And A Fool`, `300 Pounds of Joy >`,
  `40 Miles From Denver`, `2 hits and the Joint Turned Brown`) — so the
  enumerated-tape gate protects them, exactly as in Part 1.

Requires no download, no tag parsing, and no new dependency: both formats'
`title` fields are already inside the single cached `metadata(identifier)`
response. It stays fully offline in tests.

### Measured outcome

- **Perfect stem bijection on 166 of 166** flagged items (0 same-length /
  different-stems, 0 length mismatches).
- **166 of 166 flip** from "no usable titles" to titles that pass
  `is_real_title`.

### Accepted risk, stated not buried

On `LosLobos2007-05-06` the FLAC's own embedded tags are off by one against
its own filenames **in the uploader's source data** — the `d1t01` file is
tagged `One Time One Night` while its filename says `Chuco's Cumbia`.
Recovery would import a real-looking but wrong title there, silently.

This is the same trust already extended to mp3 tags, and structure alignment
plus jerrybase anchoring remain downstream. But **"usable" is not "correct"**,
and `is_real_title` cannot tell the difference. Accepted, not mitigated.

A second population is recorded but out of scope: **15 items where FLAC
titles are worse than mp3**. Not enumerated or spot-checked. Do not assume
lossless is uniformly the safer source without looking at these.

## Testing

- **A1 protection is pinned by name.** Real titles from the measured corpus —
  `100 Years`, `200 More Miles`, `20 Eyes`, `2 x 4`,
  `52 Vincent Black Lightning` — asserted to survive intact in a
  single-numbered-file recording.
- **A1's two known false negatives are pinned too** (`Fishbone1992-09-18`'s
  0.60-coverage partial numbering, `gd2024-06-20`'s 2-of-18). If someone later
  widens the gate, that is then a deliberate, visible change rather than a
  silent one.
- **The `\d{1,3}` bound is pinned** by a test asserting
  `1952 Vincent Black Lightning` is untouched even inside an enumerated tape.
- **Format preference order is pinned** by a fixture item carrying both `Flac`
  and `24bit Flac`, asserting each track is kept exactly once.
- **`24bit Flac`-only selection is pinned** — an item whose only lossless is
  24-bit must yield a non-empty kept set for `audio_format="flac"`.
- **Recovery declines without a bijection** — differing stems or counts must
  produce `unresolved`, not a positional guess.
- Recovery tests run offline against existing captured fixtures; no new
  network fixture is needed.

## Out of scope

- **A2**, the comma-splitting parser defect — its own spec.
- Adding `Shorten` to the delivery formats.
- The 15 "FLAC worse than mp3" items.
- Verifying recovered titles against setlist evidence.
- Anything about tape *selection*: the measurement corpus structurally cannot
  speak to it.
