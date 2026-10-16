### Spec Compliance

- ✅ Spec compliant. Every file the brief lists has its hunk, and each one matches Steps 2 to 7 nearly verbatim: llama `models.py` (`DJAudioTTS` and the three optional `DJAudio` fields), `test_the_cut.py` (one new test), transmitter `station.py` (docstring only: "four file-level" plus the fifth-leg paragraph), `docs/station-brief.md` (new `dj_audio` block and the legacy-keys note), `README.md` (run/status/move lines, the "Moving shows between profiles" subsection, the agent paragraph, the corollary parenthetical), `CLAUDE.md` (run-plan insert, the `emcee move` entry, the fifth readiness leg, `resolve_voicing`, the `dj_audio` record, `moves.json` strictness) and `docs/playout-incident-runbook.md` (§6 bullet). Both controller additions are done: emcee `models.py:4-5` now says "shape-compatible", and CLAUDE.md:643-645 now says `resolve_voicing`/effective profile. The spec "Docs" list (spec:437-447) and the Rollout agent line (spec:428-433, CLAUDE.md:108 and README "Running `emcee run` from an agent") are covered.
- ⚠️ Cannot verify from diff: the full-suite result the implementer claims (3137 passed). I did not re-run it; a docs/doc-model change gave me no doubt that needed a re-run.

Spot-checks of the new doc claims against code at HEAD. All of these hold:
- `Proceed? [y/N]` on stderr, `--yes`/`-y`, no-TTY refusal exit 1, `nothing voiced`: `cli.py:422-424, 515-519`. The plan goes to stderr through `_echo_plan`'s `out` (`cli.py:366-367`).
- `--dry-run` "the would-voice rows and the plan; never asks or writes": `cli.py:491-512`.
- `skip <slug>: N audio file(s) missing; re-deliver from llama`: `cli.py:487-490`.
- `emcee move <show> <profile>|--delivered|--clear`, `--list`, `missing`, `[no assign entry]`: `cli.py:886-1011`. A move to an unassigned profile that is not the delivered one is refused: `cli.py:980-983` plus `station.target_problem`. Moves are keyed by `source.performance_id`: `cli.py:974-977`.
- flock + atomic write: `moves.py:122-145`, using `atomic_write_bytes(..., fsync=True)`.
- `effective_profile` order (move > rule > `source.profile`): `station.py:147-167`. Voiced profile is `dj_audio.profile` when the key is present, else `source.profile`: `station.py:131-139`.
- A presenter, TTS-pin or house-voice change never re-voices: the check compares profiles only (`station.py:225-246`).
- `moves.json` strictness for run/status/move (`cli._load_station:216-224`) and for voice (`cli.py:593-598`). `require_present` is at `moves.py:96-112`.
- `DJAudioBlock` requires `profile`/`profile_source`/`tts` and legacy blocks are updated as raw dicts: emcee `models.py:55-70`.
- `resolve_voicing` → `resolve_assignment(config, profile)` → `resolve_tts`, returning a `Voicing`: `process.py:84-103`.
- Artist-name normalization (case, `&`/`and`, apostrophes, one trailing `[...]`, leading "the"): `artists.py:13-35`. A rule targeting an unassigned profile is a config load error: `config.py:188-191`. Every command except `config init` calls `load_config`.
- `--list` "southern (from funk)": `cli._profile_cell:726-735`. Status summary ready/pending/other: `cli.py:821-824`.
- Example values in station-brief: `voxtral-mini-tts-2603` is `tts/voxtral.py:13` DEFAULT_MODEL, and a 16-hex `clone:` hash matches `voxtral.py:83` and `mlx_audio.py:70`.
- Runbook transmitter claims match `pipeline.py:5-15` and `:243-302`:
  - an encoded row is frozen;
  - "package changed" on an unencoded row is re-planned in place on first mismatch;
  - a show that is no longer eligible is excluded and planned around;
  - LayoutError is raised only when `on_air` and the encode is missing.
  emcee clears the DJ blocks before a re-voice, after preflight (`cli._process_one:227-262`).

### Strengths
- The doc model is shaped correctly: `DJAudioTTS.model` defaults to None and every post-`outro` field is optional, so legacy manifests still validate. The new test proves both directions on real behavior: a full-block `model_dump` round trip, and None defaults on a legacy construction (`test_the_cut.py:74-84`).
- The `DJAudio` docstring states the boundary that matters: llama's `status`/`deliver --profile` keep using `source.profile`, not `dj_audio.profile`.
- The transmitter docstring and runbook frame the non-mirrored fifth leg accurately against the actual re-plan code, not just the spec.
- The README states the operationally dangerous facts plainly: back up `moves.json`, the rollout order, and the `--yes` re-scan gap.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
- **CLAUDE.md:109-112**: stale filter semantics in the same bullet this task edited. It still says "`--profile <name>` (repeatable) limits it to those llama profiles' packages, `--assigned` to packages whose profile has its OWN `[assign.profiles.<name>]` entry". Since this feature, both select by the EFFECTIVE profile: `cli.py:412-417` help text says "a move or artist rule counts", and the docstring at `cli.py:442-444` says the same. A reader or agent who trusts CLAUDE.md would expect `emcee run --profile funk` to include a funk-delivered show that was moved to `southern`, and it does not. The same stale "keyed off `source.profile`" framing also survives at CLAUDE.md:215-217 (the "What this is" `[assign]` sentence, a duplicate of the architecture sentence the controller asked to correct) and README.md:315-316 ("`[assign]` maps the llama profile name stamped at `manifest["source"]["profile"]`"). The brief did not list these lines, but the task's contract is that the docs describe the shipped behavior, and this is the feature's only docs pass. Fix:
  - CLAUDE.md:109: "limits it to packages whose EFFECTIVE profile (move > artist rule > llama's) is one of those".
  - CLAUDE.md:215-217: "keyed off the package's effective profile (`manifest["source"]["profile"]` unless an `emcee move` or `[assign.artists]` rule overrides it)".
  - README.md:315-316: a parenthetical pointing at "Moving shows between profiles".

#### Minor (Nice to Have)
- **CLAUDE.md:108** says "A package whose only problem is missing track audio is skipped". The code skips any pending package with missing track audio, whatever else is wrong with it (`cli.py:487` checks `missing_tracks` before anything else, with the comment "tracks first"). The spec says so explicitly (spec:369-370: "If it also fails another leg, it is still skipped: tracks come first"). As written, the doc implies that an unvoiced show with missing tracks gets voiced. The `run` docstring at `cli.py:436` carries the same understatement, but that line comes from an earlier task. Suggested wording: "A package with missing track audio is skipped (tracks first, even if it also needs voicing)".
- **docs/playout-incident-runbook.md** (new bullet, last sentence) says "A re-voice that FAILS leaves the package off the pool until `emcee voice <show>` succeeds". The package also stays `pending`, so the next `emcee run` retries it too. Suggested wording: "until a later `emcee run`/`emcee voice <show>` succeeds".
- **packages/emcee/src/emcee/models.py:4-5**: the stacked parentheticals read awkwardly: "...llama's `DJNotes` and `DJAudio` (llama's copy carries the newer fields as optional) (packages/llama/src/llama/models.py)". Moving the path next to the names would fix it: "`DJAudio` (packages/llama/src/llama/models.py; llama's copy carries the newer fields as optional)".
- **CLAUDE.md:108, 131, 639, 652, 663**: each insert is one unwrapped line of 200 to 450 characters inside otherwise hard-wrapped bullets. The file already has a few long lines, so this is cosmetic.
- **CLAUDE.md:104** (pre-existing, not in the diff): "emcee has the same treatment on its own six models". `config.py` now has 10 `_StrictModel` subclasses (T1 added `ArtistRule`), plus `Presenter`. The count was already stale at main (9), so this is optional cleanup.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** Every brief step and both controller additions are implemented accurately, and every new claim I spot-checked matches the code at HEAD. However, CLAUDE.md still describes `emcee run --profile`/`--assigned` (and `[assign]` keying, in two more places) as acting on llama's delivered profile. The feature changed that to the effective profile, and this task is the docs pass meant to catch it. The fix is three short wording edits.
