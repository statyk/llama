# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Implemented. The full pipeline (interpret through package) works offline
against the `fake` LLM backend and real archive.org fixtures; see
`docs/superpowers/plans/2026-07-14-llama.md` for the task-by-task
implementation plan this was built from. The approved design spec is
`docs/superpowers/specs/2026-07-14-llama-design.md`.
The repo also holds `transmitter` (playout, phases 1-3; not a released/signed
binary — `.github/workflows/release.yml` has no transmitter) and `antenna/`
(a Cloudflare Worker + static player).

## Where the detail lives

This file holds only what every session needs. The rest is in one `CLAUDE.md` per
component. Those load on their own when you read a file under that directory, but
**running a CLI or a script loads nothing, so read the file first**.

| Before running or changing | Read |
|---|---|
| `llama`: commands, pipeline, overrides, titles, junk filter, pacing, the adjudicator, domain gotchas | `packages/llama/CLAUDE.md` |
| `emcee`: commands, voicing, TTS, presenters | `packages/emcee/CLAUDE.md` |
| `transmitter`: playout service, scheduler | `packages/transmitter/CLAUDE.md` |
| `antenna/`: Worker, cost guard, metronome, player | `antenna/CLAUDE.md` |
| `herder`: LLM providers, model tiers, usage limits | `packages/herder/CLAUDE.md` |
| `scripts/`: one-off backfills, the bulk-apply campaign, replay and probe harnesses | `scripts/CLAUDE.md` |

## Rules that hold everywhere

Each is stated in full in the component's file.

- `emcee`, `transmitter` and `llama` never import each other; the delivered package on
  disk is the only contract.
- `show.json` is derived and never hand-edited. Change a show with `llama fix` or
  `llama triage`, which write `overrides.json`.
- `llama deliver --replace-voiced` discards the destination's DJ script and audio.
- Run one `emcee run` at a time against a station root. emcee takes the station lock
  (`<delivered>/.lma-station.lock`) per package, so llama's station writes refuse while a
  package is being voiced. An agent (no TTY) runs `emcee run --dry-run`, shows the plan,
  and passes `--yes` only after the operator approves.
- `scripts/bulk_apply.py` runs from the pinned worktree by path, never with a venv
  activated.

## Commands

- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
- Test: `pytest -q` (offline, deterministic). Single test: `pytest packages/llama/tests/test_setlist.py::test_parses_sets_segues_and_confidence -q`
  **In a git worktree, give the worktree its own `.venv` and run `./.venv/bin/pytest`.**
  The repo-root `.venv` installs llama editable against the *main* checkout, so a
  bare `pytest` from a worktree collects the worktree's tests but imports the main
  checkout's source — it silently tests the wrong code and still passes.
  **And never run a `.venv/bin/*` console script from a COPY of the tree.** `pytest`, `pip`, `llama`, `emcee` and `transmitter` are all shebanged with an absolute path to the original venv's interpreter, so from a copy they act on the original: `.venv/bin/pytest` tests the worktree instead of the copy (so a mutation you applied does nothing and the suite stays green), and `.venv/bin/pip install -e` reinstalls into the worktree's venv and repoints its `_editable_impl_*.pth` at your copy — poisoning every other process using that worktree, invisibly to `git status`. Use `python -m <tool>`, or shadow with `PYTHONPATH`. To check: `./.venv/bin/python -c "import llama; print(llama.__file__)"` must resolve inside the tree you meant to test.
- Live tests (real archive.org, no LLM): `pytest -m live -q`
- Refresh a fixture: `python scripts/capture_fixture.py <identifier>`

## What this is

Two Python CLIs — `llama` and `emcee` — that together carry an archive.org
Live Music Archive (LMA) recording all the way to air (the playout side,
`transmitter` + `antenna/`, is described in its own files). They ship as separate
signed binaries and know nothing of each other's internals; the only
contract between them is the delivered package on disk. Usage tilts heavily
toward Grateful Dead shows (two sets + encore).

`llama` finds concerts on the LMA, winnows them for quality, researches the
specific performance online, and emits a self-contained "show package"
(verified audio, m3u, manifest v3 with track titles/set breaks, vetted
research + reviews digest, and a required neutral vetted `briefing` for
scriptwriters) for an automated in-house radio station. `brief` is llama's
sole text stage — llama does not write DJ scripts, has no presenters, no
TTS, and no `[tts]`/presenter config. Its `deliver` gate is just: packaged,
not held for review, and every manifest track's audio file present on disk
— plus it refuses an emcee-voiced destination unless `--replace-voiced` (single
name only). After delivering it drops the library's own copy of the audio (the
station copy is the one that airs; archive.org is the re-fetch source), so
a delivered show in `~/.llama/shows/` normally has an empty `package/audio/`.

`emcee` is the station-side CLI that scripts and voices delivered packages. `transmitter` and
`antenna/` are the playout side, airing them as a live HLS stream.

## Architecture (the short version)

- **Staged pipeline over an on-disk workspace** (default `~/.llama/`):
  interpret → search (wide net) → winnow (quality gate + optional human gate)
  → select-recording → gather → research → vet (grounding check) →
  brief (always on) → package. Every stage reads/writes plain files;
  run-level artifacts live in a per-run directory, show-level artifacts in a
  canonical `shows/<slug>/` library (one dir per performance, reused across
  runs); stages write outputs only on success and are individually
  re-runnable (`llama redo <show> --from <stage>`). `brief` is llama's sole
  text stage — it emits a neutral vetted briefing (`briefing.md`/
  `briefing.json`) for scriptwriters — no flag, no config gate, factually
  guarded (retry-once-then-hold), and stamped with the `narration`
  directive from `overrides.json`. The show-package contract is **manifest
  v3**: a required `briefing` block (`file`, `json`, `narration`, `vetted`)
  alongside the existing fields; `package` copies both briefing files into
  `package/` and hard-fails if a show has no briefing artifacts. The
  manifest model also carries `dj_notes`/`dj_audio` fields, which llama
  always writes as `null` — they are **emcee-written passthrough blocks**,
  filled in station-side after delivery; llama itself never populates them.
  `stages/synthesize.py` (the in-house DJ script/voice path) was cut
  entirely in this split — scriptwriting and voicing moved wholesale to
  `emcee` (umbrella spec:
  `docs/superpowers/specs/2026-07-28-split-architecture-design.md`).
- **`awaiting_fix` and `campaign.json`** (bulk-apply; spec `docs/superpowers/specs/2026-10-25-bulk-apply-design.md`, "The `awaiting_fix` contract" and "The library side"): a STATION manifest may carry top-level `awaiting_fix: {reason, marked_at}` (absent or null = none), written only by `llama/station_mark.py` as a raw-JSON read-modify-write under the show lock (never llama's `Manifest` model, which has no such field; library packages never carry it). Any non-null value means not to be voiced and not to be aired. Per-show `<show>/campaign.json` is `{marks: [{at, reason, start_stage: gather|select, batch}], processed: {at, digests, manifest_sha256}|null, clears: [{at, outcome: equal|change accepted}]}`; a show is AWAITING FIX when `marks` is non-empty and `processed` is null or older than the last mark; an UNREADABLE record counts as awaiting (`status` shows it, `deliver` refuses `<slug>: cannot read campaign.json (<error>); check it by hand`, `reapply` fails the row retryably). `<show>/reuse-anchor.json` (`{identifier, tracks: [{filename, title}], written_at}`) is the pre-commit `show.json` track list that strict station reuse pairs against after a held outcome rewrote `show.json`. emcee has an `awaiting-fix` state: `emcee status` reason `awaiting fix from llama: <reason>` (`emcee status --state awaiting-fix`), `emcee run` prints `skip <slug>: awaiting fix from llama`, `emcee voice` and `run` refuse `awaiting fix from llama (<reason>); re-deliver from llama first`; a malformed mark (non-null, no usable `reason`) reads `awaiting fix from llama` / `awaiting fix from llama; re-deliver from llama first`; emcee's manifest rewrite preserves the field. transmitter treats a non-null `awaiting_fix` as not airable (see `packages/transmitter/CLAUDE.md`, the scheduler paragraph). Marking refuses while an `emcee` process runs.
- **Quality philosophy:** the LMA is a completist archive. Winnowing demands
  evidence a show is well received by people who were *not* there (LMA reviews
  are heavily attendance-biased). Suspicious output (unresolved track titles,
  duration mismatches, low-confidence setlist parse, a briefing contradicting
  the setlist, a long show with zero set breaks, research asserting songs or
  dates that don't belong to the show) marks a show `needs-review` rather
  than shipping; `--auto` runs skip such shows.

## Conventions

- Audio files (`*.mp3`, `*.flac`, `*.shn`) are gitignored; never commit audio.
  One exception: `packages/emcee/src/emcee/data/preflight_en.wav`, the ~2.6 s
  bundled check clip for the verification preflight (provenance in
  `docs/superpowers/2026-10-12-mlx-audio-calibration.md`).
- Test fixtures are captured real archive.org API responses (gd73-06-10 is the
  canonical one). Pipeline tests use the `fake` LLM backend and run offline;
  the only live end-to-end test is manual/opt-in.
