# t13-rev verdict (Task 13, ba4e10a..e576259)

### Spec Compliance

- ✅ Spec compliant against the Task 13 brief. Every listed file has its hunk: `pipeline.py` (`process_show(..., audio_reuse=)` → `run_package(..., reuse=)`, diff l.121/144), `stages/package.py` (`run_package(*, reuse=)` → `build_package(reuse=)`, diff l.307-313), `cli.py` (`_redo_show_locked` computes `plan_reuse(show_ws, config.delivery_path / show_ws.dir.name ...)` BEFORE `drop_stage_artifacts`, diff l.55-59, passes it at l.76-77), `reapply.py` (plan, recorded names, `try/except BaseException` cleanup, `put_back`, `discard_aside` after the commit marker, diff l.226-282), and all five named tests in `test_redo_cmd.py` (diff l.690), `test_fix.py` (l.451, l.469), `test_reapply.py` (l.611, l.639).
- ✅ All `_redo_show_locked` call sites run inside `show_unit` (checked cli.py:1951/1956 untitled, 2147 triage, 2688 `_redo_show`, 3471 fix), so `put_back`/`discard_aside` cover redo single/batch, fix and triage.
- ✅ Station dir naming matches deliver: deliver writes `target_dir / show_dir.name` (cli.py:2538), the plan reads `delivery_path / show_ws.dir.name`.
- ✅ Global-constraint grep: the diff modifies none of the protected names; `DURATION_TOLERANCE_S` is only referenced in unchanged context.
- ⚠️ Reapply places `discard_aside` + `plan_reuse` after the fresh-brief LLM call and the dry-run/skip returns (reapply.py diff l.226-230), not "right after the still-held check" as the brief words it. Nothing writes in between and the stored show.json/manifest are still in place, so the plan is equivalent; the controller should accept or reject the wording deviation (implementer disclosed it).

### Strengths

- The plan is taken before the drop in `_redo_show_locked`, so the Focus 6 case is decided from disk: a held re-gather leaves `show.json` new and the manifest gone, `library_names` is None, and everything is set aside. `test_held_regather_then_overrule_never_reuses_old_audio_by_name` (diff l.469-491) checks it the right way, by downloads AND by the source encoded in each file's bytes, plus no old-numbered `03 - C.mp3` left over.
- The reapply cleanup is narrow and correct in order: delete unrecorded audio (reuse copies, downloads, `.part`/`.reuse.tmp` leftovers), delete the manifest only if its bytes differ from the recorded ones, then `put_back`, which `os.replace`s old names over any same-named new file. The failure test injects at the commit marker, the latest point, and asserts names+bytes, no manifest, no aside, still held, and a clean re-run.
- The test helpers (`reuse_gd73`, `stub_stages`) let the CLI tests run real `build_package` over fake audio that carries its source, so they test placement and not mocks.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **A new recording pick reuses the OLD recording's audio** (cli.py diff l.57-58, together with `audio_reuse._pair`/`reuse_into` from Task 12). The plan is keyed by source filename only. `redo --from select` (advertised as "new recording pick", cli.py:2376) can pick a different archive item, and Task 13 now wires a plan into that path unconditionally. When the new item uses the same filenames as the old one, every track whose cached length is within 5 s of the old copy is copied from the old item's library aside or station copy and never downloaded. The manifest and ID3 `comment` then name the new identifier while the audio is the old taper's. That silently defeats the re-selection, and where lengths differ it can mix two tapers in one show.
   - **Measured (read-only):** 138 of 288 multi-item `gd*` dates in `~/.llama/cache` share mp3 filenames across items (e.g. `gd83-10-21d1t01.mp3`).
   - **Reproduced in a scratch copy** (`git archive e576259`; `PYTHONPATH` shadowing; a sentinel test asserted `llama.__file__` was inside the scratch tree and passed). `redo --from gather` with a stub gather that writes the same tracks under `identifier="gd73-other-taper"` gives `ia.downloads == []`: both files came from the old item. The stub stands in for the post-select show; the plan path does not depend on the stage.
   - **Spec:** 5.4 "Why this is enough" claims the index pairing with equal titles "ties each file to its source". That only holds inside one item, so this is also a spec gap; the controller may want an operator ruling, since 5.4 declares itself not strict.
   - **Fix:** `ReusePlan` records the plan-time `show.identifier`. `build_package` keeps the set-aside step but empties `library`/`station` when `show.identifier` differs. Add a test like the probe.

#### Minor (Nice to Have)

1. **reapply.py diff l.229:** `discard_aside(ws)` ignores errors and does not refuse when the leftover aside survives, unlike `show_unit._discard_leftover` (show_unit.py:132-138), which the brief cites as the model ("as in show_unit"). If removal fails, `set_aside` raises inside the `try`, and the cleanup's `put_back` moves the stale leftover into `package/audio/`. The manifest was already dropped by then, so the next unit sets those files aside and no stale file ships under a name; the cost is clutter and a redownload. Fix: after `discard_aside`, raise `LlamaError` if `ws.dir / ASIDE_DIR` still exists.
2. **test_reapply.py diff l.639-649:** the second half (`a real apply deletes it`) cannot tell deletion at entry apart from the final `discard_aside` after the commit marker, and nothing pins that a leftover is never put back on a failed reapply. Inject a failure on that second run and assert the leftover's file does not appear in `package/audio/`.
3. **cli.py diff l.33:** `from llama.audio_reuse import plan_reuse` sits between `llama.errors` and `llama.ia_client`, out of alphabetical order.
4. **Brief-mandated, disclosed:** after a reapply failure the dropped library manifest is not restored (pinned at test_reapply.py diff l.627/631-632), so the next run re-downloads instead of reusing. This is cost only and the brief says to delete only a manifest this call wrote. It matches pre-Task-13 behaviour.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The wiring matches the brief file by file and the Focus 6 protection is correct and well tested. But the filename-keyed plan now runs on `redo --from select`, where a different recording sharing filenames (common for GD) gets the old recording's audio under the new identifier. Reproduced in a scratch copy. One identifier check fixes it.
