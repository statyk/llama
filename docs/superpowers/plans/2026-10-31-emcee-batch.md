# emcee batch: script prompt, keep-script, say --tts, voiced_on

Spec and plan in one document: a batch of small changes agreed in chat on
2026-10-31. The operator stood down the presenter-memory idea the same day; do
not build any ledger, used-list or occasional-mention machinery.

**Review mode:** Opus (spec, plan and final branch review).

**Stakes:** the station root holds 2,786 delivered packages, 328 of them voiced,
on a NAS that transmitter reads for live playout. Voiced clips and scripts cost
real LLM and TTS money and some are not reproducible (TTS is non-deterministic,
LLM scripts differ each time). **Strict surfaces:** the voiced_on backfill
(writes to live station manifests); the keep-script failure path (must never
lose a script).

**Priority:** the operator will not bulk re-voice soon (limited Voxtral
credits); new-show voicing comes first. No default path of `emcee run` or
`emcee voice` may change behaviour for a new show beyond the prompt and
`voiced_on`.

**Test command:** create the worktree's own `.venv` first:
`python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
Then `./.venv/bin/python -m pytest packages/emcee -q` per task (Task 6:
`./.venv/bin/python -m pytest packages/emcee scripts -q`), and the full
`./.venv/bin/python -m pytest -q` before the finish. Confirm
`./.venv/bin/python -c "import emcee; print(emcee.__file__)"` resolves inside
the worktree.

**Never during this run:** write to `/Volumes/media/lma-radio/delivered`, or to
`~/.emcee`, except by reading. Task 1's samples work on scratch copies. The real
backfill and any re-voice are the operator's to run after release.

---

## Task 1: scriptwrite prompt (model: Opus implementer; wording needs judgment)

Files: `packages/emcee/src/emcee/prompts/scriptwrite.md`, and
`packages/emcee/tests/test_scriptwrite.py`, whose lines 358 (`Five hard rules`)
and 367-368 (the text just before `Show data`, which the new section moves) pin
the prompt and must change.

**Why.** Measured over the 328 voiced scripts (phrase counts by script,
out of Phil 123 / James Brown 89 / Kurt 48 / Monroe 53 / Prine 15):
- "Earns its airtime" framing (`earn*`, `deserve*`, `why does this`, `why this`):
  80 / 75 / 24 / 35 / 9. The prompt itself says "why this show earns airtime".
- "Listen for" framing (`listen for`, `keep your ears on`, `keep an ear`,
  `want you listening`): 101 / 86 / 42 / 47 / 12. The prompt itself says "what to
  listen for".
- Personal approval (`to my ear`, `I find`, `I like`, `I love`, `my favorite`,
  `I'll be honest`, `I've always`, `soft spot`, `for my money`, `if you ask me`,
  `in my book`, `I'm partial`, ...): 103 / 43 / 35 / 39 / 15. The operator: "a very
  LLM-sounding tendency to note its personal approval of everything".
- "On this show we've got" (Monroe 29, Kurt 15) tracks the timeless rule's
  `say "on this show"`.

Sign-on and sign-off repetition is **fine** ("radio-ish"); do not touch it.
"Why are we playing this" stays a valid thing for an intro to convey, more
subtly.

**Changes, wording as below unless a test against real output shows it fails.**

1. "Five hard rules" becomes "Six hard rules", adding at the end of the list:

   ```
   - Clean on air: this is broadcast radio. Never say a song or album title
     that contains a word you could not say on the air (fuck, shit, bitch,
     cock, motherfucker and the like; "damn", "hell" and "Moby Dick" are fine).
     Do not bleep it, spell it, hint at it or quote part of it. Refer to it in
     your own words, as in "a title I can't say on the air", and leave it out of
     mentioned_songs. Artist names are exempt: the show must be identified.
   ```

2. The "Names are the exception" paragraph gains, as its first sentence's
   qualifier or a closing sentence: the clean-on-air rule outranks it for
   song and album titles.

3. In the Timeless rule, change `say "on this show" for the broadcast and "that
   night" for the concert` to `say "that night" for the concert, and if you must
   refer to the broadcast, "on this show", though never as a way to open a
   lead-in`.

4. A new section after the Names paragraph:

   ```
   Let the show make its own case. A listener stays for specifics from the
   briefing: a story from that tour, what had just changed in the band, what
   happens in the music on this tape. Choosing them IS the reason for playing
   the show, so never argue the point out loud: do not ask or answer why this
   show is on, why it was chosen, or what it earns or deserves.

   Point at the music in passing. Work a moment worth catching into the telling,
   as something that happens, rather than announcing it: no "what to listen
   for", "listen for", "keep your ears on" or "here's what I want you hearing".

   Tell, don't review. Character comes from how you tell a thing, not from
   telling us you approve of it. State the fact and let it land. Across the
   whole script allow at most one or two personal opinions, and make each one
   specific and earned. Do not reach for "I love", "I like", "I find", "my
   favorite", "to my ear", "to my mind", "for my money", "if you ask me", "in my
   book", "I've always", "I'll be honest", "a soft spot for", or their
   equivalents in your character's voice, and do not call things great,
   remarkable or beautiful on the band's behalf: show why instead.
   ```

5. The JSON shape's `set_intros` description: replace `artist, date, venue, why
   this show earns airtime (~60-90 seconds) — then what to listen for` with
   `artist, date, venue, then the specifics that make this show worth hearing
   (~60-90 seconds), running on into the set ahead`. Leave every other clause
   of it alone, and leave the persona block (`persona_style`) alone.

6. The JSON shape's `mentioned_songs`: `<every song title referenced anywhere
   above, other than one you refuse to name, spelled exactly as in the show
   data>`.

**Sample gate.** After the edit, write a script in the session scratchpad, never
the worktree, that copies 6 voiced packages' manifest and briefing files into a
scratch dir there and calls `write_script` with the real presenter and the real
`scriptwrite` provider, script only, no TTS: 2 Phil, 1 James Brown, 1 Monroe,
1 Kurt, 1 Prine, chosen to include one show with a profane title (candidates
exist for Monroe, Kurt, James Brown and Prine; none for Phil) and one
`narration=vague` show if a voiced one exists. Copying the files is the only
contact with the station. Report old and new phrase counts and the path of a
file holding old and new scripts side by side, then **stop Task 1 at the gate**:
the operator reads them, and the wording may change. Six high-tier LLM calls is
the budget; do not iterate on your own.

`persona_style` is byte-locked and stays out of scope, but it says "You may voice
opinions". If the samples show it drives the approval tone, report that at the
gate; the operator may widen the scope.

## Task 2: `emcee voice --keep-script` (Opus; strict surface, adoption needs judgment)

Files: `cli.py`, `process.py`, `audio.py` (clip adoption), `station.py` (the
`kept script` reason).

Reuse `manifest["dj_notes"]` as the script; no scriptwrite call, no LLM unless
a content filter block triggers the existing `_repair`.

- **One parse, first.** `_process_one` parses `dj_notes` once
  (`ScriptNotes.model_validate`), beside the presenter check, before preflight,
  before any `--fresh` unlink and before any clear. A missing or invalid
  `dj_notes` refuses there with nothing touched, an EmceeError naming the
  package: `no script to keep; run emcee voice without --keep-script`.
- `process_package` takes `notes: ScriptNotes | None`. Given notes, it neither
  calls `write_script` nor builds the scriptwrite provider.
- **Failure safety (strict).** `_process_one`'s clear step today nulls both
  blocks. With keep_script it must clear **only `dj_audio`**: dj_notes stays,
  so a failed run leaves the package pending with its script, and a retry works.
  (`rewrite_manifest` takes both blocks; pass the parsed notes through.) After
  each successful `_repair` in this mode, also `rewrite_manifest(pkg,
  dj_notes=notes, dj_audio=None)`, so a later failure keeps the reworded text.
- `dj-notes.md` is written if it is missing, or if `_repair` changes the notes.
- **Presenter check.** Refuse when the recorded `dj_audio.presenter` differs from
  the resolved presenter: `script was written for <id>; re-voice without
  --keep-script`. A recorded null means `house`; an absent key always refuses and
  prints `?`. When dj_audio is null (a failed previous attempt) the check passes.
  The refusal happens before preflight and before anything changes.
- **`--fresh` with `--keep-script` renders only the named clips.** Every other
  clip already on disk is adopted: its key under today's formula goes into
  `segments.json` with no render. Measured: recomputing today's `_render_key` over
  all 328 voiced packages gives 94 all-match, about 11 partial, about 223
  no-match, so shows voiced by mid-October would otherwise re-render whole.
  Adopted keys are written before the first render and hold across a repair
  round, so a retry of a failed attempt, which has no `--fresh`, still matches
  them. A missing non-named clip renders as usual. When the recorded
  `dj_audio.tts` backend or model differs from today's resolution, print one
  warning line that re-rolled clips will sound different from the kept ones.
- Without `--fresh`, normal key comparison applies, so `--keep-script` alone may
  re-render everything: the help says so. Update the `--fresh` help, dropping
  caveat (1) in favour of pointing at `--keep-script`. Docstring for `voice`
  updated.
- **Failed-attempt state** (`dj_notes` present, `dj_audio` null; 0 of 2,786
  today). Plain `emcee run` skips it with `skip <slug>: kept script awaiting
  retry (emcee voice <slug> --keep-script)`, not counted as new. Plain `emcee
  voice` on it is an explicit operator act and proceeds as a fresh script. `emcee
  status` reason: `kept script`.
- The failure line of a keep-script run prints the retry command, and `_repair`'s
  "re-run ... for a fresh script" hints become that command in this mode.

- `--force` with `--fresh` and `--keep-script` together is a usage error: `--fresh` here means only the named clips, `--force` means every clip.

Tests: a kept script reaches TTS unchanged with the LLM provider never called; a
TTS failure leaves dj_notes in the manifest and a retry succeeds; presenter
mismatch refuses with nothing written; `--fresh` plus invalid notes leaves clip
and manifest byte-identical; plain `run` skips the failed-attempt state; `--fresh
x --keep-script` on a package with non-matching keys renders exactly x and leaves
other clip bytes untouched; a failed `--fresh x` retried with `--keep-script`
alone renders only x; the warning line; `_repair` under keep-script persists the
reworded segment; a failure after a repair keeps the reworded text.

## Task 3: `emcee run --keep-script` (Sonnet)

Files: `cli.py`, `audio.py` (key comparison), `station.py` if selection belongs
there.

`emcee run --keep-script --presenter ID [--drifted] [--profile P] [--force]
[--dry-run] [--yes]`.

- `--keep-script` requires `--presenter`; `--presenter` and `--drifted` without
  `--keep-script` are usage errors.
- **Selection** (replaces the "not broadcast-ready" sweep for this mode): every
  package with non-null `dj_notes` whose resolved presenter is ID, ready or
  pending, the failed-attempt state included. The id compares case-insensitively,
  as `emcee status` does. An empty selection prints `note: no package resolves to
  presenter X`. `--drifted` keeps only those whose recorded TTS differs from
  today's by the same comparison `emcee status --drifted` uses (reuse it, do not
  reimplement); on top of that, a voiced block with no TTS record counts as
  drifted (18 today: 16 Kurt, 2 Monroe), as does a null dj_audio. awaiting-fix
  packages, packages with missing track audio and error rows skip exactly as `run`
  skips them today. A recorded-presenter mismatch prints `skip <slug>: script was
  written for <id>`.
- The plan prints one `kept script` group (not `repair`), says the scripts are
  kept and there is no scriptwriting LLM cost (a content-filter repair can still spend), gives an exact `N of M clips will re-render` from
  key comparison (all of them under `--force`; cache the bed hash per presenter),
  and asks `Proceed?`.
- The batch stops after 3 consecutive failures: this mode clears `dj_audio` on
  shows that may be airing, so a dead API key must not walk the station. Other
  selections keep today's continue behaviour.

Tests: selection across ready, pending-with-notes, failed-attempt, no-notes, other
presenter, mismatch and awaiting-fix packages; the empty-selection note; a
differently cased id; `--drifted`, including no TTS record; the exact clip count;
the stop after 3 consecutive failures; usage errors; no-TTY refusal.

## Task 4: `emcee say --tts` (Sonnet)

Files: `cli.py`, `process.py` (`ad_hoc_speech`), `tts/resolve.py` as needed.

`--tts voxtral|elevenlabs|mlx_audio`, and `--tts-model` (needs `--tts mlx_audio`,
else a usage error; default the presenter's `tts_model` when the presenter names
it). Overrides the backend for this render alone, bypassing the "never inherits
mlx_audio" resolution error; the voice source (presenter clip, transcript,
`--clone`, `--voice`) stays what it was. Every gate in `say_cmd` keyed on the
house backend (`house_mlx`, the `clone_text if house_mlx` pass-through) uses the
effective backend.

Refuse with a plain message whatever cannot work: a clone on elevenlabs; mlx_audio
with no clip or no transcript; a preset voice carried to a different backend,
whether a presenter's or the house `[tts] voice` (preset ids are not portable: the
message says to use `--voice` instead of `--presenter`); an uncalibrated model
(existing guard). No change without the flag.

Tests: override reaches the provider for the presenter, `--clone` and `--voice`
paths; each refusal; `--tts-model` without `--tts mlx_audio`; no-flag path
byte-identical in resolution.

## Task 5: `voiced_on` (Sonnet)

Files: `models.py`, `process.py`, `cli.py` (`status --json`), `station.py`
(`PackageStatus`), and llama's hand-kept copy of the block (`DJAudio` in
`packages/llama/src/llama/models.py`), as optional fields there too.

`DJAudioBlock.voiced_on: str | None = None` (local `YYYY-MM-DD`) and
`voiced_before: str | None = None`, written by `process_package`. `voiced_on`
means "the newest clip was rendered on this date". `_process_one` reads both from
the raw `dj_audio` block before the clear and passes them in. A run that rendered
a clip sets `voiced_on` to today and clears `voiced_before`. A run that rendered
nothing (every cache key matched) carries both unchanged. `emcee status --json`
adds `voiced_on` and `voiced_before`. Readers must tolerate absence; legacy
blocks are raw dicts and must never round-trip through the model (see
`DJAudioBlock`'s docstring).


This task edits `llama/models.py`, so run the full `./.venv/bin/python -m pytest -q`, not just `packages/emcee`.

Tests: a render gives today; no render carries both; a legacy block in `status
--json`; `test_package_io.py:85` still builds.

## Task 6: `scripts/backfill_voiced_on.py` (Sonnet; strict surface)

One-off, imports emcee and llama, modelled on `scripts/backfill_voiced_by.py`:
`python scripts/backfill_voiced_on.py [--station-root P] [--apply]`, dry run
unless `--apply`.

For each package with a non-null `dj_audio` and neither `voiced_on` nor
`voiced_before` set (a null counts as unset), take the newest mtime of the clips
the block names (never the manifest's: 198 were touched later).

- Inside the NAS-copy window, 2026-10-10 19:28:00 to 19:40:00 at -04:00, inclusive
  at both ends (timezone-aware constants, comment citing the measurement: 118
  packages, clips and music stamped in the same second, 11 minutes): set
  `voiced_before: "2026-10-10"`, no `voiced_on`.
- Else `voiced_on: <that date>` (measured: 210 packages).
- Clip missing: leave the package alone and print it.

Writes are raw-JSON read-modify-write, adding one key to `dj_audio` and nothing
else, and **restore the manifest's previous mtime with `os.utime`**: transmitter
treats a newer manifest mtime as "changing" for its quiet period, so a plain
rewrite would make every voiced show briefly ineligible. Per package: stat the
manifest, read it, build the new bytes, re-read the bytes immediately before
replacing and skip with a printed line on any change, write with
`atomic_write_bytes(..., fsync=True)`, then `os.utime` to the stat's times. The
instant between the replace and the utime is an accepted limit; say so in the
script's docstring.

Refuse under `--apply` while an `emcee` or `llama` process runs:
`llama.campaign_gate.tool_processes` with `self_script`, called before each write.
Known limit: a sleeping sweep loop is invisible to it. Idempotent. Dry run prints
the counts per outcome and per presenter.

Run the backfill before any re-voice. Before the first `--apply`, the operator
checks on the mount that `os.utime` preserves mtime on one scratch file over SMB,
read back from hugo.

Tests use a tmp station with set mtimes, pinning the window edges, mtime
preservation, a manifest changed before the replace being skipped, `awaiting_fix`
surviving, and legacy blocks surviving byte-equal apart from the new key.

---

## Docs

Task-by-task, update `CLAUDE.md` (emcee Commands and architecture text) and the
README for the new flags and `voiced_on`. Also record:

- `themotet-2007-04-22` and `warrenzevon-2000-05-29` have scripts that say profane
  titles, so re-voice those with a fresh script, not `--keep-script`.
- Limit: `llama deliver` reads only `dj_audio`, so it treats the failed-attempt
  state as unvoiced.

## Order

1, 2, 4, 5, 6 (needs 5), then 3 (needs 2). Tasks 1 and 4 are independent of the
others. Task 3 is built last because the operator will not use it soon.

Task 1's sample gate pauses Task 1 only: the peer proceeds with the other tasks
while the operator reads, and applies any wording changes as a follow-up commit.

Review per task: spec-compliance and code-quality, both Opus; final branch review
on Opus.

## Left to the builder

Option wiring, help text wording, where selection code lives, test file placement.
