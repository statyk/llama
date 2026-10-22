### Code Quality (CODE-QUALITY role) — Approved; no Critical or Important issues. Do-not-retune grep: none of the global-constraints names appear in the diff.

### Strengths
- The edit-callable + common-tail restructure is clear. Each branch does its prompts lock-free, then hands one callable and one stage to a single `with show_unit(entry.ws, view): edit(); echo; _redo_show_locked(...)` tail (cli.py ~1969-1980). The show lock is taken once: `show_unit` holds it and `_redo_show_locked` takes none. `[u]` stays outside the tail, and `_untitled_resolution` opens its own single unit, so the lock is never nested.
- No branch lost today's behaviour or echo text:
  - `[i]`'s picker error is still `str(exc)` to stderr followed by `continue`.
  - `[m]`'s invalid-input echoes are unchanged; `None` replaces `False`, and the result is still `continue`.
  - "nothing selected; skipping" and "unrecognized; skipping" are unchanged.
  - The unexclude routing note and "metadata override updated" are now buffered in `lines` and echoed inside the unit, after `edit()` and before the redo. That is the same relative order as before, and they are never written after the last show write.
- Late binding: I checked every closure (`files`, `undo`/`readmit`, `kwargs`, `picks`, `entry`). Each one is created and called in the same loop iteration with no reassignment in between, and `edit = None` is reset at the top of each iteration. There is no late-binding bug.
- Exception classes check out (focused check): `IAError(LlamaError)`, `CatalogError(LlamaError)` and `ShowChanged(LlamaError)` are all `LlamaError`s; `TaskFailed` and `RateLimited` are `HerderError`s. So the `except (LlamaError, HerderError)` handler covers every failure the brief names. KeyboardInterrupt and other exceptions propagate after `show_unit`'s BaseException restore.
- Most tests assert the specific failure they name:
  - The fixed refusal string.
  - `"error: boom"` / `"error: refused"` together with byte-identical trees.
  - The PROMPT count, for "same show" and "next show never offered".
  - The retry test, which proves the session view is still valid after a restore.
  - `[o]`, `[v]` and `[m]` all write before the stubbed redo raises, so the restore assertions are real, not vacuous.
- Tests are hermetic: every test stubs `_redo_show_locked`, and nothing reaches archive.org or claude.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
1. **The per-turn re-resolve scans the whole library. Plan-mandated.** cli.py:1833-1836 calls `_resolve_show(config, ledger, str(entry.ws.dir))` on every show's turn, skips included. `catalog.resolve_show` calls `iter_shows`, which parses provenance and show.json for every show.
   - Measured read-only against `~/.llama` (3983 shows): 3.0 s cold, 1.1 s warm per call.
   - Walking ~900 holds therefore adds roughly 1 s before each show appears, about 15+ minutes over a full pass of an interactive tool.
   - It also runs once more, under the show lock, inside the unit (`_resolve_show(..., entry.slug)` at ~1977). That one was already there before, but it ran without the lock.
   - Fix: factor `iter_shows`' per-directory body into a one-directory entry builder (the delivered set comes from one ledger read) and use it for both re-resolves. A missing directory still raises the same "no show matches" error.
2. **The new `[u]` try/except in triage has no test** (cli.py ~1949-1954). The existing `[u]` tests cover only the decline and still-held paths, so deleting the wrapper would leave the suite green (I reasoned this, I did not mutate). This is a behavioural change: a failed `[u]` used to escape triage. The global constraint says every behavioural change gets a test that fails on today's code. Fix: stub `_redo_show_locked` to raise `LlamaError` and answer `u\ny\ns\n`. Then assert `error:`, PROMPT count == 2 and byte-identical trees.
3. **The removed-show test accepts any error** (test_triage.py, `test_a_show_removed_before_its_turn_is_reported_and_skipped`, written verbatim from the brief). `"error: " in r.output` would also pass on an unrelated error. Tighten it to `"no show matches" in r.output and "gratefuldead-1974-01-01" in r.output`. Related operator-facing point: the message the operator sees is `error: no show matches '/abs/path/shows/<slug>'`, not slice C's fixed `<slug>: the show was removed; nothing changed`. The brief explicitly chose `f"error: {exc}"`, so this is a note only.
4. **`test_a_failed_metadata_edit_restores_the_overrides` does not assert `exit_code == 0` or the PROMPT count.** Its input also carries a stray trailing `s\n`: the fifth `\n` already answers the returned prompt, so "returns to the prompt" is not actually pinned there. Add `r.exit_code == 0` and `r.output.count(PROMPT) == 2`.
5. **Two minor oddities in how the edit callables are written** (cli.py ~1885-1950):
   - There are five `# noqa: E731` comments, but the repo configures no linter (no ruff/flake8 in pyproject or the workflows), and the pre-change cli.py had one `noqa` in total.
   - `edit = None`, four lambdas and one `def edit()` are mixed under one name.
   - Suggestion: use `functools.partial(_edit_overrides, entry.ws, add_exclude=files)` and the like, which also binds values eagerly, keep a local `def` only for `[v]`, and drop the `noqa`s. Cosmetic.
6. **Ordering window.** `entry` (and so `entry.state`, the flags, and the `[t]`/`[i]`/`[u]` offers) is resolved before `view = capture_view(...)` (cli.py ~1836-1840). A change that lands between those two reads leaves the offers computed from the older show while the view holds the newer bytes, and the unit then accepts. The window is microseconds, and `_print_show_entry` re-reads show.json after the view, so what is displayed is covered. Capturing the view before the re-resolve would close it fully, because any later difference would then refuse.
7. **"metadata override updated" is echoed and then followed by `error: refused` when the redo fails.** The message is now slightly misleading, since the override was rolled back. The brief mandates echo-inside-the-unit; the alternative is `_untitled_resolution`'s print-after-the-unit pattern, used three functions above. The two patterns now coexist in the same feature. Consider wording such as "metadata override applied; redoing from gather" if this matters.

### Assessment
**Task quality:** Approved
**Reasoning:** The restructure is correct and readable: the lock is taken once, prompts run outside it, there are no late-binding hazards, today's echoes are preserved, and the named failures are asserted and restored. Remaining items are a plan-mandated ~1 s/turn latency cost on the 4k-show library, one untested new `[u]` handler, and test-tightening.

Risks checked outside the diff (one focused check each):
- Lock nesting: read `_redo_show_locked`, `show_unit` and `_untitled_resolution`.
- Exception class coverage: grepped the `IAError`/`CatalogError`/`TaskFailed`/`RateLimited` bases.
- The removed-show message: read `catalog.resolve_show`/`_resolve`.
- Per-turn cost: timed `iter_shows` read-only.
- `[u]` coverage: listed the triage `[u]` tests.
- Linter: grepped the lint config.
