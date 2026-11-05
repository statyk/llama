# emcee

Commands and architecture for `emcee` (`packages/emcee/`). The repo overview is the root `CLAUDE.md`.

## Overview

`emcee` (dist name `llama-emcee`, bare CLI `emcee`) is station-side and runs
**after** `llama deliver` — it operates on the delivered-packages folder
(`[station] root`), never on llama's own library. "Not broadcast-ready" IS
the work predicate: `emcee run` scans the station root and voices every
package that isn't yet broadcast-ready, no separate state file needed.
The one exception to the package-shaped rule is `emcee say`, which voices
an arbitrary text file to an MP3 — no package, no manifest, no LLM call —
reusing the same voice/bed resolution and `audio.render_speech_mp3`
renderer as the DJ clips.
emcee owns presenters (`presenters/<id>.toml`: name/sex/character +
`voice` XOR `voice_clone`), the script LLM task and its own factual guard,
`speech_text` normalization, TTS (hosted Mistral Voxtral by default,
ElevenLabs as an opt-in alternative, and a free local `mlx_audio` backend
over mlx-audio's server; a presenter may pin any of the three with `tts`, and
clones are voiced on voxtral or mlx_audio, never elevenlabs), instrumental
beds, the per-segment render cache, and
assembling `dj-audio/`/`broadcast.m3u`. Its `[assign]` config maps a llama
profile name to a presenter + on-air title, keyed off the
effective profile (`manifest["source"]["profile"]`, which llama stamps on every
package it delivers, unless a move or `[assign.artists]` rule overrides it). emcee writes `dj-notes.md`, `dj-audio/`, and `broadcast.m3u`
straight into the package directory llama delivered, and rewrites the
manifest's `dj_notes`/`dj_audio` blocks in place (llama writes both as
`null` — they are emcee-written passthrough blocks in the shared manifest
model). emcee never imports llama.

**The station lock, per package.** `emcee run` and `emcee voice` take the
station lock (`<delivered folder>/.lma-station.lock`, the package directory's
absolute parent; `station_lock.py`, whose format is a contract shared with
llama) per package, held from `_process_one`'s manifest re-read through the
package's last write (clips and manifest) and released before the next
package, never across the `Proceed?` question (`emcee retitle` holds it for
its whole write phase, also after the question). While it is held, llama's
station writes (deliver, clear-mark, bulk-apply) refuse. A lock held by
another writer stops `run` at that package (`error: <slug>: the station is
locked by another writer (...)`, the holder, `not attempted: <it and the
rest>`, exit 1) and refuses `voice` (exit 1, nothing touched). On SIGTERM or
SIGHUP inside the hold emcee releases the lock and exits at once
(`os._exit(128 + signum)`, no caller cleanup). That leaves at most a stray
temp for every station write that is a temp plus rename (emcee's own, llama's
clear-mark and bulk-apply marks): keep them that way. Two are not, and there
SIGTERM acts like SIGKILL minus the stuck lock: llama deliver's overlay copy
(`shutil.copytree` into the live package; a truncated manifest or audio file)
and its replace path's two renames (an exit between them leaves no package,
only the `.<slug>.old-*`/`.<slug>.deliver-*` siblings). SIGKILL or power
loss leaves the lock; nothing breaks or expires it, so clear it with `emcee
lock clear`. `move`, `say`, `--dry-run` and the read-only commands don't take
it. Two concurrent `emcee run`s are still not supported: the lock serializes
packages, not runs, so both would voice the same pending packages and double
LLM/TTS spend. Don't fan out `emcee run` the way llama's workspace tolerates
concurrent `llama get`s.

## Commands

- Run (emcee, station-side, post-`llama deliver`): `emcee run` (scan
  `[station] root` and voice every not-yet-broadcast-ready package;
  it prints a plan on stderr (new / re-voice by reason / repair, the exact clip count, presenter and TTS per group) and asks `Proceed? [y/N]` before ANY LLM or TTS spend; `--yes`/`-y` skips the question; with no TTY and no `--yes` it prints the plan and exits 1. A pending package with missing track audio is skipped (`re-deliver from llama`), not voiced, whatever else is wrong with it; a failed `--keep-script` attempt is skipped too (`skip <slug>: kept script awaiting retry (emcee voice <slug> --keep-script)`). **`emcee run --keep-script --presenter ID [--drifted] [--profile P] [--force] [--dry-run] [--yes]`** is the batch form of `emcee voice --keep-script` and replaces that sweep: every package with non-null `dj_notes` whose resolved presenter is ID (case-insensitive), ready or pending, the failed-attempt state included; `--keep-script` needs `--presenter`, and `--presenter`/`--drifted` need `--keep-script` (usage errors, exit 2); an empty selection prints `note: no package resolves to presenter X`; `--drifted` reuses `emcee status --drifted`'s comparison (`_TtsNow`) and also takes a voiced block with no TTS record and a null `dj_audio`; awaiting-fix, missing-audio and error rows skip as in `run`, a recorded presenter other than ID prints `skip <slug>: script was written for <id>`. The plan is one `kept script` group plus `N of M clips will re-render` (`audio.count_clips_to_render`, the `_synthesize_dj_audio` comparison; all clips under `--force`, also in `--dry-run`; one speech provider and one bed hash per batch) and the `Proceed?` question. **The batch stops after `MAX_CONSECUTIVE_FAILURES = 3` consecutive failures** (`stopping after 3 consecutive failures`, `not attempted: ...`; a success resets the count) because each clear nulls `dj_audio` on shows that may be airing; other selections keep continuing after a failure. **An agent (no TTY) runs `emcee run --dry-run`, shows the plan, and passes `--yes` only after the operator approves**; the `--yes` run re-scans, so keep the gap short;
  **`--sample N [--seed S]`** voices a random N of what the run would voice, drawn LAST (after every filter and skip, and after `--keep-script`'s all-current skip), voiced in station order; the plan opens with `sampled N of M to voice (seed S)` (stderr; not printed when nothing is to voice); without `--seed` a seed is drawn and printed, so an agent passes the dry-run's seed to the `--yes` run. Each package ranks by sha256(`seed:slug`) rather than a shuffle, so a station change between the two runs moves only the packages it touches; `--sample 0` and `--seed` without `--sample` are usage errors (exit 2);
  `--profile <name>` (repeatable) limits it to packages whose EFFECTIVE profile (move > artist rule > llama's) is one of those, `--assigned` to packages whose effective profile has its OWN
  `[assign.profiles.<name>]` entry (not those falling to `[assign] default`
  or the house voice), `--dry-run` lists what
  would be voiced and by whom — an explicit assignment prints `<id>`, the
  default `<id> (default)`, none `house`; a pinned presenter's row also shows
  `[<backend> <model>]`, an unloadable presenter file
  `[invalid presenters/<id>.toml]`, a failed TTS resolution
  `[unresolved: …]`),
  `emcee voice <package>` (script + voice + assemble one package —
  a path, or a name/unique substring under `[station] root`, overridable
  with `--station-root`, exact name beating substring hits;
  `--fresh <clip-stem>` deletes just that cached clip, but without
  `--keep-script` emcee re-scripts first, and a real LLM's regenerated text
  usually invalidates every clip's cache too; `--force` re-synthesizes
  all of them unconditionally; `--keep-script` voices the manifest's existing
  `dj_notes` with no scriptwriting LLM call, refuses a script written for
  another presenter (`script was written for <id>; re-voice without
  --keep-script`, `?` = no recorded presenter), and with `--fresh` renders only
  the named clips, adopting every other clip on disk; alone it compares cache
  keys as usual, so every clip may re-render; `--force` with `--fresh` and
  `--keep-script` together is a usage error;
  `themotet-2007-04-22` and `warrenzevon-2000-05-29` have scripts that say
  profane titles, so re-voice those with a fresh script, not `--keep-script`),
  `emcee status` (default: a summary by profile, ending in `voiced on`, the voiced packages by recorded TTS backend; `--list`/`-l`
  gives the per-package table (a header row unless `--no-header`) of ready/pending/unsupported/`error` with a TTS column (the recorded backend, `?` = no usable record, `(now: <backend>)` when the presenter now resolves to a different backend, `(now: new model)` when only the model moved, `(now: unresolved)` when it cannot resolve; models are in `--json`; the voice hash is not compared; display only, drift never changes readiness) and a short reasons column (`unvoiced`, `kept script`, `no script`, `no m3u`, `N clips missing`, `N of M audio missing`; blank for `awaiting-fix`; `--json` keeps the full text), `--profile`,
  `--state`, `--tts BACKEND` (`none` = voiced, no record) and `--drifted` filter and switch to that table on their own, `--json` is
  always per-show and adds `tts_now`/`tts_drifted`, `voiced_on` and `voiced_before` (raw reads, null when absent or not a string); `station.scan` checks packages on `SCAN_WORKERS = 16` threads and reads each manifest once, output unchanged; a `--profile` no package carries prints a `note:` rather
  than looking like an empty queue; the voicing presenter is the
  recorded `dj_audio.presenter` — null is the house narrator, an absent key
  means voiced before it was recorded and shows `?`), `emcee move <show> <profile>|--delivered|--clear`, `emcee move --list` (one-off profile moves in `<emcee root>/moves.json`, keyed by `source.performance_id`; flock + atomic write; a move to an unassigned profile other than the delivered one is refused), `emcee say <text-file>` (ad-hoc
  narration: text file in, MP3 out, no package/script/LLM — voice via
  `--clone`/`--voice`/`--presenter` else the house `[tts] voice`, bed via
  `--bed`/`--bed-gain`/`--no-bed` else the package rules, chunking ON by
  default like `[tts] chunk`; `--no-chunk` without a bed is the one render
  that is not loudness-normalized; `--tts voxtral|elevenlabs|mlx_audio` overrides
  the backend for that render alone, bypassing the unpinned-presenter-under-mlx
  error, with the voice source unchanged, and `--tts-model` (needs `--tts
  mlx_audio`; default the presenter's `tts_model`) picks the mlx model; refused
  plainly: a clone on elevenlabs, mlx_audio without clip or transcript, a preset
  voice (a presenter's or the house `[tts] voice`) carried to another backend
  (use `--voice`), an uncalibrated model; without the flag resolution is
  unchanged), `emcee presenter add/edit/list/show/remove`
  (`presenters/<id>.toml`; `edit` changes any field with set/`--clear-*`
  flags, `--transcribe` drafts `voice_clone_text` on the mlx-audio server's
  STT model and writes it only on confirmation; `voice_clone` is stored as an
  absolute path), **`emcee retitle [--station-root P] [--dry-run] [--yes]`** (the
  program-title backfill; STRICT, it rewrites live station manifests: stamps
  `dj_audio.title` on already-voiced packages, no re-voicing, and resyncs it
  after a config rename (a removed title is written as null). The target is
  `assignment_for(config, manifest_voiced_profile(m)).title`; `emcee.retitle`
  holds the plan and the raw single-field writer. It prints the plan (`would
  write <slug>: <old> -> <new>`, `(none)` = null; `skip <slug>: awaiting fix
  from llama`; `refused <slug>: <reason>`; `stray temp: <slug>/<name>` for a
  `.manifest.json.emcee-*.tmp` a killed write left, a listing only; then
  `<n> to write, <n> unchanged, <n> awaiting fix, <n> refused, <n> unvoiced`),
  and `--dry-run` stops there. It never writes an awaiting-fix show (136 at
  design time): any write changes its sha256, which breaks `bulk_apply unmark`
  for it, and a wave snapshot restore covering a stamped show refuses with
  station-changed (accepted 2026-11-04); such shows get the title when
  re-delivered and re-voiced. It refuses (lists, leaves byte- and
  mtime-identical) any manifest not in emcee's exact encoding
  (`json.dumps(m, indent=2) + "\n"`), pre-v3, unreadable, or with a non-object
  `dj_audio`. It keeps each manifest's original mtime (set on the temp before
  the rename, re-checked after) because hugo's transmitter treats a manifest
  younger than `quiet_minutes` (10) as ineligible and would drop planned
  shows. Order: plan, `Proceed?` (no TTY and no `--yes`: `error: refusing to
  write without confirmation; pass --yes`, exit 1), then a `ps` check
  (`refusing: other emcee or llama processes are running` plus the lines, exit
  1: the only guard against `scripts/backfill_*.py` and the campaign worktree's
  older llama, which ignore the lock), then the station lock for the whole
  write phase (a held lock: exit 1, nothing written), then a re-read of every
  planned manifest (any change: `refusing: <n> manifest(s) changed since the
  plan; nothing written; run again`, exit 1). Per show it first saves
  `<emcee root>/title-backups/<UTC %Y%m%dT%H%M%SZ>[-n]/<slug>.json` (the
  original bytes) and appends `{slug, before_sha256, mtime_ns, title}` (the
  target title, null for none) to
  `record.jsonl`, both fsynced, with their directory entries, before the write (a SIGTERM under the lock ends
  the process with no cleanup); a backup failure stops before that show
  (`not attempted: …`, exit 1). After a write it prints `<slug>: <old> -> <new>`
  and appends `{slug, after_sha256}`. A show changed just before its rename is
  skipped and listed (exit 1); any write or verify failure stops the run
  (`not attempted: …`, exit 1). Exit 1 only for a refused package, a skipped
  write or a stop; awaiting-fix, unchanged and unvoiced never affect it.
  **Hand restore:** see "Retitle hand restore" below. **An agent runs `emcee retitle --dry-run`, shows
  the plan, and runs `emcee retitle --yes` only after Shawn approves, in a
  separate tool call.**),
  `emcee lock show [--station-root]` (prints the station lock's
  holder, read-only) and `emcee lock clear [--station-root] [--yes]` (shows the
  holder, asks, and removes the lock only if it is unchanged; for a lock whose
  writer is gone). **An agent runs `emcee lock show`, reports it, and runs `emcee
  lock clear --yes` only after Shawn approves, in a separate tool call.**
  `emcee config init`.

## Retitle hand restore

To undo one show of an `emcee retitle` run, put its backup back with the same
care as the writer: a temp file in the package directory, flushed and fsynced,
its mtime set from the record BEFORE `os.replace` over `manifest.json`, then
the mtime re-checked and re-applied (a `cp` rewrites the live manifest in
place and leaves a fresh mtime, and hugo then drops its planned shows for
`quiet_minutes`). Run it only with no emcee or llama process running (`ps`;
that also covers `scripts/backfill_*.py` and the campaign worktree's older
llama, which ignore the lock) and no `.lma-station.lock` in the station root,
or from emcee's venv inside `with station_lock(<station root>,
command="hand restore"):`.

Per slug, `record.jsonl` in the run's `title-backups/<stamp>/` holds a before
line `{slug, before_sha256, mtime_ns, title}` and, once the write landed and
was recorded, an after line `{slug, after_sha256}`. What the manifest now
holds decides it:

- **An after line, and the file's sha256 equals `after_sha256`**: this run's
  write; restore it. Any other sha256: someone wrote it since; leave it.
- **A before line and no after line** (skipped as changed, put back after a
  failed verify, an after-rename failure, a failed after-append, or a kill
  between the rename and the append):
  (a) **sha256 equals `before_sha256`**: the original; nothing to do (but if
  its mtime is not `mtime_ns`, re-apply it: a put-back whose mtime restore
  failed);
  (b) **the bytes equal the backup with only `dj_audio.title` set to the
  line's `title`, in emcee's encoding**: this run's unrecorded write; restore
  it;
  (c) **anything else**: a foreign write; leave it.
- **A failed put-back** (`did not verify after the title write, and putting
  the original back failed`: the file holds this write's bytes) is case (b);
  `the original was put back, but restoring its mtime failed` is case (a).

A before line with no `title` key predates the field: the snippet stops with
a KeyError there, writing nothing; compare such a file by hand. Paste this into
`python3 -` with the three names filled in; it applies the rules above and
writes only in the restore cases (a killed run leaves at most a
`.manifest.json.emcee-*.tmp`, which `emcee retitle --dry-run` lists):

```python
import hashlib, json, os, secrets, stat
RUN, ROOT, SLUG = "<emcee root>/title-backups/<stamp>", "<station root>", "<slug>"  # fill in
sha = lambda b: hashlib.sha256(b).hexdigest()
recs = [r for r in map(json.loads, open(f"{RUN}/record.jsonl")) if r["slug"] == SLUG]
before = next(r for r in recs if "before_sha256" in r)
after = next((r["after_sha256"] for r in recs if "after_sha256" in r), None)
orig = open(f"{RUN}/{SLUG}.json", "rb").read()
if sha(orig) != before["before_sha256"]:
    raise SystemExit("the backup does not match its record; stop")
data = json.loads(orig)
data["dj_audio"]["title"] = before["title"]          # what this run wrote
ours = sha((json.dumps(data, indent=2) + "\n").encode())
man = f"{ROOT}/{SLUG}/manifest.json"
cur, st = open(man, "rb").read(), os.stat(man)
times = (st.st_atime_ns, before["mtime_ns"])
if sha(cur) == before["before_sha256"]:              # (a) the original
    if st.st_mtime_ns != before["mtime_ns"]:
        os.utime(man, ns=times)                      # a put-back whose mtime failed
    print("original; nothing to restore")
elif sha(cur) not in {after, ours}:                  # (c) a foreign write
    print("changed by someone else; left alone")
else:                                                # this run's write: put it back
    tmp = f"{ROOT}/{SLUG}/.manifest.json.emcee-{secrets.token_hex(8)}.tmp"
    with open(tmp, "xb") as f:
        try:
            os.fchmod(f.fileno(), stat.S_IMODE(st.st_mode))
        except OSError:
            pass                                     # an SMB share may refuse it
        f.write(orig); f.flush(); os.fsync(f.fileno())
    os.utime(tmp, ns=times)
    if open(man, "rb").read() != cur:
        os.unlink(tmp); raise SystemExit("changed during the restore; left alone")
    os.replace(tmp, man)
    if os.stat(man).st_mtime_ns != before["mtime_ns"]:
        os.utime(man, ns=times)
    print("restored, mtime", os.stat(man).st_mtime_ns == before["mtime_ns"])
```

## Architecture

- **emcee (station-side voicing), architecture:** `emcee run`/`emcee status`
  scan `[station] root` for delivered packages (`packages/emcee/src/emcee/
  station.py`; scans skip dot-prefixed dirs, which are llama's replace-swap
  siblings); `readiness()` computes the same "broadcast-ready" signal
  llama used to (script present, DJ audio present, `broadcast.m3u` present,
  every manifest track's audio on disk, and, since 2026-10-16, the profile check: the voiced profile (`dj_audio.profile`, else, for a legacy block, `source.profile`) equals the EFFECTIVE profile, `station.effective_profile` = a `moves.json` move > an `[assign.artists]` rule > `source.profile`; transmitter deliberately does not mirror this leg) — but as emcee's own derived,
  never-stored state (`ready`/`pending`, plus `unsupported` for a pre-v3
  manifest), not llama's. There is no separate work-queue file: "not
  broadcast-ready" *is* the predicate `emcee run` sweeps on.
  `process.py:process_package` orchestrates one package: resolve the
  package ONCE (`resolve_voicing`: effective profile, then `resolve_assignment(config, profile)`
  against `[assign]`, then `resolve_tts`) and pass that `Voicing` through → `scriptwrite.py` (script LLM task + `script_guard`,
  emcee's own port of llama's old `factual_guard`; `known` also holds each component of a merged title split on `>`, `->` and a `/` not followed by a digit and not a `w/` ("with"), a leading `E: ` dropped from each part, empty parts dropped (a spaced ` - ` merge is not split: a documented limit, such a component is refused); persona-styled when a
  presenter is assigned, byte-for-byte neutral otherwise) → render
  `dj-notes.md` → TTS via a `SpeechProvider` (`packages/emcee/src/emcee/tts/`:
  `voxtral` default, `elevenlabs` alternative, `fake` for tests; same
  per-segment cache, `[tts] chunk`, and `[tts] bed` instrumental-bed mixing
  llama used to have) → assemble `broadcast.m3u` → atomically rewrite the
  manifest's `dj_notes`/`dj_audio` blocks last (`dj_audio` records `presenter`, `profile`, `profile_source`, `tts` (`backend`/`model`/`voice`), `voiced_on`, `voiced_before` and `title` (the program's current `[assign.profiles.<p>] title`, null when none; always the LAST key, so the title backfill (emcee retitle) appends it in the same position); `profile`/`profile_source`/`tts` are required in `DJAudioBlock`, the two dates optional, always serialized (`voiced_on` is the local `YYYY-MM-DD` the newest clip was rendered: `process_package` sets it to today and clears `voiced_before` when `rendered` is non-empty, else carries both from the raw block `_process_one` read before the clear; adopted clips never enter `rendered`, and a failed attempt clears `dj_audio`, so its retry carries nothing: both null, no invented date; llama's `DJAudio` has both as optional fields), so a legacy block must never be round-tripped through the model: update it as a raw dict), in place, in the package
  directory llama delivered (`package_io.py:rewrite_manifest`).
  Chunked clips are packed by paragraph at `[tts] chunk_chars` (default 250; a chunk never ends inside a sentence) and exact-silence gaps are filled with the clip's own room tone (`[tts] room_tone`, default on); the scriptwriter writes paragraphs.
  Chunked and bed-active clips are loudness-normalized per chunk/segment
  before the gap and the bed mix (`tts/loudness.py`: −20 dBFS speech-active,
  −1 dBFS peak ceiling, ±10 dB clamp; module constants, no config), because
  Voxtral returns every call at its own level; the unchunked no-bed path ships
  the provider's MP3 untouched and is not normalized.
  **`--keep-script` (strict: it must never lose a script).** `_process_one` parses `dj_notes` once (`process.kept_notes`) and checks the presenter (`process.script_writer_mismatch`) before provider construction, so a refusal touches nothing (`no script to keep; run emcee voice without --keep-script`). With `--fresh`, `audio.adopt_clips` writes today's key for every other clip on disk into `segments.json` after the preflight and before the unlink, with no render, and warns once if the recorded TTS backend or model is not today's: measured over 328 voiced packages, today's `_render_key` matched every clip of only 94, so shows voiced by mid-October would otherwise re-render whole. Adopted clips never enter `rendered`. The clear nulls only `dj_audio`, and each accepted `_repair` is written straight into the manifest (the only copy a retry reads). `dj-notes.md` is written only if missing or repaired. **Failed-attempt state** (`dj_notes` present, `dj_audio` null, reason `kept script`, `Assessment.kept_script`): the failure prints the retry command once the clear path has begun (a preflight failure changes nothing and prints none: the same command is the retry, and `--keep-script` alone would drop `--fresh`). The retry needs no `--fresh`, since the adopted keys are on disk. Plain `emcee run` skips the state; plain `emcee voice` on it writes a fresh script. `run --keep-script` skips a READY package whose count is 0 of M clips (`skip <slug>: every clip is already current`; no clear, no rewrite, manifest mtime unmoved) unless `--force`, and the plan counts only what is processed; pending packages and the failed-attempt state are never skipped on that count (no usable `dj_audio`). **Limits (operator-accepted):** `llama deliver` reads only `dj_audio`, so it treats the failed-attempt state as unvoiced; and with `dj_audio` null the presenter check passes, so a move or assign change between a failed attempt and its retry voices that script under the new presenter.
  **`moves.json` is never read leniently**: unreadable or malformed is a hard error for `run`/`voice`/`status`/`move`, and so is a missing file while any package records `profile_source: "move"`.
  Everything else in a package is llama-owned and read-only from emcee's side.
  A Voxtral content-filter refusal (403 `guardrail_violation`) is `SpeechBlocked`:
  emcee narrows it to the sentence, rewords just that segment with the small
  `rephrase` task (2 attempts, gated by `rephrase_problems` + `script_guard`),
  and re-voices only that segment (the task has its own `[llm.rephrase]` config key and does not inherit scriptwrite's backend); on the chunked path a blocked
  multi-sentence chunk is narrowed to its sentence and, when every sentence
  passes alone, falls back to its passing takes; with `[tts] chunk = false` a
  block that exists only across sentences fails with "re-run with `[tts] chunk = true`". Blocks are deterministic
  (measured 7/7), so they are never retried identically; transport errors, 429
  and 5xx get one retry.
  **Per-presenter TTS pinning + the local `mlx_audio` backend**
  (`docs/superpowers/specs/2026-10-12-local-tts-presenter-pinning-design.md`).
  A presenter's `tts` pins its backend; an unpinned presenter inherits
  `[tts] backend` — EXCEPT that a presenter never inherits `mlx_audio` (a
  resolution error, `pin tts explicitly`), so moving the house voice never
  moves a presenter. `tts/resolve.py:resolve_tts` is pure and runs before any
  spend; `speech_provider_for(config, resolution, *, voice, clone_ref,
  clone_text)` takes no defaults, so no call site can fall back to `[tts]
  backend` or drop the transcript. Hosted keys/models live in
  `[tts.voxtral]`/`[tts.elevenlabs]` (legacy `[tts] api_key`/`model` still mean
  the HOUSE hosted backend's; the env var still wins). `tts/mlx_audio.py` is
  clone-only, sends `ref_audio` as an ABSOLUTE path (the server reads it from
  its own cwd) plus `ref_text` (`voice_clone_text`), always requests WAV, and
  never falls back. Every mlx clip passes the per-model runaway guard
  (`tts/calibration.py`: `max_tokens` capped in proportion to the text, the
  duration checked; `CALIBRATED_MODELS` holds MEASURED entries only, and an
  uncalibrated model is a resolution error). The quality layer
  (`tts/quality.py`) owns the ONE re-synthesis; a second guard or
  verification failure is a `SpeechDefect` that fails the package. Optional
  transcript verification (`[tts.verify] backends`, `tts/verify.py`) fails only
  gross mismatches and never re-verifies cached clips. `preflight()` runs in
  `cli._process_one` before the `--fresh` unlink, the manifest clear and any
  LLM spend: a no-op on hosted providers, one fixed sentence on mlx, and the
  STT path end to end when verification applies (hosted: the bundled
  `emcee/data/preflight_en.wav`). Evidence: `docs/superpowers/2026-10-12-mlx-audio-probe.md`
  and `…-mlx-audio-calibration.md` (adding a model means a calibration run,
  `scripts/mlx_audio_calibrate.py`). Runbook: README "Local TTS on this Mac".
  `presenters.py` manages `presenters/<id>.toml` (`emcee presenter
  add/edit/list/show/remove`) — the same TOML shape llama's presenters used to
  have (`name`/`sex`/`character` + exactly one of `voice`/`voice_clone`,
  optional `bed` override, plus the optional `tts`/`tts_model`/`voice_clone_text` pin; strict — an unknown key is a load error). emcee never imports llama (enforced by
  `packages/emcee/tests/test_no_llama_imports.py`) — its only input is the
  delivered package directory's files.
