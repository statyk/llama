# emcee profile flow — task list (bounded change, design approved in chat 2026-10-02)

No written spec: this was approved as a bounded in-chat design. This file is
the SDD task list; the design text below is the authority.

## Global Constraints

- Run tests with `./.venv/bin/pytest -q` from the worktree root
  (`/Users/shawn/projects/llama/.claude/worktrees/emcee-profile-flow`). Baseline: 1980 passed.
- emcee must never import llama (enforced by `packages/emcee/tests/test_no_llama_imports.py`); llama must never import emcee.
- emcee validates no full manifest model: read manifests as raw dicts, tolerate missing keys.
- `resolve_assignment`'s three rules are the single source of truth for "which presenter": (1) `[assign.profiles.<manifest.source.profile>]` entry → that presenter + title; (2) else `[assign] default` → that presenter, no title; (3) else house narrator (no presenter). Any new code that reports a presenter must derive it from the same rules — no second implementation.
- Presenter ids compare **case-insensitively** wherever two ids are compared (the user's config says `BillyG`, the file is `billyg.toml`; macOS is case-insensitive).
- Presenter label strings (used by `run --dry-run` and `status`): an explicit profile assignment → `<id>`; the default → `<id> (default)`; no presenter → `house`.
- Follow existing code idiom: typer options, `typer.echo`, `EmceeError` taxonomy, atomic writes via existing helpers. Match surrounding comment density.
- Commit per task with a conventional-commit message ending with:
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`

## Task 1: emcee — shared selection helpers + `emcee run --profile / --assigned / --dry-run`

Files: `packages/emcee/src/emcee/process.py`, `packages/emcee/src/emcee/station.py`,
`packages/emcee/src/emcee/cli.py`, tests in `packages/emcee/tests/` (extend
`test_run_cmd.py`, `test_station.py`, `test_process.py` as fits).

1. **Pure assignment view.** Add to `process.py` a pure function
   `assignment_for(config, profile: str | None) -> AssignmentView` (a small frozen
   dataclass: `presenter: str | None`, `title: str | None`,
   `source: Literal["profile", "default", "house"]`) implementing the three rules
   WITHOUT loading any presenter TOML. Refactor `resolve_assignment` to call it and
   then `load_presenter` when `presenter` is set, so the rules live in one place.
   Behaviour of `resolve_assignment` must not change (its existing tests stay green).
   Add `presenter_label(view) -> str` producing the label strings from Global Constraints.
2. **Profile on PackageStatus.** Add `profile: str | None = None` to
   `station.PackageStatus`, populated from `manifest["source"]["profile"]` by both
   `station.scan` and `cli._scan_broad`. For `unsupported` rows read it best-effort
   from the raw JSON; for `error` rows set it only if the raw JSON parses and has it,
   else `None`. Never let reading the profile raise.
3. **`emcee run` options** (keep all existing behaviour when none are given):
   - `--profile NAME`, repeatable: only packages whose `profile` equals one of the
     names (exact match).
   - `--assigned`: only packages whose `assignment_for(...).source == "profile"`
     (i.e. skip ones that would fall to `[assign] default` or the house voice).
     Combined with `--profile`, a package must pass both.
   - When `--profile` or `--assigned` is given, `error`/`unsupported` rows whose profile
     is `None` are excluded from the run and NOT reported per-row; instead print one
     line `note: N package(s) skipped: manifest unreadable (see emcee status --list)`
     when N > 0. `error`/`unsupported` rows whose profile IS known and matches the
     filter are reported exactly as today. Rows that don't match the filter are
     silently skipped regardless of state.
   - `--dry-run`: for each selected `pending` package print
     `would voice: <slug>  <profile or (none)>  <presenter label>` and, when the
     view names a presenter whose `config.root / "presenters" / f"{id}.toml"` does
     not exist, append `  [missing presenters/<id>.toml]`. Then print
     `N package(s) would be voiced`. No LLM, TTS, or file writes of any kind
     (prove it in a test: e.g. the manifest bytes are unchanged and no provider is
     constructed). Error/unsupported rows are reported as in a real run; exit code
     follows the real run's rule (1 if any error row was reported), otherwise 0.
     `--force` is ignored under `--dry-run`.
   - Update `run`'s docstring to describe the new options.
4. Tests: each option alone, `--profile` repeated, `--profile` + `--assigned`,
   `--assigned` excluding a default-assigned profile, the dry-run output lines and
   the missing-presenter marker, the unreadable-manifest note, and that no-option
   behaviour is unchanged. Build fixtures with `tests/helpers.py`'s `build_package`.

## Task 2: emcee — record the presenter + `emcee status` summary/per-show views

Files: `packages/emcee/src/emcee/models.py`, `packages/llama/src/llama/models.py`,
`packages/emcee/src/emcee/process.py`, `packages/emcee/src/emcee/station.py`,
`packages/emcee/src/emcee/cli.py`, tests (`test_status_cmd.py`, `test_process.py`,
`test_station.py`, and the llama `test_the_cut.py` if a model test fits there).

Uses Task 1's `assignment_for`, `presenter_label`, and `PackageStatus.profile`.

1. **Record who voiced it.** Add `presenter: str | None = None` to emcee's
   `DJAudioBlock` and to llama's passthrough `DJAudio` (keep them shape-compatible;
   update the emcee models.py docstring line that cites llama's line numbers if it
   is now wrong). `process_package` sets it to the resolved presenter's `id`, or
   `None` for the house narrator, before `rewrite_manifest`. Because `model_dump`
   writes the key, a house-voiced manifest carries `"presenter": null`, which is
   distinguishable from a legacy manifest that lacks the key.
2. **voiced_by on PackageStatus.** Add `voiced_by: str | None = None` populated by
   both scan paths from the manifest's `dj_audio` block: `None` when `dj_audio` is
   null/absent (not voiced); `"?"` when `dj_audio` is a dict without a `presenter`
   key (legacy); `"house"` when the key is present and null; else the id string.
3. **`emcee status` views.**
   - No flags → **summary by profile** (new default). One row per profile, sorted by
     profile name, with rows for `(none)` (package has no profile) and `(unknown)`
     (manifest unreadable) last, each only when non-empty. Columns: profile,
     presenter (the `presenter_label` of `assignment_for(config, profile)`; blank for
     `(unknown)`), ready, pending, other (unsupported + error). Header row and a
     final total line. `no packages found` when empty, as today.
   - `--list` / `-l`, or any of `--profile NAME` (repeatable, exact match) /
     `--state STATE` (repeatable; ready|pending|unsupported|error) → **per-show
     table**, filtered by any given filters: columns slug, profile (`(none)` when
     None), state, voiced-by, reasons. Voiced-by cell: `-` when `voiced_by` is None;
     otherwise the `voiced_by` value, and when it is a known presenter id or
     `house` and it differs case-insensitively from the current assignment's
     presenter (house ↔ `None`), append ` (now: <current presenter id or house>)`.
     `?` never gets a drift annotation.
   - `--json` → always per-show (filters apply). Each object keeps `slug`, `state`,
     `reasons` and adds `profile`, `voiced_by` (same values as the dataclass field),
     `assigned_presenter` (id or null), `assignment_source`
     (`profile`|`default`|`house`).
   - Update the command docstring.
4. Tests: presenter recorded for an assigned, a default, and a house-voiced package;
   all four voiced_by states; summary rows/counts/labels including `(none)`; per-show
   via `--list`, via `--profile`, via `--state`; drift annotation incl. the
   case-insensitive non-drift (`BillyG` vs `billyg`); `--json` fields.
   Update existing `test_status_cmd.py` tests that assumed the old default table
   (they should use `--list` now) — do not delete their assertions.

## Task 3: llama — refuse to re-deliver over a voiced package; `--replace-voiced`

Files: `packages/llama/src/llama/cli.py`, `packages/llama/tests/test_deliver_cmd.py`,
`packages/emcee/src/emcee/station.py` + `packages/emcee/src/emcee/cli.py` (dot-dir skip),
emcee tests.

Background: `_deliver_one` does `shutil.copytree(pkg, out, dirs_exist_ok=True)`,
which overwrites `manifest.json` with llama's (`dj_notes`/`dj_audio` null), silently
un-voicing a show emcee already voiced while leaving `dj-notes.md`/`dj-audio/`
/`broadcast.m3u` behind. NOTE: `deliver --force` was deliberately REMOVED earlier
(it overrode the held gate) and `test_force_and_allow_unvoiced_options_no_longer_exist`
pins its absence — do NOT add `--force`; the new flag is `--replace-voiced`.

1. In `_deliver_one`, under the existing show lock and after the deliver gate passes:
   if `out / "manifest.json"` exists, parses as a JSON object, and its `dj_audio` is
   not None → the destination is voiced. Unparseable/non-object → treat as not voiced.
   - Voiced and not `replace_voiced` → raise `LlamaError` with message
     `refusing to deliver <slug>: <out> is already voiced by emcee; re-delivering would un-voice it (pass --replace-voiced to replace it with a fresh, unvoiced copy)`.
     Nothing on disk changes; no ledger row.
   - Voiced and `replace_voiced` → replace the destination wholesale: copytree the
     package to a sibling temp dir `target_dir / f".{name}.deliver-<uuid hex>"`, rename
     `out` to `target_dir / f".{name}.old-<uuid hex>"`, rename the temp dir to `out`,
     then `shutil.rmtree` the old dir. On failure before the swap, remove the temp
     dir and leave `out` untouched. Record the ledger row as today.
   - Not voiced (or no destination yet) → exactly today's behaviour, flag or not.
2. Add `--replace-voiced` to `deliver` (help: "Replace a destination emcee has already
   voiced with a fresh, unvoiced copy (discards its DJ script and audio)"), threaded
   through `_deliver_one` and `_deliver_batch`. In a batch the refusal is printed via
   the existing `LlamaError` arm and the batch continues. Update the deliver docstring.
3. emcee: the swap uses dot-prefixed sibling dirs that contain `manifest.json`, so
   `station.scan` and `cli._scan_broad` must skip directory entries whose name starts
   with `.`. Test that a `.x.deliver-…` dir with a manifest is not reported.
4. Tests (llama): refusal by name (exit 1, message, destination bytes unchanged incl.
   `dj-audio/`, no ledger row); `--replace-voiced` replaces it (manifest dj blocks null,
   `dj-audio/` and `dj-notes.md` gone, no leftover dot dirs, ledger row recorded);
   unvoiced existing destination still overlays as before; batch with one voiced
   refusal and one normal delivery continues; `--force` still absent (existing test).

## Task 4: backfill script + docs

Files: `scripts/backfill_voiced_by.py` (new), `scripts/test_backfill_voiced_by.py`
(new; `scripts` is in pytest testpaths — check how `scripts/` tests import their
module and follow that), `CLAUDE.md`.

1. `scripts/backfill_voiced_by.py [--station-root PATH] [--apply]`. It MAY import emcee
   (`load_config`, `Package`, `rewrite_manifest`, `DJAudioBlock`, `ScriptNotes`,
   `list_presenters`). Station root defaults to emcee config's `[station] root`.
   For every package directory (skip dot-dirs, skip dirs without manifest.json, skip
   unreadable manifests with a printed `skip <slug>: <reason>`) whose `dj_audio` is a
   dict WITHOUT a `presenter` key:
   - Gather the script text: every string value of `dj_notes`
     (`context`, `set_intros` values, `outro`).
   - For each loadable presenter (ignore `list_presenters` error entries), test whether
     its `name` occurs in the text as a whole-word, case-sensitive match
     (`re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text)`).
   - Exactly one presenter matches → `<slug>: <id>` and, with `--apply`, rewrite the
     manifest with `dj_audio.presenter = <id>`, keeping `dj_notes` and every other
     `dj_audio` field and every other manifest key unchanged (use emcee's
     `rewrite_manifest` with the existing blocks re-validated through the models).
   - Zero or 2+ matches → `<slug>: left as ? (<no presenter name found | ambiguous: a, b>)`, no write.
   - Without `--apply`, print a final `dry run: pass --apply to write` line and write nothing.
   - Packages that already carry the key, or are unvoiced, are ignored silently.
2. Tests: single match applied (and every other manifest byte-equivalent key preserved),
   dry run writes nothing, zero match, ambiguous match, whole-word (`K.C.` must not match
   inside another token; a name `Al` must not match `Alan`), already-recorded ignored.
3. `CLAUDE.md`: in the emcee "Run" commands bullet, document `emcee run --profile/
   --assigned/--dry-run`, `emcee status`'s summary default with `--list`/`--profile`/
   `--state`/`--json`, and the recorded `dj_audio.presenter` (null = house, absent =
   voiced before it was recorded); in the llama commands, document that `llama deliver`
   refuses over an emcee-voiced destination unless `--replace-voiced`; add the backfill
   script next to `stitch_m3u.py`. Keep it brief and in the file's existing voice.
