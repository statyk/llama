# Task 1b review (6e0e282..30a359a): `awaiting_fix` makes a package unairable

### Spec Compliance

Checked against the brief, the draft contract's "The `awaiting_fix` contract" section, the operator instruction and ruling R20.

- **Any non-null value is Ineligible.** Met. `station.awaiting_fix_reason` returns None only for an absent field or `null`. A falsy value (`""`, `0`, `False`, `{}`) is still marked; mutants M2 and M5 both fail tests.
- **Reason text.** Met. A dict with a non-empty string `reason` gives `awaiting fix from llama: <reason>`, with whitespace and newlines collapsed to single spaces. Anything else gives the bare `awaiting fix from llama`.
- **Never crashes.** Met. I probed a string, list, number, bool, `{}`, a dict without `reason`, a non-string `reason`, `{"reason": None}`, `{"reason": {...}}`, `[{"reason": "x"}]`, `1.5`, NaN, a 1 MB reason, ` ` and NUL. None of them raised, and every one is marked. The function only calls `.get` on dicts and `.split` on strings. In `scan_delivered` the manifest is already known to be a dict when the call is reached.
- **Placement in `_evaluate`.** Met. The check comes right after the schema_version gate and before every other check. It is not an early return, so the other legs stay visible. A marked package lists this reason first; mutant M7b fails the "first" test.
- **Quiet period.** Behaves correctly. llama's in-place rewrite bumps the manifest mtime, so for `quiet_minutes` the package lists both the mark and "changed ...s ago". It is ineligible either way, so nothing changes. When the mark clears by re-delivery, the quiet period applies as usual.
- **`station.scan` lists it as Ineligible.** Met and pinned by `test_scan_lists_a_marked_package_as_ineligible_with_its_reason`.
- **R20, `scan_delivered` exclusion.** Met. The check runs before `evaluate` and before the `_manifest_show` fallback, so it covers both voiced and unvoiced packages. Without it, a voiced marked package would come back through the unvoiced fallback; mutant M4 fails all 8 parametrised cases.
- **Render skip path.** Met. A planned row whose package is now marked gets `piece is None`, so the reason is "no longer eligible" and `replan_from` re-extends without it. No new pipeline code was needed, which is correct.
- **Already-encoded pieces air as planned.** Met. The mid-render test passes because the row's whole-show encode exists (`store.has(r.key)`), so the row is never re-validated. That is the right mechanism, but it is not the `LayoutError` on-air guard the brief names. The test is not trivial: it asserts the scan really excludes the show, and mutant M9 (re-validate encoded rows against eligibility) fails it and only it.
- **Status and library visibility.** Correctly left alone. No cli, service or pipeline line lists Ineligible reasons today; I confirmed this with grep.
- **One brief clause is not faithfully pinned:** "the file-set key does not change". See Important #1.

**Other transmitter readers of delivered manifests (risk d):**

| Reader | What it does with a marked show | Matters? |
|---|---|---|
| `pipeline.Station.scan_now` / `scan_pieces` → `station.scan` → `evaluate` | Planning and render re-validation use this. | Covered by this task. |
| `pieces.scan_delivered` (the `--library delivered` rehearsal, also imported by `naive_filler.py`) | Excludes it. | Covered. The measurement results were taken before any mark existed. |
| `service.row_analysis` | Reads the analysis cache first. Only if `cache/<key>.json` is missing does it fall back to `evaluate`, which now returns None for a marked show. | Publish timeline detail only, no audio. See Minor #2. |
| `site.read_package_notes` (from `publish.py:257`) | Builds the notes page for rows already in the plan. | Display only. A marked show still on air keeps its notes, which is consistent. |
| `interstitials.scan` | Reads the clips folder, not packages. | No. |
| `status` / `library` CLI | List no Ineligible reasons yet. | Task 13. |

No reader schedules or encodes a marked show except through the encoded-row path, which the spec allows.

### Strengths

- Small and well placed: one pure function, one call site in `_evaluate` and one in `scan_delivered`. The module docstring records the contract, and the function docstring states the shape-tolerance rule ("inner shape is display only").
- The tests cover the full malformed-value matrix the operator named, plus null and absent.
- The tests measurably catch faults. I ran 9 mutants in a scratch copy, each with the expected red tests named first, after checking that both `transmitter.__file__` and `tests_transmitter.__file__` resolved inside the copy:

| Mutant | Result |
|---|---|
| M1: drop the evaluate check | 17 red, as predicted, including both pipeline tests |
| M2: treat `{}` as unmarked | 3 red: station `{}` case and pieces `{}` ×2 |
| M3: crash on a non-dict mark | 10 red |
| M3b: crash on a non-string reason | 1 red: the `{"reason": 7}` case |
| M4: drop the `scan_delivered` exclusion | 8 red |
| M5: test with `not mark` instead of `is None` | 6 red |
| M6: no newline collapse | 1 red |
| M7b: list the reason last | 1 red |
| M9: re-validate encoded rows | 1 red: the mid-render test |

  M7 (`insert(len, …)`) turned out to be equivalent to the original append, so I discarded it.
- The full suite on a scratch copy of 30a359a: 859 passed, 1 skipped. That matches the implementer's report.

### Issues

#### Critical
None.

#### Important

1. **`packages/transmitter/tests_transmitter/helpers.py:342-351` (`mark_awaiting_fix`) and `test_pipeline.py:1263`.**
   - **What.** The helper calls `set_age(pkg, age_s)`, which re-stamps the mtime of every file in the package. The file-set key hashes each `broadcast.m3u` entry's `st_mtime_ns`, so in the tests the key does change. I measured this in a scratch probe: the key before the mark was `ad9f0ec5…` and after it was `b21c2900…`. The comment at `test_pipeline.py:1263` ("manifest only: the file-set key is unchanged") is therefore false inside the test. In production llama rewrites only `manifest.json`, so the key stays the same.
   - **Why it matters.** The operator's binding instruction pins this exact condition: "the file-set key does not change". The drop test still discriminates today, because the reason is "no longer eligible", not "package changed". But it is not exercising the production condition. A future shortcut that skips re-validation when the key is unchanged would pass here and air a marked show in production.
   - **Fix.**
     - Have the helper age only `manifest.json`: `os.utime(pkg / "manifest.json", (t, t))`. `build_package` already aged the other files, and only the newest watched mtime matters for the quiet period.
     - Have the drop test assert `station.file_set_key(pkg, station.read_m3u(pkg / "broadcast.m3u")) == victim.key` after marking.
     - I checked this in a scratch copy: with both changes, all 147 tests across station, pieces, pipeline and my probes pass, and the key assertion holds.

#### Minor

1. **Lost encode plus mark on an on-air show raises `LayoutError` (`pipeline.py` render's `on_air` branch; pre-existing behaviour, newly reachable).**
   - **What.** If a marked show is on air and its `render/shows/<key>.aac` is lost (an operator cleaned `render/shows`, or a restore left it out), render refuses with "already on air … cannot be re-made (no longer eligible)". I confirmed this in a scratch probe. The plan stays untouched and render stalls until the lead drains and recovery cuts a new run.
   - **Why it matters.** This is the same class as the existing "ineligible" damage case, which the plan already accepts. But a mark, unlike a removed `broadcast.m3u`, leaves the audio intact, so re-encoding would be safe and would honour "air as planned, never silence".
   - **What I suggest.** This is outside Task 1b's brief, so I suggest a controller ruling rather than a fix here: either accept and document it, or allow the on-air re-encode when the package is ineligible only for `awaiting_fix`. In the second case render would need the Ineligible reasons, or a scan that does not filter on the mark.
2. **`service.py:97` (`row_analysis` fallback).**
   - **What.** When the analysis cache is missing, a marked show still on air gets `None`, so its publish timeline shows no track detail.
   - **Why it matters.** Display only, and reachable only after `cache/` is lost.
   - **Fix.** Document it in the docstring, or accept it as is.
3. **`station.py` (`awaiting_fix_reason`): the reason length is not capped.**
   - **What.** A 1 MB `reason` becomes a 1 MB Ineligible reason, which Task 13's `library` summary will print.
   - **Why it matters.** The contract says the reason is "one line", but the reader cannot trust llama to keep it short.
   - **Fix (optional).** Truncate to about 200 characters with an ellipsis. Alternatively, leave it to Task 13's display.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The production code is correct, crash-proof, placed sensibly, and meets the brief, the contract and R20. The mutant run shows the tests catch the faults that matter. The one Important item is test fidelity: the helper makes the file-set key change, so the binding pin "the file-set key does not change" is not exercised. That is a two-line fix in the helper plus one assertion. The Minor items are a controller ruling to make (lost encode on an on-air marked show) and two cosmetic points.

Scratch evidence (outside the worktree): `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-scheduler/6a271170-52a3-49a3-b4db-a9d5cd08acfc/scratchpad/t1b/` holds `probe/` and `probe2/`, which contain the probe tests and the fixed helper. Log: `$D/task1b-review/task1b-review.log`.
