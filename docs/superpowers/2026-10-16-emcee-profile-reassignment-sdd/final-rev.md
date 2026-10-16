# Final whole-branch review: emcee profile reassignment (16f0e72..885dad4)

Reviewer: Opus, read-only. I reviewed in three passes: production code under `packages/emcee/src` read in full at HEAD (artists, moves, config, models, station, process, cli), then scripts/llama/transmitter, then docs and the strict-surface tests. I ran the focused suite (emcee + transmitter import guard + backfill script + llama `test_the_cut`) with `./.venv/bin/python -m pytest`: **929 passed**. I confirmed the import paths resolve inside this worktree. In a scratch `git archive` copy run from an empty cwd, I re-ran the T4 `_scan_broad` mutant, which forces `voiced_source=None` on second-arm error rows, with PYTHONPATH shadowing (I verified the mutated source was the one imported). It **still survives at HEAD** (emcee suite: 909 passed, 1 skipped).

## Strengths

- **Strict surface 1 holds.** Nothing before the prompt builds a provider. `_load_station` is read-only. `_plan_tts_cell` and `_dry_run_marker` only call the pure `resolve_tts` and read presenter TOML. `_process_one` → `speech_for_voicing` → `preflight` runs only after the yes (cli.py:514-528). The EOF, decline, no-TTY and dry-run tests assert `spent == []`, no `error:`, no `voiced:` and unchanged manifests (test_run_plan.py:183-260), so the "a broad except swallows the spend" blindness is closed.
- **Every profile resolves exactly once, through one path.** No production code reads `source.profile` directly: every read goes through `manifest_profile`. `resolve_assignment` now takes a profile, not a manifest. `resolve_voicing` is the only resolver for voicing. `process_package` takes `voicing` keyword-only with no default, and `moves` is never optional anywhere in the resolution path. The `--profile`/`--assigned` filters, `_note_unmatched_profiles`, the summary grouping, `_voiced_by_cell`, `_status_json_row`, `--dry-run` rows and the plan's TTS grouping all key off `PackageStatus.profile`, which is now the effective profile.
- **Strict surface 3 is structurally sound.** `manifest_voiced_profile` falls back to `manifest_profile` for a legacy block, and both sides go through the same `""`/non-string → None mapping. This matches the real-station check (zero state differences).
- **`moves.json` loading is strict and total.** The writers lock, edit the raw dict in place, and write temp + fsync + rename. `require_present` gives the path, the count, and both ways out.
- **`DJAudioBlock` makes legacy round-trips fail.** Its new fields are required, and `backfill_voiced_by.py` was switched to a raw-dict update with a test that pins unknown-key survival.
- **The import fences hold.** emcee never imports llama, and transmitter imports neither; transmitter's change is a docstring only (Python 3.11 is unaffected).

## Issues

### Critical
None.

### Important

**I1. Strict surface 2: a move-voiced package that becomes an error row can drop out of the missing-`moves.json` guard (already a PARENT RULING; this sharpens the fix spec).** cli.py:193-202.
- **Arm 1** (cli.py:193-196). `pkg.manifest()` raises on valid JSON with the wrong structure, e.g. `"schema_version": "3"` raises TypeError at package_io.py:50, or a non-dict top level raises AttributeError. That row carries no `voiced_source` and no `performance_id`, so `require_present` cannot count it.
- **Arm 2** (cli.py:200-202) does carry `voiced_source` via `identity()`, but no test pins it. The mutant survives: in `test_a_missing_moves_file_with_move_voiced_packages_fails`, the malformed package (`_malformed`, test_profile_readiness.py:155-158) is not move-voiced.
- **Fix, arm 1:**
  ```python
  raw = _raw_manifest(pkg.manifest_path)
  ident = identity(raw, config, moves) if isinstance(raw, dict) else {"profile": raw_profile(...), "delivered_profile": ...}
  ```
  `identity` is total over any dict. Only use it when `raw` is a dict: for unparseable JSON, `identity(None)` would stamp `profile_source: "llama"` on an unreadable manifest. Side benefits:
  - arm-1 rows get the effective profile, so `--profile`/the summary are consistent with arm 2;
  - they get `performance_id`, so `_stale_moves` and `move --list` stop calling a moved package "missing" just because its manifest is malformed.

  Unreadable JSON stays the documented limit, per the ruling.
- **Tests:**
  - **(a)** In the `broken` parametrizations, make **m2 itself** the malformed package: move-voiced, plus a track missing `filename`. Keep the `"2 package(s)"` assertion; the mutant then reports 1 and fails.
  - **(b)** Add an arm-1 case: a move-voiced manifest with `"schema_version": "3"` and `dj_audio.profile_source = "move"`, counted toward the error. Also assert its `--list`/`--json` profile is the effective one. This absorbs T8's "no test of an error row's profile cell under a rule/move".
  - Name the expected red test before flipping each mutant.

### Minor

**M1. Empty profile names are broken everywhere, not just in `emcee move` (sharpens the T6 PARENT RULING).** I confirmed this with a probe. Config validation accepts `[assign.profiles.""]` and `[assign.artists] "Tedeschi Trucks Band" = ""`. Then:
- `effective.profile == ""`;
- `assignment_for` treats `""` as falsy, so the show is voiced by the default/house voice and not the assigned presenter;
- the recorded `dj_audio.profile: ""` reads back as None (`_nonempty_str`, station.py:137), so the package is **pending forever and re-voiced on every run**;
- `emcee move X ""` writes a file that `load_moves` then rejects (the T6 finding).

**Fix:**
- In `AssignConfig._check_artists` (config.py:170), reject an empty `[assign.profiles]` key ("profile names must be non-empty"). With that in place, a rule or a move can never target `""` through config.
- Defence in depth, per the ruling: have `write_moves` (moves.py:141) run the reader's own `_validated(data, path)` on the dict before writing, so no writer can ever produce a file the reader rejects. That covers `record_move` and `clear_move` alike.
- Tests:
  - a config load error for `[assign.profiles.""]`;
  - `record_move(root, pid, "", ...)` raises with `moves.json` byte-identical;
  - CLI `emcee move X ""` exits 1.

**M2. `normalize_artist` Unicode (sharpens the T1 PARENT RULING).** artists.py:23-28. Confirmed: NFD `"Béla Fleck"` normalizes to `"be la fleck"`.
- Apply NFC **after** casefold: `s = unicodedata.normalize("NFC", name.casefold())`. Casefold can itself emit decomposed sequences, so NFC before casefold alone is not enough.
- Also keep combining marks in the character filter: `ch.isalpha() or ch.isdigit() or unicodedata.category(ch).startswith("M")`. Otherwise a mark with no precomposed form still splits a word (`"İstanbul"` → `"i stanbul"`).
- Test: NFD and NFC spellings match each other, and two such config keys now trip the duplicate-key error.

**M3. `run --help` contradicts the code.** cli.py:436: "A pending package whose only problem is missing track audio is skipped". The code skips any pending package with missing tracks (cli.py:487). CLAUDE.md was already corrected for this under the T9 ruling, and this is the same defect class in user-facing `--help`. Fix: "A pending package with missing track audio is skipped, whatever else is wrong with it".

**M4. `docs/station-brief.md:78-81` is now incomplete.** It still says the presenter is "decided by matching the llama profile name stamped in the manifest (`source.profile`)". Add: "...unless an emcee move or `[assign.artists]` rule changes the profile it is voiced as (recorded as `dj_audio.profile`)". This is the consumer-facing contract doc.

**M5. Runbook bullet** (docs/playout-incident-runbook.md, the new bullet's last sentence): "until `emcee voice <show>` succeeds". The next `emcee run` retries it too. Fix: "until a later `emcee run` or `emcee voice <show>` succeeds".

**M6. Optional, cheap while touching `identity()` for I1:** `identity()` omits `voiced`, so error rows report `voiced=False` beside a `voiced_by` value. Add `"voiced": isinstance(_get(manifest, "dj_audio"), dict)`. Nothing consumes it on error rows today, so this is not required.

## Seam checks with no finding

- **Double resolution:** none. The plan's TTS lines and `--dry-run` markers are display-only; voicing re-resolves once per package via `resolve_voicing` with the same `config`/`moves` objects, and does not re-scan.
- **`moves` defaulted or omitted:** none (`scan`, `_scan_broad`, `_station_statuses`, `_load_station`, `assess`, `readiness`, `identity`, `package_status`, `effective_profile`, `move_target_problem`, `resolve_voicing` and `_process_one` all require it).
- **Error-row vs success-row drift:** only arm 1 (I1) and `voiced` (M6).
- **`voice`** loads moves before resolving the package and checks only the named package, per the spec. `move` runs `_load_station` (bad/missing-file guard) before any write, `--list` and `--clear` included.
- **Other help text:** `--profile` help (cli.py:410-413), the `status` docstring and README/CLAUDE.md now say "effective".
- **llama `DJAudio`:** the new fields are optional, it is permissive, and a test is added. llama behaviour is unchanged.

## Triage of final-triage-list.md deferred minors

| Item | Verdict | Why |
|---|---|---|
| T1 normalize_artist no Unicode normalization | **FIX-BEFORE-MERGE** (PARENT RULING) | Confirmed; spec as in M2: NFC after casefold, keep category-M marks. |
| T1 `from_` accepted as TOML key | OK-TO-DEFER | Harmless alias; `extra=forbid` still rejects real typos. |
| T1 redundant `extra="forbid"` on ArtistRule | OK-TO-DEFER | No-op duplication of `_StrictModel`. |
| T1 mid-module import in test_config.py:499 | OK-TO-DEFER | Test style only. |
| T1 comment alignment test_artists.py:32 | OK-TO-DEFER | Cosmetic. |
| T2 no parent-dir fsync after `os.replace` | OK-TO-DEFER | Atomic already; only the power-loss durability of the rename is at stake, on a local `~/.emcee`. |
| T2 identical record_move does not refresh renamed package name | OK-TO-DEFER | `package` is informational; `--clear` by the old name still matches. |
| T2 lock release on exception / after clear unpinned | OK-TO-DEFER | `try/finally` + `os.close`; flock also dies with the fd. |
| T2 no RED evidence for T2 | OK-TO-DEFER | Process record only; the tests exist and pass. |
| T2 workspace.py docstring lists only presenters/package_io | OK-TO-DEFER | Stale docstring, no behavioural claim. |
| T3 test_accessors_are_total gaps | OK-TO-DEFER | Accessors are trivially total (`_get`/`_nonempty_str`); I read them. |
| T3 Effective invariant docstring-only | OK-TO-DEFER | Only `effective_profile` constructs `Effective`, and it honours the invariant. |
| T4 `run --profile` help says "delivered" | Already fixed (cli.py:410-413) | Verified at HEAD. |
| T4 scan reads each manifest three times | OK-TO-DEFER | 341 small JSONs; correctness unaffected. |
| T4 `_scan_broad` arm-2 mutant unpinned | **FIX-BEFORE-MERGE** (PARENT RULING) | Re-measured: still survives at HEAD. Test spec in I1(a). |
| T4 `_scan_broad` arm-1 row lacks voiced_source | **FIX-BEFORE-MERGE** (PARENT RULING) | Fix spec in I1: `identity(raw)` only when raw is a dict; test in I1(b). |
| T4 identity() omits `voiced` | OK-TO-DEFER (optional fold-in, M6) | No consumer reads it on error rows. |
| T4 `status --state bogus` + bad moves.json reports moves first | OK-TO-DEFER | Strict-first ordering is defensible. |
| T5 models.py "shape-identical" | Already fixed (T9) | Verified: now "shape-compatible". |
| T5 `voice --fresh` help silent on moves/rules | OK-TO-DEFER | Not contradicted, just silent. |
| T5 bed computed twice | OK-TO-DEFER | Pure function of the same presenter; cannot diverge. |
| T5 SpeechProvider Protocol lacks voice/model | OK-TO-DEFER | All four providers + `QualitySpeech` define both; a Protocol line is nice-to-have. |
| T5 pre-existing llama fork() DeprecationWarnings | OK-TO-DEFER | Pre-existing, unrelated. |
| T5 failed re-voice clears the "move" record | OK-TO-DEFER (runbook candidate) | Needs two independent failures; inside the spec's stated limit. |
| T6 empty-string move write | **FIX-BEFORE-MERGE** (PARENT RULING) | Sharpened in M1: reject `""` profile keys in `AssignConfig` too (it also causes a perpetual re-voice via a rule), and validate in `write_moves` with the reader's `_validated`. |
| T6 `--list` `[no assign entry]` on a missing stale `--delivered` row | OK-TO-DEFER | False alarm only on a stale row whose delivered profile is unknowable. |
| T6 unchanged move doesn't refresh name (dup) | OK-TO-DEFER | Duplicate of the T2 item. |
| T6 broad except around post-write assess | OK-TO-DEFER (keep as is) | The move is already written, so "state unknown" is the right outcome; narrowing would turn a malformed-manifest KeyError into a traceback after a successful write. |
| T6 usage-error test checks only exit code | OK-TO-DEFER | Exit 2 is distinctive enough. |
| T7 `--yes`/exit codes only in CLI help | Already addressed (T9) | README and CLAUDE.md now document `--yes`, no-TTY refusal and the agent flow. |
| T7 `_stdin_is_tty` with `sys.stdin is None` | OK-TO-DEFER | Fails closed (traceback, exit 1, no spend). |
| T7 `-y` alias / bare-Enter default untested | OK-TO-DEFER | Declared by typer; default=False is visible in code. |
| T7 test_run_cmd.py:437 weakened stderr check | OK-TO-DEFER | Brief-mandated, since the plan now writes to stderr. |
| T7 filters drop an invalid-move package silently | OK-TO-DEFER | Unfiltered `run` and `status` both surface it. |
| T7 EOF "Aborted." exit 1 not in docstring | OK-TO-DEFER | Docs polish. |
| T7 other forbid_spend callers ignore attempts | OK-TO-DEFER | Checked: each asserts `isinstance(result.exception, EmceeError)` or an exact error message, which a swallowed AssertionError cannot produce; the `move` paths have no provider reachable. |
| T8 unused `Path` import test_status_profiles.py:4 | OK-TO-DEFER | Lint only (fold in if convenient). |
| T8 no test of error/unsupported row profile cell under rule/move | **FIX-BEFORE-MERGE** (folded into I1(b)) | Same test as the arm-1 fix; free. |
| T9 runbook "until emcee voice succeeds" | **FIX-BEFORE-MERGE** (M5) | One-phrase operator-runbook correction. |
| T9 models.py stacked parentheticals | OK-TO-DEFER | Cosmetic. |
| T9 CLAUDE.md long unwrapped lines | OK-TO-DEFER | Cosmetic. |
| T9 CLAUDE.md "six models" stale | OK-TO-DEFER | Pre-existing (8 strict models at base, 10 now). |
| T9 cli.py:436-438 `run` docstring "only problem" | **FIX-BEFORE-MERGE** (M3) | `--help` contradicts the code; same class as the ruled CLAUDE.md:108 fix. |
| T9 station-brief.md:78-81 presenter by source.profile | **FIX-BEFORE-MERGE** (M4) | The consumer contract doc now states an incomplete rule; one clause. |
| Orch note CLAUDE.md:109 `--profile` wording | Already fixed (885dad4) | Verified: says EFFECTIVE profile. |

## Declined to judge

- **Spec plan layout.** The spec's example puts the reason inline after the re-voice count; the implementation prints it on its own line. This is a cosmetic deviation from an illustrative block; the message texts themselves are verbatim.
- **TOCTOU between `_load_station`'s missing-file guard and `record_move`'s lock** in `emcee move`. This is covered by the spec's single-operator limitation.
- **Apostrophe variants beyond `'` and `’`** (e.g. U+02BC `ʼ`, which is a letter, so "Densonʼs" ≠ "Densons"). The spec lists exactly two characters, and the real-data collision check passed.
- **mkstemp's 0600 mode on `moves.json`.** This is pre-existing `atomic_write_bytes` behaviour and appropriate for `~/.emcee`.

## Assessment

**Merge verdict: Ready after fixes.** The fix wave is:
- I1 (both `_scan_broad` arms, with the two tests);
- M1 (empty profile names: config validator + `write_moves` validation);
- M2 (NFC after casefold + marks);
- M3/M4/M5 (three one-line doc/help corrections).

Everything else is OK to defer. The core design holds on all three strict surfaces: one resolution per package, the effective profile used consistently, and no spend before confirmation. The remaining gaps are narrow edge paths that the parent rulings already identified, plus one sibling (empty profile names) that the T6 fix should close at the config layer as well as the writer.
