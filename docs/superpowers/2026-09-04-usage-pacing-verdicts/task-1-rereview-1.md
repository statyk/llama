# Task 1 scoped re-review (round 1): fix diff `ecd2fc1..05d6279`

Scope: verdict the two open findings against the fix diff only. Read-only,
no edits, no commits, no suite re-run (report evidence judged instead).

Diff reviewed: `.superpowers/sdd/2026-09-04-usage-pacing-phase1/review-ecd2fc1..05d6279.diff`,
cross-checked against the actual working tree at HEAD (`05d6279`), which
matches the diff exactly.

## Finding 1 (Important) — `capture_failure`'s "never raises" contract was false

**Verdict: ADDRESSED.**

`packages/herder/src/herder/failures.py:39-45`:

```python
path.write_text(
    f"cmd: {' '.join(cmd)}\n"
    f"exit_code: {getattr(proc, 'returncode', None)}\n"
    f"--- stdout ---\n{getattr(proc, 'stdout', '') or ''}\n"
    f"--- stderr ---\n{getattr(proc, 'stderr', '') or ''}\n",
    encoding="utf-8", errors="replace",
)
return path
except Exception:  # noqa: BLE001 - defensive: a capture problem must never mask the backend failure being captured
    return None
```

Both required pieces landed:

- `path.write_text(...)` now pins `encoding="utf-8", errors="replace"`,
  which removes the locale-dependent `UnicodeEncodeError` path the finding
  named. `errors="replace"` additionally covers stray surrogates from a
  mis-decoded subprocess read, not just plain non-ASCII — reasonable and
  matches the cited `workspace.atomic_write_text` precedent
  (`packages/llama/src/llama/workspace.py:20`, confirmed: opens with
  `encoding="utf-8"`).
- The handler is widened from `except OSError` to `except Exception`, with
  a `# noqa: BLE001` and an inline rationale comment. This now also covers
  the `' '.join(cmd)` `TypeError`-on-`PathLike`-argv-element case the
  finding named, since that expression sits inside the same `try` block
  (line 40) and any exception it raises is caught by the same handler.
- The cited "repo's existing defensive-noqa idiom" precedent
  (`packages/llama/src/llama/jerrybase.py:128`,
  `except Exception:  # noqa: BLE001 - defensive: absence must never
  raise`) is real, not fabricated — checked directly.

The `return None` behavior on the escape path is unchanged from before —
only the exception types caught got broader, not the outcome. The function
still returns `Path | None`, matching its declared contract; nothing about
the widening loses or alters the return semantics.

## Finding 4 (Important) — the "never raises" test didn't test the write path

**Verdict: ADDRESSED**, and the load-bearing claim in the fix report checks
out under independent reasoning (I did not re-run the suite, per
instruction, but traced the mechanism by hand).

New test, `packages/herder/tests/test_failures.py:43-58`:

```python
def test_capture_never_raises_when_the_write_itself_fails(tmp_path, monkeypatch):
    ...
    def _boom(self, *args, **kwargs):
        raise ValueError("simulated encoding failure")

    monkeypatch.setattr(Path, "write_text", _boom)
    failures.set_capture_dir(tmp_path)
    try:
        assert failures.capture_failure(["claude"], FakeProc(returncode=1)) is None
    finally:
        failures.set_capture_dir(None)
```

Tracing it against the current `failures.py`:

- `tmp_path` is a real, writable directory, so `_capture_dir.mkdir(parents=True,
  exist_ok=True)` (line 38) succeeds trivially and the code proceeds past
  the arm the old test exercised — this test genuinely reaches the write,
  unlike `test_capture_never_raises_when_the_dir_is_unwritable`.
- `monkeypatch.setattr(Path, "write_text", _boom)` replaces the method at
  the class level for the duration of the test (auto-restored by
  `monkeypatch` afterward — no cross-test leakage). When
  `capture_failure` calls `path.write_text(f"...", encoding="utf-8",
  errors="replace")`, that dispatches to `_boom(path, f"...",
  encoding="utf-8", errors="replace")`, which unconditionally raises
  `ValueError` — regardless of the `encoding=`/`errors=` kwargs added by
  Finding 1's fix, since `_boom` accepts `*args, **kwargs` and ignores
  them. So this test is compatible with (and unaffected by) the Finding 1
  change, and would exercise the write path correctly even if Finding 1's
  fix hadn't landed.
- `ValueError` is not a subclass of `OSError` (both descend independently
  from `Exception`), so under the pre-fix `except OSError:` handler this
  `ValueError` would propagate uncaught out of `capture_failure`, and
  pytest would record it as a test failure/error — not a silent pass.
  Under the shipped `except Exception:` handler, it's caught and `None`
  is returned, satisfying the assertion. This confirms the test is
  discriminating exactly the arm it claims to.
- The report's claim to have manually narrowed the handler back to
  `except OSError:`, re-run, and observed exactly
  `test_capture_never_raises_when_the_write_itself_fails` fail (4 passed,
  1 failed) while the other four stayed green is consistent with this
  trace: none of the other four tests exercise a non-`OSError` escape, so
  narrowing the handler wouldn't touch them. The reported command output
  (`...F.` / `1 failed, 4 passed`) matches the position of the new test
  (5th of 5, alphabetically it's actually not sorted — pytest runs file
  order, and the new test is inserted between
  `test_capture_never_raises_when_the_dir_is_unwritable` and
  `test_each_capture_gets_its_own_file` in the source, matching the `...F.`
  pattern positionally). The evidence is internally consistent and the
  mechanism independently reproducible by inspection — no need to
  re-run to trust it.

The test's docstring-style comment inside the test body accurately
describes why the old test was insufficient (blocks `mkdir`, never reaches
`write_text`, passes even narrowed to `except FileExistsError`) — this
matches the original Finding 4 text precisely.

## New breakage introduced by the fix diff

None found. Specifically checked:

- **Scope**: `git show 05d6279 --name-only` touches only
  `packages/herder/src/herder/failures.py` and
  `packages/herder/tests/test_failures.py` — nothing else in the repo was
  touched by this fix commit.
- **Return contract**: `capture_failure` still returns `Path | None` and
  still returns `None` on any capture-side failure; the widened handler
  changes only which exception *types* are absorbed, not the function's
  observable contract.
- **Silent-swallowing risk**: `except Exception` is broad, but it is used
  here for a function whose entire declared purpose is "never raises" as a
  defensive capture-only side channel — this is the correct place in the
  codebase for that idiom (mirrored at `jerrybase.py:128` for the same
  "absence/failure of a best-effort side channel must never raise" reason),
  not a case of over-broad exception handling creeping into real logic.
  It does not swallow anything the caller depends on: `capture_failure`'s
  only contract is "write a diagnostic file or don't," and callers already
  treat a `None` return as "no diagnostic file was written," not as
  success/failure of the underlying backend call.
- **Bare `except Exception` and control-flow exceptions**: `except
  Exception` (not bare `except:`) does not catch `KeyboardInterrupt` or
  `SystemExit` (both subclass `BaseException`, not `Exception`), so a
  ctrl-C or `sys.exit()` during the write is not swallowed. No new hazard
  there.
- **Finding 1/Finding 4 interaction**: verified above that the new test
  exercises the write path in a way compatible with the `encoding=`/
  `errors=` kwargs added by Finding 1 — the two fixes don't conflict or
  paper over each other.

## Deferred (out of scope, not part of verdict)

Per instructions, these were pre-ruled Minor and deliberately not
re-litigated:

- `time.monotonic_ns() % 1_000_000` filename uniquifier and its collision
  window — untouched by this fix diff, as expected (commit message
  explicitly confirms it was left alone).
- The timestamp being unmarked local time — untouched.
- `test_each_capture_gets_its_own_file` pinning the uniquifier only
  probabilistically — untouched.
- The `proc` parameter being unannotated — untouched.

One incidental observation, not a finding (out of scope, noted only for
completeness): the new test's `_boom(self, *args, **kwargs)` monkeypatch
replaces `Path.write_text` globally for the test's duration via
`monkeypatch.setattr`, which is standard pytest practice and is
auto-reverted — no leakage into other tests. Not a concern.

## Overall verdict

**Both findings ADDRESSED.** Finding 1's fix closes both named escape
paths (`UnicodeEncodeError` via the encoding pin, and the general
non-`OSError` escape via the widened handler) without weakening the
function's `None`-on-failure return contract. Finding 4's new test is
genuinely load-bearing — traced by hand, it reaches the write (unlike the
old test), fails under the pre-fix `except OSError` handler for the
reason claimed (`ValueError` is not an `OSError`), and the report's cited
command output is consistent with that mechanism. No new breakage was
introduced by the fix diff, and the fix diff's scope is confined to the
two files it should have touched.
