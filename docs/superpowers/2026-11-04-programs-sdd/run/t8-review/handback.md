### Spec Compliance

- ✅ Spec compliant. Every Task 8 sentence of "The title backfill" and every brief plan rule and writer step is implemented in order:
  - Plan order (retitle.py `plan_retitle`): read → parse/object → schema<3 refused (before the dj_audio check, so v2 unvoiced is refused too) → dj_audio None → unvoiced → non-dict refused → `raw != encode(data)` refused → awaiting → target vs current. This matches the brief's sequence exactly. The test is `test_plan_refuses_pre_v3_voiced_or_not`.
  - Absent and null are the same title: `dj_audio.get("title")` against target, so None == None gives unchanged. The test is `test_plan_absent_and_null_title_are_the_same`.
  - awaiting_fix is skipped by `station.awaiting_fix_reason`, which returns a non-None string for any non-null value, malformed ones included (station.py:36-48). The test covers a `"not a dict"` mark.
  - Writer order (`_swap` + `write_title`): stat → build from `expect` → `xb` temp in `path.parent` → write/flush/fsync/close → `os.utime` on the closed temp → re-read == current, else unlink and return None → `os.replace` → mtime re-check with one re-apply → verify → put back only if the file holds exactly `new`, using the original `st` → two distinct messages. The put-back reuses `_swap(current=new)`, so it gets the same immediately-before-rename re-check.
  - The encoding is `(json.dumps(data, indent=2) + "\n").encode()`, with ensure_ascii at its default.
  - procs is a line-for-line port of campaign_gate.py:22-121 (constants, `_unquote`, `_shell_string`, `_simple_commands`, `_runs_tool`, ancestor walk, ps invocation). It has exactly two differences, both intended: `_SCRIPTS_RUN` is gone, so scripts/*.py counts for both tools, and `self_script` is dropped because the interface does not have it.
- ⚠️ Cannot verify from the diff alone (Task 9 / go-live):
  - The backup-before-write, the whole-run re-read under the lock, `--yes` printing, the `ps` refusal call site and a non-zero exit on `TitleWriteFailed` all belong to Task 9.
  - Task 9 must also treat ANY exception from `write_title` as stop-run, not only `TitleWriteFailed`. Raw `OSError`/`FileNotFoundError` can escape it; see Minor 2.
  - SMB/NFS mtime behaviour is covered under the named risks below.

### Strengths
- Requiring `after_raw == new` in step 8 (beyond-brief choice 1) is the right call, and it is needed for Task 9's put_back sha rule: the returned bytes are provably what is on disk. Same content in different bytes is correctly treated as a foreign write.
- The `_swap` helper means the put-back gets the same temp → fsync → utime → re-check → replace → mtime sequence instead of a hand-copied second version. It is DRY on exactly the strict path.
- Atomicity under `os._exit`: the only state-changing op on `manifest.json` is one `os.replace` from a same-directory temp. Wherever the process stops, the file is fully old, fully new or fully put-back, with at most one stray dot-temp. The `except BaseException` cleanup covers in-process interrupts.
- The test spies are tight. `test_write_sets_mtime_before_the_rename` asserts the temp is closed at utime and that `os.stat(src).st_mtime_ns == OLD_NS` at the moment of replace. `test_write_sets_only_the_title_key` checks the byte splice, so no other byte changed.
- The foreign-encoding test covers all five Review Focus 4 cases plus not-utf8, not-an-object and invalid JSON, and it asserts both bytes and mtime unchanged.
- The implementer's mutation evidence is credible. It reports a PYTHONPATH shadow proven with a sentinel, no bytecode cache, and predictions named before each run.

### Named-risk checks
1. **Temp on another filesystem or directory:** `tmp = path.parent / ...` (retitle.py `_swap`, first line), so it is in the same directory and on the same mount. The test asserts `Path(opened[0].name).parent == pkg`. One residual edge: if `manifest.json` were a symlink, `os.replace` would replace the link with a regular file. Station manifests are not symlinks, so no action is needed.
2. **Temp collisions and scanners:**
   - The name is 64-bit random with `"xb"`, so collisions are negligible (but see Minor 1 for the cleanup path).
   - Scanners checked: transmitter `station.py:219-224` watches `manifest.json`, `broadcast.m3u` and `dj-audio/*` by name, so a stray `.manifest.json.emcee-*.tmp` in the package root is neither eligible-blocking nor watched. `station.scan` and `_packages` look at directories only. llama's `show_unit` `os.walk` covers the library workspace, not the station.
   - No consumer picks up the stray temp. Nothing cleans it up either (Minor 4).
3. **utime-before-rename on SMB:**
   - What can be shown locally: the order (tested) and that a local rename preserves the temp's mtime.
   - What cannot: (a) that macOS smbfs does not stamp a new mtime at a deferred server-side close or at rename; (b) that hugo's NFS view gets the pre-set mtime immediately.
   - Step 7's re-check runs through the Mac's SMB client, whose attribute cache may report the value it set. A clean step 7 on the Mac is therefore not proof of what hugo sees.
   - This needs go-live check 4 (spec Rollout). Recommendation: make that probe call `emcee.retitle._swap` itself, not a hand-written equivalent, so the code path is what gets measured.
4. **Put-back interrupted:**
   - Before its replace: the file holds `new`, plus a stray temp.
   - After: it holds `expect`, with at most a wrong mtime if killed before the re-apply.
   - Both are whole files, and Task 9's backup covers the operator restore. The put-back branch is reachable only when the bytes equal `new` but `_unchanged_except_title` fails, which in practice means a bug or a patched verify. Acceptable.
5. **Plan rule order:** verified against the brief (above), including pre-v3 refused regardless of voicing and a list dj_audio refused (`dj-audio-list` in FOREIGN). A missing, non-int or bool `schema_version` is refused as unsupported. That is stricter than `Package.manifest`, which would TypeError on a string; this is fine.
6. **Duplicate keys and floats:** both are caught purely by the encode round-trip. `json.loads` keeps the last duplicate and `dumps` emits one; `1.50` → 1.5 → `"1.5"`. By the same mechanism, `-0`, `1e5`, `é`, `\/` and a BOM are refused too. `NaN` round-trips byte-identically, which is correct, since it *is* emcee's encoding.
7. **procs fidelity:** diffed by eye against campaign_gate.py:22-121; identical apart from the two intended changes. Self and ancestor exclusion is the same loop, cycle-safe through `while cur not in skip`. The tests cover a self chain 500→400→300 that itself runs `llama` and `emcee`, and a scripts/*.py match under `("emcee",)` alone.

### Beyond-brief choices
1. Byte equality after the rename: **approve** (see Strengths).
2. JSON-encoded value comparison (`_canon`): **approve**. It is redundant given (1), but harmless, and it makes the isolated `_unchanged_except_title` meaningful on its own (1 vs 1.0 vs True). `sort_keys` hides nested key order, but (1) covers that.
3. ValueError guard on `expect`: **approve**. It is a caller-contract check, it runs before any temp exists and it writes nothing. It is tested by `test_write_refuses_bytes_not_in_emcees_encoding`.
4. Vanished manifest: **approve with a gap**. Gone at the step-5 re-read returns None and never re-creates the file (correct and tested). Gone after the rename raises TitleWriteFailed "left as…" (correct). Gone *before* step 1 raises a raw FileNotFoundError from `os.stat`, which is inconsistent (Minor 2).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **retitle.py `_swap`, `except BaseException: tmp.unlink(missing_ok=True)`:** the cleanup also runs when `open(tmp, "xb")` itself fails with FileExistsError. On a (64-bit, practically impossible) collision it would delete a temp it did not create. Fix: open first, then enter the try/cleanup only after a successful create.
2. **retitle.py `write_title`, raw OSErrors escaping the strict path:**
   - `os.stat(path)` at entry raises FileNotFoundError, while the same condition at step 5 returns None.
   - The post-rename `os.stat`/`os.utime` in `_swap`, and any non-FileNotFoundError on the verify read, escape as raw OSError while the file holds `new`.
   - Either is safe on disk, but the caller gets no TitleWriteFailed message saying what state the file is in.
   - Fix: wrap these in TitleWriteFailed with an explicit "holds the new bytes" or "nothing written" message, or have Task 9 treat any exception as stop-run and list the show.
3. **test_retitle_writer.py `test_write_sets_mtime_before_the_rename`:**
   - The "fsynced" assertion is only `assert fsynced` (some fd went through fsync). It does not compare against the temp's descriptor, despite the comment. Record `f.fileno()` in `spy_open` and assert membership.
   - Not covered: the put-back path where the file changes between the verify and the put-back's own re-check. That path ends in "left as the other writer wrote it" with nothing written. It is one more small test.
4. **No sweep of stray `.manifest.json.emcee-*.tmp`:** these are left after an `os._exit` mid-write. They are harmless to all scanners checked, but Task 9 could list them in its dry run. Flagged for Task 9, not this task.
5. **The temp's mode comes from the umask, not `st.st_mode`:** it is typically 0644, which is better than `atomic_write_bytes`' mkstemp 0600. On SMB the server maps modes anyway. Optional: `os.chmod(tmp, st.st_mode & 0o777)` before the utime.
6. **Implementer-reported test output:** the full suite showed 26 warnings, including a multiprocessing fork DeprecationWarning that the report says is not from these files. Not attributable to this diff. Noted only because test output should be clean.

### Assessment

**Task quality:** Approved

**Reasoning:** The plan rules and writer order match the brief and the spec exactly, the manifest is touched only by one same-directory atomic replace (so os._exit leaves it whole), and the encoding round-trip refuses every foreign encoding in Review Focus 4. The remaining items are about how errors are reported and about test tightness, not about on-disk safety. SMB/NFS mtime behaviour can only be proven by go-live check 4, which should exercise `_swap` directly.

Checks run: read the brief, global constraints, spec §"The title backfill", the implementer handback and the full diff (two passes: source, then tests); compared against campaign_gate.py:22-121, station.py:30-48/157-164/374-391, process.py:54-67, package_io.py:18-54, workspace.py:21-38 and transmitter station.py:205-224 (stray-temp scanner check). Tests were not re-run: no doubt arose that reading did not settle.
