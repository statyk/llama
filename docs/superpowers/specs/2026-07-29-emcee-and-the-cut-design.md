# emcee + the cut (split sub-project 3)

**Date:** 2026-07-29
**Status:** Approved design for sub-project 3 of the split architecture
(`docs/superpowers/specs/2026-07-28-split-architecture-design.md`). This is the
largest sub-project: it builds the persona tool and performs the removal the
umbrella deferred until a replacement existed.

## Goal

Build **emcee** — the station-side package→package filter that gives delivered
show packages a voice (DJ script + TTS audio + broadcast.m3u) — and cut
scriptwriting, presenters, and speech synthesis out of llama. After this
sub-project llama ends at an unvoiced delivery and emcee owns everything
personality- and speech-related, meeting only at the manifest-v3 contract.

## Decisions (settled here, in the Q&A, or in the umbrella; don't relitigate)

- **Name: `emcee`** — module `emcee`, dist name `llama-emcee`, **bare `emcee`
  console command** (collision check 2026-07-29: PyPI `emcee` is hard-taken by
  the astrophysics MCMC sampler and two unrelated Homebrew CLIs exist; verdict
  SOFT, accepted for this non-commercial project; audio/radio domain fully
  clear).
- **Station-side, post-deliver.** emcee operates on the folder llama delivers
  into, never on llama's library. llama's story ends at an unvoiced delivery.
- **Scan + batch discovery.** A configured station root; `emcee run` processes
  every package that isn't broadcast-ready. Not-ready **is** the work
  predicate — no separate state files, no watcher daemon.
- **Profile stamp.** llama stamps the originating profile name into the
  manifest (`source.profile`, additive v3 field, absent for one-off runs).
  emcee's `[assign]` config maps profile → `{presenter, title}`. **Title and
  presenter live emcee-only**; `Profile.presenter`/`Profile.title` die
  llama-side.
- **They move, they don't morph**: the presenter TOML format, the presenter
  CLI, `speech_text.py`, and the whole `tts/` layer transfer unchanged.
- **emcee never imports llama** (guard test, as herder has). The manifest is
  the only contract; emcee defines its own models for the blocks it writes.
- **No migration.** Already-voiced packages (station or library) are left as
  they are; pre-stamp packages simply have no `source.profile`.

## 1. Package, dependencies, CLI

New `packages/emcee/` (monorepo package #3):

```
packages/emcee/
  pyproject.toml            # dist llama-emcee, console script emcee, GPL-3.0-or-later
  src/emcee/
    __init__.py
    cli.py                  # typer app
    config.py               # EmceeConfig (station root, [llm], [tts], [assign], defaults)
    errors.py               # EmceeError(Exception) base; CLI boundary catches it + HerderError
    station.py              # scan, readiness, package addressing
    package_io.py           # manifest read/validate/rewrite (atomic), package paths
    models.py               # ScriptNotes, DJAudioBlock, Assignment — emcee's own pydantic models
    scriptwrite.py          # LLM task: briefing + character -> verbatim script; guard
    presenters.py           # moved from llama (Presenter model + TOML load/save)
    speech_text.py          # moved from llama
    tts/                    # moved from llama: provider.py, voxtral.py, elevenlabs.py, fake.py, bed.py
    prompts/
      scriptwrite.md
  tests/
```

- **Dependencies:** `llama-herder`, `typer`, `numpy`, `lameenc` (all already in
  the monorepo's dependency set — no new third-party deps repo-wide; httpx and
  pydantic arrive via herder).
- **CLI:** `emcee run` (scan + batch), `emcee voice <package-path>` (one
  package; `--fresh <stem>` re-rolls named DJ clips, moved from `llama voice
  --fresh`), `emcee status` (station table), `emcee presenter
  add/list/show/remove` (moved verbatim from llama, storing under emcee's
  workspace), `emcee config init` (commented defaults, llama-config-init
  style). `--help` panels follow llama's ordered-panel convention.
- **Workspace:** `~/.emcee/` — `config.toml`, `presenters/*.toml`, and the
  pronunciation lexicon (`pronunciations.csv` seed copied from llama's data
  package into emcee's, since speech normalization moves).

## 2. Station model and choreography

- `[station] root` in emcee's config points at the delivered-packages folder
  (llama's deliver target). A **package** is any direct subdirectory containing
  a `manifest.json` with `schema_version >= 3`; v2 manifests are reported as
  `unsupported (v2 — re-deliver from llama)` and skipped, never modified.
- **Readiness (emcee's broadcast-ready):** script present (`dj_notes` block +
  `dj-notes.md`), DJ audio present (`dj_audio` block + files on disk),
  `broadcast.m3u` present, and every manifest track's audio file on disk.
  `emcee run` processes exactly the packages failing one of those legs;
  `emcee status` shows per-package state (`ready` / `pending` / `unsupported`)
  with reasons.
- **Re-delivery is the invalidation mechanism:** llama re-delivering a redone
  show replaces the package wholesale with a fresh unvoiced one; the next scan
  sees not-ready and re-voices. The per-segment TTS cache (unchanged, keyed
  text+voice+model+chunk) keeps unchanged segments from re-spending.
- **Failure semantics:** a script that still fails the guard after retry, or a
  TTS failure, fails that package only — logged with reasons, package left
  not-ready (partial outputs are not written), `emcee run` continues the batch
  and exits non-zero if any package failed. No hold queue, no state files:
  rerun after fixing the cause (usually upstream in llama, via its triage).

## 3. Scriptwriting

- **One LLM task, `scriptwrite`** (emcee's own herder task registry:
  `TASK_KEYS = ["scriptwrite"]`, `DEFAULT_TIERS = {"scriptwrite": "high"}`,
  `[llm]`/`[llm.scriptwrite]` config semantics identical to llama's, resolved
  through `herder.LLMSettings`).
- **Inputs**, all read from the package: `briefing.md` + `briefing.json`
  (primary source material), manifest `show`/`tracks`/`set_breaks` (the
  setlist), and the manifest `briefing.narration` directive. The prompt is a
  port of llama's `synthesize.md` (write-for-the-ear rules, segue-in-words,
  no-short-sentences, show-ID-every-break, one lead-in per non-encore set +
  outro) re-sourced from briefing + manifest instead of show.json + research.
- **Style:** `persona_style(presenter, title)` and `NEUTRAL_STYLE` move from
  llama's synthesize module **byte-for-byte** (they are the persona contract).
  Presenter + title come from assignment (§4); no assignment → neutral.
- **Output model `ScriptNotes`** (emcee-owned, shape-identical to llama's
  `DJNotes`: `context`, `set_intros` keyed by non-encore set, `outro`,
  `mentioned_songs`) — written to the package as the `dj_notes` manifest block
  and rendered `dj-notes.md` (port of `render_notes_md`).
- **Guard (deterministic, emcee-owned):** port of `factual_guard` checked
  against manifest tracks/set_breaks instead of `Show` — unknown
  `mentioned_songs` (normalize via a ported `normalize_song`), set_intros keys
  = exactly the non-encore sets, set-count claims in prose — **plus** the
  narration directive: under `vague`, any named song or any set-count claim in
  the prose fails the guard (the per-gap segment structure itself is physical —
  a lead-in clip per set gap exists in both modes; vague constrains what the
  text may assert, exactly as in llama today). Retry once
  with feedback (herder ladder escalation applies); then fail the package
  (§2 failure semantics).
- **Speech + audio:** `speech_text` normalization + lexicon, chunking, bed
  mixing, per-segment cache and `dj-audio/` emission are the moved llama code
  paths, driven by emcee: synthesize per-gap clips, write `dj_audio` block and
  `broadcast.m3u` (interleave logic ported from `manifest.py`'s
  `interleave_broadcast`/`broadcast_m3u_text`).
- **Manifest rewrite is atomic and additive:** read dict → validate v3 → set
  `dj_notes`/`dj_audio` → unique-temp atomic write. emcee never touches the
  music blocks, briefing block, or `schema_version`.

## 4. Presenters and assignment

- `presenters/<id>.toml` unchanged: `name`/`sex`/`character`, exactly one of
  `voice` XOR `voice_clone` (clone Voxtral-only), optional `bed`. Lives under
  `~/.emcee/presenters/`; `emcee presenter` CLI is llama's moved verbatim.
- **Assignment**, in emcee's config:

```toml
[assign]
default = "waldo"                 # optional station-default presenter

[assign.profiles.prime-dead]      # keyed by llama profile name (manifest source.profile)
presenter = "waldo"
title = "The Primal Dead Hour"
```

  Resolution: manifest `source.profile` → `[assign.profiles.<name>]` entry →
  else `[assign] default` → else no presenter (neutral narrator + station
  `[tts] voice`/`voice_clone`). A presenter owns the voice (its
  `voice`/`voice_clone`/`bed`), exactly as in llama today.
- `[tts]` config moves to emcee unchanged (enabled flag dropped — emcee's
  whole purpose is voicing, so TTS is always on; `backend`, `voice`,
  `voice_clone`, `model`, `api_key`, `chunk`, `bed`, `bed_gain_db` keep their
  semantics).

## 5. llama-side changes (the stamp, then the cut)

**The stamp (small, additive):** `Provenance` gains `profile: str | None`;
`process_show` receives the profile name from profile-driven runs (one-offs:
`None`); `run_package`/`build_manifest` write it as manifest `source.profile`.
No schema_version bump (additive optional field).

**The cut** — llama drops:

- `stages/synthesize.py` (brief is now the sole text stage), `presenters.py`,
  `speech_text.py`, `tts/` (whole package), the `voice` command, `redo`'s
  `--voice` handling, the `--script/--no-script` flags (nothing left to skip),
  `[tts]` config, `Profile.presenter`/`Profile.title`, Provenance's
  `script`/`voice`/`presenter`/`title` fields, and `pipeline.py`'s
  speech/bed/lexicon plumbing (`process_show` loses `script`, `voice`,
  `speech`, `chunk`, `bed`, `presenter`, `title` params).
- `SHOW_STAGE_ORDER` becomes `[select, gather, research, vet, brief, package]`;
  the `scripted` state, `dj-notes` artifacts, and `redo --from synthesize`
  disappear (`fix`/triage narration already targets `brief`).
  `data/pronunciations.csv` moves to emcee with the speech layer (llama's copy
  is deleted).
- `broadcast_readiness`, `derive_voiced`, `VOICE_BUNDLE_REASONS`, the
  `--broadcast-ready`/`--voiced` selectors and status columns, and the
  `broadcast-ready` line on `llama show` are removed. **Deliver's gate becomes
  package-complete + not-held** (manifest exists, every manifest track's audio
  file on disk, not held); `--allow-unvoiced` disappears.
- The manifest **schema keeps** `dj_notes`/`dj_audio` (emcee-written); llama's
  `Manifest` model retains them as passthrough-optional so a re-package of a
  show llama still owns doesn't need them — but llama code never writes them
  again. `DJNotes`/`DJAudio` models stay in llama's models.py solely as the
  contract schema for those blocks (documented as emcee-written).
- `package.py` reduces to its music half: the `speech`/dj-audio/broadcast.m3u
  code paths go; `playlist.m3u`, audio verification, briefing copy, research/
  reviews digests all stay.

## 6. Testing

- **emcee suite** (offline): fixture packages fabricated by a helper (v3
  manifest + briefing files + fake audio), fake TTS provider and herder's
  `FakeProvider` for scriptwrite; coverage: scan/readiness/unsupported-v2,
  assignment resolution chain, scriptwrite guard (all checks + vague), retry
  and failure semantics (no partial outputs, non-zero exit, batch continues),
  manifest rewrite atomicity/additivity, broadcast.m3u interleave, `--fresh`
  re-roll, presenter CLI round-trip, config parsing.
- **Guard test:** emcee never imports llama (scans `packages/emcee/src` and
  `packages/emcee/tests`, mirroring herder's).
- **llama suite:** voice/presenter/speech/tts tests move or die with their
  code; cut-verification tests assert no `llama.tts`/`speech_text`/
  `presenters` modules remain, deliver's new gate, the shortened stage order
  and state set, and that `source.profile` stamps correctly (profile run vs
  one-off).
- Full monorepo suite stays green from the repo root; emcee's suite also runs
  standalone (`pytest packages/emcee/tests -q`).

## 7. Docs, packaging, release

- `docs/station-brief.md`: the two-tool story — llama delivers unvoiced
  packages with briefings; emcee (or the station's own machinery) voices them;
  `dj_notes`/`dj_audio`/`broadcast.m3u` documented as emcee-written; `source.profile`
  documented.
- README: the monorepo root README stays the single entry point and gains an
  emcee section (no per-package READMEs); workflow.md rewrites
  the voice sections around `emcee run`; CLAUDE.md updated for the new
  architecture; emcee gets `config init`-embedded documentation like llama's.
- **Packaging/release:** `packaging/` + `.github/workflows/release.yml` build
  and sign an `emcee` binary alongside `llama` (PyInstaller spec per binary,
  same signing legs, both in SHA256SUMS). The next release is the first
  carrying the monorepo layout, manifest v3, AND the split binaries — verify
  the workflow end-to-end at release time.

## Out of scope

- Any llama→emcee invocation or shared runtime state; scheduler/streamer/
  flattener; Phish.in; publishing either dist to PyPI (names noted as
  unregistered — reserving them is a separate owner decision).
- Migration of pre-v3 or already-voiced packages.
- claude_cli `--json-schema` adoption in herder (still a noted improvement,
  still deferred).
- The deferred herder API polish items from sub-project 1's review (tracked in
  that SDD ledger; natural to fold into this sub-project's plan only if they
  block emcee's registry — otherwise they remain deferred).
