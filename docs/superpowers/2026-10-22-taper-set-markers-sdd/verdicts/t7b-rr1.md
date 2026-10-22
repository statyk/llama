# t7b-rr1: DONE — all findings ADDRESSED, no new Critical/Important breakage

### Finding Verdicts

- **Important 1: a numbered→encore relabel at an existing boundary was tiered `labels renamed`, and rows showed only break positions** — ADDRESSED.
  - The new encore check at scripts/replay_holds.py `_tier` (`if [_is_encore(x) for x in b] != [_is_encore(x) for x in a]: return "songs moved"`) runs after the break-position comparison. So a 2→encore change at the same positions now lands in `songs moved` and gets the full pre-screen.
  - Every row now carries `labels: before <runs> | after <runs> | stored <runs>`, built by `_runs`.
  - Test `test_taper_changes_numbered_to_encore_is_not_a_plain_rename_and_rows_show_labels` asserts: the show is not under `labels renamed` and is under `songs moved`; the row still reads `before [2] after [2]`; and the row reads `before 1x2 2x1 | after 1x2 encorex1 | stored 1x2 2x1`.
  - Check (a), whether encore detection matches the shipped label: it matches, so the fix is live.
    - gather/structure ship the literal `"encore"` (packages/llama/src/llama/models.py:91,96 `"1" | "2" | "3" | "encore"`; jerrybase.py:47 `return "encore"`; taper.py:135 the same; setlist.py:452 `current_set = "encore"`).
    - `_is_encore` lowercases and accepts `encore` or `e`, so the shipped label is covered, and `E` is accepted as harmless extra tolerance.
    - The test drives the real `"encore"` string.
- **Minor 1: the stored-llm section listed an `unreplayable` candidate as now replayable** — ADDRESSED.
  - The condition is now `c.get("outcome") not in ("needs-llm", "unreplayable")`, in the stored-llm loop of `_taper_changes`.
  - `test_stored_llm_section_excludes_an_unreplayable_candidate` asserts `stored-llm shows now replayable (0)`.
- **Minor 2: validate `--config` up front, and have the summary name the delivery path or say the voiced check is off** — ADDRESSED.
  - `compare` now refuses a missing explicit `--config` and loads `delivery_path`, both before `_gates` and before `out.mkdir` (replay_holds.py `compare`, first lines after `_load_arm`).
  - The refusal text `no such config: <path>` is identical to `run`'s at replay_holds.py:157.
  - The summary prints `voiced check: delivery_path <P>` or `voiced check: off (no delivery_path in config)`.
  - `test_compare_refuses_a_missing_config_before_writing_and_summary_names_delivery` asserts:
    - rc 2, the refusal text, and `not out.exists()`;
    - the "off" summary line;
    - the "delivery_path" summary line.
  - `_taper_changes` now takes the resolved `delivery` rather than reading the config lazily, so a partial output directory can no longer happen.
- **Minor 4: `overruled:` should print only when before != after, else `step1:`** — ADDRESSED.
  - The code is `step1 = ("overruled" if before != after else "step1")`, and the row prints `{step1}: {step1_alignment}`.
  - `test_provenance_only_row_says_step1_not_overruled` asserts `step1: jerrybase` and that `overruled` is absent.

### Check (b): `compare` now loads the config on every run

- **An operator with no config:** the missing-file refusal fires only for an explicit `--config`. Without one, `_delivery_path(None)` calls `load_config(DEFAULT_ROOT/"config.toml")`, which returns `Config()` for a missing file (packages/llama/src/llama/config.py:177-178). `delivery_path` defaults to None (config.py:146), so the summary reads "voiced check: off". There is no refusal and no crash, which matches `run`'s missing-default behaviour.
- **A `-prev` arm comparison or a stripped arm with no delivered rows:** it now reads `~/.llama/config.toml` read-only (nothing is written). For stripped arms the value is computed but unused, and no voiced line is printed. Output is unchanged otherwise.
- **The refusal text** is identical to `run`'s.
- **A malformed or strict-invalid config:** this raises an uncaught `ConfigError` (a traceback, exit 1), not a `Refusal` (exit 2), despite the fix's comment "a malformed config also refuses". It still happens before any write, and `run` behaves the same way (load_config at :158 is also uncaught). So it is consistent, not a regression; see the Minor below.

### Check (c): the new autouse fixture redirecting `rh.DEFAULT_ROOT`

It does not weaken any existing test.
- Every `run` call in scripts/test_replay_holds.py passes `--config` explicitly (grep of lines 57-891). That includes `test_run_refuses_a_missing_config_file` (:246), which still checks the explicit-path refusal. No `run` test resolves `rh.DEFAULT_ROOT`.
- The voiced-check compare tests (:1004, :1042, :1050) pass `--config` explicitly through `cfg_with`.
- Before this fix, `compare` read the default config only for a delivered row reaching a tier, and no test relied on that reaching the real `~/.llama`.
- The fixture patches the name `rh` actually resolves at call time (`from llama.config import DEFAULT_ROOT` binds a module global in `rh`, which `_delivery_path` and `run` read). It keeps compare hermetic: without it, every compare test would now read the developer's real `~/.llama/config.toml`. It strengthens isolation and masks nothing.
- `Config().root` still defaults to llama.config's unpatched `DEFAULT_ROOT`. That matters only to a `run` without `--config`, and no test does that.

### New Breakage in the Fix Diff

- Minor: the comment on `_delivery_path(config_arg)` in `compare` says "a malformed config also refuses before any write". A malformed config actually raises `ConfigError`, which `main` does not catch (traceback, exit 1, not exit 2). No write happens first, and this matches `run`. Fix the wording, or catch `ConfigError` into a `Refusal` in both `run` and `compare`.
- Minor: when no config file exists at all, the summary reads `voiced check: off (no delivery_path in config)`. That is slightly imprecise, but harmless.
- Otherwise: none.

### Out-of-Scope Observations

- Deferred minors 3, 5 and 6 from t7b-rev are untouched, as the fix report states. The orchestrator ruled them out of scope.
- Because `compare` now always loads the default config, a `~/.llama/config.toml` that this tree's strict `Config` rejects blocks every `compare`, including `-prev` arm comparisons that never needed it. `run` from the same tree already requires the same config, so in practice this is no new constraint.

### Verdict

**Fix round:** all findings addressed, no new Critical/Important breakage.

Checks run (read-only, no tests re-run; the fix report claims 70 passed in scripts/test_replay_holds.py and 4427 in the full suite):
- Read the fix diff and the fix report.
- Grepped the encore label in packages/llama/src/llama/{models,jerrybase,taper,setlist}.py.
- Read `run`'s config handling (replay_holds.py:153-158), argparse/main (:1084-1101) and `load_config` (config.py:175-186).
- Grepped scripts/test_replay_holds.py for `run`/compare calls and `--config` usage.

No commits, no repo edits, nothing written to ~/.llama.
