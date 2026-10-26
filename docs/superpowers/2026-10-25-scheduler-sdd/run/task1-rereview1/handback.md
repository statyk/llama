### Finding Verdicts

**I1: ADDRESSED.** In `packages/transmitter/tests_transmitter/test_publish.py:482-485` the show is now at segments 100..103 (`frames=441 * 4`) and the interstitial at segment 104, inside the published window 100..109. The test still asserts `all(r.kind == "show" for r in asked)` and that the timeline lists only `["band-1"]`. I checked the mutant claim myself in a scratch copy (`git archive af46d72 packages/transmitter antenna/templates`, run from an empty cwd, `transmitter.__file__` confirmed inside the scratch tree):
- Unmutated: the test plus all of `test_layout.py` give 21 passed.
- With the `if r.kind != "show": continue` guard in `_publish_site` (`publish.py:244-245`) removed, the test FAILS on the `all(r.kind == "show" ...)` assertion, because the interstitial row was passed to `analysis_for`. That is the predicted reason, not an incidental error.

(Note for anyone repeating this: a scratch copy also needs `antenna/templates/show.html`, which `helpers.make_publisher` reads. Without it the test fails before reaching its assertion, which would score a false CAUGHT.)

**I2: ADDRESSED.**
- `layout.py:22` defines `_PHASE1_FIELDS` as exactly the eight fields R5 lists.
- `PlanRow.to_json` (`layout.py:58-74`) writes every phase-1 field always, writes a scheduler field only when `v != f.default`, then adds `extra` with `setdefault`.
- The phase-1 build (`02b6d49`) wrote rows with `asdict` plus `json.dumps(..., sort_keys=True)`. The current `write_plan` (`planner.py:158-160`) uses the same `sort_keys=True` dump, so a phase-1 row now comes out byte-identical.
- Tests pin this. `test_layout.py:147-149` asserts a phase-1 row serialises to exactly the eight keys. `test_layout.py:152-161` checks that `read_plan` then `write_plan` leaves a phase-1 `plan.jsonl` byte-identical (with `run_start: true` and `cut_frame: null`, the phase-1 shape).
- The runbook (`docs/playout-setup.md:429-430`) now says everything R5 asked for:
  - this commit writes phase-1-shaped rows, so rolling back to the build before it stays safe until the first scheduler row is written;
  - an older build cannot read scheduler rows, and plan, render and publish wedge;
  - once the scheduler has run, this commit is the oldest safe rollback target;
  - this commit is also the one that keeps interstitial rows out of `timeline.json`, `notes/` and `show/`.
  The never-truncate and `[interstitials]` bullets are kept. Commits are named by what they do, never by task number.
- All plan readers go through `read_plan`/`from_json` (`pipeline.py`, `service.py`, `publish.py`); `planner.write_plan` is the only caller of `PlanRow.to_json`. Nothing reads raw plan rows expecting a `kind` key.

### New Breakage in the Fix Diff

**Minor** (`layout.py:66-73`): "known fields win on collision" no longer holds for a default-valued field. If an `extra` mapping holds a known field name (say `kind`) while that field is at its default, the known field is skipped and the `extra` value is written in its place; on reload it becomes the field's value. `from_json` can never produce this, because it puts only unknown keys into `extra`. No source code builds a `PlanRow` with `extra` except `from_json` (`layout.py:93`), and `dataclasses.replace` only copies an already-clean `extra`. So it is reachable only by constructing a `PlanRow` directly. Possible hardening: skip `extra` keys that are in the known field set, rather than relying on `setdefault`.

Checked and clean:
- Fields set to their default (`degraded=False`, `announcement_broken=False`, `bends=()`, `names=()`, `kind="show"`, the `None` fields) are omitted and reload to the same default, so `from_json(to_json(r)) == r` holds.
- `miss=False` differs from the `None` default, so it is written and preserved. No non-default value is lost.
- A list passed as `bends=[]` does not compare equal to `()`, so it is written as `[]` and reloads as `()`, which is harmless.
- Every scheduler field has a plain default (only `extra` uses `default_factory`, and it is skipped), so comparing against `f.default` is sound.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
