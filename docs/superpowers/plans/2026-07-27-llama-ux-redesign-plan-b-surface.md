# UX redesign Plan B — Surface Re-cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-cut the CLI command surface to the spec's show-centric tree — `get`,
`artists`, `status`, `show`, `pipeline`, `triage`, `fix`, `redo`, `voice`, `deliver`,
`rm`, `suppress`, `unsuppress`, and the `run`/`profile`/`presenter`/`history`/`config`
namespaces — rewriting the CLI tests and the docs command reference to match.

**Architecture:** Pure command-layer work in `src/llama/cli.py`, consuming the
foundations from Plan A (`cli_select`, `sessions`, `catalog.deliver_refusals` /
`remove_show` / `recording_info` / `library_performance_ids`, `Ledger` helpers,
`unique_run_name`). The pipeline, stages, workspace layout, `overrides.json`
semantics, and LLM/TTS layers are untouched. Sequencing is add-before-remove: `fix`
and `triage` land before `show` is stripped; `get` lands before `find`/`profile run`
are deleted; the `run` namespace lands before `run`/`review` are deleted — so every
capability exists at every commit and the tree stays green throughout.

**Tech Stack:** Python ≥3.11, Typer, Pydantic v2, pytest + `typer.testing.CliRunner`
(offline, `fake` LLM backend). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-27-llama-ux-redesign-design.md` (approved) —
read it in full before starting; the per-command sections (§§3-11) are the contract.

**HARD DEPENDENCY: Plan A** (`2026-07-27-llama-ux-redesign-plan-a-foundations.md`)
must be complete and merged first. Every task below assumes its interfaces exist.

## Global Constraints

- **Backward compatibility is explicitly NOT a goal** — no aliases, no deprecation
  shims, no migration. Old commands/flags are deleted, not hidden.
- Pipeline tests must keep passing untouched. CLI tests are rewritten per task; a
  task that deletes a command deletes/rewrites its tests in the same task.
- One selector implementation: every selector-capable command goes through
  `cli_select.build_selector`/`apply_selector`/`split_held`. No command re-implements
  filtering; acting commands (`triage` excepted per spec §2) enforce the held opt-in
  via `split_held` + `HELD_NOTE`.
- Exact user-facing strings specified here and in the spec (refusal messages, echo
  lines, hints) are contracts — assert them verbatim.
- Read-only commands (`status`, `show`, `pipeline`, listings) never prompt and never
  write. Acting batches print a plan and confirm (`--yes` skips); per-show failures
  print `FAILED <slug>: …` and continue.
- Holds are cleared only via `fix`/`triage` (real fix self-clears, or `--overrule`).
  No other bypass anywhere; `deliver` has no hold override.
- Mid-plan cosmetic transients are acceptable within the branch (e.g. Task 5's
  attention hints name `llama run approve` before Task 12 creates it) but the final
  state must be exactly the spec's tree — Task 15 sweeps.
- Commit after every task (conventional prefixes + project trailers); full suite
  green before every commit.

## Command tree (target — spec §1)

```
Acquire        get · artists
Watch          status · show · pipeline
Fix & ship     triage · fix · redo · voice · deliver · rm · suppress · unsuppress
Sessions & config   run (list|approve|resume|rm) · profile (add|list|show|remove|artists)
                    · presenter (add|list|show|remove) · history (list) · config (init)
```

Deleted by the end: `find`, `review`, root `run` command, `runs`, `version` command,
`ledger add/remove` (namespace renamed `history`), `show`'s set form and edit flags,
`deliver --force`, `run --stage/--force`.

---

### Task 1: Harness — `--config` to the app callback, drop `version`, panels, `artists --include-junk`

**Files:**
- Modify: `src/llama/cli.py` (callback, `_setup`, every command's `config_path`
  param, `_COMMAND_ORDER`/panels, `artists`), `tests/conftest.py` (invoke helper)
- Test: sweep all CLI tests; extend `tests/test_cli.py`

**Interfaces:**
- The app callback (`cli.py:77-87`) gains
  `config: Path = typer.Option(None, "--config", help="Config file (default ~/.llama/config.toml)")`
  stored in a module-level holder; `_setup()` (`cli.py:98`) becomes zero-argument and
  reads it. Every command drops its `config_path` parameter. Supported spelling:
  `llama --config PATH <command> ...`. Exception: `config init` keeps its own
  `--config` (it means *target file to write*, not *config to load* — `cli.py:1172`);
  leave it and its help text alone.
- The `version` command (`cli.py:90-95`) is deleted; `--version` on the callback
  stays.
- Panels become the spec's four (spec §1): `Acquire`, `Watch`, `Fix & ship`,
  `Sessions & config`. Update `_COMMAND_ORDER` (`cli.py:40`) to the full target-tree
  order (names not yet existing are harmless — `OrderedPanelGroup` sorts unknowns
  last); update each existing command/sub-app's `rich_help_panel` to its target
  panel (`artists`→Acquire, `status`/`show`→Watch, `redo`/`deliver`→Fix & ship,
  `profile`/`presenter`/`config`/`ledger`→Sessions & config; `find`/`run`/`review`/
  `runs` keep a panel until their deletion tasks).
- `artists --all` → `--include-junk` (same behavior, `cli.py:357`).
- `tests/conftest.py` gains the helper every rewritten CLI test uses:

```python
def cli_invoke(cfg_path, *args):
    """Invoke the app with the callback-level --config."""
    from typer.testing import CliRunner
    import llama.cli as cli
    return CliRunner().invoke(cli.app, ["--config", str(cfg_path), *args])
```

- [ ] **Step 1: Write/adjust the failing tests** — in `tests/test_cli.py`: `--version`
  works; `version` is no longer a command (`invoke(app, ["version"])` exits non-zero
  with "No such command"); `llama --config <cfg> status` works;
  `llama status --config <cfg>` now fails (option moved); `artists --include-junk`
  accepted, `--all` rejected; `--help` shows the four panel titles.
- [ ] **Step 2: Run to verify the new assertions fail** — `pytest tests/test_cli.py -q`.
- [ ] **Step 3: Implement** — callback option + module global + zero-arg `_setup()`;
  mechanical sweep removing `config_path` from all commands; delete `version`;
  panels; `--include-junk`.
- [ ] **Step 4: Sweep the existing CLI tests** — mechanically rewrite every
  invocation from `["cmd", ..., "--config", cfg]` to `["--config", cfg, "cmd", ...]`
  (or the `cli_invoke` helper). Touches `tests/test_cli.py`,
  `test_cli_commands.py`, `test_cli_voice.py`, `test_cli_errors.py`,
  `test_broadcast_ready.py`, `test_profiles.py`, and any other CliRunner user
  (grep `"--config"` under `tests/`).
- [ ] **Step 5: Run the full suite** — `pytest -q`, Expected: PASS.
- [ ] **Step 6: Commit** — `refactor: config on the app callback; drop version cmd; target panels`

---

### Task 2: `fix` — the override editor that applies its own redo

**Files:**
- Modify: `src/llama/cli.py` (new command; reuse `_edit_overrides` :504,
  `_resolve_exclude_tokens` :538, `_clear_hold` :560, `_redo_show` :953)
- Test: create `tests/test_fix.py`

**Interfaces (spec §6.2):** `llama fix <show> <edit-flags> [--no-run]` — single-show
only; at least one edit flag required (bare `fix <show>` errors:
`nothing to fix: give an edit flag (see --help), or inspect with: llama show <show>`).

| Flag | Maps to (today) | Stage |
|---|---|---|
| `--exclude FILE\|N` (repeatable) | `show --exclude` | gather |
| `--unexclude FILE\|N` (repeatable) | `show --include` | gather |
| `--set-venue` / `--set-city` / `--set-date` | same names | gather |
| `--set-title N="…"` (repeatable) | `show --title` | gather |
| `--clear-title N` / `--set-breaks "9,17"` / `--clear-set-breaks` | same names | gather |
| `--narration vague\|full` (enum `NarrationMode`) | `show --vague`/`--full` | synthesize |
| `--overrule` | `show --clear` | package |

- Stage precedence (earliest wins when combined) is today's line verbatim
  (`cli.py:827`): gather if any exclude/unexclude/metadata, else synthesize if
  narration, else package.
- Hold semantics unchanged: `--narration vague` and `--overrule` call `_clear_hold`;
  excludes/metadata never pre-clear (re-gather decides). `--narration full` sets the
  override without clearing. `--overrule` on a non-held show: no-op + note
  `not held; nothing to overrule`.
- **Applies by default**: after edits, re-resolve the entry and run
  `_redo_show(..., stage)`; print `packaged: {pkg}` / `still held: {slug}`.
  `--no-run` prints the per-edit confirmations then
  `staged; next: llama redo {slug} --from {stage}`.
- Input validation ported verbatim from `show` (`cli.py:754-773`): title spec shape,
  numeric clear-title, numeric comma breaks. Panel: `Fix & ship`.

- [ ] **Step 1: Write the failing tests** — `tests/test_fix.py` (stub `_redo_show`
  via monkeypatch, per `tests/test_broadcast_ready.py::test_redo_broadcast_ready_selector`):
  each flag writes the expected `overrides.json` content; renamed spellings exist and
  `--include`/`--title`/`--vague`/`--full`/`--clear` do NOT (invoke errors);
  auto-run fires with the right stage per flag and earliest-stage on combos
  (`--exclude 3 --narration vague` → gather); `--no-run` fires nothing and prints the
  staged hint; `--narration vague`/`--overrule` clear the hold, `--exclude` doesn't;
  bare `fix` errors; bad inputs error cleanly; `--narration nonsense` is a Typer enum
  error listing `vague|full`.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** — new `fix` command assembled from the existing helpers;
  do not modify `show` yet (both expose editing until Task 4).
- [ ] **Step 4: Run `tests/test_fix.py`, then the full suite** — PASS.
- [ ] **Step 5: Commit** — `feat: llama fix — override edits with auto-applied redo`

---

### Task 3: `triage` — the named interactive walkthrough

**Files:**
- Modify: `src/llama/cli.py` (new command; evolve `_interactive_resolve` :596,
  `_pick_excludes` :588)
- Test: create `tests/test_triage.py`

**Interfaces (spec §6.1):** `llama triage [SELECTOR]` — panel `Fix & ship`.

- Requires a TTY: when `not sys.stdin.isatty()`, error
  `triage is interactive; use 'llama status' or 'llama show' for scripted reads`
  (exit 1). Never TTY-modal about *which job* it does.
- Default selector `--held`; accepts the full shared selector set
  (`cli_select.build_selector`). Held matches get the resolve loop; non-held matches
  print (`_print_show_entry`) and skip. The held opt-in rule does NOT apply (spec §2:
  triage is the exception — resolution is its purpose).
- Per held show: print the full inspection block **including the archive-URL block**
  (Task 4 adds `_print_recording_info`; until then call `catalog.recording_info`
  directly and print `url` + considered lines — same formatter, defined once and
  shared with Task 4), then prompt:
  `[e]xclude tracks / [m]etadata / [v]ague / [o]verrule / [s]kip / [q]uit`
- Actions (each ends with re-resolve + `packaged: …` / `still held: {slug}` before
  advancing, as today `cli.py:623-625`):
  - `e` — numbered track list, pick indices (`_pick_excludes`), write excludes, redo
    from gather.
  - `m` — NEW mini-editor: sequential prompts, each showing the current effective
    value, empty = keep: `venue`, `city`, `date (YYYY-MM-DD)`,
    `title overrides (N=Title, comma-separated)`, `set breaks (e.g. 9,17)`.
    Validation identical to `fix`'s flags; on any change write overrides and redo
    from gather; nothing changed → back to the prompt.
  - `v` — narration=vague + clear hold + redo from synthesize.
  - `o` — clear hold + redo from package (renamed from today's `c`; `c` is no longer
    accepted).
  - `s`/empty — next; `q` — stop.

- [ ] **Step 1: Write the failing tests** — `tests/test_triage.py`: scripted stdin
  (`CliRunner.invoke(..., input=...)`) with `_redo_show` stubbed; a pytest fixture
  monkeypatching `sys.stdin.isatty` to `True` for interactive cases. Cover: off-TTY
  errors with the exact message; default selection walks held only; broader selector
  (`--state packaged --held`… use two shows) prints-and-skips non-held; each of
  e/m/v/o/s/q does its documented thing (assert overrides written + stage passed to
  the stub); `m` round-trips venue/date/title/breaks and empty-input keeps values;
  `o` accepted, `c` rejected ("unrecognized"); URL line appears in the header.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** — rename/extend `_interactive_resolve` (new prompt
  string, `[m]` branch, `[o]` key), a `_metadata_editor(entry) -> bool` helper, the
  `triage` command wiring selector → loop.
- [ ] **Step 4: Full suite** — PASS (flagless `show` still has its old behavior;
  removed next task).
- [ ] **Step 5: Commit** — `feat: llama triage — interactive held-show walkthrough with metadata editing`

---

### Task 4: `show` — strictly read-only, `--json`, archive URLs

**Files:**
- Modify: `src/llama/cli.py` (`show` :694-833 rewritten; `_print_show_entry` :628
  extended)
- Test: rewrite `show` coverage into `tests/test_show_cmd.py`; prune old
  `show`-editing/set-form tests from `test_cli_commands.py`/`test_cli.py`

**Interfaces (spec §5.2, §10):** `llama show <show> [--tracks] [--json]` — panel
`Watch`. Positional name **required**. All set-form selectors, all edit flags,
`--apply`, and the TTY-interactive branch are removed from `show` (now owned by
`status`/`triage`/`fix`).

- Never prompts, never edits — delete the `cli.py:780-787` special-casing outright.
- `_print_show_entry` changes:
  - after the `recording:` line, the archive-URL block via `catalog.recording_info`
    (exact format, spec §10):

    ```
    recording: {identifier}  ({n} tracks)
      https://archive.org/details/{identifier}
    considered:
      {identifier:<44} {score:.1f}
    ```

    `considered:` omitted when empty; both omitted when `recording_info` is `None`.
  - the overrule hint (`cli.py:680`) becomes
    `to overrule after inspecting: llama fix {slug} --overrule`.
  - a show with no `show.json` no longer hard-errors (`cli.py:630-632`): print
    slug/state/path + the stages table + the URL block when `selection.json` exists,
    and skip the identity/overrides/needs-review sections.
- `--json`: one object —
  `{slug, state, flags, artist, date, venue, city, identifier, archive_url,
  considered: [{identifier, score, lineage, kept_tracks}], path, run, voiced,
  broadcast_ready, broadcast_reasons, needs_review,
  overrides: {exclude, narration, venue, city, date, titles, set_breaks},
  stages: {label: age_days|null}}`; `tracks` included when `--tracks`. Fields absent
  from disk are `null`.

- [ ] **Step 1: Write the failing tests** — `tests/test_show_cmd.py`: URL + considered
  block (scores sorted desc, chosen excluded, single-recording → no considered
  block); read-only guarantee — a held show with `isatty` monkeypatched `True` never
  prompts (no prompt text, exit 0); `--tracks`; `--json` schema spot-checks incl.
  `broadcast_reasons` and overrides; `show` with selectors (`show --held`) is a
  usage error; missing-name is a usage error; pre-`show.json` show prints state
  instead of erroring; `fix --overrule` hint text.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement**; delete the now-dead set-form/edit code paths from
  `show` (the helpers stay — `fix`/`triage` use them).
- [ ] **Step 4: Prune obsolete tests** — remove/relocate old `show` set-form and
  edit-flag tests (their behaviors now live in `test_fix.py`/`test_triage.py`/
  `status` tests).
- [ ] **Step 5: Full suite** — PASS.
- [ ] **Step 6: Commit** — `feat!: llama show is strictly read-only with archive URLs and --json`

---

### Task 5: `status` re-cut — shared selectors, `--by-run`, attention list; delete `runs`

**Files:**
- Modify: `src/llama/cli.py` (`status` :1067-1139 rewired; `runs` :1142-1165 deleted)
- Test: rewrite into `tests/test_status_cmd.py`; prune `runs` tests

**Interfaces (spec §5.1):** `llama status [SELECTOR] [--all] [--by-run] [--json]` —
panel `Watch`; read-only class (no held opt-in).

- Selector flags come from the shared vocabulary (`--state` as the `ShowState` enum,
  repeatable; `--held`/`--packaged` sugar; `--voiced/--unvoiced`;
  `--broadcast-ready`; `--artist`; `--run`), reconciled via
  `cli_select.build_selector` + `apply_selector`. Row format, held-first sort,
  marks, and the recent-delivered tail (`--all`) are unchanged.
- **Attention header** (before the table, human view only, whenever
  `sessions.attention_sessions(root)` is non-empty):

  ```
  sessions needing attention:
    {id:<36} {state:<18} llama run approve {id}   # awaiting-approval
    {id:<36} {state:<18} llama run resume {id}    # incomplete
  ```

  (Hint command chosen by state. These commands land in Task 12 — acceptable
  transient, see Global Constraints.)
- **`--by-run`**: absorbs `runs` — one row per session dir (id, per-state show
  counts via provenance grouping, query) — port the body of `runs`
  (`cli.py:1147-1165`). Mutually exclusive with selector flags and `--all`
  (usage error).
- **`--json`**: now an object `{"sessions": [...], "shows": [...]}` — `sessions`
  from `iter_sessions` where state != complete (`[{id, state, updated_at, query,
  profile}]`), `shows` rows keep today's fields (`cli.py:1113-1120`). With
  `--by-run`: `{"sessions": [...], "runs": [{id, query, states: {state: n}}]}`.
- Delete the `runs` command and its tests.

- [ ] **Step 1: Write the failing tests** — `tests/test_status_cmd.py`: enum `--state`
  rejects a typo listing legal values; `--state held --state packaged` ORs; sugar ≡
  enum; attention header appears with an awaiting + an incomplete session (build via
  `sessions` helpers) and is absent when all complete; `--by-run` rollup matches the
  old `runs` content; `--by-run --held` errors; `--json` object shape (sessions +
  shows keys; by-run variant); `runs` is gone ("No such command").
- [ ] **Step 2-4: fail → implement → prune old `status`/`runs` tests.**
- [ ] **Step 5: Full suite** — PASS.
- [ ] **Step 6: Commit** — `feat!: status absorbs runs (--by-run), session attention list, selector enum`

---

### Task 6: `redo` re-cut — one re-execution verb (`--run` session scope, renames)

**Files:**
- Modify: `src/llama/cli.py` (`redo` :998-1064 rewritten; `run` command loses
  `--stage`/`--force` — moved here)
- Test: rewrite into `tests/test_redo_cmd.py`

**Interfaces (spec §7.1):**
`llama redo <show | SELECTOR> --from STAGE [--redo-research] [--script/--no-script]
[--voice/--no-voice] [--yes]`, plus `--run SESSION` session scope. Panel `Fix & ship`.

- Three addressing forms; exactly one of {positional, `--run`, other selectors}
  (`--run` combined with other selector flags is an error in this re-cut; positional
  + any selector is an error, as today):
  1. positional show — `_redo_show` unchanged; stage ∈
     `select|gather|research|vet|synthesize|package`; naming a held show is
     implicit opt-in (spec §2).
  2. selector batch — shared layer; `split_held` + `HELD_NOTE`; plan/confirm/`--yes`;
     per-show failure isolation (as `cli.py:1045-1051`).
  3. `--run SESSION`:
     - `--from search|winnow` (valid ONLY with `--run`): resolve via `resolve_run`;
       if the doomed shortlist carries approvals, confirm
       `this rebuilds the shortlist and discards the approvals recorded on it`
       (today `cli.py:414-419`); delete downstream run artifacts
       (`candidates.json`+`shortlist.json` for search; `shortlist.json` for winnow —
       today `cli.py:420-426`); re-run `_execute` with the persisted criteria
       (auto, presenter/title/voice from criteria as `run` does today
       `cli.py:411-440`).
     - `--from <show-level>`: batch over that session's shows ≡ selector form with
       only the run filter.
- `--redo-research` replaces `--with-research` (same `keep_research` logic,
  `cli.py:968`; old spelling gone).
- Stage validation lists the legal set for the form used:
  `unknown stage 'X'; valid here: ...` (run-level stages rejected without `--run`,
  naming the rule).

- [ ] **Step 1: Write the failing tests** — `tests/test_redo_cmd.py` (stub
  `_redo_show` and `_execute`): form exclusivity errors; stage validation per form;
  `--run X --from search` deletes candidates+shortlist, confirms on recorded
  approvals (input-driven), declines cleanly, and calls `_execute`; `--from winnow`
  deletes only the shortlist; `--run X --from package` batches exactly that run's
  shows; selector batch drops held with `HELD_NOTE` unless `--held`; positional held
  show runs; `--redo-research` accepted, `--with-research` gone; batch plan/`--yes`.
- [ ] **Step 2-3: fail → implement.** Strip `--stage`/`--force` (and the
  approvals-wipe block) out of the root `run` command in the same edit so the logic
  lives in exactly one place; `run` keeps resume behavior until Task 12.
- [ ] **Step 4: Rewrite affected old tests** (`run --stage` tests move here as
  `redo --run` tests).
- [ ] **Step 5: Full suite** — PASS.
- [ ] **Step 6: Commit** — `feat!: redo owns all re-execution; --run session scope; --redo-research`

---

### Task 7: `voice` — TTS as a verb

**Files:**
- Modify: `src/llama/cli.py` (new command)
- Test: create `tests/test_voice_cmd.py` (fold in what `test_cli_voice.py` covers at
  the command layer; keep its provider-level tests where they are)

**Interfaces (spec §7.2):** `llama voice <show | SELECTOR> [--off] [--yes]` — panel
`Fix & ship`; acting class. Pure sugar: single show → `_redo_show(entry, "package",
voice=not off)`; selector batch → same per show with plan/confirm and held opt-in.
Bare `voice` errors: `give a show or a selector (e.g. --unvoiced)`. Help text owns
the stamped-voice replay rules (spec §7.2): replays the stamp when one exists (clone
edits live, preset changes need a fresh stamp), house `[tts]` voice otherwise,
`--off` always wins.

- [ ] **Step 1: Write the failing tests** — stub `_redo_show`, assert it is called
  with `from_stage="package"` and `voice=True` (default) / `voice=False` (`--off`)
  for single and selector forms; `voice --unvoiced --yes` hits exactly the unvoiced
  packaged shows; held dropped with note unless `--held`; bare invocation errors;
  `voice --help` mentions "stamped".
- [ ] **Step 2-4: fail → implement → full suite.**
- [ ] **Step 5: Commit** — `feat: llama voice — first-class TTS verb over redo --from package`

---

### Task 8: `deliver` re-cut — broadcast-ready gate, `--allow-unvoiced`, no `--force`

**Files:**
- Modify: `src/llama/cli.py` (`deliver` :900-950 + `_deliver_one` :867 rewritten)
- Test: rewrite into `tests/test_deliver_cmd.py` (absorb the deliver rows of
  `test_broadcast_ready.py`)

**Interfaces (spec §7.3):**
`llama deliver <show | SELECTOR> [--dest DIR] [--allow-unvoiced] [--yes]` — panel
`Fix & ship`.

- Per-show gate (single and batch): `catalog.deliver_refusals(entry.ws,
  allow_unvoiced)`; empty → copytree `package/` + record `delivered` (mechanics
  unchanged from `_deliver_one`); else refuse with:

  ```
  refusing to deliver {slug}: {"; ".join(reasons)}
  ```

  plus one pointer line by category (first match wins):
  - any reason == `held for review` → `  resolve it: llama triage {slug}`
  - `not packaged` or `audio files missing` → `  re-package: llama redo {slug} --from package`
  - otherwise (voice bundle) → `  voice it: llama voice {slug}  (or --allow-unvoiced to ship music-only)`
- `--force` is deleted. The old needs-review-JSON check inside `_deliver_one`
  (`cli.py:879-884`) is deleted — the refusal classifier is the single gate.
- Batch: shared selectors; `split_held`+note applies at selection; a held show that
  still reaches the gate (explicit `--held`) is refused per show (defense in depth,
  spec §7.3). Single refusal exits 1; batch refusals print per show and continue.
- `--allow-unvoiced` carries no extra prompt (the flag is the consent; batch plan
  confirm still applies).

- [ ] **Step 1: Write the failing tests** — table-driven over `build_ready` knobs:
  ready → delivered (+ledger row asserted); unvoiced-bundle blocked without /
  shipped with `--allow-unvoiced`; held and missing-audio and unpackaged refused
  even with `--allow-unvoiced`, exact message + pointer lines; `--force` unknown;
  `deliver --broadcast-ready --yes` ships only ready shows; single refusal exit
  code 1.
- [ ] **Step 2-4: fail → implement → full suite.**
- [ ] **Step 5: Commit** — `feat!: deliver requires broadcast-ready; --allow-unvoiced sole exception`

---

### Task 9: `rm` — delete a show with intentional history

**Files:**
- Modify: `src/llama/cli.py` (new command)
- Test: create `tests/test_rm_cmd.py`

**Interfaces (spec §8.1):**
`llama rm <show | SELECTOR> [--forget | --suppress] [--yes]` — panel `Fix & ship`;
acting class (held opt-in for selectors; `rm --held` is the explicit junk-hold
purge).

- Confirmation by default: print each dir to delete plus its disposition line, then
  `Proceed? [y/N]`; `--yes` skips. Then per show call `catalog.remove_show(entry,
  ledger, forget=..., suppress=...)` and echo its returned lines verbatim.
- `--forget`/`--suppress` mutual exclusion and no-pid errors surface from the
  machinery as clean `error:` output (the `LlamaError` boundary, `cli.py:1413`).

- [ ] **Step 1: Write the failing tests** — single show default: prompt shown,
  declining deletes nothing; `--yes` deletes and echoes the disposition (assert the
  Plan A echo strings appear); `--forget`/`--suppress` behaviors visible in ledger;
  both flags → error; selector batch (`rm --state selected --yes`) removes exactly
  the matches; held excluded from `rm --artist ...` with note, included with
  `--held`.
- [ ] **Step 2-4: fail → implement → full suite.**
- [ ] **Step 5: Commit** — `feat: llama rm — show deletion with explicit history dispositions`

---

### Task 10: `suppress`/`unsuppress` + `history` namespace (delete `ledger add/remove`)

**Files:**
- Modify: `src/llama/cli.py` (two new commands; `ledger_app` → `history`; delete
  `ledger add`/`ledger remove` :1391-1410; rework `ledger list` :1384)
- Test: create `tests/test_history_cmd.py`

**Interfaces (spec §8.2, §11):**
- `llama suppress <show-or-performance-id>` — resolve via `resolve_show` first
  (metadata from show.json/provenance); on no match, accept a raw id iff
  `util.parse_performance_id` parses it (artist=collection, date=date-part), else
  the `CatalogError` propagates. Appends
  `LedgerEntry(status="rejected", run="manual")`; echo
  `suppressed: {pid}`. No prompt (reversible).
- `llama unsuppress <show-or-performance-id>` — same resolution;
  `ledger.remove_status(pid, "rejected")`; echo `removed {n} rejected row(s) for {pid}`
  (n=0 is a clean no-op message, exit 0).
- `history` namespace (renamed from `ledger`; sub-app help: "Dispositions for shows
  no longer on disk; the library covers what's on disk"):
  `history list [--log] [--json]` — default prints `latest_dispositions()`:
  `{recorded_at[:10]}  {status:9s}  {performance_id}  ({run})`; `--log` prints every
  row (today's format, `cli.py:1388`); `--json` emits the corresponding row dicts
  `[{performance_id, status, run, recorded_at}]`.
- `ledger add`/`ledger remove` and the `ledger` name are deleted.

- [ ] **Step 1: Write the failing tests** — suppress on-disk (metadata from
  show.json) and off-disk (`GratefulDead/1980-05-16` → artist/date derived;
  `not-a-pid` errors); suppress→unsuppress round-trip leaves other statuses intact;
  unsuppress with nothing to remove exits 0; `history list` collapses to latest
  disposition, `--log` shows the trail, `--json` both forms; `ledger` command gone.
- [ ] **Step 2-4: fail → implement → full suite** (prune old ledger-cmd tests).
- [ ] **Step 5: Commit** — `feat!: suppress/unsuppress verbs; ledger renamed history (list-only)`

---

### Task 11: `get` — one acquisition verb (+ `--plan`); delete `find` and `profile run`

**Files:**
- Modify: `src/llama/cli.py` (new `get`; `_execute` gains `plan`; delete `find`
  :287-346 and `profile_run` :1251-1280)
- Test: create `tests/test_get_cmd.py` (absorb `find`/`profile run` CLI tests)

**Interfaces (spec §3):**

```
llama get "query"        [--limit N] [--auto] [--plan] [--name NAME]
                         [--script/--no-script] [--voice/--no-voice]
                         [--artist-cap F] [--min-score F] [--year-cap F]
                         [--full-rationale]
llama get --profile NAME [--auto] [--plan] [--full-rationale]
```

- Exactly one of positional query / `--profile` (usage error otherwise). Panel
  `Acquire`.
- Query mode: port `find`'s body verbatim (interpret → flag-stamp into criteria →
  `_execute`), with `--name` replacing `--run-name` (still routed through
  `unique_run_name` when unset) and `script` declared `Optional[bool] = None`
  (None→True in query mode) so explicit use is detectable.
- Profile mode: port `profile_run`'s body (profile load, presenter/voice resolution,
  criteria stamping incl. `profile=name` from Plan A). Tuning flags
  (`--limit --name --script/--no-script --voice/--no-voice --artist-cap --min-score
  --year-cap`) given alongside `--profile` error:
  `set these on the profile: {flags}` (exit 1).
- `--plan` (both modes, beats `--auto`): `_execute` gains `plan: bool = False`;
  after the shortlist prints (`cli.py:243`), when `plan`: `mark_awaiting(ws)`, echo

  ```
  shortlist ready — nothing processed.
  to approve & process:  llama run approve {ws.name}
  to discard:            llama run rm {ws.name}
  ```

  and return — before the approval prompt, `choose_entries`, and any
  `process_show`.
- The gate-stop echo (`cli.py:256`) becomes
  `Shortlist awaits review: llama run approve {ws.name}` (name, not path).
- Delete `find` and `profile run` (+ their tests; port the coverage).

- [ ] **Step 1: Write the failing tests** — query/`--profile` exclusivity; profile
  mode rejects tuning flags with the exact message; `--plan` stops after winnow
  (stub `process_show`/`choose_entries`, assert never called), writes
  `awaiting-approval`, prints both hint lines; second same-day `get` of one query
  gets `-2` (via `unique_run_name`); flag-stamping behavior ported (reuse old `find`
  test assertions); `find` and `profile run` gone.
- [ ] **Step 2-4: fail → implement → full suite.**
- [ ] **Step 5: Commit** — `feat!: llama get replaces find/profile run; --plan cheap preview`

---

### Task 12: `run` namespace — `list` / `approve` / `resume` / `rm`; delete `review` and the root `run`

**Files:**
- Modify: `src/llama/cli.py` (new `run_app` sub-app; delete root `run` :383-440 and
  `review` :443-486)
- Test: create `tests/test_run_namespace.py` (absorb `review`/`run` CLI tests)

**Interfaces (spec §4):** sub-app `run` (help: "Acquisition sessions — they surface
only while awaiting approval or incomplete"), panel `Sessions & config`.

- `run list [--json]` — `attention_sessions(root)` newest-first:

  ```
  SESSION                              STATE               AGE   CRITERIA
  {id:<36} {state:<18} {age:>4}  {criteria}
  ```

  `age` humanized from `updated_at` (`3h`, `2d`); `criteria` =
  `profile: {profile}` when set else the query quoted+truncated (40 chars). Empty:
  `no sessions need attention`. `--json` = the SessionInfo dicts.
- `run approve <session>` — today's `review` body with: resolution via
  `resolve_run` substring; after processing (`_execute`) the marker completes
  (Plan A already writes it inside `_execute`); on declining the process prompt,
  echo `next: llama run resume {ws.name}` (id, not path — replaces `cli.py:486`);
  the `--script/--voice` overrides are dropped; keep `--full-rationale`.
- `run resume <session>` — today's `run` body minus `--stage`, `--force`,
  `--script`, `--voice` (persisted criteria rule; keep `--auto/--interactive`
  defaulting auto, and `--full-rationale`).
- `run rm <session>` — y/N confirm showing id + state (`--yes` skips);
  `shutil.rmtree(ws.dir)`; shows untouched; echo `removed session {id}`.

- [ ] **Step 1: Write the failing tests** — `run list` shows awaiting+incomplete
  only, hides complete, formats profile vs query; `run approve` approves ranks,
  persists them, processes on confirm (stubbed `_execute`), prints the resume hint
  by id on decline; `run resume` runs `_execute` from artifacts and rejects
  `--stage`; `run rm` confirms, deletes the dir, leaves `shows/` intact; `review`
  and bare `llama run <x>` (old positional form) gone; `--run-name` no longer
  anywhere.
- [ ] **Step 2-4: fail → implement → full suite** (port `review` test coverage).
- [ ] **Step 5: Commit** — `feat!: run namespace (list/approve/resume/rm); review and root run removed`

---

### Task 13: `profile show/remove` + enriched `list`; `presenter remove`

**Files:**
- Modify: `src/llama/cli.py` (`profile_app`, `presenter_app`);
  `src/llama/profiles.py` if a delete helper is cleaner there
- Test: extend `tests/test_profiles.py`, `tests/test_presenters.py`

**Interfaces (spec §11):**
- `profile show <name>` — prints name, query, count, human_gate, script, presenter,
  title, pinned roster (or "no pinned roster"), and criteria highlights
  (collection/artist, date range, artist_cap/year_cap/min_quality_score). No LLM
  call.
- `profile remove <name> [--yes]` — y/N confirm; delete `profiles/<name>.toml`;
  sessions/shows untouched.
- `profile list` enriched: `{name:<20} {count:>3} {presenter or '-':<14} {query:40.40s}`.
- `presenter remove <id> [--yes] [--force]` — if any `profiles/*.toml` names the id
  as `presenter`, refuse listing the profiles (`presenter {id} is used by: a, b —
  --force to remove anyway`); else/with `--force` confirm and delete the TOML.

- [ ] **Step 1: Write the failing tests** — show prints all fields incl. roster;
  remove confirms + deletes; enriched list columns; presenter remove refusal with a
  referencing profile, `--force` override, clean removal otherwise.
- [ ] **Step 2-4: fail → implement → full suite.**
- [ ] **Step 5: Commit** — `feat: profile show/remove + enriched list; presenter remove`

---

### Task 14: `pipeline` — the teaching command

**Files:**
- Modify: `src/llama/cli.py` (new command; static text, no config/IO)
- Test: extend `tests/test_cli.py`

**Interfaces (spec §5.3):** `llama pipeline` — panel `Watch`. Prints three static
sections (source the content from `docs/workflow.md`'s diagram/tables, maintained
inline in `cli.py` as a module constant):

1. the stage flow with both gates marked
   (`interpret → search → winnow →(gate 1: run approve)→ select → gather → research
   → vet → synthesize → package →(gate 2: held → triage / fix)→ deliver`), one line
   per stage with what it does/writes;
2. the eight states + the `voiced` and `broadcast-ready` annotations (the five
   readiness conditions);
3. the redo cheat-sheet (excludes/metadata→gather, narration→synthesize,
   overrule→package, new recording→select, re-research→research) noting `fix`
   applies these automatically and `redo --from` is the manual escape hatch.

- [ ] **Step 1: Write the failing tests** — exit 0 with no config present; output
  contains each stage name, each state name, `gate 1`, `gate 2`,
  `broadcast-ready`, and `fix`.
- [ ] **Step 2-4: fail → implement → full suite.**
- [ ] **Step 5: Commit** — `feat: llama pipeline teaching command`

---

### Task 15: Docs pass + dead-code sweep + final verification

**Files:**
- Modify: `docs/workflow.md`, `README.md`, `CLAUDE.md`, `docs/station-brief.md`
  (only if it names commands), `src/llama/cli.py` (dead code)
- Test: full suite + help-surface assertions

- [ ] **Step 1: Dead-code sweep** — delete `_batch_select`, `_has_selector`, and any
  helper now unused (verify with grep before deleting); confirm no occurrence of the
  removed spellings anywhere in `src/` or `--help` output: `--with-research`,
  `--include ` (as un-exclude), `--vague`, `--full` (narration flags), `--clear`
  (overrule), `--deliver-held`, `--run-name`, `deliver --force`, `run --stage`,
  `profile-setup-`. Reconcile `_COMMAND_ORDER` to exactly the final tree.
- [ ] **Step 2: Docs** —
  - `docs/workflow.md`: rewrite the Command reference (:382-660) to the new tree;
    rewrite the Recipes (:661+) in new spellings; update "The two human gates"
    (:180) to name `run approve` and `triage` (the section's "don't confuse them"
    apparatus should now shrink); update the troubleshooting table (drop rows for
    removed flag-apology notes); document sessions (`session.json`,
    attention-list) and the dedup "library ∪ ledger" model.
  - `README.md`: command examples to new spellings.
  - `CLAUDE.md`: the Commands bullet list and any flag mentions (`--vague` etc.) to
    the new surface.
- [ ] **Step 3: Final verification** — `pytest -q` full suite; `llama --help`
  renders the four panels with the spec's tree and nothing else; spot-run against a
  scratch root: `get "test" --plan` (fake backend) → `run list` → `run approve` →
  `status` → `show` → `deliver --broadcast-ready --yes` happy path per the workflow
  doc's own examples.
- [ ] **Step 4: Commit** — `docs: rewrite command reference for the show-centric surface; dead-code sweep`

---

## Review checkpoints

- [ ] **Mid-plan review** after Task 8 (superpowers:requesting-code-review): the
  watch/fix/act core (`show`/`status`/`triage`/`fix`/`redo`/`voice`/`deliver`)
  against spec §§2, 5-7 — selector uniformity, held opt-in enforcement in one place,
  read-only guarantees, deliver gate non-overridability, exact strings.
- [ ] **Whole-plan review** after Task 15: full spec conformance sweep (§1 tree,
  §§3-11 per command), no legacy spellings, docs consistency, test coverage against
  the spec §13 checklist.

## Self-review notes

- **Spec coverage:** §3 (Task 11 + Task 1 `artists`), §4 (Tasks 5, 11, 12), §5
  (Tasks 4, 5, 14), §6 (Tasks 2, 3), §7 (Tasks 6, 7, 8), §8 (Tasks 9, 10), §10
  (Tasks 3, 4), §11 (Tasks 10, 13, Task 1 hygiene), §12 (Tasks 1, 14, 15), §13
  (each task's tests + Task 15 sweep).
- **Add-before-remove sequencing:** fix/triage (2-3) before show strips (4); get
  (11) before find/profile-run deletion (same task, after `get` passes); run
  namespace (12) after `redo --run` (6) took over re-execution. Every commit leaves
  a complete, green surface.
- **One selector implementation:** only `cli_select` filters; Tasks 5-9 must not
  re-declare semantics — reviewers should reject any inline held-filtering.
- **Exact-string contracts** (refusal messages, HELD_NOTE, rm echoes, hints) come
  from Plan A/`spec` and are asserted verbatim; they are the UX, not incidental
  text.
