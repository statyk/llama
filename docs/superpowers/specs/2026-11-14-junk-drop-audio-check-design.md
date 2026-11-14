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
(3) the rollout's station-side marking, which must see the check's holds before it marks.
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

The classifier is built as a **reusable module** (per-window labels and summary measures for
any audio file). The junk check is its first consumer; later ones (short-kept crowd check,
junk among untitled tracks, adjudicator evidence) are out of scope here.

## Goals

1. Every junk-title drop (reason `junk title`) is checked by audio before it ships.
2. A drop that sounds like music holds the show, with a flag naming the track and the
   measured numbers so the operator can triage from the held list alone.
3. A drop that sounds like junk proceeds as today, silently.
4. A drop that could not be checked proceeds as today, recorded as unchecked, so a later
   pass can find and re-check it.
5. The existing ~960 drops are checked before the rollout marks or re-voices anything, and
   checked-as-music shows leave the rollout wave for triage.
6. Remove `silence` from the junk-title vocabulary (operator decision 2026-11-14: every
   "Silence" drop in the corpus is the Gomez song "Silence", 4 tracks; no combination titles
   use it).

## Non-goals

- Restoring a dropped track automatically, or retitling anything.
- Checking tracks that are not junk-title drops (short-kept files, untitled tracks, the
  older junk filter's drops). v1 stores verdicts for junk-title drops only.
- Telling house music from live performance (not possible from audio; such a track holds).
- Detecting songs under ~2 minutes (they cannot meet the run bar; they drop as today).

## Anti-goals (a failure even if it "works")

- The check ever drops, or keeps out, a track the current code would keep.
- A check failure ever blocks a show or turns into a hold (decided: degrade to today).
- Hold volume that swamps the operator: the budget is **a few dozen shows** across the
  backlog. Measured: 22 (see Calibration).
- A heavyweight dependency (TensorFlow, PyTorch, a 300 MB model) in the signed binary.

## Decisions (operator's)

- **Hold on music, never restore.** (2026-11-14)
- **Runs on every new show**, in the binary; a dependency is acceptable only if llama
  degrades gracefully without it; bundling preferred if the trade-offs are small. (Bundling
  is the outcome: see Packaging.)
- **On failure, drop as today**, recorded unchecked. (2026-11-14)
- **Gather may download the dropped tracks** to listen to them, then discard the audio.
- **Drop `silence`** from the vocabulary.
- **mmj-2006-12-29 "Intro"** ("Ave Maria", house or live, unclear): operator leans drop; the
  chosen threshold drops it. That is the calibration's boundary case.

## The classifier (decided by the spike)

**Model: YAMNet** (Google, AudioSet 521 classes, ~3.7M params, 16 kHz mono input,
0.96 s frames at 0.48 s hop). PANNs CNN14 and MS-CLAP were tested and rejected: CLAP's text
prompts labelled bluegrass songs "tuning"; PANNs added precision at 0.5 but YAMNet alone at a
tighter music bar matched or beat it (Calibration), so PANNs' 320 MB PyTorch model is not
needed.

**Measure, per track:**
1. Decode to 16 kHz mono; run YAMNet; average its frame scores over consecutive **10 s
   windows** (last partial window dropped; a track under 10 s is one padded window).
2. A window is **musical** when (`Music` > **0.6** OR max(`Drum kit`, `Drum`, `Percussion`,
   `Snare drum`, `Bass drum`, `Drum roll`) > **0.3**) AND `Speech` < **0.3**.
3. `run` = longest unbroken stretch of musical windows, in seconds; `frac` = share of
   windows that are musical.
4. **Verdict `music`** when `run` >= **120 s** AND `frac` >= **0.70**; otherwise `junk`.
   The drum clause exists for GD "Drums"; the speech clause is what separates tuning (mic
   talk) and house music under crowd chatter from songs.

These constants are fixed in code, not config. They were chosen on the labelled data below;
changing them is a recalibration with evidence, not a tweak.

**Known limits:** a song under 2 min can't be detected; unstructured Space reads as music
in 7 of 12 known Space/Drums tracks under the 0.5 bar and 5 of 12 under 0.6 (only matters if
Space is mislabelled junk, which drops today anyway); house music long enough to clear the bar
holds.

## Calibration (spike, 2026-11-14)

All numbers from the spike in the session scratchpad; the scripts, label files and per-track
tables are to be committed under the evidence directory.

- **Round 1** (blind, shuffled, scores hidden): 51 junk-title drops labelled by the operator
  (15 longest, 12 short <2 min, 12 mid, 12 set-opening intros >3 min) plus 12 ordinary songs
  and 12 GD Space/Drums as known music. 7 song / 44 junk.
- **Round 2**: the 28 further tracks YAMNet at the 0.5 bar flagged. 13 song, 13 junk,
  2 unsure.
- **Full population**: 933 of the 960 drops had a station copy (27 have none).

| Rule | Songs caught (of 19 drop-songs) | False alarms | Shows held (of 933 drops) |
|---|---|---|---|
| YAMNet, Music > 0.5 | 19 | 13 (+2 unsure) | 31 |
| YAMNet + PANNs speech/drum | 16 | 3 | 17 |
| **YAMNet, Music > 0.6 (chosen)** | **19** | **4 (+2 unsure)** | **22** (7 already size-held) |

Every track the chosen rule holds across the 933 was labelled by the operator, so its hold
count and false-alarm count are measured, not estimated. Its recall is measured only on
tracks the 0.5 rule flagged (a song both rules miss was never labelled). The 0.6 bar was
picked on the same labels it is scored on (mild overfit expected); the operator's triage of
the first held lists is the out-of-sample check.

Speed: YAMNet + PANNs + CLAP together ran 5-15 s per track on an M4 CPU; YAMNet alone is a
fraction of that.

## Where it runs and what it writes

**New shows (gather).** Immediately after the junk-title drop chooses its drops, gather
obtains each dropped file's verdict:
1. From the show's **verdict cache** if present for this exact file (identifier, filename,
   and archive.org md5 or size), else
2. by downloading the file from archive.org (the normal `IAClient.download_file` path, to a
   temp location, deleted afterwards), decoding, and classifying, then writing the verdict to
   the cache.

**Effect of each verdict:**
- `music`: a hold flag is added. Wording is the builder's; it must name the track
  (position/filename and its title), its duration, and the two numbers, e.g.
  `d2t09 "Crowd/Tuning" (9:19) sounds like music: 9:10 continuous, 98% music`. The drop
  itself still happens in the computed list (the show is held, so nothing ships); the track
  list is not otherwise changed.
- `junk`: nothing changes.
- `unchecked`: nothing changes except the record.

**The verdict cache** is a per-show file (name the builder's, e.g.
`<show>/audio-check.json`) holding, per checked file: identity (as above), verdict, `run`,
`frac`, model id/version, threshold version, checked-at. A verdict computed under a
different model or threshold version is stale and recomputed. Failures are not cached as
verdicts (so a later run retries), but the drop's record says unchecked.

**The manifest.** Each `dropped_tracks` entry records the check's outcome (`music` /
`junk` / `unchecked`, plus `run` and `frac` when checked). **Constraint:** the manifest must
stay readable by the emcee, transmitter and antenna already deployed. The builder verifies
how each reads `dropped_tracks` (strictness on unknown keys) and chooses placement
accordingly (new optional fields on the entry if all tolerate them; otherwise somewhere they
ignore). Shows that are held don't package, so a `music` outcome appears in a manifest only
after the operator resolves the hold.

**Its own overrule (my call).** The music hold is a distinct hold kind with its own
overrule key, not the size breaker's `junk-drop` kind: overruling a size hold on a file must
not release a music hold on the same file, or the reverse (7 of the 22 measured shows carry
both). Adjudicator bar `never`, like the size hold: only the operator clears it.

**Failure = unchecked**, for any of: the file can't be fetched (download error, station copy
missing); it can't be decoded (corrupt, truncated, or not MP3/FLAC); the model or runtime
fails to load or run. The failure reason goes in the run's notes. Never a hold, never a raise
that stops gather.

## Replay and the rollout (existing drops)

Replay (`replay_holds.py`, `CacheOnlyIA`) is offline and refuses downloads, so in replay
the check can only read the verdict cache: a drop with no cached verdict is `unchecked`.
`compute_gather` reads only `overrides.json` from its workspace, and replay's
`compute_legs` gives it a scratch directory holding only that file, so the verdict cache
must be passed in explicitly or copied into the scratch workspace; otherwise replay and
reapply never see it. The same holds for `reapply`, which also runs through `CacheOnlyIA`.

Therefore the rollout gains one step **before its replay arm** (Appendix A of
`docs/superpowers/plans/2026-11-14-junk-tag-drop.md`): a pre-pass that fills each library
show's verdict cache from the **station copy** of each dropped file (library audio is purged
after delivery; the station holds all delivered audio, all MP3), falling back to download
where there is no station copy. With caches filled, the replay arm computes the check's holds
like any other hold, and the existing list/mark machinery leaves held shows out of the wave.

The pre-pass is read-only on the station and touches only the verdict caches in the library.
It must be resumable and must not hold the station lock longer than needed per show (builder
detail). Whether it is a `llama` subcommand or a `scripts/` tool is the builder's call; a
`llama` command is preferable because gather already needs the same code.

**Unchecked drops on the voiced path (operator, 2026-11-14).** "Drop as today on failure"
holds for new shows and for unvoiced rollout members. On the rollout's voiced path it does
not: (a) the pre-pass **fails loudly** if the classifier cannot load (no silent all-unchecked
run from a worktree venv missing the runtime); (b) a **voiced** member with any `unchecked`
drop is **set aside** from the re-voice wave (`approval`/`recheck` refuse or list it
separately; the builder picks where, `list` being the earliest point that can) until its
drops are checked. Unvoiced members with unchecked drops proceed as today.

**Marking (operator, 2026-11-14).** A show the check holds is still a rollout member and is
**marked like every other member** (an unvoiced station copy goes off air until triage, as
size-held members do today). The check's hold reaches the list as a held drop, alongside the
size test, including for needs-llm rows whose drops come from the current `show.json` plan
(those must consult the verdict cache too).

The rollout runbook is updated: the pre-pass step, and the expected held count (~22 shows,
7 of them already size-held) as the acceptance check against this evidence.

## Packaging

Bundled in the llama signed binary (macOS and Linux builds, PyInstaller):
- the YAMNet model as a single file (~4 MB) in a format a small runtime executes (TFLite or
  ONNX), **including its log-mel front end**, or with the front end reimplemented in numpy;
- a small inference runtime (e.g. `onnxruntime` or LiteRT, the builder's choice, proven to
  build into both binaries);
- numpy;
- an MP3 + FLAC decoder library (e.g. `soundfile`/libsndfile or `miniaudio`).

No TensorFlow, no PyTorch, no ffmpeg. The builder must show the bundled classifier
reproduces the spike's per-track verdicts on the labelled set (all 79 operator labels + 24
known-music controls) and the spike's population verdicts on the 933: an exact match is not
required (resampler/decoder differences) but any verdict flip is listed and justified.
Binary size growth is reported.

**Pass bar for the reproduction (my call, 2026-11-14):** any of the 19 operator-labelled
drop-songs flipping music -> junk is a blocker (back to recalibration with evidence, not a
written excuse); the population hold count must land within 22 +/- 3 shows; every other
flip is listed for the operator to look over. The runtime/front-end choice is therefore a
gate in the plan with a fallback branch (e.g. TFLite with the built-in front end, else ONNX
plus a numpy log-mel), not a single validation step.

Graceful degradation: if the runtime or model can't load (e.g. a platform wheel is missing
in a dev install), every check is `unchecked` and llama otherwise runs unchanged.

## Considered and declined

- **Delivering dropped tracks' audio** (out of the track list and m3u, listed only in
  `dropped_tracks`) for a cheap restore and station-side re-checks: declined by the
  operator 2026-11-14. The expensive undo is the re-voice, which this would not avoid; the
  dropped audio is not delivered.

## Evidence

Committed with this spec under `docs/superpowers/2026-11-14-audio-check-evidence/`: the
spike scripts, sample lists, both label files, and the per-track tables (round 1, round 2,
population verdicts under the three rules). The audio is not committed.

## Left to the builder

Flag wording; verdict-cache file name and schema details; manifest field placement within
the constraint; the runtime and decoder choice; how the YAMNet front end is carried; where in
`compute_gather` the call sits (after the drop decision); temp-file handling; the pre-pass
command's name and form; test layout (tests stay offline: a fake classifier for pipeline
tests, plus a small committed non-audio fixture or a synthetic tone for a real-model smoke
test if one is feasible without committing audio).
