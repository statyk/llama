### Spec Compliance
- ❌ One issue found (Important I1 below): `scripts/bulk_apply.py:108` (`_STATION_OK` includes `"no station copy"`) together with `:418-419` (`elif not out.is_dir(): station = "no station copy"`). This departs from the brief's explicit exit rule ("Exit 0 only when every delivered item is `marked` or `already marked`"). It also rests on `Path.is_dir()`, which on this interpreter (3.14.7, `os.path.isdir`) turns every OSError into `False`. So a station-side stat error is recorded as a terminal "no station copy". It counts as OK for the exit code, and a re-run never revisits it.
- Everything else matches the brief and the cited spec sections:
  - **Pointer (a):** `:220-232`. `split_overruled` runs over the row's `stored_brief_guard` with the show's overrules, and the show is marked only if held problems remain.
  - **Pointer (b):** `:421`. `emcee_running()` is checked immediately before each `_mark_station` / `write_mark`.
  - **Pointer (c):** `:366-367`. `LlamaError`/`OSError` become `refused: <one line>`. The item is listed and the batch continues (`:465-468`).
  - **Pointer (d):** `:250-253`. The `_NO_DIFF` outcome check runs before `row_label_only`/`row_visible_changes`.
  - **Priority order** (`:244-266`): re-selection, then visible change (even when processed), then processed skip, then frozen, then guard. Label-only rows are never marked.
  - **Library mark first and durable, then the station mark, under the show lock:** `:401-425`.
  - **`record.jsonl` line shape:** `:426-429`.
  - **Re-run skips non-refused lines:** `:444-445`.
  - **Station backup** taken once, `index.json` last: `:688-693` and `:299-327`.
  - **Batch id** = sha256 of arm, frozen and reselections bytes: `:685`.
  - **`retire_rekey_restore`** runs before any write: `:686`.
  - **Gates:**
    - arm sha against `code_identity`, including `-dirty`: `:655-659`
    - config fingerprint: `:660-662`
    - stale re-selections, with the fixed string: `:675-677`
    - pin and tools on `--apply`: `:649-651`
  - **`unmark` rules:**
    - `mark_added` lines only: `:533`
    - processed since the mark is listed: `:497-498`
    - put back only on `after_sha256`: `:501-508`, `:516`
    - then `remove_marks`: `:517`
  - **`reselect_rows`:**
    - builds the assessment as `cli.py:3087-3090` does;
    - uses `CacheOnlyIA`, `force=True` and a TemporaryDirectory workspace;
    - drops voiced shows and shows already on their pick;
    - an unmounted station raises `StationUnreadable` through `destination_voiced` (I checked `station_mark.py:97-101`), so the whole check refuses.
  - **Fixed strings** are verbatim (`:97-102`).
- ⚠️ Cannot verify from the diff alone:
  - The source rows' shape: I checked it read-only. `~/.llama-harness/piece4/fw1/m3_changed-r1.json` is a bare list of `{"show", "stored", ...}`, which `cmd_reselect_check` (`:575`) and `_source_slug` (`:155-159`) handle.
  - Task 5's `write_mark` detecting a concurrent emcee rewrite before or after the rename (Review Focus 1) lives in `station_mark` and is out of this diff. This task's part of Focus 1 holds: the `emcee_running()` check comes right before each write, a `write_mark` refusal is recorded `refused:` and listed, and the saved before-copy is re-saved when `write_mark`'s `before` differs from what marking read (`:364-365`).
  - Checkpoint B's numbers come from the orchestrator's dry run.

### Strengths
- **Pointer handling:** all four pointers are handled at the right place and each is pinned by a mutant (m1 to m4 in the handback).
- **Pointer (d):** implemented as an early return on outcome, so the provider-less artefact diff can never reach `row_visible_changes` (`:250`).
- **Interpretation #1 (plain show lock instead of `show_unit`) is correct per the spec.** "Writing a mark" orders the campaign record first and durable, then the station. A library mark without a station mark is therefore the intended intermediate state: deliver refuses the show, and the exit-1 listing plus the runbook's emcee rule cover the station side. A refused line is not "done" (`:444-445`). A re-run sees `is_awaiting`, skips `add_mark` and still reports `mark_added: True` via `_has_batch_mark` (`:407-410`). `test_unreadable_station_manifest_is_refused_and_listed_exit_1` pins this, including "not marked twice".
- **Interpretation #4 (`mark_added` = "the record holds this batch's mark") is the right reading.** Without it, a retried refused item would record `mark_added: false` on its `marked` line, and `unmark` would leave the batch's station mark in place. The same reasoning backs using each slug's last line.
- **Interpretations #6 (reselect-check refuses the whole check) and #7 (emcee check before `put_back`) are the safe direction.** #7 closes the same concurrency hole on the reversal.
- **The unparseable-time rule in `_after`** (`:484-488`) fails toward listing the show instead of unmarking it.
- **The tests use real fixture trees, not mocks.**
  - `_tree`/`_files` snapshots prove nothing was written: the dry run, the refusals, and reselect under the library.
  - The emcee-stop test checks that the remaining items are untouched both on the station and in the library.
- **Untouched list:** a grep of the diff finds no hits for `DURATION_TOLERANCE_S`, `STOP_AFTER_LLM_FAILURES`, `briefing_reusable`, `purge_package_audio`, `load_list`, the junk constants, `audio_reuse`, any emcee import, or the `Manifest` model. Only `scripts/bulk_apply.py` and its new test changed.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

**I1. "no station copy" counts as marked and is terminal, and it is derived from an error-swallowing `is_dir()`.** Locations: `scripts/bulk_apply.py:108`, `:418-419`, `:431`, `:444-445` (interpretation call #2).

- **What's wrong:**
  - `out.is_dir()` is `os.path.isdir`, which returns `False` on any OSError (EIO, ETIMEDOUT, ENOTCONN on a flaky or stale SMB mount), not only on ENOENT.
  - The per-item root check at `:416` runs first, but SMB attribute caching can let the root stat succeed while a subdir stat fails.
  - Such an item is recorded `station: "no station copy"`. It counts as OK for the exit code (`_STATION_OK`), and because the station outcome does not start with `refused`, every re-run of the batch skips it (`done`).
  - Result: a delivered show whose station copy exists but is unmarked, in a batch that exits 0. The runbook then permits `emcee run`, which can spend a Voxtral credit voicing a show the library says is awaiting fix. That voiced show can later only be fixed with `--replace-voiced`, which costs another credit.
  - This is also a departure from the brief's explicit exit rule. The brief lists `no station copy` among the station outcomes but not among the exit-0 outcomes.
  - The implementer's argument holds only for a genuine ENOENT under a mounted root.
- **Why it matters:** strict surface 1. The marking batch's exit 0 is the single signal the runbook's emcee rule depends on.
- **How to fix (minimum):**
  - Decide the station copy with a stat that tells errors apart. `os.stat(out)`: `FileNotFoundError` gives "no station copy"; any other `OSError` gives `refused: station copy unreadable (...)`, which is listed and retried.
  - Then either follow the brief literally (list "no station copy" and exit 1), or keep it as OK and surface it. The dry run already shows a `delivered no station copy` column (`:600-601`), so Shawn can confirm the count is zero or expected at Checkpoint B. Record his call.
  - Add a test for each outcome. Today neither "no station copy" nor the per-item "station root not readable" refusal is tested.

#### Minor (Nice to Have)

**M1. A station mark written without its record line is unreversible, and `unmark` reports success.** Locations: `:357-368` and `:501-509`.

- **What's wrong:** two narrow windows leave the station marked by this batch with no `marked` line and no shas:
  - a crash between `write_mark`'s rename and `_append_jsonl` (documented by the implementer, limitation 8);
  - `_write_durable(saved, before)` at `:365` raising after a successful `write_mark`, which records `refused:` although the station is marked.
- **What follows:** the re-run records `already marked`. `unmark` removes the library mark and prints `batch mark removed`, exit 0, with no hint that the station still carries this batch's mark. On a voiced show, that leaves a stray station mark with the library not awaiting.
- **How to fix (cheap; the evidence exists):** on `already marked`, if `mark_of(data)["marked_at"]` equals this batch's library mark `at` (they are the same value, `:406`/`:363`) and `before/<slug>.json` exists, record `marked` with `before_sha256 = sha(before file)` and `after_sha256 = sha(current)`. At minimum, `unmark` should list `already marked` lines that have `mark_added: true` and a `before/<slug>.json` instead of reporting them silently.

**M2. A missing show directory or an unreadable `show.json` silently drops a row from the plan.** Locations: `:291-292` (`if not ws.dir.is_dir(): continue`) and `:254-266` (`stored is None` skips the visible-change and label checks).

- **What's wrong:** a re-selection whose show dir is gone, or a visibly changed row whose `show.json` no longer parses, is not marked and not listed. That is the unsafe direction, even if rare.
- **How to fix:** list them in the dry run, or refuse the plan, as `reselect_rows` does.

**M3. `--campaign-dir` with `--apply` splits campaign state.** Location: `:663`.

- **What's wrong:** `campaign.frozen_slugs(root)` (`campaign.py:57`, used by deliver's `--with-gather-llm` hint at `cli.py:2617`) always reads `<root>/campaign/needs-llm-frozen.json`. A real `--apply` pointed elsewhere would put the backup, the batch and the frozen list where llama does not look.
- **How to fix:** refuse `--campaign-dir` together with `--apply`; it exists for Checkpoint B's dry run.

**M4. Duplicated definitions that can drift.**

- **What's wrong:**
  - `FROZEN_NAME = "needs-llm-frozen.json"` (`:94`) duplicates `campaign.FROZEN_FILE` (`campaign.py:26`).
  - The assessment expression at `:183-186` is a verbatim copy of `cli.py:3087-3090`. If redo's assessment changes, reselect-check silently stops predicting what `redo --from select` picks.
- **How to fix:** derive the name from `FROZEN_FILE`, and lift the assessment into a small llama helper that both call. The second touches llama source, so it may be deferred with a note.

**M5. Private helpers imported across modules.**

- **What's wrong:** `batch_snapshot._durable_replace`/`_sync_dir`/`_write_copy`, `campaign._now`/`_parse` and `catalog._performance_id` (`:127-129`, `:321`, `:406`, `:487`, `:591`, `:402`). An earlier task set the precedent with `_sync_fd`, but this task adds six more.
- **How to fix:** consider public names.

**M6. Broad catches.**

- **What's wrong:**
  - `_guard_holds`'s `except Exception: rules = []` (`:227-230`). It fails toward marking, which is safe, but it would also hide a programming error.
  - `_plan_state`'s `except Exception: return "unreadable"` (`:278`).
- **How to fix:** narrow them to `(OSError, ValueError, LlamaError)`.

**M7. Test gaps.**

- **What's wrong:**
  - `test_mark_apply_refuses_without_the_pin_or_tools` exercises only the tools refusal, not a missing pin.
  - Nothing tests that a re-run after an emcee stop resumes the unreached items.
  - Nothing tests `unmark`'s emcee refusal.
  - The "no station copy" and per-item root-unreadable outcomes are untested (see I1).

**M8. `freeze` takes any arm.** Location: `:143-152`.

- **What's wrong:** there is no check of the arm's sha, its fingerprint, or that it covers every show. A `--held` arm would freeze a partial list, and the list is write-once.
- **How to fix:** at least print the row count, or gate it like `mark`.

**M9. Reversal ordering across batches (documentation only).** If batch B2 recorded `already marked` / `mark_added: false` for a show B1 marked, then `unmark B1` puts the station back and removes the library mark. A re-run of B2 then skips the show (it is "done"), so B2's intent is lost. Worth a runbook line: reverse only the latest batch, or re-derive with a fresh batch afterwards.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** The marking rule, the four pointers, the record and re-run semantics and the reversal are correct and well tested, and interpretation calls #1 and #4 are the right readings of the spec. Interpretation #2 is not acceptable as built. It turns any station stat error into a terminal, exit-0 "no station copy" on the strict station surface. That needs an ENOENT-only distinction, and a recorded decision on whether a genuinely missing copy fails the batch, before this batch can be trusted to gate emcee.
