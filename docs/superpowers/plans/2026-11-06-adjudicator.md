# Adjudicator: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Judge held shows with one LLM call each, auto-apply the verdicts a deterministic policy gate passes, and leave the rest held with a stored proposal that `llama triage` accepts in one keystroke. This is for the backlog (`llama adjudicate`) and from now on as a pipeline step in `get`, `redo` and `run resume`. A recording pin lets the adjudicator or Shawn pick a better sibling recording.

**Architecture:** There is a new subpackage, `llama/adjudicator/`. `bundle` builds the evidence text and the structured facts from the show workspace and caches. `verdict` holds the typed, filename-keyed schema and the one `adjudicate` LLM task. `gate` is pure code that decides per edit whether the verdict may auto-apply. `apply` runs inside one `show_unit`: it writes overrides by filename, runs one `_redo_show_locked`, then runs the whole-show, silenced-flag, coverage and re-hold checks. `record` keeps `adjudication.json` and the digest loop guard. `runner` puts these together per show. The subpackage never imports `llama.cli`: the CLI passes in the redo callable, and owns the pacing gates and printing.

**Tech Stack:** Python 3.12, pydantic v2 (a discriminated union for edits), Typer, herder `run_json_task`, pytest with the `fake` backend.

**Spec:** `docs/superpowers/specs/2026-11-06-adjudicator-design.md` (approved; authoritative). House-style plans: `docs/superpowers/plans/2026-11-04-programs-and-lineup.md`, `2026-10-26-bulk-apply.md`. Prototype to port: `~/.llama-harness/t3/adjudicator-brief-v2.md` (prompt), `tools/build_bundles.py` (bundle), `tools/daemon.py` (old gate).

## Global Constraints

- Worktree: `<repo>/.claude/worktrees/adjudicator` with its own `.venv`, on a new branch `adjudicator-impl` cut from `adjudicator` (the main checkout already holds the `adjudicator` branch). Tests run as `./.venv/bin/pytest -q` in the worktree, never as a bare `pytest`. Check `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree. Every task leaves the full suite green.
- Offline and deterministic: the `fake` backend (`herder.FakeProvider`), captured fixtures (`tests/fixtures/`, gd73), and `FakeIA`/stub IA objects. No test touches archive.org, setlist.fm or a real `claude -p`. No implementer runs `llama`/`emcee` or the pilot script against `~/.llama` (see Checkpoint B).
- `llama` never imports emcee or transmitter. `llama/adjudicator/*` never imports `llama.cli`. `scripts/` may import llama.
- The adjudicator never delivers, never removes a show, never writes a station copy, never runs `clear-mark` and never voices. Every write goes to the library show directory and happens under the show lock: inside `show_unit`, or, for a proposal record, under `file_lock(show_ws.lock)` after the unit has exited. `file_lock` is not re-entrant. Never take the show lock inside a `show_unit` for the same show. Lock order is run ⊃ show ⊃ ledger.
- Config: `[adjudicate] enabled = true` is a new `_StrictModel` section. The `adjudicate` LLM task is tier `high` in `DEFAULT_TIERS` and overridable via `[llm.adjudicate]`. `tests/test_config.py::test_default_config_template_matches_defaults` must pass. Unknown config keys stay errors.
- Gate constants live in `llama/adjudicator/gate.py` only, with these exact values: `SHORT_EDIT_MAX_S = 60.0`, `VERDICT_SUM_MAX_S = 120.0`, `SIBLING_TOL_S = 2.0`, `SIBLING_TOL_FRAC = 0.01`, `COVERAGE_ADDED_MAX_S = 60.0`. A boundary is inclusive on the passing side: 60.0 s is short and 120.0 s total is still short; 60.01 is long.
- Evidence source kinds are a closed set, written exactly as: `taper-description`, `original-tag`, `derivative-tag`, `sibling-tracks`, `setlistfm`, `jerrybase`, `review`.
- Edits name **files, never track numbers**. Overrules carry `source: "adjudicate"`.
- Propose-only, never applied (not even by `[a]`): `set_date`, `untitled`, `narration`, `rm`, `redo_research`.
- Adjudication is not in `SHOW_STAGE_ORDER`, and `adjudication.json` is no stage's artifact, so `drop_stage_artifacts` never deletes it. `show_unit`'s snapshot covers it, being outside `package/audio/`.
- The apply's own redo never adjudicates. Hook points are exactly `get`, `run approve`, `run resume` (all three via `_execute`) and `redo` (single and batch). `fix`, `triage` and `reapply` have none, and neither does the adjudicator's apply.
- Every adjudication LLM call runs behind llama's pacing gate (`_meter` + `decide`), except under `--no-pacing`. A `RateLimited` during adjudication leaves the show held with `adjudication.json` unchanged.
- Rollout caveat for the operator, to go in the docs (Task 11): a llama binary older than this release rewrites `overrides.json` through its own model and drops the new `recording` key.
- Every commit ends with the session's attribution lines.

## Review Focus

1. **A verdict that names a file almost right:** different case, the FLAC original's name for an MP3 track, a path prefix, a track number instead of a name. Expected: the verdict is malformed, the show stays held with the verdict stored, and nothing is fuzzy-matched. Pinned in Task 5 (`test_validate_rejects_near_miss_filenames`).
2. **Bundle text the prompt renderer could choke on:** a taper description containing `{{slug}}` or `{{bundle}}`, NUL or odd control characters, or a 200 KB description. Expected: the prompt renders, the substring check still works on the escaped text, and the bundle stays under `BUNDLE_CAP`. Pinned in Task 3 (`test_bundle_escapes_braces_and_caps_size`) and Task 4 (`test_call_renders_a_bundle_with_placeholders`).
3. **Someone edits the show while the LLM call is in flight**, for example Shawn runs `llama fix` or a sweep re-gathers it. Expected: the apply's `show_unit` raises `ShowChanged`, the outcome is `skipped: changed`, nothing is written (no proposal record either), and the next run judges it again. Pinned in Task 7 (`test_concurrent_change_writes_nothing`).
4. **Ctrl-C or a crash in the middle of an apply**, after `overrides.json` is written and during the redo. Expected: the unit restores every file byte-identical, `adjudication.json` returns to its prior state, and the next run judges the show again. Pinned in Task 6 (`test_interrupt_mid_redo_restores_everything`).
5. **A delivered, voiced show whose apply changes the track list**, and a delivered show whose station copy is unmounted. Expected: in the first case the report prints `llama deliver <slug> --replace-voiced`. In the second the station-reuse refusal restores the show and stores a proposal carrying the error, with no LLM spend past the verdict. Pinned in Task 6 (`test_station_refusal_restores_and_becomes_proposal`) and Task 8 (`test_report_names_redeliver_command_for_voiced`).

## Setup (before Task 1)

- [ ] `git worktree add .claude/worktrees/adjudicator -b adjudicator-impl adjudicator`. In it: `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`.
- [ ] Check `./.venv/bin/python -c "import llama; print(llama.__file__)"` prints a path inside the worktree, and `./.venv/bin/pytest -q` is green. Record the baseline count.

## File structure

```
packages/llama/src/llama/config.py              AdjudicateConfig, Config.adjudicate, DEFAULT_TIERS["adjudicate"], template
packages/llama/src/llama/pipeline.py            TASK_KEYS += "adjudicate"
packages/llama/src/llama/models.py              Overrides.recording; Overrule.source comment; ShowNotes docstring
packages/llama/src/llama/workspace.py           ShowWorkspace.adjudication
packages/llama/src/llama/staleness.py           NEW: stale_message (moved out of cli._stale)
packages/llama/src/llama/override_keys.py       filename_keyed_entries, clear_hint
packages/llama/src/llama/stages/select_recording.py   honours overrides.recording; lineage_table
packages/llama/src/llama/adjudicator/__init__.py      NEW (docstring only)
packages/llama/src/llama/adjudicator/bundle.py        NEW: evidence bundle + structured facts
packages/llama/src/llama/adjudicator/verdict.py       NEW: schema, call_adjudicator, model_label
packages/llama/src/llama/prompts/adjudicate.md        NEW: the prompt ({{bundle}} only)
packages/llama/src/llama/adjudicator/gate.py          NEW: validate_targets, evaluate, constants
packages/llama/src/llama/adjudicator/apply.py         NEW: write_edits, checks, apply_verdict
packages/llama/src/llama/adjudicator/record.py        NEW: adjudication.json, digest
packages/llama/src/llama/adjudicator/runner.py        NEW: adjudicate_show, accept_proposal, hook_enabled
packages/llama/src/llama/adjudicator/report.py        NEW: run report + proposal rendering
packages/llama/src/llama/cli.py                 fix --recording/--clear-recording/--clear-include; adjudicate cmd;
                                                hooks in _execute/redo; --adjudicate flags; triage [a]
packages/llama/tests/conftest.py                autouse _no_ambient_adjudication
packages/llama/tests/test_adjudicator_*.py      NEW, one per module
scripts/adjudicate_pilot.py, scripts/test_adjudicate_pilot.py   NEW
packages/llama/CLAUDE.md, CLAUDE.md             docs
```

---

### Task 1: Plumbing: config, task key, workspace path, models, staleness helper

**Model hint:** sonnet.

**Files:**
- Modify: `packages/llama/src/llama/config.py`, `pipeline.py` (`TASK_KEYS`), `models.py` (`Overrides`, `Overrule`, `ShowNotes`), `workspace.py` (`ShowWorkspace.__init__`), `cli.py` (`_stale` becomes a delegate)
- Create: `packages/llama/src/llama/staleness.py`, `packages/llama/src/llama/adjudicator/__init__.py`
- Test: `tests/test_config.py`, `tests/test_models.py`, `tests/test_workspace.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces:
  - `config.AdjudicateConfig(_StrictModel)`: `enabled: bool = True`. `Config.adjudicate: AdjudicateConfig`.
  - `DEFAULT_TIERS["adjudicate"] == "high"`, and `"adjudicate" in pipeline.TASK_KEYS`, so `make_providers(config)["adjudicate"]` is a ladder.
  - `Overrides.recording: str | None = None` (an archive.org identifier: the pinned recording).
  - `ShowWorkspace.adjudication == dir / "adjudication.json"`.
  - `staleness.stale_message(ia, config, show_ws, slug: str) -> str | None`: `cli._stale`'s body moved verbatim, with the same message text. `cli._stale` returns `stale_message(...)`.

- [ ] **Step 1: Write the failing tests**

```python
# test_config.py
def test_adjudicate_section_defaults_on_and_is_strict():
    assert Config().adjudicate.enabled is True
    with pytest.raises(ValidationError):
        Config.model_validate({"adjudicate": {"enabeld": False}})
    assert DEFAULT_TIERS["adjudicate"] == "high"
# existing test_default_config_template_matches_defaults must stay green; also extend the
# DEFAULT_TIERS literal in test_config.py:61 with "adjudicate": "high".

def test_default_template_documents_adjudicate():
    assert "[adjudicate]" in DEFAULT_CONFIG_TOML and "enabled = true" in DEFAULT_CONFIG_TOML.split("[adjudicate]")[1]

# test_pipeline.py
def test_make_providers_includes_adjudicate_at_high_tier():
    providers = make_providers(Config())
    assert [p.model for p in providers["adjudicate"]] == ["opus", "opus", "opus"]

# test_models.py
def test_overrides_recording_round_trips_and_defaults_none():
    assert Overrides().recording is None
    assert Overrides.model_validate({"recording": "gd73.x"}).recording == "gd73.x"

def test_shownotes_docstring_no_longer_claims_notes_never_reach_an_llm():
    assert "can never reach an LLM" not in ShowNotes.__doc__
    assert "adjudicat" in ShowNotes.__doc__

# test_workspace.py
def test_adjudication_path_is_not_a_stage_artifact(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    assert ws.adjudication == tmp_path / "s" / "adjudication.json"
    assert all(ws.adjudication not in show_stage_artifacts(ws, st) for st in SHOW_STAGE_ORDER)
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest packages/llama/tests/test_config.py packages/llama/tests/test_models.py packages/llama/tests/test_workspace.py packages/llama/tests/test_pipeline.py -q`. Expect failures on the new attributes.

- [ ] **Step 3: Implement.** Add the `[adjudicate]` block to `DEFAULT_CONFIG_TOML` after `[pacing]`, with this comment: `# Judge a show that ends held (get, redo, run resume) with one LLM call and auto-apply only what the policy gate passes; --adjudicate/--no-adjudicate overrides this for one run`. The `Overrule.source` comment gains `| "adjudicate"`. Rewrite the `ShowNotes` docstring's LLM sentence to: notes never reach the briefing LLM, but they do reach the adjudicator's bundle (adjudicator spec, "Evidence bundle"). Move `_stale` into `staleness.py`. The existing `_stale` tests must pass unchanged.

- [ ] **Step 4: Run the full suite**: `./.venv/bin/pytest -q`. Expect it green.

- [ ] **Step 5: Commit**: `git commit -am "adjudicator: config section, task key, recording field, workspace path"` (add the new files first).

---

### Task 2: Recording pin and `fix --recording` / `--clear-recording` / `--clear-include`

**Model hint:** sonnet.

**Files:**
- Modify: `packages/llama/src/llama/stages/select_recording.py`, `override_keys.py`, `cli.py` (`fix`)
- Test: `tests/test_stage_select.py`, `tests/test_fix.py`, `tests/test_override_keys.py`

**Interfaces:**
- Consumes: `Overrides.recording` (Task 1).
- Produces:
  - `run_select_recording` honours the pin. When `read_overrides(show_ws).recording` is set and is one of `candidate.recordings`' identifiers, `chosen` is the pin, scores are still computed in full, and `selection.json` gains `"pinned": true`. When the pin is set but is not a candidate recording, it raises `LlamaError(f"{slug}: overrides.recording {pin} is not a recording of this performance; clear it with: llama fix {slug} --clear-recording")`.
  - `select_recording.lineage_table(selection: SelectionConfig, collection: str, date: str) -> dict[str, float]`: the era scores, else `scoring.LINEAGE_SCORES`. This makes `_era_lineage_scores` public for the gate.
  - `override_keys.filename_keyed_entries(ov: Overrides) -> list[tuple[str, str]]`: `(key, filename)` in the order exclude, include, titles, set_breaks, encore_after.
  - `override_keys.clear_hint(slug: str, entries: list[tuple[str, str]]) -> str`: `f"llama fix {slug} " + " ".join(flags)`, where the flags are `--unexclude F`, `--clear-include F`, `--clear-title F`, `--clear-set-breaks` (once) and `--clear-encore`.
  - `fix --recording IDENT`: writes `overrides.recording` and redoes from `select`. `fix --clear-recording`: writes `None` and redoes from `select`. `fix --clear-include FILE|N`: removes the file from `overrides.include` (a number resolves through `show.json`) and redoes from `gather`.

- [ ] **Step 1: Write the failing tests**

```python
# test_stage_select.py (two recordings A scoring higher than B, as the existing tests build them)
def test_pin_wins_over_score_and_is_recorded(tmp_path):
    write_artifact(ws.overrides, Overrides(recording="B"))
    assert run_select_recording(ws, ia, cand, assess) == "B"
    sel = read_json(ws.selection)
    assert sel["pinned"] is True and set(sel["scores"]) == {"A", "B"}

def test_pin_not_among_candidates_refuses(tmp_path):
    write_artifact(ws.overrides, Overrides(recording="Z"))
    with pytest.raises(LlamaError, match=r"overrides.recording Z is not a recording of this performance; "
                                          r"clear it with: llama fix .* --clear-recording"):
        run_select_recording(ws, ia, cand, assess)

def test_no_pin_has_no_pinned_key(tmp_path):
    run_select_recording(ws, ia, cand, assess)
    assert "pinned" not in read_json(ws.selection)

# test_override_keys.py
def test_filename_keyed_entries_and_clear_hint():
    ov = Overrides(exclude=["x.mp3"], include=["i.mp3"], titles={"t.mp3": "T"},
                   set_breaks=["b.mp3"], encore_after="e.mp3", venue="V", recording="R")
    assert filename_keyed_entries(ov) == [("exclude", "x.mp3"), ("include", "i.mp3"),
        ("titles", "t.mp3"), ("set_breaks", "b.mp3"), ("encore_after", "e.mp3")]
    assert clear_hint("s", filename_keyed_entries(ov)) == (
        "llama fix s --unexclude x.mp3 --clear-include i.mp3 --clear-title t.mp3 "
        "--clear-set-breaks --clear-encore")
    assert filename_keyed_entries(Overrides(venue="V", recording="R")) == []

# test_fix.py (packaged gd73 show via the existing helpers; selection.json scores hold IDENT and "gd73.sib")
def test_fix_recording_pins_and_redoes_from_select(...):
    r = cli_invoke(cfg, "fix", SLUG, "--recording", "gd73.sib", "--no-run")
    assert r.exit_code == 0 and read_overrides(ws).recording == "gd73.sib"
    assert "staged; next: llama redo gratefuldead-1973-06-10 --from select" in r.output

def test_fix_recording_refuses_unconsidered_identifier(...):
    r = cli_invoke(cfg, "fix", SLUG, "--recording", "nope")
    assert r.exit_code == 1
    assert f"{SLUG}: nope is not one of this show's considered recordings (llama show {SLUG} lists them)" in r.output

def test_fix_recording_refuses_while_filename_keyed_entries_exist(...):
    write_artifact(ws.overrides, Overrides(exclude=["x.mp3"], titles={"t.mp3": "T"}))
    r = cli_invoke(cfg, "fix", SLUG, "--recording", "gd73.sib")
    assert r.exit_code == 1
    assert (f"{SLUG}: overrides.json has filename-keyed entries (exclude: x.mp3; titles: t.mp3); "
            f"clear them first with: llama fix {SLUG} --unexclude x.mp3 --clear-title t.mp3") in r.output
    assert read_overrides(ws).recording is None

def test_fix_recording_combines_with_no_other_edit_flag(...):
    r = cli_invoke(cfg, "fix", SLUG, "--recording", "gd73.sib", "--set-venue", "V")
    assert r.exit_code == 1 and "--recording cannot be combined with --set-venue" in r.output

def test_fix_clear_recording(...):   # pin present -> cleared, staged from select; absent -> refusal
    assert "no recording pin to clear" in cli_invoke(cfg, "fix", SLUG, "--clear-recording").output

def test_fix_clear_include_by_name_and_number(...):
    # overrides.include = ["gd73-06-10d1t01.mp3"]; --clear-include 1 (show.json track 1 is that file) empties it
    # --clear-include other.mp3 -> exit 1, "other.mp3 is not in overrides.include"
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest packages/llama/tests/test_stage_select.py packages/llama/tests/test_fix.py packages/llama/tests/test_override_keys.py -q`.

- [ ] **Step 3: Implement.** In `fix`, the considered set is `read_json(sws.selection)["scores"]`'s keys (no `selection.json` gives the same refusal). `--recording` and `--clear-recording` refuse to combine with any other edit flag, with the message `--recording cannot be combined with <flag>`. `--no-run` and `--allow-download` are the exceptions. They are checked before any lock, like the `--untitled` block. The keyed-entries refusal goes through `filename_keyed_entries` and `clear_hint`, and `clear_hint` gains `--clear-include` from this task. Add the new flags to the `--untitled` exclusion list. The redo stage for both recording flags is `select`.

- [ ] **Step 4: Run the full suite.** Expect it green.

- [ ] **Step 5: Commit**: `git commit -am "llama: recording pin (overrides.recording), fix --recording/--clear-recording/--clear-include"`

---

### Task 3: Evidence bundle

**Model hint:** sonnet.

**Files:**
- Create: `packages/llama/src/llama/adjudicator/bundle.py`
- Test: `packages/llama/tests/test_adjudicator_bundle.py`

**Interfaces:**
- Consumes: `capture_view`, `read_model`, `read_overrides`, `catalog.recording_info`, `jerrybase.lookup`, `setlistfm.cache_key`, `util.length_seconds`, `ia.metadata(identifier) -> dict`.
- Produces:
  - `EVIDENCE_KINDS: tuple[str, ...]`: the seven kinds, in Global Constraints order.
  - Caps (module constants, ported from the prototype): `DESC_CAP = 6000`, `NOTES_CAP = 3000`, `ROWS_PER_ITEM = 80`, `REVIEWS_MAX = 12`, `REVIEW_CAP = 1200`, `RESEARCH_CAP = 12000`, `BRIEFING_CAP = 6000`, `VETTING_CAP = 4000`, `NOTES_JSON_CAP = 3000`, `SIBLINGS_MAX = 8`, `SIBLING_DESC_CAP = 3000`, `BUNDLE_CAP = 150_000` characters.
  - `escape_braces(text: str) -> str`: breaks every adjacent brace pair, `re.sub(r"\{(?=\{)", "{ ", ...)` then `re.sub(r"\}(?=\})", "} ", ...)`, so `{{{` becomes `{ { {`. It is applied to every row's text at build time, so the text the model sees and the text the gate checks are the same.
  - `@dataclass(frozen=True) class Row: text: str; filename: str | None = None; identifier: str | None = None; length_s: float | None = None; title: str | None = None`.
  - `@dataclass(frozen=True) class FileMeta: name: str; source: str; format: str; title: str; length_s: float | None; original: str | None`.
  - `@dataclass(frozen=True) class Bundle:` with fields `slug: str`, `show: Show`, `overrides: Overrides`, `view: ShowView`, `provenance: Provenance | None`, `selection: dict` (`selection.json`, or `{}`), `files: dict[str, FileMeta]` (the selected item's audio files by name), `sections: dict[str, list[Row]]` (every evidence kind present, `[]` when empty), `text: str` (the rendered markdown).
  - `Bundle.own_row(kind: str, filename: str) -> Row | None`: for `original-tag`, the row of the file's original (the file itself if it is an original, else `FileMeta.original`). For `derivative-tag`, the file's own derivative row.
  - `Bundle.length_of(filename: str) -> float | None`: the larger of the `show.json` duration (track or excluded row) and the metadata length. None only when both are unknown.
  - `build_bundle(show_ws: ShowWorkspace, ia, config: Config) -> Bundle`. It is read-only and never fetches setlist.fm (it reads `<root>/cache/<cache_key>.json` only). JerryBase is used only when `config.jerrybase.enabled`.

The rendered layout. Headers are exact, because the prompt (Task 4) names them:

```
# <slug>
## review flags            - <flag>, one per line
## track table             n | set | title | title_source | matched | dur s | file
## excluded files          filename | reasons | dur s
## overrides.json          json (overrule `at` kept)
## vetting                 json, VETTING_CAP
## notes                   json, NOTES_JSON_CAP
## research                RESEARCH_CAP
## briefing                BRIEFING_CAP
## considered recordings   identifier | lineage | kept_tracks | title_fraction | score  (selected marked "*")
## evidence: taper-description   selected item's description (DESC_CAP) then notes (NOTES_CAP); one Row each
## evidence: original-tag        name | format | title tag | length s   (Row.filename = name)
## evidence: derivative-tag      same, derivative files
## evidence: sibling-tracks      per sibling (SIBLINGS_MAX, recording_info order): one Row for its description
                                 (SIBLING_DESC_CAP, filename None) then identifier | name | title tag | length s rows
## evidence: setlistfm           cached setlist json
## evidence: jerrybase           one Row per event (repr)
## evidence: review              [date stars*] title: body (REVIEWS_MAX x REVIEW_CAP)
```

Past `BUNDLE_CAP`, drop sibling blocks from the last one back, then cut research. Never cut the flags, track table, excluded files, overrides or taper-description.

- [ ] **Step 1: Write the failing tests.** Use the gd73 fixture through `fixture_library.library_show`, plus a stub IA serving the fixture metadata and one sibling.

```python
def test_bundle_has_every_section_header_in_order(tmp_path): ...   # headers listed above, in order
def test_track_table_row_format(tmp_path):
    t = b.show.tracks[0]                     # expected values read from the fixture, never literals
    assert (f"1 | {t.set} | {t.title} | {t.title_source} | {t.matched} | {round(t.duration_sec)} | "
            f"{t.filename}") in b.text       # the gd73 fixture has no setlist: matched is not asserted True
def test_original_and_derivative_rows_carry_filename_and_length(tmp_path):
    row = b.own_row("derivative-tag", "gd73-06-10d1t01.mp3")
    assert row.filename == "gd73-06-10d1t01.mp3" and row.length_s == pytest.approx(664.0, abs=1)   # fixture: 664 s
    assert b.own_row("original-tag", "gd73-06-10d1t01.mp3").filename.endswith(".shn")   # via FileMeta.original
def test_length_of_takes_the_larger_and_unknown_is_none(tmp_path): ...
def test_sibling_rows_carry_identifier_and_length(tmp_path): ...
def test_setlistfm_is_read_from_cache_only(tmp_path):   # no cache file -> empty section; IA stub has no setlist client
def test_jerrybase_section_obeys_config(tmp_path): ...
def test_bundle_escapes_braces_and_caps_size(tmp_path):        # Review Focus 2
    # description = "{{slug}} " + "x" * 200_000 + "\x00"
    assert "{{" not in b.text and "{ {slug} }" in b.text
    assert len(b.text) <= BUNDLE_CAP
    assert len(b.sections["taper-description"][0].text) <= DESC_CAP + len("{ {slug} } ")
def test_escape_braces_breaks_every_adjacent_pair():
    assert escape_braces("{{{x}}}") == "{ { {x} } }" and "{{" not in escape_braces("{{{{")
def test_build_bundle_writes_nothing(tmp_path):
    before = helpers.tree_bytes(ws.dir); build_bundle(ws, ia, cfg); assert helpers.tree_bytes(ws.dir) == before
def test_bundle_view_is_captured_before_reading(tmp_path):
    assert b.view == capture_view(ws)
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest packages/llama/tests/test_adjudicator_bundle.py -q`.
- [ ] **Step 3: Implement `build_bundle`.** Capture the view first. Lengths go through `util.length_seconds`. File rows are the audio files only (the prototype's `\.(flac|mp3|shn|ogg)$`, case-insensitive), at most `ROWS_PER_ITEM` per source.
- [ ] **Step 4: Run the tests, then the full suite.** Expect both green.
- [ ] **Step 5: Commit**: `git add ... && git commit -m "adjudicator: evidence bundle"`

---

### Task 4: Verdict schema, prompt and the `adjudicate` call

**Model hint:** opus. Porting the prompt means writing the operator rulings and the class rulings as instructions the model will follow.

**Files:**
- Create: `packages/llama/src/llama/adjudicator/verdict.py`, `packages/llama/src/llama/prompts/adjudicate.md`
- Modify: `tests/test_prompts.py` (`EXPECTED["adjudicate"] = {"bundle"}`)
- Test: `packages/llama/tests/test_adjudicator_verdict.py`

**Interfaces:**
- Consumes: `Bundle.text` (Task 3), herder `run_json_task`, `resolve_model`, `RateLimited`.
- Produces (pydantic v2; the LLM output is permissive about extra keys, `extra="ignore"`):
  - `EvidenceKind = Literal[<the seven kinds>]`, `Confidence = Literal["high", "medium", "low"]`.
  - `Evidence(kind: EvidenceKind, quote: str)`, with `quote` stripped and non-empty.
  - The edits. Each one carries `confidence: Confidence`, `evidence: list[Evidence]` (at least one, except on `ProposeOnly`) and `why: str`. They form a union discriminated on `op`:
    `Include(op="include", file)`, `Exclude(op="exclude", file)`, `SetTitle(op="set_title", file, title)`,
    `Structure(op="structure", breaks_after: list[str], encore_after: str | None)`, `Venue(op="venue", venue)`,
    `City(op="city", city)`, `SwitchRecording(op="switch_recording", identifier)`, `OverruleFlag(op="overrule", flag)`,
    `ProposeOnly(op=Literal["set_date","untitled","narration","rm","redo_research"], value: str | None = None, evidence=[])`.
    `Edit = Annotated[Union[...], Field(discriminator="op")]`.
  - `PROPOSE_ONLY_OPS = frozenset({"set_date", "untitled", "narration", "rm", "redo_research"})`.
  - `FlagJudgement(flag: str, verdict: Literal["real-fixed-by-action","spurious","real-not-fixable","undecidable"], confidence: Confidence, why: str)`.
  - `Verdict(flags: list[FlagJudgement], edits: list[Edit], kind: Literal["fix","overrule","hold"], show_correct_after: Literal["yes","no","unsure"], partial_tape: bool = False, better_sibling: str | None = None, decide: str | None = None, rationale: str, root_causes: list[str] = Field(default_factory=list))`. `decide` is what Shawn must decide, for `hold`.
  - `call_adjudicator(provider, bundle: Bundle) -> Verdict` = `run_json_task(provider, "adjudicate", Verdict, template=load_prompt("adjudicate"), bundle=bundle.text)`. It lets `RateLimited`, `TaskFailed`, `HerderError` and the render `ValueError` propagate. The runner classifies them.
  - `model_label(config: Config) -> str` = `"{backend}:{model}"` from `herder.resolve_model(config.llm_settings(), "adjudicate")`.

The prompt (`adjudicate.md`) ports `adjudicator-brief-v2.md` and drops what no longer applies (shell commands, `expect`, steps, file paths, "write verdict files"). It contains, in this order:
1. The role and the evidence order (archive.org item first, then siblings, then the rest), with no web access.
2. **Binding operator rulings**, verbatim from v2: tape notes presumed correct and taper wording ships; venue strings; discs are not sets; titles from reviews only are weak; "rather repeat a taper's error than mis-correct it".
3. **Class rulings**, from the spec's "Operator class rulings", written as instructions:
   - A partial tape with no more complete sibling: set `partial_tape: true` and judge its partial-tape flags spurious; it airs.
   - A partial tape with a more complete sibling: give `better_sibling` and a `switch_recording` edit.
   - A fully untitled tape: `hold`. `untitled` is propose-only.
   - Scrambled or shifted tags: `set_title` edits only when confident, else `hold`.
   - Needs a listen: `hold`.
4. The pilot's catalogue of common causes, verbatim from v2 "What the 160-show pilot found". Drop the `Not fixable by fix` command names.
5. **Edits**: the ten ops above, each in one line. Name files exactly as the bundle's track table, excluded files and evidence rows spell them; never track numbers. `structure` is the complete result: every file a set break follows, and the file the encore follows or null. Any structure edit drops segues, and that is acceptable. The propose-only ops say what Shawn would run.
6. **Evidence**: every edit quotes the bundle, copying text exactly from one `## evidence: <kind>` section and naming that kind. Name the quoting rules the gate enforces, in plain words:
   - A long or unknown-length include/exclude needs a high-confidence quote from the taper description, an original-file tag or a sibling's track list, outside the file's own tag row, containing the file's name (without its extension).
   - A title needs the taper's text, this file's own original tag, or a duration-matched sibling file, with the title inside the quote.
   - A structure edit needs taper-side text such as set headers, `s1tNN` filenames or `Encore:`.
   - An overrule of a title- or structure-kind flag needs the same kinds of evidence as a title or structure edit.
   - setlist.fm, JerryBase and reviews alone only propose.
   - In `flags`, copy each flag verbatim from the review-flags section.
7. The JSON shape, as an example object using every field, and a final instruction to reply with the JSON object only.
8. `{{bundle}}` as the last line, and the only placeholder.

- [ ] **Step 1: Write the failing tests**

```python
def test_prompt_has_only_the_bundle_placeholder_and_the_rulings():
    text = load_prompt("adjudicate")
    assert set(re.findall(r"\{\{(\w+)\}\}", text)) == {"bundle"} and text.rstrip().endswith("{{bundle}}")
    for phrase in ("presumed correct", "Discs are not sets", "partial_tape", "better_sibling",
                   "never track numbers", "copy each flag verbatim from the review-flags section",
                   *EVIDENCE_KINDS,
                   *("include", "exclude", "set_title", "structure", "venue", "city",
                     "switch_recording", "overrule", *PROPOSE_ONLY_OPS)):
        assert phrase in text

def test_verdict_parses_every_op_and_rejects_unknown_op():
    v = Verdict.model_validate(FULL_VERDICT)          # one edit of each op
    assert [e.op for e in v.edits] == [...]
    with pytest.raises(ValidationError):
        Verdict.model_validate({**FULL_VERDICT, "edits": [{"op": "delete", "file": "a"}]})

def test_typed_edit_needs_evidence_but_propose_only_does_not():
    with pytest.raises(ValidationError):
        Verdict.model_validate({**BASE, "edits": [{"op": "exclude", "file": "a.mp3", "confidence": "high",
                                                   "evidence": [], "why": "w"}]})
    Verdict.model_validate({**BASE, "edits": [{"op": "rm", "confidence": "low", "why": "w"}]})

def test_evidence_kind_is_closed():
    with pytest.raises(ValidationError):
        Evidence(kind="web", quote="q")

def test_call_renders_a_bundle_with_placeholders():                 # Review Focus 2
    fake = FakeProvider(completes=[json.dumps(FULL_VERDICT)])
    v = call_adjudicator([fake], bundle_with_text("desc { {slug} } {x}"))
    assert isinstance(v, Verdict) and "{ {slug} }" in fake.calls[0][1]

def test_call_retries_then_raises_taskfailed():
    with pytest.raises(TaskFailed):
        call_adjudicator([FakeProvider(completes=["not json"] * 3)], bundle)

def test_model_label():
    assert model_label(Config()) == "claude_cli:opus"
    assert model_label(Config.model_validate({"llm": {"adjudicate": {"model": "sonnet"}}})) == "claude_cli:sonnet"
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest packages/llama/tests/test_adjudicator_verdict.py packages/llama/tests/test_prompts.py -q`.
- [ ] **Step 3: Implement** the schema and `call_adjudicator`, and write the prompt.
- [ ] **Step 4: Run the tests, then the full suite.** Expect both green.
- [ ] **Step 5: Commit**: `git commit -m "adjudicator: verdict schema, adjudicate prompt and call"`

---

### Task 5: Target validation and the policy gate (pure)

**Model hint:** opus. This is the strict surface, and every bar boundary is mutation-checked.

**Files:**
- Create: `packages/llama/src/llama/adjudicator/gate.py`
- Test: `packages/llama/tests/test_adjudicator_gate.py`

**Interfaces:**
- Consumes: `Verdict`, edit classes, `PROPOSE_ONLY_OPS` (Task 4); `Bundle`, `escape_braces` (Task 3); `overrules.flag_key`; `placeholders.is_placeholder_title`; `structure.is_filler`; `songs.normalize_song`; `select_recording.lineage_table`, `override_keys.filename_keyed_entries` (Task 2).
- Produces:
  - Constants (Global Constraints), plus:
    - `TITLE_BAR_SOURCES = {"unresolved","tags","desc-position","sibling-format","sibling-align","sibling","setlist","setlist-gap"}`
    - `LONG_BAR_KINDS = {"taper-description","original-tag","sibling-tracks"}`
    - `TITLE_WEAK_KINDS = {"setlistfm","jerrybase","review"}`
    - `TAPER_SIDE_KINDS = {"taper-description","original-tag","derivative-tag"}`
    - `REFUSED_INCLUDE_REASONS = {"duplicate-listing","duplicate derivative", junk.SPAM_REASON}`
    - `OVERRULE_BAR: dict[str, str]`, the spec's table with values `"title" | "structure" | "medium" | "never"`, and `STRUCTURE_KINDS = {k for k, b in OVERRULE_BAR.items() if b == "structure"}`. An unmapped kind, and a flag whose `flag_key` is None, is `"never"`.
  - `normalize(s: str) -> str`: `html.unescape`, then curly quotes to straight (`‘’` to `'`, `“”` to `"`), then `casefold`, then collapse whitespace.
  - `quote_ok(ev: Evidence, bundle: Bundle) -> bool`: `normalize(escape_braces(ev.quote))` is a substring of `normalize("\n".join(r.text for r in bundle.sections[ev.kind]))`. The quote is escaped the way the bundle text was.
  - `quote_rows(ev, bundle) -> list[Row]`: the rows of `ev.kind` whose normalized text contains the quote, normalized as in `quote_ok`.
  - `stem_in(quote: str, filename: str) -> bool`: `normalize(Path(filename).stem)` occurs in the normalized quote as a whole token, not preceded or followed by a letter or digit (`(?<![0-9a-z])` … `(?![0-9a-z])`), so `d1t1` does not match inside `d1t10`.
  - `is_filler_title(title: str) -> bool`: every segue component (split on `->` and `>`) is `structure.is_filler`.
  - `sibling_match(ev, bundle, track: Track) -> bool`: true when some `quote_rows` row has a non-None `length_s` with `abs(row.length_s - d) <= max(SIBLING_TOL_S, SIBLING_TOL_FRAC * d)`, where `d = bundle.length_of(track.filename)`. Unknown `d` is false.
  - `@dataclass(frozen=True) class Facts: bundle: Bundle; delivered: bool; marked: bool; lineage: dict[str, float]; complaints: dict[str, int]`.
  - `@dataclass(frozen=True) class EditGate: index: int; op: str; bar: str; passed: bool; reason: str`. `bar` is one of `short`, `long`, `title`, `structure`, `medium`, `switch`, `propose-only`, `never`.
  - `@dataclass(frozen=True) class GateResult: edits: list[EditGate]; vetoes: list[str]; auto: bool`. `auto` means no vetoes, every edit passed, and at least one edit.
  - `validate_targets(verdict: Verdict, bundle: Bundle) -> list[str]`: the malformed reasons; empty means valid.
  - `evaluate(verdict: Verdict, facts: Facts) -> GateResult`.
  - `flag_passes(j: FlagJudgement, show: Show, verdict: Verdict, gate: GateResult) -> bool`. `real-fixed-by-action` passes at medium or high. `spurious` passes when the flag's `OVERRULE_BAR` is `medium` and the confidence is medium or high. When the bar is `title`/`structure`, `spurious` passes only when the verdict has an `overrule` edit for that flag whose `EditGate` passed; a bare judgement fails. `never`, and anything else, fails.
  - `has_track_list_edit(verdict) -> bool`: true for any of `include`, `exclude` or `switch_recording`.
  - `has_track_list_or_structure_edit(verdict) -> bool`: `has_track_list_edit`, or a `structure` edit.

**Validation rules**, from spec "Before judging". Each failure is one reason string naming the edit index and file:
- `exclude`, `set_title` and every `structure` file must be a current track filename, exact and case-sensitive.
- An `include` target must be an `excluded_files` row.
- A `switch_recording` identifier must be a key of `selection["scores"]` other than the current `show.identifier`.
- An `overrule` flag must be in `show.review_flags` exactly.
- A file named by two of `include`, `exclude` and `set_title` is a conflict, and so is a file named both by an `exclude` and by the structure edit.
- An `exclude` of a file carrying `overrides.titles`, `set_breaks` or `encore_after` is malformed, and so is more than one `structure` or `switch_recording` edit.
- A `FlagJudgement.flag` that is not a current flag, or that is judged twice, is malformed.

**Gate rules.** These are the spec tables. The substring check applies to every quote of every non-propose edit: one failing quote fails that edit, with the reason `quote not found in <kind>`.
- `include`/`exclude`: `dur = bundle.length_of(file)`, and unknown is `inf`. The verdict sum is the sum of `dur` over every include and exclude, so an unknown makes it `inf`. The long bar applies when `dur > SHORT_EDIT_MAX_S` or `sum > VERDICT_SUM_MAX_S`, else the short bar.
  - Short bar: confidence medium or high.
  - Long bar: confidence high, and some quote must pass three tests: `ev.kind in LONG_BAR_KINDS`; some `quote_rows` row is not `bundle.own_row(kind, file)`; and `stem_in(ev.quote, file)`. There is no track-position alternative.
  - Before either bar, these go `propose-only`:
    - an exclude of a track whose `title_source != "unresolved"` and whose title is neither a placeholder nor `is_filler_title` (`exclude of a track with a resolved song title`);
    - an include of a row whose reasons meet `REFUSED_INCLUDE_REASONS`;
    - an include of an `operator-excluded` row, or an exclude of a file in `overrides.include` (`changes an existing overrides.json entry`).
- `set_title`:
  - The current title source is `override`, or the file is in `overrides.titles`: `propose-only` (`changes an existing overrides.json entry`).
  - The source is not in `TITLE_BAR_SOURCES` and the title is not a placeholder: `never`.
  - Otherwise the title bar: confidence high, and some quote with `normalize(edit.title)` inside it must be either (a) `sibling-tracks` with `sibling_match`, (b) `taper-description`, or (c) `original-tag` with the quote inside `bundle.own_row("original-tag", file)`. If every quote's kind is in `TITLE_WEAK_KINDS`: `propose-only` (`setlist.fm, JerryBase or reviews alone`).
- `structure`:
  - `overrides.set_breaks` or `encore_after` is not None: `propose-only`.
  - Otherwise the structure bar: confidence high and at least one quote of a kind in `TAPER_SIDE_KINDS`. Evidence only from `setlistfm`/`jerrybase`: `propose-only`.
- `venue`: `overrides.venue` set gives `propose-only`, else confidence medium or high. `city`: always `propose-only`.
- `overrule`:
  - `OVERRULE_BAR[flag_key(flag, show).kind]`. `medium` needs medium or high confidence; `never` fails.
  - `structure` uses the structure bar's evidence rule: high, and at least one quote of a kind in `TAPER_SIDE_KINDS`.
  - `title` uses the title bar's evidence kinds: high, and at least one quote of kind `taper-description`, `original-tag` or `sibling-tracks`. When every quote's kind is in `TITLE_WEAK_KINDS` the edit fails. These flags (`research-song`, `research-date`) name a song or a date, not a file, so the per-file anchors (`sibling_match`, the own-tag row) do not apply.
  - The flag's judgement must be `spurious`, else the edit fails with `overrule of a flag not judged spurious`.
- `switch_recording`: the auto-switch bar. Each failing part gives its own reason:
  - The sibling's `kept_tracks > 0` (it has the wanted format), its `complaints == 0`, and `lineage.get(sibling class)` ranks no worse than `lineage.get(current class)`. If either class is missing from the table (`.get` gives None), the switch is propose-only: an unknown class counts as worse.
  - Confidence high, with at least one checked quote.
  - The show is not `delivered` and not `marked`.
  - `filename_keyed_entries(overrides) == []`.
  - `overrides.recording is None`, else propose-only (`changes an existing overrides.json entry`).
  - Every other edit in the verdict is a `venue`. An `overrule` is refused here: its record would be scoped to the old recording. The reason names the offending op.
  - That the switch adds tracks or resolved titles is checked after the re-gather, by coverage (Task 6), not here.
- Propose-only ops: `propose-only`.

**Vetoes**, each its own string:
- `kind` is not `fix`/`overrule`; `show_correct_after != "yes"`.
- A flag is judged `real-not-fixable` or `undecidable`.
- A current flag has no judgement (`flag not judged: <flag>`).
- `better_sibling` is set with no `switch_recording` edit to it.
- No edits.

- [ ] **Step 1: Write the failing tests.** The `make_facts` fixture builds a `Bundle` directly (dataclass), with no IO. Each boundary test comes as a pass/fail pair, and the comment names the boundary it pins, for the mutation pass in Step 5.

```python
# 60 s boundary (short vs long bar)
def test_exclude_at_exactly_60s_takes_short_bar(): assert gate_for(exclude(dur=60.0, conf="medium")).passed
def test_exclude_at_60_01s_takes_long_bar_and_medium_fails():
    g = gate_for(exclude(dur=60.01, conf="medium")); assert (g.bar, g.passed) == ("long", False)
# unknown duration
def test_unknown_duration_is_long_bar(): assert gate_for(exclude(dur=None, conf="medium")).bar == "long"
# 120 s cumulative boundary
def test_three_40s_edits_sum_120_stay_short(): assert all(g.bar == "short" for g in gates(excludes(40, 40, 40)))
def test_two_61s_free_sum_121_moves_short_edits_long(): assert all(g.bar == "long" for g in gates(excludes(30, 30, 61.0)))
def test_unknown_in_verdict_sends_every_track_edit_long(): ...
# long-bar evidence rules: each pass and each fail
def test_long_bar_passes_with_description_quote_naming_stem(): ...
def test_long_bar_fails_when_quote_only_in_own_tag_row(): ...
def test_long_bar_fails_from_derivative_tag_kind(): ...
def test_long_bar_fails_without_stem(): ...
def test_long_bar_fails_on_track_position_alone(): ...                   # "track 7" names no file
def test_long_bar_stem_is_token_bounded():
    # exclude of x-d1t1.mp3: a quote naming only "x-d1t10" fails; "x-d1t1 and x-d1t10" passes
def test_long_bar_needs_high_confidence(): ...
# propose-only classes
def test_exclude_of_resolved_song_is_propose_only_any_length(): ...      # 5 s "Sugaree" -> propose-only
def test_exclude_of_filler_titled_track_is_not_resolved_song(): ...      # "Tuning" -> short bar
def test_filler_segue_with_a_song_is_a_resolved_song(): ...              # "Tuning > Promised Land" -> propose-only
@pytest.mark.parametrize("reason", ["duplicate-listing", "duplicate derivative", "spam-shaped name or tag"])
def test_include_of_refused_reason_is_propose_only(reason): ...
def test_include_of_operator_excluded_row_changes_existing_entry(): ...
# substring check
def test_quote_normalisation_folds_case_whitespace_curly_quotes_and_entities():
    assert quote_ok(Evidence(kind="taper-description", quote="Bertha > ‘Greatest’"), b_with("bertha &gt;  'greatest'"))
def test_fabricated_quote_fails_the_edit(): ...
def test_quote_checked_against_claimed_kind_only(): ...   # present in review, claimed as taper-description -> fails
def test_quote_with_unescaped_braces_matches_escaped_bundle(): ...   # quote "{{x}}" vs bundle "{ {x} }"
# sibling-match tolerance
@pytest.mark.parametrize("d,row,ok", [(100, 102.0, True), (100, 102.01, False),        # 2 s floor
                                       (400, 404.0, True), (400, 404.01, False)])      # 1 % above 200 s
def test_sibling_match_tolerance(d, row, ok): ...
def test_sibling_match_unknown_duration_fails(): ...
# title bar: each path pass and fail
def test_title_from_sibling_needs_match_and_title_in_quote(): ...
def test_title_from_taper_description_passes(): ...
def test_title_from_own_original_tag_row_passes_other_row_fails(): ...
def test_title_from_setlistfm_jerrybase_or_review_alone_is_propose_only(): ...
def test_title_over_override_source_is_propose_only(): ...
def test_title_needs_high_confidence(): ...
@pytest.mark.parametrize("src", sorted(TITLE_BAR_SOURCES))
def test_every_title_bar_source_is_eligible(src): ...
# structure bar
def test_structure_with_s1t_filename_quote_passes(): ...
def test_structure_from_setlistfm_only_is_propose_only(): ...
def test_structure_over_existing_override_is_propose_only(): ...
# venue, city
def test_venue_medium_passes_low_fails_existing_override_proposes(): ...
def test_city_always_propose_only(): ...
# overrule bars by flag kind: every kind in the spec table
@pytest.mark.parametrize("flag,kind,bar", OVERRULE_CASES)   # one real flag string per kind, incl. briefing-other, other
def test_overrule_bar_by_kind(flag, kind, bar): ...
def test_duration_mismatch_is_never_overruled(): ...
def test_overrule_of_flag_not_judged_spurious_fails(): ...
def test_title_and_structure_overrules_need_high_and_quote(): ...
def test_structure_overrule_needs_taper_side_quote(): ...          # setlistfm-only quote fails
def test_title_overrule_from_weak_kinds_alone_fails(): ...          # review-only quote fails; taper-description passes
# auto-switch bar: each part
@pytest.mark.parametrize("break_it", ["no_format", "complaints", "worse_lineage", "unknown_lineage", "low_conf",
                                      "delivered", "marked", "keyed_entries", "existing_pin",
                                      "other_title_edit", "overrule_too"])
def test_switch_fails_each_part(break_it): ...
def test_switch_passes_when_every_part_holds(): ...
def test_switch_with_venue_only_passes(): ...
# vetoes
@pytest.mark.parametrize("veto", ["kind_hold", "not_correct_after", "not_fixable", "undecidable",
                                  "unjudged_flag", "better_sibling_without_switch", "no_edits"])
def test_verdict_level_vetoes(veto): ...
def test_any_failing_edit_blocks_auto(): ...
def test_propose_only_op_blocks_auto(): ...
# validation (Review Focus 1)
def test_validate_rejects_near_miss_filenames():
    for bad in ("GD73-06-10D1T01.mp3", "gd73-06-10d1t01.shn", "disc1/gd73-06-10d1t01.mp3", "1"):
        assert validate_targets(v_exclude(bad), b)
def test_validate_conflicts_and_keyed_exclude_and_unknown_flag_and_unconsidered_switch(): ...
# flag_passes
@pytest.mark.parametrize("verdict,conf,kind,ok", FLAG_PASS_CASES)
def test_flag_passes(verdict, conf, kind, ok): ...
def test_flag_passes_title_and_structure_kinds_need_a_passing_overrule_edit():
    # spurious/high with no overrule edit fails; with a failing overrule edit fails; with a passing one passes
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest packages/llama/tests/test_adjudicator_gate.py -q`.
- [ ] **Step 3: Implement** `gate.py`. Every comparison reads the module constants, with no literals inline.
- [ ] **Step 4: Run the tests, then the full suite.** Expect both green.
- [ ] **Step 5: Mutation check (recorded, not committed as code).** For each mutant below, name the expected red test **before** applying it. Clear `__pycache__` per mutant, run `./.venv/bin/python -m pytest packages/llama/tests/test_adjudicator_gate.py -q`, and record CAUGHT or MISSED with the red test's name in the task report.
  - The 60 s boundary: `>` to `>=` on `SHORT_EDIT_MAX_S`.
  - The 120 s sum: `>` to `>=` on `VERDICT_SUM_MAX_S`.
  - Unknown duration: `inf` to `0`.
  - The sibling floor: `SIBLING_TOL_S` 2 to 3.
  - The sibling fraction: `max` to `min`.
  - The own-tag-row exclusion removed.
  - The stem clause removed.
  - The `stem_in` token lookarounds removed.
  - `LONG_BAR_KINDS` gains `derivative-tag`.
  - The `TITLE_WEAK_KINDS` propose-only branch removed.
  - The title-in-quote requirement removed.
  - Each `OVERRULE_BAR` value flipped one step.
  - The resolved-song exclude rule removed.
  - Each of the five vetoes removed.
  - Each auto-switch part removed.
  - These, with the predicted red test:
    - `quote_ok` removed or always true: `test_fabricated_quote_fails_the_edit`.
    - The quote checked against any section instead of the claimed kind: `test_quote_checked_against_claimed_kind_only`.
    - The existing-overrides propose-only rule removed: `test_include_of_operator_excluded_row_changes_existing_entry`.
    - `REFUSED_INCLUDE_REASONS` emptied: `test_include_of_refused_reason_is_propose_only`.
    - The structure taper-side requirement removed: `test_structure_from_setlistfm_only_is_propose_only`.
    - The venue existing-override rule removed: `test_venue_medium_passes_low_fails_existing_override_proposes`.
    - The existing-pin switch rule removed: `test_switch_fails_each_part[existing_pin]`.
  - Every MISSED mutant gets a test before the commit.
- [ ] **Step 6: Commit**: `git commit -m "adjudicator: target validation and policy gate"`

---

### Task 6: Apply in one unit: filename-keyed writes, whole-show check, silenced flags, coverage, re-hold

**Model hint:** opus.

**Files:**
- Create: `packages/llama/src/llama/adjudicator/apply.py`
- Test: `packages/llama/tests/test_adjudicator_apply.py`

**Interfaces:**
- Consumes: `show_unit`, `ShowChanged`, `capture_view`; `overrules.records_for`/`merge_rules`/`flag_key`; `gather._sets_from_breaks`; `songs.normalize_song`; gate (Task 5): `flag_passes`, `STRUCTURE_KINDS`, `has_track_list_edit`, `has_track_list_or_structure_edit`, `GateResult`, `COVERAGE_ADDED_MAX_S`; `StationUnpaired`, `station_mark.StationUnreadable`, `IAError`, `HerderError`, `TaskFailed`, `RateLimited`.
- Produces:
  - `Redo = Callable[[str], Path | None]`: the caller's `_redo_show_locked` bound to the show. It is called inside the unit.
  - `earliest_stage(edits: Sequence[Edit]) -> str`:
    - `switch_recording` gives `select`.
    - `include`, `exclude`, `set_title`, `structure`, `venue`, `city`, and an `overrule` of a gather-family kind, give `gather`.
    - An `overrule` of `research-*` gives `vet`, and an `overrule` of `briefing-*` gives `brief`.
    - The earliest by `SHOW_STAGE_ORDER` wins.
  - `write_edits(show_ws, edits, *, show: Show, at: str, defer_subjectless_structure: bool) -> Overrides`. It is a raw `Overrides` model update written with `write_artifact`. It never goes through `cli._edit_overrides`, and never translates a number.
    - An include of an `operator-excluded` row removes it from `exclude`; any other include appends to `include`.
    - An exclude appends to `exclude` and removes the file from `include`.
    - `titles[file] = title`.
    - A structure edit sets `set_breaks` to its files in `show.json` play order (`[]` is kept as forced-no-breaks) and sets `encore_after`.
    - It sets `venue`, `city` and `recording`.
    - Overrules are `merge_rules(ov.overrules, records_for([flag], show, source="adjudicate", at=at))`, skipping subject-less `STRUCTURE_KINDS` when `defer_subjectless_structure`.
    - Propose-only ops are ignored.
  - `@dataclass(frozen=True) class TrackRow: filename: str; title: str; title_source: str; set: str; segue: bool; duration_s: float | None`. `capture_before(show: Show) -> list[TrackRow]`.
  - `whole_show_diff(before: list[TrackRow], after: Show, edits) -> list[str]`: the differences the edits did not predict, empty when they match.
    - The kept set must equal (before ∪ includes) − excludes, exactly.
    - Unnamed tracks keep their relative order, title, title_source, and set. Unnamed means not included, not excluded, and not `set_title` targets.
    - With a structure edit, a non-included track's set must equal `_sets_from_breaks(len(after.tracks), [1-based after position of each break file], 1-based after position of the encore file)`.
    - A `set_title` target must show `title == edit.title` and `title_source == "override"`.
    - Unnamed segues are compared only when the verdict has no structure edit.
    - Each difference is one line, e.g. `"gd73d1t03.mp3: title 'Bertha' -> 'Jam' (not predicted)"`.
  - `track_changes(before: list[TrackRow], after: Show) -> list[str]`, for the run report. It is built from before and after, not from the edit list:
    - Added files read `"+ <file> (<m:ss>) <title>"`.
    - Removed files read `"- <file> (<m:ss>) <title>"`.
    - A title change reads `"~ <file>: '<old>' -> '<new>'"`.
    - A set change reads `"~ <file>: set <old> -> <new>"`.
  - `silenced_flags(pre: Show, post: Show, verdict, gate: GateResult | None, *, mode: Literal["auto","accept"]) -> list[str]`: the pre-apply flags whose key (`flag_key`, or the flag text when that is None) is absent after the apply and that are not accounted for. In `auto`, accounted for means the judgement passes `flag_passes(j, pre, verdict, gate)`. In `accept`, it means the verdict judged the flag `spurious` or `real-fixed-by-action` at any confidence: Shawn's acceptance replaces the bar.
  - `coverage_failures(pre: Show, post: Show, *, mode: Literal["auto","accept"]) -> list[str]`, for a switch. The rules, each its own failure string:
    - missing title: a resolved pre title (`normalize_song`) is missing from the post titles.
    - total duration: the post total duration is below the pre total.
    - added duration: (sum of `duration_sec` over post tracks that are `unresolved` or `short_kept`) minus (the same sum over pre tracks) is over `COVERAGE_ADDED_MAX_S`.
    - gain (`auto` only): the post show has neither more tracks nor more resolved titles than the pre show.
    - held (`auto` only): the post show is held (`post.needs_review`).
  - `rehold_flags(pre: Show, post: Show, verdict, gate: GateResult) -> list[str] | None`: the post flags to auto-overrule, or None when any post flag does not qualify. All or nothing.
    - A post flag qualifies when its key is not None and equals, kind and subject both, the key of a pre-apply flag judged `spurious` that passes `flag_passes(j, pre, verdict, gate)`.
    - Never `alignment`, never a duration mismatch, and never a subject-less `STRUCTURE_KINDS` flag when `has_track_list_or_structure_edit(verdict)`.
  - `@dataclass class ApplyResult: status: Literal["applied","restored","transient","refused"]; held: bool; diff: list[str]; changes: list[str]; error: str | None; reheld: list[str]`.
  - `apply_verdict(show_ws, verdict, *, expect: ShowView, redo: Redo, mode: Literal["auto","accept"], gate: GateResult | None, on_commit: Callable[[Show, ApplyResult], None], trial: bool = False, at: str) -> ApplyResult`. `gate` is the verdict's `GateResult` in `auto` and None in `accept`.

**`apply_verdict` algorithm**, inside `with show_unit(show_ws, expect):`:
1. `pre = read show.json`, `before = capture_before(pre)`.
2. `write_edits(..., defer_subjectless_structure=has_track_list_edit(verdict))`.
3. `redo(earliest_stage(applicable edits))`, then `post = read show.json`.
4. Check by kind. If any check finds anything, raise `_Restore(failures)`:
   - With a switch: `coverage_failures(pre, post, mode=mode)`, then `silenced_flags`.
   - Without a switch: `whole_show_diff`, then `silenced_flags`.
5. If `mode == "auto"` and post is held, and `rehold_flags` is not None: write `records_for(those, post, source="adjudicate")` into overrides, clear `needs_review` and `review_flags` in show.json, `redo("package")`, and re-read post.
6. `result = ApplyResult("applied", post.needs_review, [], track_changes(before, post), None, reheld)`, then `on_commit(post, result)`, which writes the applied record inside the unit (Task 7).
7. If `trial`, raise `_TrialRestore(result)`.

Outside the unit:
- `_Restore` gives `status="restored"` with its diff.
- `_TrialRestore` gives its result with `status="applied"`. The files are restored.
- `StationUnpaired`, `StationUnreadable`, and any `LlamaError` other than `ShowChanged`, give `status="refused"` with the error.
- `IAError`, `HerderError` other than `RateLimited`, and `TaskFailed` give `status="transient"`.
- `RateLimited`, `ShowChanged` and `KeyboardInterrupt` propagate. The unit has restored the files first.

Accepted limitation: a restore after a successful `package` leaves the ledger's `selected` row (the ledger is outside the snapshot, as today), so the pilot's byte-identical claim covers the show directory, not the ledger.

- [ ] **Step 1: Write the failing tests.** Use `helpers.stub_stages` / `fixture_library.library_show` and a `redo` built from a fake `_redo_show_locked` that runs `process_show` with stub stages. Deterministic gather outcomes come from writing the post `show.json` the test wants inside the stub.

```python
def test_write_edits_is_filename_keyed_and_records_adjudicate_overrules(tmp_path):
    ov = write_edits(ws, [exclude("b.mp3"), set_title("c.mp3", "Jam"), structure(["c.mp3"], None),
                          overrule("venue mismatch: archive 'X' vs jerrybase 'Y'")], show=show, at=AT,
                     defer_subjectless_structure=False)
    assert ov.exclude == ["b.mp3"] and ov.titles == {"c.mp3": "Jam"} and ov.set_breaks == ["c.mp3"]
    assert [(r.kind, r.source) for r in ov.overrules] == [("venue", "adjudicate")]
def test_write_edits_include_of_operator_excluded_row_unexcludes(): ...
def test_write_edits_defers_subjectless_structure_overrules_with_track_list_edit(): ...
def test_structure_only_verdict_writes_subjectless_structure_overrule(): ...   # no deferral without a track-list edit
def test_earliest_stage_mapping(): ...   # select < gather < vet < brief, one case each
def test_whole_show_diff_accepts_exact_prediction(): ...
def test_whole_show_diff_catches_unnamed_title_shift(): ...      # include shifts desc-position titles one over
def test_whole_show_diff_catches_reorder_and_set_change_and_extra_drop(): ...
def test_whole_show_diff_predicts_structure_labels_and_ignores_segue_loss(): ...
def test_whole_show_diff_does_not_predict_included_track_title(): ...
def test_silenced_flag_without_passing_judgement_restores(tmp_path):
    r = apply_verdict(...)   # stub gather drops a "venue mismatch" flag the verdict judged spurious at low confidence
    assert r.status == "restored" and helpers.tree_bytes(ws.dir) == before_bytes
def test_silenced_flag_in_accept_mode_counts_any_confidence_spurious_or_fixed(tmp_path): ...
def test_switch_also_runs_silenced_flags(tmp_path): ...
@pytest.mark.parametrize("rule", ["missing_title", "total_duration", "added_duration", "gain", "held"])
def test_coverage_failures_each_rule(rule): ...   # one failing case per rule
def test_coverage_added_duration_boundary():
    # unresolved+short_kept post sum minus pre sum: 60.0 s passes, 60.01 s fails
def test_coverage_accept_mode_skips_gain_and_held(): ...
def test_switch_coverage_failure_restores_snapshot(tmp_path): ...
def test_rehold_overrules_only_full_key_matches_all_or_nothing(tmp_path): ...
def test_rehold_never_alignment_or_subjectless_structure_after_track_edit(): ...
def test_accept_mode_skips_rehold(): ...
def test_applied_record_written_inside_unit_commits(tmp_path):
    seen = []; r = apply_verdict(..., on_commit=lambda post, res: seen.append(capture_view(ws)))
    assert r.status == "applied" and seen   # called while the unit held the lock
def test_trial_restores_but_reports_applied(tmp_path): ...
def test_station_refusal_restores_and_becomes_proposal(tmp_path):        # Review Focus 5
    # redo raises StationUnpaired -> status "refused", error text kept, files byte-identical
def test_transient_failure_restores_and_is_transient(tmp_path): ...       # IAError, TaskFailed
def test_ratelimited_propagates_after_restore(tmp_path): ...
def test_showchanged_when_expect_is_stale(tmp_path): ...
def test_interrupt_mid_redo_restores_everything(tmp_path):                # Review Focus 4
    # redo raises KeyboardInterrupt after writing show.json and adjudication.json
    with pytest.raises(KeyboardInterrupt): apply_verdict(...)
    assert helpers.tree_bytes(ws.dir) == before_bytes and not (ws.dir / ".txn").exists()
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest packages/llama/tests/test_adjudicator_apply.py -q`.
- [ ] **Step 3: Implement** `apply.py`.
- [ ] **Step 4: Run the tests, then the full suite.** Expect both green.
- [ ] **Step 5: Mutation check (recorded).** Name the expected red test first, as in Task 5. The mutants:
  - The whole-show order check removed.
  - The unnamed-title check removed.
  - The structure-label prediction off by one.
  - `COVERAGE_ADDED_MAX_S` `>` to `>=`.
  - The `rehold_flags` all-or-nothing replaced with any-subset.
  - The `alignment` exclusion removed.
  - The subject-less deferral removed.
  - `silenced_flags` ignoring `flag_passes`.
  - These, with the predicted red test:
    - Kept-set exactness dropped (an extra drop passes): `test_whole_show_diff_catches_reorder_and_set_change_and_extra_drop`.
    - Coverage missing-title rule removed: `test_coverage_failures_each_rule[missing_title]`.
    - Coverage total-duration rule removed: `test_coverage_failures_each_rule[total_duration]`.
    - Coverage added-duration rule removed: `test_coverage_failures_each_rule[added_duration]`.
- [ ] **Step 6: Commit**: `git commit -m "adjudicator: apply in one unit with whole-show, silenced-flag, coverage and re-hold checks"`

---

### Task 7: Adjudication record, digest, and the per-show runner

**Model hint:** opus. The runner sequences six failure classes against the loop guard.

**Files:**
- Create: `packages/llama/src/llama/adjudicator/record.py`, `packages/llama/src/llama/adjudicator/runner.py`
- Test: `packages/llama/tests/test_adjudicator_record.py`, `packages/llama/tests/test_adjudicator_runner.py`

**Interfaces:**
- Consumes: everything in Tasks 3-6, `staleness.stale_message`, `override_keys.refusal`, `campaign.read_record`/`last_mark`/`awaiting_fix`, `is_delivered`, `catalog.CatalogEntry`. `runner.py` imports the two `read_record`s under aliases: `from llama.campaign import read_record as read_campaign` and `from llama.adjudicator.record import read_record as read_adjudication`.
- Produces (`record.py`):
  - `RECORD_FILE_VERSION = 1`.
  - `view_digest(view: ShowView) -> str`: the sha256 of canonical JSON (`sort_keys`, compact) over, parsed from the view's `show` and `overrides` bytes:
    - `review_flags`;
    - per track `[filename, title, title_source, set, segue, duration_sec]`;
    - per excluded row `[filename, reasons]`;
    - the `overrides.json` model dump with every overrule's `at` removed;
    - `show.identifier`.
    A missing show.json digests as `"absent"`. Research and briefing are not part of it.
  - `show_digest(show_ws) -> str` = `view_digest(capture_view(show_ws))`.
  - `AdjudicationRecord(BaseModel)`, permissive, with these fields:
    - `version`, `at`, `model`, `dry_run: bool`;
    - `outcome: Literal["applied","proposal","malformed","dry-run","accepted"]`;
    - `digest`, `verdict: dict`, `malformed: list[str]`;
    - `gate: list[dict]` (`EditGate` as a dict), `vetoes: list[str]`;
    - `applied: list[dict]` (`{"index","op","target","evidence_kinds"}`);
    - `result: dict` (`ApplyResult` fields), `partial_tape: bool`;
    - `held_proposal: dict | None = None`: for an applied show that is still held, `{"flags": [{flag, judgement}], "edits": [{op: "overrule", flag, confidence, why, evidence}]}`. `flags` lists every remaining post flag (its post text) with the verdict's judgement of the pre flag with the same key (None when there is none). `edits` holds an overrule of each remaining flag that judgement calls `spurious`, with the judgement's confidence and why, and the evidence of the verdict's own `overrule` edit for that key, else `[]`. Accept builds `OverruleFlag`s from them with `model_construct`, since accept runs no gate and the evidence minimum is a gate input.
  - `write_record(show_ws, rec) -> None`: an atomic write to `show_ws.adjudication`, with no lock of its own.
  - `read_record(show_ws) -> AdjudicationRecord | None`: unreadable reads as None.
  - `is_current(show_ws) -> bool`: a readable record that is not a dry run and whose `digest == show_digest(show_ws)`.
  - `write_outside_unit(show_ws, rec_without_digest, *, expect: ShowView) -> bool`. Under `file_lock(show_ws.lock)`, if `capture_view == expect`, it stamps the digest and writes, then returns True. Otherwise it writes nothing and returns False. The runner maps False to `CHANGED`.
- Produces (`runner.py`):
  - `@dataclass class Context`:
    - `config: Config`, `ia`, `ledger: Ledger`, `provider` (a ladder, or None), `redo: Callable[[CatalogEntry, str], Path | None]`;
    - `sink: Path | None = None`: the pilot writes records here (`<sink>/<slug>.json`) instead of `adjudication.json`, and the digest/current logic is unchanged;
    - `now: Callable[[], str]`.
  - Outcome constants, a closed set of strings:
    `APPLIED = "applied"`, `APPLIED_HELD = "applied, still held"`, `PROPOSAL = "held with proposal"`, `MALFORMED = "malformed"`, `STALE = "stale: reprocess first"`, `CURRENT = "skipped: current"`, `HAS_RECORD = "skipped: has a record"`, `NOT_HELD = "skipped: not held"`, `CHANGED = "skipped: changed"`, `UNJUDGED = "unjudged"`, `FAILED = "failed"`, `DRY_RUN = "dry-run"`, `ACCEPTED = "accepted"`, `PROPOSAL_STALE = "proposal stale"`, `NO_PROPOSAL = "no proposal"`.
  - `@dataclass class ShowOutcome: slug: str; outcome: str; detail: str = ""; record: AdjudicationRecord | None = None; changes: list[str] = field(default_factory=list); delivered_changed: bool = False; fixed_eligible: bool = False; llm_failure: bool = False`.
  - `adjudicate_show(ctx, entry: CatalogEntry, *, dry_run: bool = False, force: bool = False, trial_policy: Callable[[Verdict, GateResult], bool] | None = None) -> ShowOutcome`. The order:
    1. Not held gives `NOT_HELD`.
    2. Not `force` and `is_current` gives `CURRENT`. Not `force`, `dry_run`, and a readable non-dry-run record with outcome `applied`, `proposal` or `accepted` gives `HAS_RECORD` (`--force` to replace it), with no call.
    3. A legacy overrides refusal or `stale_message` gives `STALE` with the message as detail.
    4. `build_bundle`: any exception gives `FAILED`, logged, with nothing written.
    5. `call_adjudicator`:
       - `RateLimited` propagates.
       - `TaskFailed`/`HerderError` give `FAILED` with `llm_failure=True`.
       - A render `ValueError` gives `FAILED`.
       - `ctx.provider is None` gives `FAILED` with `no adjudicate provider`.
    6. `validate_targets`: reasons give a `MALFORMED` record via `write_outside_unit`.
    7. `evaluate` with `Facts` built from the bundle:
       - `delivered = is_delivered(ledger, pid)`;
       - `marked = last_mark(read_campaign(ws)) is not None`, where an unreadable campaign record counts as marked;
       - `lineage = lineage_table(...)`;
       - `complaints = {prov.assessment.reviewed_identifier: len(recording_complaints)}`.
    8. `dry_run`: when `trial_policy` is given and `trial_policy(verdict, gate)` is true, a trial: the step 9 call with `trial=True` and a no-op `on_commit`, restored by the unit, then a `DRY_RUN` record carrying the trial's `result` is written after the restore. Otherwise a `DRY_RUN` record (`dry_run=True`). Not dry-run and not `auto` gives a `PROPOSAL` record.
    9. Otherwise `apply_verdict(mode="auto", gate=gate, expect=bundle.view, redo=partial(ctx.redo, entry), on_commit=<write applied record with the digest computed then>)`, then map the result:
       - `applied` gives `APPLIED` or `APPLIED_HELD`, with `changes`. `delivered_changed = delivered and view_digest(bundle.view) != <the applied record's digest>`, which covers venue edits and overrules too. `fixed_eligible = last_mark(campaign) is not None and not awaiting_fix(campaign)`, read after the apply. For `APPLIED_HELD` the applied record carries `held_proposal`.
       - `restored` gives a `PROPOSAL` record carrying the diff.
       - `refused` gives a `PROPOSAL` record carrying the error.
       - `transient` gives `UNJUDGED`, with no record write.
       - `ShowChanged` gives `CHANGED`, with nothing written.
  - `accept_proposal(ctx, entry) -> ShowOutcome`. The steps:
    1. The record must not be a dry run and must have outcome `proposal`, or outcome `applied` with a `held_proposal` that has edits. Else `NO_PROPOSAL`.
    2. `bundle = build_bundle(...)` captures the view first. `view_digest(bundle.view) == rec.digest` must hold, else `PROPOSAL_STALE`. The digest and the unit's expected view are therefore the same state.
    3. The applicable edits are the verdict's non-`PROPOSE_ONLY_OPS` edits, or the `held_proposal` edits for an applied record; none gives `NO_PROPOSAL`.
    4. `validate_targets` is re-run against that bundle; any reason gives `MALFORMED`.
    5. A switch with `filename_keyed_entries` gives `FAILED`, with the Task 2 refusal text.
    6. `apply_verdict(mode="accept", gate=None, expect=bundle.view)`. There is no gate and no re-hold. A switch runs coverage's title and duration rules (`mode="accept"`); a non-switch runs the whole-show diff. Both run `silenced_flags` in accept mode. The `on_commit` record has outcome `accepted`.
    The outcomes. On anything but a commit, the stored record is left unchanged:

    | Apply result | Outcome | Detail |
    |---|---|---|
    | committed | `ACCEPTED` | `still held` when post is held |
    | restored (diff, silenced flags) | `FAILED` | `accept restored: <first failure>` |
    | restored (switch coverage) | `FAILED` | `accept restored: <first failure>; to switch anyway: llama fix <slug> --recording <id>` |
    | refused (station) | `FAILED` | the error |
    | transient | `FAILED` | `transient: <error>; try again` |
    | `ShowChanged` | `CHANGED` | |
    | `RateLimited` | propagates | the caller prints it |
  - `hook_enabled(config: Config, flag: bool | None) -> bool`: `flag if flag is not None else config.adjudicate.enabled`.

- [ ] **Step 1: Write the failing tests.** The runner tests use a `Context` with `FakeProvider` verdicts and the `redo` fake from Task 6.

```python
# record
def test_digest_ignores_overrule_timestamps_research_and_briefing(): ...
def test_digest_changes_on_flags_tracks_excluded_overrides_identifier(): ...   # one parametrized case each
def test_is_current_false_for_dry_run_unreadable_and_changed(): ...
def test_write_outside_unit_refuses_when_view_changed(): ...
def test_show_digest_equals_view_digest_of_captured_view(): ...
# runner
def test_not_held_and_current_are_skipped_without_llm_call(): ...   # FakeProvider has no queued reply
def test_force_rejudges_a_current_show(): ...
def test_stale_show_is_not_judged(): ...      # outcome STALE, detail = stale_message text, no call
def test_bundle_error_is_failed_and_writes_nothing(): ...
def test_llm_failure_marks_llm_failure_and_writes_nothing(): ...
def test_ratelimited_propagates_and_record_unchanged(): ...
def test_malformed_verdict_stores_record_and_stays_held(): ...
def test_gate_failure_stores_proposal_with_gate_reasons(): ...
def test_auto_apply_clears_and_writes_applied_record_with_post_digest(tmp_path):
    out = adjudicate_show(ctx, entry)
    rec = read_record(ws)
    assert out.outcome == APPLIED and rec.outcome == "applied" and rec.digest == show_digest(ws)
    assert is_current(ws)                     # loop guard: a later pipeline run skips it
    assert rec.applied[0]["evidence_kinds"] == ["taper-description"]
def test_applied_but_still_held_is_current_and_not_rejudged(): ...
def test_applied_but_still_held_stores_held_proposal_of_leftover_flags(): ...
def test_delivered_changed_by_digest_covers_venue_only_apply(): ...   # no track changes, digest moved -> True
def test_fixed_eligible_for_marked_show_whose_campaign_record_ends_processed(): ...
def test_restored_apply_becomes_proposal_with_pre_state_digest(): ...
def test_transient_apply_failure_leaves_no_record(): ...
def test_proposal_write_refused_by_changed_view_is_changed(): ...    # write_outside_unit False -> CHANGED
def test_concurrent_change_writes_nothing(tmp_path):              # Review Focus 3
    # the FakeProvider's complete() side effect rewrites overrides.json mid-call
    assert adjudicate_show(ctx, entry).outcome == CHANGED and not ws.adjudication.exists()
def test_dry_run_record_is_never_current_and_never_accepted(): ...
def test_dry_run_keeps_proposal_and_applied_records_unless_forced(): ...   # HAS_RECORD, no call
def test_trial_policy_true_trials_and_restores_false_records_dry_run(): ...   # one LLM call either way
def test_sink_writes_to_pilot_dir_not_adjudication_json(): ...
def test_accept_applies_failed_gate_edits_but_not_propose_only(): ...
def test_accept_refuses_stale_digest(): ...
def test_accept_race_show_changes_between_check_and_write_refuses(tmp_path):
    # change overrides.json after build_bundle captured the view -> CHANGED, record unchanged, files unchanged
def test_accept_switch_refuses_with_keyed_entries(): ...
def test_accept_switch_coverage_failure_restores_and_names_fix_recording(): ...
@pytest.mark.parametrize("result", ["restored", "refused", "transient", "changed"])
def test_accept_non_commit_leaves_record_unchanged(result): ...      # outcome per the table
def test_accept_ratelimited_propagates_and_record_unchanged(): ...
def test_accept_held_proposal_overrules_leftover_flags(): ...
def test_hook_enabled_tristate(): assert hook_enabled(Config(), None) and not hook_enabled(Config(), False)
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest packages/llama/tests/test_adjudicator_record.py packages/llama/tests/test_adjudicator_runner.py -q`.
- [ ] **Step 3: Implement** `record.py` and `runner.py`.
- [ ] **Step 4: Run the tests, then the full suite.** Expect both green.
- [ ] **Step 5: Commit**: `git commit -m "adjudicator: adjudication.json record, digest loop guard, per-show runner"`

### Checkpoint A (operator, after Task 7)

The core (bundle, verdict, gate, apply, record, runner) is done and reviewed, before any CLI wiring. Report to Shawn: the suite count, both mutation tables from Tasks 5 and 6, and any MISSED mutant still open. Task 8 starts on his go.

---

### Task 8: `llama adjudicate`: the backlog command, pacing, `--dry-run`, `--force`, `--accept`, run report

**Model hint:** sonnet. The loop is `_reapply_list`'s template.

**Files:**
- Create: `packages/llama/src/llama/adjudicator/report.py`
- Modify: `packages/llama/src/llama/cli.py` (new `adjudicate` command, `_adjudicate_context`)
- Test: `packages/llama/tests/test_adjudicate_cmd.py`, `packages/llama/tests/test_adjudicator_report.py`

**Interfaces:**
- Consumes: `runner.*` (Task 7), `_meter`, `decide`, `Progress`, `pacing_state.read_state`, `pace_options`, `count_llm_calls`, `make_providers`, `_destination_is_voiced`, `reapply_mod.STOP_AFTER_LLM_FAILURES`.
- Produces:
  - `cli._adjudicate_context(config, ia, ledger, providers) -> runner.Context`. The `redo` is `lambda e, st: _redo_show_locked(config, ia, ledger, _resolve_show(config, ledger, e.slug), st)`, and the provider is `providers.get("adjudicate")`. Task 9 and Task 10 reuse it.
  - `report.proposal_commands(slug: str, verdict: Verdict) -> list[str]`: the propose-only items as commands, per op:
    - `set_date`: `llama fix <slug> --set-date <value>`
    - `untitled`: `llama fix <slug> --untitled`
    - `narration`: `llama fix <slug> --narration <value>`
    - `rm`: `llama rm <slug>`
    - `redo_research`: `llama redo <slug> --from research`
  - `report.render_proposal(rec: AdjudicationRecord, show: Show) -> list[str]`:
    - First `proposal (<model>, <at>): <kind>; correct after: <yes|no|unsure>`.
    - Then per flag `  flag: <flag> -> <verdict> (<confidence>): <why>`.
    - Then per edit `  edit <i>: <op> <target> [<bar>: passed|<reason>]`, and per evidence item `    <kind>: "<quote>"`.
    - Then `  decide: <text>` for a hold, `  partial tape` when set, and `  run: <command>` per `proposal_commands` line.
    - For an applied record with `held_proposal`: first `applied (<model>, <at>), still held:`, then per remaining flag `  flag: <flag> -> <verdict> (<confidence>): <why>` (`-> not judged` when None), then per edit `  edit <i>: overrule <flag>`.
  - `report.render_report(outcomes: list[ShowOutcome], *, voiced: Callable[[str], bool]) -> list[str]`. The exact headers:
    - `summary: N shows: <outcome> K, ...`, one count per outcome present, in the constant order of Task 7.
    - `auto-applied track-list changes:`, then `  <slug>:` and `    <change>` per `ShowOutcome.changes`.
    - `held with proposal:`, then `  <slug>: <first failing gate reason, or veto, or diff, or error>`. `APPLIED_HELD` shows are listed here too, as `  <slug>: applied, still held: <first remaining flag>`.
    - `stale: reprocess first:`, then `  <slug>: <detail>`.
    - `eligible for llama deliver --fixed:`, then `  <slug>` per `delivered_changed` outcome with `fixed_eligible`.
    - `delivered shows changed (re-deliver):`, then `  llama deliver <slug>` per other `delivered_changed` outcome, with ` --replace-voiced` appended when `voiced(slug)`.
    - An empty section is omitted.
  - The command `llama adjudicate [SLUG...] [--held] [--state S] [--artist A] [--profile P] [--run R] [--dry-run] [--force] [--accept] [--yes] [--no-pacing]` (`rich_help_panel="Fix & ship"`).
    - With no slug and no selector, it takes the held shows. Slugs and selectors are exclusive: `give shows OR selectors, not both`.
    - `--dry-run` never overwrites a proposal or applied record unless `--force` is also given (`skipped: has a record`).
    - `--accept` takes named slugs only (`--accept takes named shows`) and refuses `--dry-run`/`--force`. Each proposal is printed first (`report.render_proposal`), then `Accept this proposal? [y/N]` unless `--yes`. Without a TTY and without `--yes` it refuses: `--accept needs --yes when not interactive`.
    - The loop, per show:
      1. The pacing gate `decide(_pacing._now(), _meter(config, pace), Progress(state.per_show_delta), pace)`. `PauseUntil` prints `paused: <reason>` and `  re-run the same command to continue (judged shows are skipped while current)`, then ends with the report so far.
      2. `adjudicate_show`.
      3. `RateLimited` prints the same two lines.
      4. `llm_failure` raises the consecutive count, and `STOP_AFTER_LLM_FAILURES` (3) in a row prints `stopping after 3 consecutive LLM failures` and ends. A judged show (any record written) resets the count.
      5. Any other exception is that show's `FAILED` (one bad show never aborts the run).
    - One line per show: `<slug>: <outcome>[ (<detail>)]`. Then the report. Exit 1 when any show `FAILED` or the run stopped on LLM failures, else 0. `set_capture_dir(config.root / "llm-failures")` is called before the loop. The pacing EWMA is not recorded, as in `reapply`.

- [ ] **Step 1: Write the failing tests.** `cli.make_providers` is monkeypatched to the full `test_pipeline.fake_providers(config)` dict plus `"adjudicate": FakeProvider(completes=[...])`, since the apply's redo needs every stage key. The library comes from `fixture_library.build_library`. `cli.read_usage` returns a reading when the test needs the gate.

```python
def test_default_selects_held_and_skips_current(tmp_path, monkeypatch): ...
def test_slugs_and_selectors_are_exclusive(): ...
def test_dry_run_writes_dry_run_records_and_changes_nothing_else(): ...
def test_force_rejudges(): ...
def test_pause_before_show_prints_and_stops_with_report(): ...
def test_ratelimited_pauses_and_leaves_show_unjudged(): ...
def test_three_consecutive_llm_failures_stop(): ...
def test_one_bad_show_does_not_abort(): ...       # build_bundle raises OSError on show 1; show 2 judged
def test_accept_requires_named_shows_and_yes_without_tty(): ...
def test_accept_yes_applies_and_prints_proposal_first(): ...
def test_exit_code_one_on_failure(): ...
# report
def test_report_sections_and_omits_empty(): ...
def test_report_lists_track_changes_from_diff_with_durations():
    assert "    - gd73-06-10d2t01.mp3 (3:10) Jam" in lines
def test_report_names_redeliver_command_for_voiced():            # Review Focus 5
    assert "  llama deliver s1 --replace-voiced" in lines and "  llama deliver s2" in lines
def test_report_lists_fixed_eligible_shows_apart_from_redeliver(): ...
def test_report_lists_applied_still_held_under_held_with_proposal(): ...
def test_render_proposal_renders_held_proposal(): ...
def test_render_proposal_layout(): ...       # exact first line, a flag line, an edit line with bar reason, a quote line, a run: line
def test_proposal_commands_per_op(): ...
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest packages/llama/tests/test_adjudicate_cmd.py packages/llama/tests/test_adjudicator_report.py -q`.
- [ ] **Step 3: Implement** the command and `report.py`.
- [ ] **Step 4: Run the tests, then the full suite.** Expect both green.
- [ ] **Step 5: Commit**: `git commit -m "llama adjudicate: paced backlog sweep with dry-run, force, accept and run report"`

---

### Task 9: Pipeline step: `get`, `run approve`, `run resume`, `redo` hooks and `--adjudicate/--no-adjudicate`

**Model hint:** opus. Lock ordering, the pacing boundary and pause semantics all apply.

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`_execute`, `_get_query`, `_get_profile`, `get`, `run_approve`, `run_resume`, `_resume_run`/`_resume_locked`, `_sweep_runs`, `redo`, `_redo_batch`, `_redo_run_level`; new `_adjudicate_enabled`, `_adjudicate_after`)
- Modify: `packages/llama/tests/conftest.py`
- Test: `packages/llama/tests/test_adjudicate_pipeline.py`

**Interfaces:**
- Consumes: `runner.hook_enabled`, `runner.adjudicate_show`, `cli._adjudicate_context` (Task 8).
- Produces:
  - `cli._adjudicate_enabled(config, flag: bool | None) -> bool` delegates to `runner.hook_enabled`. It is the one name tests patch.
  - `conftest._no_ambient_adjudication` (autouse): `monkeypatch.setattr(cli, "_adjudicate_enabled", lambda config, flag: bool(flag))`. The suite therefore never adjudicates on the config default; only an explicit `--adjudicate` (or a test re-patching it to `runner.hook_enabled`) does. Its docstring follows `_no_live_usage_meter`'s.
  - `_execute(..., adjudicate: bool = False)`. Every production call site passes `_adjudicate_enabled(config, flag)` explicitly. `get`, `run resume` (and `--all`) take the flag, and `redo --run --from search|winnow` passes `redo`'s own `--adjudicate/--no-adjudicate`. `run approve` passes `_adjudicate_enabled(config, None)`. `request.json` never records it.
  - `get`, `run resume` and `redo` gain `adjudicate: bool = typer.Option(None, "--adjudicate/--no-adjudicate", help="Judge a show that ends held with the adjudicator (default: [adjudicate] enabled)")`.
  - `_adjudicate_after(ctx, entry, pace, state) -> ShowOutcome | PauseUntil | RateLimited | None`. This is the gate, then `adjudicate_show`. It runs only after the caller's lock and unit are released, and returns a pause instead of raising. It is a no-op returning None when the show is not held, the hook is disabled, or the record is current.

**Hook placement:**
- In `_execute`'s show loop, right after `with file_lock(lock_path, blocking=False): _process(entry)` exits (so outside the show lock), and before the pacing boundary is recorded: when `adjudicate` and `_process` reported held (`needs-review, skipped`), call `_adjudicate_after` with the `CatalogEntry` from `_resolve_show(config, ledger, slugify(pid))`.
  - A `PauseUntil` or `RateLimited` sets `limited`. This show goes on a separate `adjudication_pending` list, and `unprocessed.extend(pending[idx + 1:])` takes the rest. The next pause cycle runs `adjudication_pending` through `_adjudicate_after` only, before `pending`: no second `_process` and no second count in `held`. A checkpointed run lists them in its resume list as before, so a later `run resume` re-runs `process_show` (stages skip) and then adjudicates.
  - Under `--no-pacing` a `RateLimited` in adjudication does not pause: the show counts as held and unjudged (`adjudicated <pid>: unjudged`), not failed.
  - On a pause the exit code is reapply's: 1 when any show failed, else 0.
  - Its outcome line prints as `adjudicated <pid>: <outcome>`.
  - The boundary is recorded after adjudication, so the learned per-show cost includes it: `llm_calls()` counts it because the adjudicate provider comes from the counted `providers`.
  - The deferred, blocking-lock pass gets the same hook after its `with file_lock(...)`.
- Single `redo`: after `_redo_show` returns None (`still held: <slug>`) and outside `_strict_refusal_hint`, call `_adjudicate_after` with `pace_options(config)`.
  - A pause prints `paused adjudication: <reason>; judge it later with: llama adjudicate <slug>` and exits 0.
  - The redo's own result is never changed by an adjudication failure. A `FAILED` outcome prints its line and the exit code stays the redo's.
- `_redo_batch`: the same per show, with the reapply-style gate before each adjudication. After the first pause it stops adjudicating, while the redos go on, and prints the `paused adjudication` line once naming `llama adjudicate --held`.
- `fix`, `triage`, `reapply` and the adjudicator's own `redo` callable never call `_adjudicate_after`.

- [ ] **Step 1: Write the failing tests.** Re-patch `cli._adjudicate_enabled` to `runner.hook_enabled` where the config default is under test. Use `test_pipeline.fake_providers` extended with `"adjudicate"`.

```python
def test_get_adjudicates_a_show_that_ends_held_and_counts_it_in_the_boundary(): ...
def test_get_no_adjudicate_flag_and_config_false_skip(): ...         # tri-state: None->config, True, False
def test_config_default_enables_hook(monkeypatch):
    monkeypatch.setattr(cli, "_adjudicate_enabled", runner.hook_enabled) ...
def test_adjudication_runs_after_the_show_lock_is_released():
    # adjudicate_show stub asserts file_lock(ws.lock, blocking=False) can be taken
def test_ratelimited_in_adjudication_pauses_run_and_resume_adjudicates_it():
    # after the pause cycle: _process ran once for the show, held counted once, adjudicate_show called twice
def test_pacing_pause_before_adjudication_puts_show_on_adjudication_pending(): ...
def test_ratelimited_in_adjudication_under_no_pacing_counts_held_unjudged(): ...   # not failed, exit 0
def test_run_resume_flag_passes_through_and_all_sweep_too(): ...
def test_run_approve_uses_config_value(): ...
def test_redo_run_level_passes_redo_flag(): ...      # redo --run --from winnow --no-adjudicate never adjudicates
def test_request_json_never_records_adjudicate(): ...
def test_redo_single_adjudicates_still_held_and_keeps_redo_exit_code(): ...
def test_redo_single_pause_prints_later_command(): ...
def test_redo_batch_gate_stops_adjudicating_but_not_redoing(): ...
def test_fix_triage_reapply_never_adjudicate():
    # spy on runner.adjudicate_show; a fix that leaves the show held, a triage edit, a reapply
def test_apply_redo_never_adjudicates(): ...   # spy count == 1 across an auto-apply that ends held
def test_adjudication_failure_never_touches_committed_result(): ...   # adjudicate_show raises OSError after get packaged/held
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest packages/llama/tests/test_adjudicate_pipeline.py -q`.
- [ ] **Step 3: Implement** the hooks as placed above.
- [ ] **Step 4: Run the full suite.** Expect it green. The autouse fixture is what keeps every existing held-show test off the adjudicator.
- [ ] **Step 5: Commit**: `git commit -m "llama: adjudicate as a pipeline step in get, run approve/resume and redo"`

---

### Task 10: Triage: print the stored proposal, `[a] accept proposal`

**Model hint:** sonnet.

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`_resolve_prompt`, `_interactive_resolve`)
- Test: `packages/llama/tests/test_triage.py`

**Interfaces:**
- Consumes: `record.read_record`/`is_current`, `runner.accept_proposal`, `cli._adjudicate_context`, `report.render_proposal`/`proposal_commands` (Task 8). `cli.py` already calls `campaign.read_record`, so the adjudicator's comes in under the alias `read_adjudication`.
- Produces:
  - `_resolve_prompt(..., accept: bool = False)` inserts `[a] accept proposal / ` before `[s]kip`, by replacement like `[t]`/`[u]`.

In triage, after `_print_show_entry` for a held show:
- A readable record that is not a dry run and has outcome `proposal`, or outcome `applied` with a `held_proposal`, prints `render_proposal`.
- If the record is not current, print `proposal is stale (the show changed since it was judged); re-judge with: llama adjudicate <slug>` and offer no `[a]`.
- If it is current with at least one non-propose-only edit (or, for an applied record, at least one `held_proposal` edit), offer `[a]`.
- `[a]` runs `accept_proposal` with the context, then handles the outcome:
  - `ACCEPTED` prints `<slug>: proposal accepted` followed by `packaged: …`/`still held: <slug>`, and returns.
  - `CHANGED` re-enters as the other edits do.
  - Anything else prints `error: <outcome> <detail>` and returns to the prompt.
  - `RateLimited` prints `error: rate limited (<reason>); accept it later with: llama adjudicate <slug> --accept --yes` and returns to the prompt.
- A dry-run or malformed record prints nothing and offers nothing.

- [ ] **Step 1: Write the failing tests**

```python
def test_triage_offers_a_only_for_current_proposal_with_applicable_edits(): ...
def test_triage_stale_proposal_says_so_and_offers_no_a(): ...
def test_triage_propose_only_proposal_prints_commands_without_a(): ...
def test_triage_dry_run_record_is_not_shown(): ...
def test_triage_a_accepts_and_leaves_show(): ...
def test_triage_applied_still_held_renders_held_proposal_and_offers_a(): ...
def test_triage_a_ratelimited_returns_to_prompt(): ...
def test_resolve_prompt_all_conditional_combinations_still_derive_from_resolve_prompt(): ...   # extend the existing M2 test
```

- [ ] **Step 2: Run them and see them fail.** Run `./.venv/bin/pytest packages/llama/tests/test_triage.py packages/llama/tests/test_adjudicator_report.py -q` and expect the new tests to fail.
- [ ] **Step 3: Implement** the rendering and the triage changes.
- [ ] **Step 4: Run the full suite.** Expect it green.
- [ ] **Step 5: Commit**: `git commit -m "triage: show the adjudicator's proposal and accept it with [a]"`

---

### Task 11: Pilot script and docs

**Model hint:** sonnet.

**Files:**
- Create: `scripts/adjudicate_pilot.py`, `scripts/test_adjudicate_pilot.py`
- Modify: `packages/llama/CLAUDE.md` (a new `## Adjudicator` section, plus a `llama adjudicate` line in Commands), the root `CLAUDE.md` (the llama row of "Where the detail lives" mentions the adjudicator), `scripts/CLAUDE.md` (the pilot)

**Interfaces:**
- Consumes: `runner.adjudicate_show(..., dry_run=True, trial_policy=...)` with `Context.sink`, `verdict.model_label`, `herder.usage.read_usage`, `catalog.iter_shows`.
- Produces: `python scripts/adjudicate_pilot.py <subcommand>` with these subcommands:
  - `select [--n 30] [--seed 20261106] [--out DIR]`: stratifies the held shows into the spec's Intent classes and writes `DIR/shows.json` (`[{slug, cls}]`). The classes are partial tape, partial tape with a better sibling, better sibling, untitled or untitled-echo, scrambled or shifted tags, needs a listen, and other. The class comes from the prototype verdict's `root_causes` at `~/.llama-harness/t3/verdicts/<slug>.json` when one exists, else from flag patterns. The allocation is proportional, with at least 2 per class. It is read-only.
  - `run --arm opus|sonnet [--out DIR] [--trial-applies 3]`:
    - Each arm's config pins `[llm.adjudicate] model` to the arm's alias, which never escalates.
    - Per show: read the meter, then call `adjudicate_show(ctx, entry, force=True, dry_run=True, trial_policy=policy)` with `sink=DIR/<arm>/`: one LLM call per show. `policy(verdict, gate)` is true when `gate.auto` and the verdict has a switch, and for the first `--trial-applies` other `gate.auto` verdicts. Then read the meter again and append a row to `DIR/<arm>/costs.jsonl`: `{slug, cls, outcome, five_hour_before, five_hour_after, wall_s, trial}`.
    - The meter reader is injected: `run(..., read_meter: Callable[[], float | None] = <herder.usage.read_usage five-hour reading>)`. The tests pass their own.
    - It refuses to start while a `llama` process runs (`campaign_gate`'s process check).
  - `compare [--out DIR]`: writes `DIR/compare.md`, and never a name starting REPORT/SUMMARY/FINDINGS/ANALYSIS. It contains:
    - per class and arm, the counts by outcome and the projected held-with-proposal count scaled to the held population;
    - the cross-arm disagreements;
    - agreement with the prototype verdicts, by `kind` and by edit target;
    - per-show cost and wall time per arm, and the projected full-sweep cost;
    - the strict-surface list for Shawn: every auto-applied edit with `bar` `long`, `title` or `structure`, or op `switch_recording`;
    - the auto-apply list for the Opus reviewer.
- Docs. `## Adjudicator` in `packages/llama/CLAUDE.md` covers, in at most ~40 lines:
  - the command and its flags;
  - the pipeline step and `[adjudicate] enabled`;
  - the bars, the constants and their location;
  - `adjudication.json` and the digest guard;
  - `[a]`, `fix --recording`/`--clear-recording`/`--clear-include`;
  - the limitation (subject-less overrules persist per recording);
  - the old-binary `recording` caveat;
  - the conftest fixture that keeps tests off the adjudicator.
  Update the "Nine named touchpoints" sentence to ten.

- [ ] **Step 1: Write the failing tests** (`scripts/test_adjudicate_pilot.py`, offline, over `fixture_library.build_library` plus fake verdict files). `scripts/` tests do not get the llama conftest, so every test injects the meter reader:

```python
def test_select_stratifies_with_floor_and_is_deterministic(tmp_path): ...
def test_run_writes_sink_records_not_adjudication_json(tmp_path): ...
def test_run_trials_switch_verdicts_and_restores(tmp_path): ...        # library tree byte-identical after
def test_run_pins_model_per_arm(tmp_path): ...                          # model_label in records == claude_cli:<arm>
def test_run_makes_one_llm_call_per_show_trial_or_not(tmp_path): ...
def test_run_never_calls_the_live_meter(tmp_path, monkeypatch):
    # herder.usage.read_usage patched to raise; run with an injected meter passes and the fake was read twice per show
def test_compare_lists_strict_surface_and_projection(tmp_path): ...
```

- [ ] **Step 2: Run them and see them fail**: `./.venv/bin/pytest scripts/test_adjudicate_pilot.py -q`.
- [ ] **Step 3: Implement** the script, then write the docs.
- [ ] **Step 4: Run the full suite.** Expect it green.
- [ ] **Step 5: Commit**: `git commit -m "adjudicator: pilot script and docs"`

### Checkpoint B (operator, after Task 11, before merge, release or install)

Implementers never run the pilot. It runs from the worktree against `~/.llama`, and only on Shawn's go, because it performs trial applies on real shows. Then, in order: the pilot (`select`, `run --arm opus`, `run --arm sonnet`, `compare`); the Opus review of every auto-applied edit and the disagreements; the acceptance bar (zero wrong auto-applied > 60 s track-list edits, title fills or replacements, structure edits or switches); Shawn's model decision; and any failing class demoted to propose-only. Merge, release and install wait for all of it.

---

## Spec coverage (self-review)

| Spec section | Task |
|---|---|
| Goals 1 (`llama adjudicate`), backlog loop, pacing, `--dry-run`, `--force`, run report | 7, 8 |
| Goal 2 (pipeline step, config, tri-state flags, never replayed) | 1, 9 |
| Goal 3 (triage proposal, `[a]`, `--accept --yes`) | 7, 8, 10 |
| Goal 4 (recording pin, `fix --recording`, select honours it, clear-include) | 1, 2 |
| Goal 5 (pilot) | 11 |
| Evidence bundle, notes reach an LLM (docstring) | 1, 3 |
| The call (tier high, `{{…}}` safe, per-show error isolation) | 1, 4, 7 |
| Verdict schema by filename, propose-only ops | 4 |
| Auto-switch bar incl. coverage | 5, 6 |
| Policy gate tables, overrule bars, vetoes, constants in one place | 5 |
| Stale pre-flight, target validation | 1, 5, 7 |
| Apply in a unit, whole-show check, silenced flags, re-hold, apply failure, `source: adjudicate`, re-delivery hints | 6, 7, 8 |
| Adjudication record, digest, loop guard | 7 |
| Mutation-checked boundaries (Constraints) | 5 Step 5, 6 Step 5 |
| Pilot acceptance bar, model decision, propose-only demotions | Checkpoint B |

## Ambiguities resolved in this plan (for the reviewer)

1. **Unknown duration in the 120 s sum** counts as `inf`, so one unknown-length edit puts every track edit in that verdict on the long bar. The spec says unknown counts as > 60 s, but gives no number for the sum.
2. **The long bar takes the filename stem only, as a whole token.** This is stricter than the spec, which also allows "the track's position": per-disc numbering makes a position collide (`d1t1` inside `d1t10`, track 1 of each disc), so there is no position alternative and the stem must not be part of a longer token.
3. **"Resolved song title"** means `title_source != "unresolved"`, and the title is neither a placeholder nor filler, where filler means every segue component (split on `>` and `->`) is `structure.is_filler`. Excluding a kept `Tuning` track is therefore a short/long-bar edit, not propose-only; `Tuning > Promised Land` stays propose-only.
4. **A new title must appear in its quote** on every title-bar path, not only the sibling path the spec names. This is stricter, in the direction of the accuracy rule.
5. **A flag judgement "at a passing bar"** (`flag_passes`). `real-fixed-by-action` passes at medium or above. `spurious` passes at medium or above for `medium` kinds; for `title`/`structure` kinds only with a passing `overrule` edit for that flag; `never` kinds never pass. Title-kind overrules use the title bar's evidence kinds, but their flags (`research-song`, `research-date`) name a song or date, not a file, so `sibling_match` and the own-tag-row rule cannot apply to them.
6. **The re-hold auto-overrule is all-or-nothing.** It writes records only when every remaining flag qualifies (then clears the hold and redoes from `package`, as `fix --overrule` does). A partial set would leave the show held with persisted overrules nobody asked for.
7. **A switch verdict allows only `venue` beside it.** An `overrule` alongside a switch would be recorded on the old identifier and go inert, so it makes the switch propose-only.
8. **Accepting a switch with `[a]` runs coverage's title and duration rules**, not its gain or held rules (those belong to the auto-switch bar, which accept skips by spec), and no whole-show diff. On a failure it restores and names `llama fix <slug> --recording <id>` as the deliberate override.
9. **Segue differences** on unnamed tracks count in the whole-show check only when the verdict has no structure edit.
10. **`run approve` is a hook point beyond the spec's list, for Shawn's sign-off.** It goes through `_execute` and follows the config value, with no flag. `redo --run --from search|winnow` passes `redo`'s own `--adjudicate/--no-adjudicate`.
11. **Pacing.** Adjudication in `_execute` is part of the show's measured boundary, so the EWMA learns held-show cost. The backlog command records no EWMA, as `reapply`.
12. **Station-marked** reads the library campaign record (`campaign.last_mark` is not None; unreadable counts as marked), not the station manifest.
13. **`fix --clear-recording`** is added. The spec gives no way to remove a pin, and the select refusal needs to name a repair.
14. **An applied show that stays held keeps a proposal.** Its applied record carries `held_proposal`: the leftover flags with the verdict's judgements, and an overrule of each one judged `spurious`. Triage offers `[a]` for it, and the run report lists it under held-with-proposal.
15. **`--dry-run` keeps an existing proposal, applied or accepted record** unless `--force` (outcome `skipped: has a record`, no LLM call). A malformed record may be overwritten.
16. **A failed accept is `failed`** (restored, refused or transient, with the reason as detail) or `skipped: changed`; it never rewrites the stored record, so the proposal stays on offer.

## Could not plan without inventing design

- **The Intent-class mapping for the pilot's stratification** (Task 11 `select`) is a heuristic over prototype `root_causes` and flag patterns. The spec names the classes but not how to assign a show to one. The plan fixes the mechanism and leaves the mapping table to the implementer, to be checked by eye at pilot time.
- **`llama status --adjudicated`** (spec "Left to the builder") is not planned (YAGNI). The run report and triage cover the need.
