# Junk-drop audio check: design

Status: draft for review, 2026-11-14. Follows `2026-11-13-junk-tag-drop-design.md`
("Planned follow-up"). Spike evidence: `docs/superpowers/2026-11-14-audio-check-evidence/`
(to be committed with this spec; see "Evidence").

## Review mode and stakes

**Review mode: Opus.** (Operator default from the handoff; second reviewer and final branch
reviewer on Opus.)

**Stakes.** The junk-title drop (merged, release held) removes ~960 tracks from ~700
delivered shows, 150 of them voiced (96 on paid Voxtral). Once the rollout re-voices a show,
undoing a wrong drop costs another `--replace-voiced` and a second paid voicing. This check
is the only thing standing between a mislabelled song and that irreversible path.
**Strict surfaces:** (1) any path where the check's failure or absence could *remove* a
track that would otherwise have been kept, or change a kept track list (it must never do
either); (2) the manifest contract read by already-deployed emcee, transmitter and antenna;
(3) the re-voice path (`approval`/`recheck` and `--replace-voiced`), which must see the
check's holds and unchecked drops live.
Everything else (scores, notes wording, timing) is ordinary.

## Intent

The junk-title drop trusts archive.org titles: a file titled "tuning", "crowd", an edge
"intro"/"outro" is dropped. The operator listened to the candidates and found the title is
often what's wrong: a full song tagged "tuning" or "crowd", usually from bad archive.org data
(often with neighbouring tags off by one, sometimes way off), occasionally from our own
mistake. The size breaker (2-of-3) catches the long ones only.

This check **listens to every track the junk-title drop is about to remove**. If it hears a
song, it **holds the show** for the operator. It never restores the track itself: a song
under a junk label usually means the neighbouring labels are wrong too, which needs a human.

It runs on **every new show** (inside llama, shipped in the signed binary) and, once, over
the existing drops before the junk-drop rollout.

The classifier is a small **separate module**, its API kept to what the junk check needs:
per-window scores in, `run` and `frac` out, a verdict. Other possible uses (short-kept crowd
check, junk among untitled tracks, adjudicator evidence) are out of scope and not designed
for here.

## Goals

1. Every junk-title drop (reason `junk title`) has an audio check attempted before it ships;
   when the attempt fails, the reason goes in the show's gather notes (`notes.json`).
2. A drop that sounds like music holds the show, with a flag naming the track and the
   measured numbers so the operator can triage from the held list alone.
3. A drop that sounds like junk proceeds as today, silently.
4. A drop that could not be checked proceeds as today, recorded as unchecked.
   `llama redo <show> --from gather` re-checks it (online), and `llama status` counts the
   shows carrying such drops (see Packaging). A dedicated re-check sweep is backlog.
5. The existing ~960 drops are checked before the rollout marks or re-voices anything, and
   checked-as-music shows are kept out of re-voicing for triage.
6. Remove `silence` from the junk-title vocabulary (operator decision 2026-11-14: every
   "Silence" drop in the corpus is the Gomez song "Silence", 4 tracks; no combination titles
   use it). The change restores those 4 tracks and changes no other kept list (no library
   `show.json` yet records a junk-title drop).

## Non-goals

- Restoring a dropped track automatically, or retitling anything.
- Checking tracks that are not junk-title drops (short-kept files, untitled tracks, the
  older junk filter's drops). v1 stores verdicts for junk-title drops only.
- Telling house music from live performance (not possible from audio; such a track holds).
- Detecting songs under ~2 minutes (they cannot meet the run bar; they drop as today).

## Anti-goals (a failure even if it "works")

- The check ever drops, or keeps out, a track the current code would keep.
- A check failure ever blocks a new show or turns into a hold (decided: degrade to today;
  the rollout's set-aside of unchecked members is not a hold, see Replay and the rollout).
- Hold volume that swamps the operator: the budget is **a few dozen shows** across the
  backlog. Measured: 28 (see Calibration).
- A heavyweight dependency (TensorFlow, PyTorch, a 300 MB model) in the signed binary.

## Decisions (operator's)

- **Hold on music, never restore.** (2026-11-14)
- **Runs on every new show**, in the binary; a dependency is acceptable only if llama
  degrades gracefully without it; bundling preferred if the trade-offs are small. (Bundling
  is the outcome: see Packaging.)
- **On failure, drop as today**, recorded unchecked. (2026-11-14)
- **Gather may download the dropped tracks** to listen to them, then discard the audio.
- **Drop `silence`** from the vocabulary.
- **One rule for every junk title class** (2026-11-14). Per-class rules were considered and
  declined: no class has a cheap gain, and catching the marginal misses roughly doubles holds.
- **mmj-2006-12-29 "Intro"** ("Ave Maria", house or live, unclear): operator leans drop; the
  chosen rule drops it (run 110 s, 64%). That is the calibration's boundary case.

## The classifier (decided by the spike)

**Model: YAMNet** (Google, AudioSet 521 classes, ~3.7M params, 16 kHz mono input,
0.96 s frames at 0.48 s hop). PANNs CNN14 and MS-CLAP were tested and rejected: CLAP's text
prompts labelled bluegrass songs "tuning"; PANNs added precision at a loose music bar but
YAMNet alone at a tighter bar matched or beat it (spike evidence), so PANNs' 320 MB PyTorch
model is not needed.

**Measure, per track:**
1. Decode straight to 16 kHz mono and run YAMNet over the whole track. Split its frame-score
   sequence (F frames) into n = max(1, floor(duration_s / 10)) equal consecutive bins, bin k
   being frames [floor(k*F/n), floor((k+1)*F/n)), and average each bin: these are the
   **10 s windows**. No partial window is dropped.
2. A window is **musical** when (`Music` > **0.55** OR max(`Drum kit`, `Drum`, `Percussion`,
   `Snare drum`, `Bass drum`, `Drum roll`) > **0.3**) AND `Speech` < **0.3**.
3. `run` = longest unbroken stretch of musical windows, in seconds; `frac` = share of
   windows that are musical.
4. **Verdict `music`** when `run` >= **120 s** AND `frac` >= **0.60**; otherwise `junk`.
   The drum clause exists for GD "Drums"; the speech clause is what separates tuning (mic
   talk) and house music under crowd chatter from songs.

These constants are fixed in code, not config. They were chosen on the labelled data below;
changing them is a recalibration with evidence, not a tweak. A different decoder or
resampler than the spike's is expected to move tracks near the bar by a window.

**Known limits:** a song under 2 min can't be detected; unstructured Space reads as music
in 7 of 12 known Space/Drums controls under the chosen rule (only matters if Space is
mislabelled junk, which drops today anyway); house music long enough to clear the bar holds.
The chosen rule misses 3 of the 22 known hidden songs, accepted by name (Calibration).

## Calibration (spike, 2026-11-14)

All numbers from the spike; the scripts, label files and per-track tables are committed
under the evidence directory.

- **Labels.** Three blind labelling rounds by the operator (shuffled, scores hidden):
  round 1, 51 junk-title drops plus 24 known-music controls (12 ordinary songs, 12 GD
  Space/Drums); round 2, the 28 further drops a `Music` > 0.5 rule flagged; round 3, 40
  tracks (19 near the bar, the one never-heard Radiators track, 20 random `junk` verdicts of
  at least 60 s). 142 distinct operator-labelled files (one file was labelled twice), plus 3 further Gomez "Silence" tracks known to be songs: 145 tracks in the labelled set. One operator mislabel was corrected
  (philleshandfriends-2006-02-11 "Crowd" is crowd).
- **Pairing.** Evidence pairs each drop to its station file by track index and title (and
  duration): 933 distinct files of the 960 drops, no duplicates (27 drops have no station
  copy). `population2.tsv` holds these verdicts; it supersedes `population.tsv`, whose
  title-and-duration pairing mis-paired 18 drops onto same-titled tuning tracks.
- **Hidden songs.** 22 songs hide under junk titles among the drops (the 4 Gomez "Silence"
  tracks are excluded: the vocabulary change restores them).

All rules at `Music` > 0.55 unless noted; shows held are distinct shows across the 933.

| Rule | Songs caught (of 22) | False alarms (labelled junk) | Shows held |
|---|---|---|---|
| 2 min / 70% | 18 | 7 | 25 |
| **2 min / 60% (chosen)** | **19** | **9** | **28** (8 already size-held) |
| 90 s / 60% | 21 | 27 | 49 |
| `Music` > 0.6, 2 min / 70% | 16, and misses 2 of the 4 Gomez songs | 4 | 22 |

- Every track the chosen rule flags across the 933 is operator-labelled (19 song, 9 junk,
  2 unsure), so its hold count is measured, not estimated.
- **Miss audit.** The 20 random `junk` verdicts (round 3) contained no song (19 junk,
  1 unsure). The sample is small: it bounds misses loosely and does not prove there are none.
  The rule was picked on the same labels it is scored on, so the operator's triage of the
  first held lists remains the out-of-sample check.
- **Accepted misses (operator, 2026-11-14):** smashingpumpkins-2007-10-04 "Intro" (a
  recorded intro track; marginally better kept); greenskybluegrass-2014-07-17 "intro" (band
  jam then intro; good to keep, not critical); radiators-1996-02-17 D3T01 "Tuning" (solo
  piano set-opener; its show is held anyway by D1T01/D2T01).
- False alarms are mostly house or walk-on music on intros and outros, and long Dead tuning
  jams.
- Loudness normalisation before YAMNet was tested and changed little; it is not used.

Speed: YAMNet + PANNs + CLAP together ran 5-15 s per track on an M4 CPU; YAMNet alone is a
fraction of that.

## Where it runs and what it writes

**New shows (gather).** Immediately after the junk-title drop chooses its drops, gather
obtains each dropped file's verdict:
1. From the show's **verdict cache** if it holds a current verdict for this source file, else
2. by downloading the file from archive.org (the normal `IAClient.download_file` path, to a
   temp location, deleted afterwards), decoding, and classifying.

`compute_gather` stays write-free: it receives an injected checker (a verdict-cache reader
plus an optional fetch-and-classify capability) and returns any newly computed verdicts in
its result; `run_gather` writes them to the cache. In replay and reapply the checker has no
fetch capability (cache-only) and never calls `CacheOnlyIA.download_file`.

**Effect of each verdict:**
- `music`: a hold flag is added. Wording is the builder's; it must name the track
  (position/filename and its title), its duration, and the two numbers, e.g.
  `d2t09 "Crowd/Tuning" (9:19) sounds like music: 9:10 continuous, 98% music`. The drop
  itself still happens in the computed list (the show is held, so nothing ships); the track
  list is not otherwise changed.
- `junk`: nothing changes.
- `unchecked`: nothing changes except the record.

**Where the outcome is recorded.** Each drop's outcome (`check`: `music` | `junk` |
`unchecked`; `run`; `frac`; and for `unchecked` a short `check_error`) is written on the
drop's `excluded_files` row in `show.json`, carried in `JunkDrop`, in the replay arm rows'
`junk_drops`, and into the manifest's `dropped_tracks` entries as new optional fields.

**The verdict cache** is a per-show file (name the builder's, e.g.
`<show>/audio-check.json`) holding, per checked file: identity, verdict, `run`, `frac`,
version, checked-at.
- **Identity is the source file:** identifier, source filename, and the archive.org metadata
  md5 (from cached metadata). Never the station file's bytes, name or size: station files are
  renamed `NN - <title>.mp3` and re-tagged by package, so they never match archive.org. A
  station file is only the audio to decode.
- **Version** is a code constant: the sha256 of the bundled model file plus a constants
  version string. Reading a cached verdict is pure JSON and never loads the runtime.
- **Stale verdicts.** A cached verdict whose version differs is stale. Online (gather,
  redo) it is recomputed. Cache-only (replay, reapply) it is **used as stored**: it is still
  a measurement of that audio, and this keeps a later recalibration from silently erasing a
  music hold. A missing entry in cache-only mode is `unchecked`.
- Writes are atomic (the workspace's `atomic_write_text`). An unreadable cache file makes
  every drop in that show `unchecked` with a note; the pre-pass rewrites it.
- Failures are not cached as verdicts (so a later run retries), but the drop's record says
  unchecked.
- The cache file is one of replay's `input_digests`, so reapply's "inputs changed" guard
  sees a cache that moved after the arm.

**The manifest.** The new optional fields on `dropped_tracks` entries are safe for the
deployed readers: emcee (scriptwrite, `package_io`), transmitter (`site.py`) and antenna
(through transmitter's projection) all read the entries as raw dicts and ignore unknown keys,
and `dropped_tracks` is outside `station_mark.COMPARED`. Shows that are held don't package,
so a `music` outcome appears in a manifest only after the operator resolves the hold.

**Its own overrule (my call).** The music hold is a distinct hold kind, not the size
breaker's `junk-drop` kind. Its flag has a fixed, unique prefix (not starting with the size
hold's prefix) and is appended after `renumber_text`, as `hold_flag` is. It gets an
`overrules._PATTERNS` entry keyed on the **filename only** (so the measured numbers in the
text never enter the key), its own kind, `OVERRULE_BAR` = `never` (only the operator clears
it), and a `replay._FAMILIES` entry. `_clear_hold` records an overrule for every current
flag at once, so one triage action clears both holds on a show carrying both (8 of the 28
measured shows); the separate key matters for carried-over overrules, so that a later
re-gather does not let an overrule of one hold release the other.

**Failure = unchecked**, for any of: the file can't be fetched (download error; in the
pre-pass, no pairable station copy and the archive.org fetch fails); it can't be decoded
(corrupt, truncated, or not MP3/FLAC); the verdict cache is unreadable; the model or runtime
fails to load or run. The reason goes in the show's gather notes (`notes.json`). For a new
show this is never a hold, never a raise that stops gather.

## Replay and the rollout (existing drops)

Replay (`replay_holds.py`, `CacheOnlyIA`) is offline and refuses downloads, so in replay
and reapply the injected checker is cache-only: a drop with no cached verdict is
`unchecked`, and a stale one is used as stored.

Therefore the rollout gains one step **before its replay arm** (Appendix A of
`docs/superpowers/plans/2026-11-14-junk-tag-drop.md`): a **pre-pass** that fills each
library show's verdict cache. Whether it is a `llama` subcommand or a `scripts/` tool is the
builder's call; a `llama` command is preferable because gather already needs the same code.
- **Input:** every track in the show's current `show.json` whose title matches the
  junk-title vocabulary (any rule A/B/C pattern, ignoring the position conditions), plus every
  drop in the needs-llm `show.json` plan. This is a superset of what the arm can drop.
- **Audio:** the station copy (library audio is purged after delivery; the station holds
  all delivered audio, all MP3). Station files are paired to source files only through
  `audio_reuse.plan_reuse` (same item, index and title, decoded-length check), against
  `show.json` or `reuse-anchor.json`, as the rollout's `list` already does. A source file it
  cannot pair is fetched from archive.org instead.
- **Locks:** the library **show lock** per show and **no station lock** (it only reads the
  station). It writes only the verdict caches.
- **Failures** (fetch or decode) are recorded per file with their reason, so they are
  distinguishable from never-reached files, and are retried on a re-run. It is resumable.
- It **fails loudly** (non-zero, no partial "success") if the classifier cannot load: no
  silent all-unchecked run from a venv missing the runtime.
- It writes a **summary** under the rollout dir: checked / music / failed-with-reason per
  show.
- Run by the bundled code over the 933, it is also the population reproduction evidence
  (compared to `population2.tsv`; see Packaging).

With caches filled, the replay arm computes the check's holds like any other hold.
`_arm_drops` and `_show_json_plan` carry each drop's outcome. After the arm, `list` prints
the count of arm drops with no cached verdict, and refuses if the arm's music-hold or
unchecked counts disagree with the pre-pass summary.

**Marking (operator, 2026-11-14).** A show the check holds is still a rollout member and is
**marked like every other member** (an unvoiced station copy goes off air until triage, as
size-held members do today). The check's hold reaches the list as a held drop, alongside the
size test, including for needs-llm rows whose drops come from the current `show.json` plan.
It is `approval` and `recheck` (live `needs_review`, plus the check below) that keep held
shows out of re-voicing.

**The re-voice gate.** `recheck` (and `approval`'s listing) re-read the live `show.json`
`excluded_files` rows for each voiced member and refuse any junk-title drop whose `check` is
not `junk`, unless it is a `music` drop with a recorded music-hold overrule. This is the gate
at the irreversible step; it also covers drops that first appear at reapply
(`--with-gather-llm`).

**Unchecked drops in the rollout (operator, 2026-11-14).** Unvoiced
members are re-delivered and then voiced by emcee in ordinary rotation, reaching the same
costly undo. The expected unchecked count after the pre-pass is near zero, so in the rollout
an unchecked drop sets aside **any** member, voiced or not, from reapply and approval until
it is checked. New shows (gather) keep "drop as today".

The rollout runbook is updated with the pre-pass step and its acceptance checks: about 28
shows held by the check (8 of them already size-held, so about 20 new), and the count of arm
drops with no cached verdict at zero except for recorded pre-pass failures.

## Packaging

Bundled in the llama signed binary (PyInstaller) on all four release legs: linux x64, linux
arm64, macOS arm64, windows x64:
- the YAMNet model as a single file (~4 MB) in a format a small runtime executes (TFLite or
  ONNX), **including its log-mel front end**, or with the front end reimplemented in numpy.
  The model file lives in the source tree as package data, so a dev or editable install has
  it, not added only at build time;
- a small inference runtime that works on all four legs (`onnxruntime` has wheels for all;
  LiteRT is an option only if it does too);
- numpy;
- an MP3 + FLAC decoder library (e.g. `soundfile`/libsndfile or `miniaudio`).

If a leg genuinely cannot carry the runtime, that leg ships always-unchecked as a documented
limitation, decided in the plan with the operator, never silently.

No TensorFlow, no PyTorch, no ffmpeg. The runtime is imported lazily, only when a show has a
junk-title drop to check. Binary size growth and startup time are reported.
`packaging/build.py` gains a smoke step on every leg: the frozen binary classifies a
synthetic tone (generated at test time, no committed audio) and the build fails if the
result is unchecked.

**Reproduction.** The bundled classifier must reproduce the spike's verdicts:
- on the 145 labelled tracks, as the pre-release gate;
- on the 933, through the rollout pre-pass itself (above), compared to `population2.tsv`.

An exact match is not required (decoder/resampler differences); every flip is listed.

**Pass bar (my call, 2026-11-14):** a labelled drop-song the chosen rule catches flipping
music -> junk is a blocker (back to recalibration with evidence, not a written excuse),
except an at-bar case where the flip is a single-window shift: smashingpumpkins-2008-08-12
(run 120 s), and any track within one window of 120 s or within 0.05 of 60%. Those are
listed, not blocking. The population hold count must land within 28 +/- 3 shows. Every other
flip is listed for the operator to look over. The runtime/front-end choice is therefore a
gate in the plan with a fallback branch (e.g. TFLite with the built-in front end, else ONNX
plus a numpy log-mel), not a single validation step.

**Graceful degradation.** If the runtime or model can't load (e.g. a platform wheel is
missing in a dev install), every check is `unchecked` and llama otherwise runs unchanged. It
prints one stderr warning per run, not only a notes line, and `llama status` reports the
count of shows with unchecked junk-title drops.

## Considered and declined

- **Delivering dropped tracks' audio** (out of the track list and m3u, listed only in
  `dropped_tracks`) for a cheap restore and station-side re-checks: declined by the
  operator 2026-11-14. The expensive undo is the re-voice, which this would not avoid; the
  dropped audio is not delivered.

## Evidence

Committed with this spec under `docs/superpowers/2026-11-14-audio-check-evidence/`: the
spike scripts, sample lists, the three label files, and the per-track tables (the labelled
rounds and the population verdicts; `population2.tsv`, index-paired, supersedes
`population.tsv`). The audio is not committed.

## Left to the builder

Flag wording and its prefix; verdict-cache file name and schema details; the decoder
choice and, within the packaging constraints, the runtime; how the YAMNet front end is
carried; where in `compute_gather` the call sits (after the drop decision); temp-file
handling; the pre-pass command's name and form; test layout (tests stay offline: a fake classifier for pipeline
tests, plus the synthetic-tone smoke test).
