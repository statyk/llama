### Spec Compliance
Compliant. The diff (0504571..5382e82) matches task-3-brief.md almost line for line, and the three orchestrator rulings are applied:
- `config init` writes through `workspace.atomic_write_text` (cli.py:97). The brief's `mkdir` + `write_text` is gone, and `atomic_write_bytes` makes the parent directory itself.
- The template comment cites `tests_transmitter/test_config.py::test_template_parses_to_the_defaults` (config.py, the comment just above `DEFAULT_CONFIG_TOML`).
- There are no unused imports. `Path` in cli.py is used by the `--config` annotation.

Every interface the brief lists is present with the specified defaults:
- `DEFAULT_ROOT`, `default_root`, all six models, `load_config`, `DEFAULT_CONFIG_TOML`.
- All ten `Workspace` paths, plus `seg_dir` and `fallback_dir`.
- `Epoch` with `.iso`, `.start_us` and `.index_at`; `load_epoch` and `load_or_create_epoch`.
- `PublishState` and its four load/save helpers.

The tests match the brief verbatim, plus one extra assertion (no temp file left after `config init`), which is an improvement.

Nothing changed outside `packages/transmitter`. That is confirmed with `git diff --stat -- . ':!packages/transmitter'`, which is empty.

**f5256ac (the Debian 12 runner):** the only change is the tar line. It now reads `--exclude="./.venv*" --exclude=./.superpowers`; the other excludes, the `"$@"` passthrough and the `sh "$@"` tail are unchanged. Double quotes are the correct choice inside the single-quoted `sh -euc` body: they keep the inner shell from globbing, and single quotes would have ended the outer quoting. I ran the exact tar command in `debian:12` (GNU tar) on a scratch tree:
- `./.venv`, `./.venv311` and `./.superpowers` are excluded.
- A nested `packages/p/.venv-keep` is kept, so the pattern does not over-match.
- `./keep` is kept.

### Strengths
- `_StrictModel` (`extra="forbid"`) is the shared base of all six config models. The tests check strictness at the top level and in two nested sections (`[render]`, `[publish]`), which is exactly where pydantic's lack of propagation would bite.
- `atomic_write_bytes` uses `mkstemp` in the target directory, a dot-prefixed `.tmp` name and `os.replace`, and removes the temp file on any `BaseException`. That meets the atomic-write constraint, and the test checks that no temp file is left.
- `test_template_parses_to_the_defaults` keeps the seeded template from drifting away from the code defaults.
- The epoch is pinned to `d`. Editing `d` in `epoch.json` raises `ConfigError` ("epoch change"). It is created once, on a whole second, and is stable on reload. Its id and ISO string are consistent and tested.
- Spend knobs are bounded below (`daily_put_budget >= 1`, `batch_segments >= 1`, `prune_min_segments >= 1`), and the comment derives the 17,500 budget arithmetic.
  - That budget is about 525k PUTs a month, inside R2's free Class A tier.
  - `low_water_hours < lead_hours` is enforced and tested.
- `config init` refuses to overwrite and exits 1. `--stdout` prints the template byte for byte.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **No fsync before rename** (`workspace.py`, `atomic_write_bytes`).
   - The write is atomic against concurrent writers but not durable across power loss.
   - `publish.json` is the only record of which segment ranges exist in R2, because no List calls are ever made. If the "range recorded before first PUT" write is lost to a crash, those segments are orphaned in R2 for good. The cost is storage, not PUT spend, and is small.
   - Adding `f.flush(); os.fsync(f.fileno())` before `os.replace` is cheap insurance. Not plan-mandated as a defect; the constraint only asks for temp + replace.
2. **Corrupt or malformed state files surface as tracebacks, not `ConfigError`.** `read_json` only catches `FileNotFoundError`, so:
   - an empty or truncated `epoch.json` or `publish.json` raises a raw `JSONDecodeError`;
   - an `epoch.json` missing `epoch_id` raises `KeyError`;
   - a non-object JSON value raises `AttributeError`;
   - `load_config` likewise leaves `OSError` and `UnicodeDecodeError` unwrapped.
   
   All of these fail closed (nothing proceeds), so this is diagnostics, not safety.
3. **`prune_margin_minutes` allows values that would delete live segments.** It is `Field(ge=0)`, and any value below the playlist window (k=6 × 10.24 s ≈ 1 min, plus player lag) would delete segments `live.m3u8` still lists, violating "never list a segment that does not exist".
   - The default of 10 is fine, and the later prune task may clamp it.
   - Consider a floor such as `ge=2`, or a validator. This is not a spend path.
4. **Epoch creation is not exclusive.** `load_or_create_epoch` is check-then-`os.replace`, so two first-ever concurrent callers could each write an epoch and the later one wins.
   - This is only a risk if callers are not serialised. Whether they are depends on later tasks (the publish flock), so I could not verify it from this diff.
   - `os.link` or `O_EXCL` on the final name would make creation first-writer-wins.
5. **Small notes.**
   - The template test catches a changed default but not a new knob that was never added to the template. Acceptable as written.
   - `mkstemp` gives `config.toml` mode 0600 rather than umask-default. Harmless, arguably better.
   - The `config init` exists-check then replace is a theoretical race: a file created in between would be overwritten. Negligible.

### Assessment
**Task quality:** Approved
**Reasoning:** The change matches the brief and the orchestrator's rulings exactly, and the strict-config, atomic-write and epoch-pinning constraints are met and tested. I ran the debian-runner tar exclusion in a Debian 12 container and it behaves correctly. The remaining items are durability and diagnostics hardening, not correctness defects.
