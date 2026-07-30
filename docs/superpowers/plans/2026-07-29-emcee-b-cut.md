# The Cut + Release Wiring (Sub-project 3, Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stamp the originating profile into the manifest, then cut scriptwriting/presenters/speech out of llama (gate shrinks to package-complete + not-held), and wire the `emcee` binary into packaging/release.

**Architecture:** Prerequisite: Plan A (`2026-07-29-emcee-a-build.md`) is merged — emcee exists and its suite is green, so every capability removed here already has its replacement. The cut proceeds consumers-first (CLI surface → readiness/deliver → pipeline/stages → module deletion) so the suite stays green after every task. Spec: `docs/superpowers/specs/2026-07-29-emcee-and-the-cut-design.md` §5-§7.

**Tech Stack:** unchanged (Python ≥3.11, pytest, PyInstaller, GitHub Actions).

## Global Constraints

- **No modifications under `packages/emcee/`** except where a task names them (release smoke test) — emcee shipped in Plan A.
- Full suite green after every task (`pytest -q` from root); commit per task.
- Deletions use `git rm` (history). Moves of test content are copies-then-delete within one task's commit.
- llama's deliver gate after this plan: manifest exists + every manifest track's audio file on disk + not held. **No voice legs anywhere in llama.**
- The manifest schema keeps `dj_notes`/`dj_audio` as optional blocks (emcee-written); llama code never writes them again.
- No new dependencies; numpy and lameenc LEAVE llama's pyproject (they were TTS-only).

---

### Task 1: Profile stamp (`source.profile`)

**Files:**
- Modify: `packages/llama/src/llama/models.py` (Provenance ~L299-314), `packages/llama/src/llama/pipeline.py` (`process_show`), `packages/llama/src/llama/stages/package.py` (`run_package` source dict), `packages/llama/src/llama/manifest.py` (`build_manifest`), `packages/llama/src/llama/cli.py` (`_execute` profile-run path)
- Test: `packages/llama/tests/test_pipeline.py`, `packages/llama/tests/test_stage_package.py`

**Interfaces:**
- Produces: `Provenance.profile: str | None = None`; `process_show(..., profile: str | None = None)` stamps it; manifest `source` dict gains `"profile"` (absent → `None`). emcee's assignment (already shipped) reads `manifest["source"]["profile"]`.

- [ ] **Step 1: Failing tests** — profile-driven `process_show` (pass `profile="prime-dead"`) → `provenance.json` and `manifest["source"]["profile"]` both carry it; one-off (no profile) → `None`. Extend one existing happy-path test in each file rather than duplicating fixtures.
- [ ] **Step 2: Implement** — `Provenance` field; `process_show` param written into the `Provenance(...)` construction (`pipeline.py:79-85`); `run_package` reads provenance (it has `show_ws`) or takes the value through `build_manifest(..., profile=...)` from `process_show` — implementer picks the smaller diff, but the manifest write happens in `build_manifest`'s `source={...}` dict (`manifest.py:23-24`). `cli.py::_execute` passes the profile name it already has for profile runs.
- [ ] **Step 3: Suite green.** — **Step 4: Commit** — `feat: stamp originating profile into manifest source block`

---

### Task 2: Remove llama's voice CLI surface

**Files:**
- Modify: `packages/llama/src/llama/cli.py` — delete the `voice` command (L1635-1743), `_resolve_voice`/`_replay_voice`/`_speech_for`/`resolve_bed` (L136-185), `redo`'s `--voice/--no-voice` (L1561-1563) and `_redo_show`'s voice/script plumbing (L1258-1304 reduces: no `prov.voice` replay, no presenter/title load, no `effective_script` — brief+package always run), `voice` from `_COMMAND_ORDER` (L52), `--script/--no-script` on `get`/profile runs, `_execute`'s speech/bed/presenter wiring (L217-224)
- Modify: `packages/llama/tests/` — delete `test_voice_cmd.py`, `test_cli_voice.py`, `test_voice_pipeline.py` (their behaviors now live in emcee's suite from Plan A); update `test_redo_cmd.py` (2 voice tests), `test_get_cmd.py`
- Test: updated files above

**Interfaces:**
- Consumes/produces: `process_show` keeps its `speech`/`chunk`/`bed`/`presenter`/`title`/`script`/`voice` params until Task 4 (callers just stop passing them) — this task is CLI-layer only, so the pipeline signature change lands with the stage cut.

- [ ] **Step 1:** Delete the commands/helpers; fix every `cli.py` reference the deletion breaks (imports of `speech_provider_for`, `Bed`, `SpeechError` teaching text mentions wait for Task 5). `fix`/`triage` need no change (they never had voice flags).
- [ ] **Step 2:** Test fallout: delete the three moved files; update `test_redo_cmd.py`'s two voice tests (batch selector loses `--voiced`? No — selector removal is Task 3; here only `redo --voice` flags die); `test_cli_commands.py` command-list assertions drop `voice`.
- [ ] **Step 3: Suite green** (llama count drops by the deleted files' totals). — **Step 4: Commit** — `refactor: remove llama voice CLI surface (moved to emcee)`

---

### Task 3: Readiness/deliver gate rework + selector removal

**Files:**
- Modify: `packages/llama/src/llama/catalog.py` — delete `derive_voiced` (L138-147), `broadcast_readiness` (L150-174), `VOICE_BUNDLE_REASONS` (L177); rewrite `deliver_refusals(ws) -> list[str]` (no `allow_unvoiced` param): not packaged / held for review / N of M audio files missing; `CatalogEntry` loses `voiced`/`broadcast_ready` (L42-43); `iter_shows`/`select_shows` lose their population/filtering
- Modify: `packages/llama/src/llama/cli_select.py` — `Selector` loses `voiced`/`broadcast_ready`; `build_selector` loses the tri-state reconciliation
- Modify: `packages/llama/src/llama/cli.py` — `deliver` loses `--allow-unvoiced`/`--voiced`/`--unvoiced`/`--broadcast-ready` (L1203-1216); same selector options removed from `redo`/`triage`/`status`/`rm` (grep `broadcast_ready|voiced` across cli.py); `_deliver_pointer` (L1129-1135) loses its `voice` hint branch; status output drops the `voiced`/`broadcast-ready` marks + JSON fields (L2040-2055); `llama show` drops its voiced/broadcast-ready lines
- Test: `test_broadcast_ready.py` + `test_deliver_gate.py` rewritten to the new gate; `test_catalog.py`, `test_cli_select.py`, `test_status_cmd.py`, `test_deliver_cmd.py`, `test_show_cmd.py` updated; `packages/llama/tests/helpers.py:build_ready` simplifies (voiced/broadcast knobs go)

**Interfaces:**
- Produces: `deliver_refusals(ws) -> list[str]` — the ONLY gate llama retains. `deliver` ships any packaged, un-held show with its audio verified.

- [ ] **Step 1: Failing tests first** — rewrite `test_deliver_gate.py` to the three-leg gate (packaged/held/audio-missing each refuse; clean package delivers); rewrite `test_broadcast_ready.py` into `test_deliver_gate.py` additions and delete the file.
- [ ] **Step 2: Implement the removals**, then chase suite fallout through the listed test files (selector tests lose two dimensions; status JSON shape shrinks).
- [ ] **Step 3: Suite green.** — **Step 4: Commit** — `refactor: llama deliver gate = package-complete + not-held; voice readiness removed`

---

### Task 4: Cut the synthesize stage + pipeline plumbing

**Files:**
- Modify: `packages/llama/src/llama/pipeline.py` — `process_show` signature loses `script`/`voice`/`speech`/`chunk`/`bed`/`presenter`/`title`; the synthesize block (L104-118 region) and `load_lexicon`/`Bed` imports go; `TASK_KEYS` loses `"synthesize"`
- Delete (git rm): `packages/llama/src/llama/stages/synthesize.py`, `packages/llama/src/llama/prompts/synthesize.md`
- Modify: `packages/llama/src/llama/workspace.py` — `SHOW_STAGE_ORDER = ["select","gather","research","vet","brief","package"]`; `show_stage_artifacts` loses `synthesize`; `ShowWorkspace` loses `dj_notes_md`/`dj_notes_json`
- Modify: `packages/llama/src/llama/stages/package.py` — delete the speech half (`_synthesize_dj_audio` L183-256 and helpers L50-180), the `speech`/`notes` params, dj-notes copy (L314-315 region), `broadcast.m3u` write, `dj_audio` manifest kwarg; `context` falls back to vetting context only
- Modify: `packages/llama/src/llama/manifest.py` — `build_manifest` loses `notes`/`dj_audio` params (Manifest model keeps the optional fields; llama passes nothing); `interleave_broadcast`/`broadcast_m3u_text` deleted (ported to emcee in Plan A)
- Modify: `packages/llama/src/llama/config.py` — `DEFAULT_TIERS` loses `"synthesize"`; `packages/llama/src/llama/catalog.py` — `_STAGES` loses `("dj_notes_json", 6, "scripted")`; `cli_select.py` — `ShowState` loses `scripted`; `cli.py` — `VALID_STAGES` loses `synthesize`, `_PIPELINE_*` text updated (stage list, states, cheat-sheet), `_stage_ages` loses dj-notes
- Test: `test_stage_synthesize.py` deleted (guard/persona halves live in emcee since Plan A; llama-specific remnants: none — brief's guard has its own suite); `test_pipeline.py`, `test_workspace.py`, `test_stage_package.py` (voice half already gone to emcee — delete those ~15 tests here), `test_manifest.py`, `test_cli_commands.py`, `test_status.py` updated

**Interfaces:**
- Produces: `process_show(run_ws, ia, ledger, entry, providers, run_name, audio_format="mp3", force=False, setlistfm=None, structure_cfg=None, selection_cfg=None, jerrybase_enabled=True, force_stage=None, profile=None)` — the post-cut signature every caller and test uses.

- [ ] **Step 1:** Delete/modify in the order listed (stage file last so imports break loudly if anything is missed); update tests as the suite directs.
- [ ] **Step 2:** Add a cut-verification test (new `test_the_cut.py`): `importlib.util.find_spec` returns None for `llama.tts`, `llama.speech_text`, `llama.presenters`, `llama.stages.synthesize`; `SHOW_STAGE_ORDER` has no synthesize; `"synthesize" not in DEFAULT_TIERS`; `Manifest` still accepts `dj_notes`/`dj_audio` blocks (passthrough contract).
- [ ] **Step 3: Suite green.** — **Step 4: Commit** — `refactor: cut synthesize stage; brief is llama's sole text stage`

---

### Task 5: Delete the moved modules + config/model fields

**Files:**
- Delete (git rm): `packages/llama/src/llama/tts/` (all six files), `packages/llama/src/llama/speech_text.py`, `packages/llama/src/llama/presenters.py`, `packages/llama/src/llama/data/pronunciations.csv`
- Modify: `packages/llama/src/llama/config.py` — `TTSConfig` class + `Config.tts` field + `DEFAULT_CONFIG_TOML`'s `[tts]` block (L210-258) deleted
- Modify: `packages/llama/src/llama/profiles.py` — `Profile.presenter`/`Profile.title` deleted; `models.py` — `Criteria.presenter`/`Criteria.title` (L33-34) and `Provenance.script`/`voice`/`presenter`/`title` deleted
- Modify: `packages/llama/src/llama/cli.py` — presenter sub-app (L2233-2337) deleted, `presenter` out of `_COMMAND_ORDER`, `profile` commands lose presenter/title columns+flags, `_profiles_using_presenter` deleted
- Modify: `packages/llama/pyproject.toml` — `numpy`/`lameenc` removed from dependencies
- Test: delete `test_tts.py`, `test_voxtral.py`, `test_bed.py`, `test_speech_text.py`, `test_presenters.py`, `test_chunk.py`; update `test_config.py` (5 tts tests out), `test_profiles.py` (2 presenter tests out), `test_cli_commands.py` (6 presenter tests out), `test_models.py`/provenance tests

**Interfaces:** none new — pure removal. Extend `test_the_cut.py`: `Config` has no `tts` attr; `Profile` has no `presenter`/`title`; llama's pyproject text contains neither `numpy` nor `lameenc` (read the file in the test).

- [ ] **Step 1:** Deletions + fallout, `test_the_cut.py` extensions first (failing), then green. Fresh-venv reinstall (`pip install -e "packages/llama[dev]"`) to prove the dependency removal doesn't break llama's imports.
- [ ] **Step 2: Suite green.** — **Step 3: Commit** — `refactor: delete moved voice modules; llama sheds tts deps`

---

### Task 6: Packaging + release — the second binary

**Files:**
- Create: `packaging/emcee.spec` (modeled on `packaging/llama.spec`: entry `packages/emcee/src/emcee/__main__.py`, pathex includes `packages/emcee/src` + `packages/herder/src`, `datas = collect_data_files("emcee.prompts") + collect_data_files("emcee.data")`, `EXE(name="emcee")`, its own Windows version resource)
- Modify: `packaging/build.py` — parameterize per target: `--target {llama,emcee}` (default both): `SPEC`/`exe_name`/`VERSION_FILE`/`package()` stem become per-target lookups (`_version.py` written into each package's src tree); smoke test runs each built binary's `--help`/`--version`
- Modify: `.github/workflows/release.yml` — the venv step adds `-e packages/emcee`; the Build step produces both binaries per matrix leg; artifact upload globs pick up `emcee-*` alongside `llama-*`; the release job's SHA256SUMS covers both (`sha256sum llama-* emcee-* > SHA256SUMS`) and `gh release create` attaches both
- Modify: `CLAUDE.md` setup line (adds `-e packages/emcee`)
- Test: `packages/llama/tests/test_packaging.py` (or its post-move location) gains an emcee-spec existence/entry-point check mirroring the llama one; CI-only verification is the release itself

- [ ] **Step 1:** Write `emcee.spec` + `build.py` parameterization; run `python packaging/build.py --version 0.0.0-dev --dry-run` locally — both binaries build and pass smoke (`--help` works from the frozen binary).
- [ ] **Step 2:** Wire release.yml (both artifacts, both in SHA256SUMS). This is log-verified at the next real release, not in CI here — but the workflow must lint clean (`gh workflow view` parse or actionlint if available).
- [ ] **Step 3: Suite green.** — **Step 4: Commit** — `feat: build+sign emcee binary alongside llama in release pipeline`

---

### Task 7: Documentation — the two-tool story

**Files:**
- Modify: `docs/station-brief.md` (llama delivers unvoiced+briefed; dj_notes/dj_audio/broadcast.m3u documented as emcee-written; `source.profile` documented), `README.md` (emcee section: install, config init, assign, run/voice/status; llama sections lose voice/presenter/TTS), `docs/workflow.md` (voice sections rewritten around `emcee run`; stage table minus synthesize; states minus scripted), `CLAUDE.md` (architecture rewrite: three packages, llama's shrunk pipeline, emcee's role; commands list updated)
- Modify: `packages/llama/src/llama/config.py` docs remnants if any grep hits for tts/presenter remain

- [ ] **Step 1:** Write the docs; grep the four files for `voice|presenter|tts|broadcast-ready|synthesize|scripted|allow-unvoiced` and resolve every hit (rewrite, move to the emcee section, or delete).
- [ ] **Step 2:** `llama pipeline` output vs workflow.md stage table consistency check (the teaching text was updated in Task 4 — verify docs agree).
- [ ] **Step 3: Suite green** (docs only). — **Step 4: Commit** — `docs: two-tool story — llama delivers briefed packages, emcee voices them`

---

### Task 8: End-to-end verification

- [ ] **Step 1:** Fresh venv, full install (`-e packages/herder -e "packages/llama[dev]" -e packages/emcee`), `pytest -q` green from root; `pytest packages/emcee/tests -q` and `pytest packages/llama/tests -q` green independently.
- [ ] **Step 2:** Offline end-to-end handshake (fake backends): run llama's pipeline test fixture to produce a delivered-style package (or use llama's test helpers to fabricate one), point `emcee run` at it via `EMCEE_ROOT`+config with `backend="fake"`, assert the package comes out broadcast-ready (dj blocks + broadcast.m3u + dj-audio files) — the contract crosses the two suites in one test file living in `packages/emcee/tests/test_handshake.py` **using only the package dir as the interface** (fabricated by emcee's `build_package` helper mirroring llama's real output; no llama import).
- [ ] **Step 3:** `python packaging/build.py --version 0.0.0-dev --dry-run` — both binaries, both smoke tests.
- [ ] **Step 4:** Commit any fixes — `test: sub-project 3 end-to-end verification`.
