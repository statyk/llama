### Spec Compliance

- ✅ Spec compliant. Every brief item has its hunk: LINEUP_KEY/LINEUP_CACHE (publish.py:56,61); `_publish_site` loads `live_clock(p.ws, save=False).clock` once per call and passes it to `build_timeline` (publish.py:247,259); `show["program"] = site.program_title(manifest)` set before both `continue`s (publish.py:266); lineup body built by the same encoder as `put_json` via the new `_json_body` (publish.py:217-222, 285), PUT only on digest change, `PutBudgetExceeded` re-raised, anything else logged `lineup step failed: ...` with the old digest kept (publish.py:284-293); digest threaded through `publish_batch` into `PublishState` (publish.py:363-365, 386-387); `PublishState.lineup` + `data.get("lineup")` (state.py:26,41); CLAUDE.md Overview sentence (CLAUDE.md:22-26). All nine named tests exist (test_publish.py:533-694).
- ⚠️ Cannot verify from diff: the Debian-12 gate (`packages/transmitter/scripts/test-in-debian12.sh`) was not run (implementer reports Docker down). No 3.12+ syntax added in this diff, but the controller should run the gate when Docker is up.
- ⚠️ Timeline `blocks` spans and per-show `block`/`nominal_start` come from Task 1's `build_timeline`; this diff only supplies the clock.

Checks run (named risks):
- Risk: removing `_publish_site`'s `clock=` parameter breaks a caller. Grepped src+tests: the only caller is publish.py:365. Clean.
- Risk: `live_clock` raises outside the lineup try and kills the site step. Read clock.py:239-269: it never raises (missing -> implicit; invalid/unreadable -> last-good, else implicit), and with save=False it writes nothing. Clean.
- Risk: lineup digest churns every minute. site.py:126-133 `build_lineup` holds no timestamp, so bytes change only when an occurrence enters or leaves the window or the clock changes. Clean.

### Strengths
- Lineup step sits after the timeline PUT, so a lineup failure cannot hold back the timeline. Budget exhaustion still propagates the same way the timeline PUT's does.
- `program` is assigned before the degraded-manifest `continue`, so an unreadable manifest gives `program: null` without re-PUTting the page. The unreadable-manifest test pins both halves (test_publish.py:551-563).
- `_json_body` extraction means the hashed bytes are exactly the PUT bytes. There is no second encoder to drift.
- The ordering test pins notes < page < timeline < lineup < horizon (test_publish.py:677-685).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- test_publish.py:640-657 (`test_lineup_failure_never_stops_the_timeline`): the second pass changes no manifest, so `after.notes == before.notes` holds whether or not this pass's notes digests survive a lineup failure. To pin the brief's "the notes digests are kept in state", also add a title in that pass (forcing a notes re-PUT) and assert that `after.notes["band-1"]` differs from `before.notes["band-1"]`. The "lineup step failed" log assertion already catches the mutant where the try/except is deleted (the error would log as "site step failed").
- test_publish.py:39-41: `lineup=load_publish_state(p.ws).lineup` compares the field to itself, which is tautological. Assert `is not None` (or the sha256 of the PUT body) instead.
- test_publish.py:551-563: the test asserts only that `notes/band-1.json` was not re-PUT. Add `show/band-1.html` count == 1 to match the brief's "keeps the published page".
- publish.py:284-290: when `PutBudgetExceeded` hits the lineup PUT, notes/page/timeline are already up but `publish_batch` returns before `save_publish_state`, so this pass's notes digests are lost and re-PUT next pass. This matches the timeline PUT's existing budget behaviour and the brief mandates propagation, so it is acceptable. It costs a few extra PUTs only when the budget is already exhausted.
- CLAUDE.md:22: the new sentence starts mid-line and runs past the paragraph's wrap width. Reflow it.
- test_publish.py:569-573, 588-614: inline imports and a module-level `dataclasses_replace` helper between tests. Import `dataclasses`, `PlanRow`, `planner`, `live_clock` and `build_package`/`make_root` at module top.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation follows the brief line for line. The lineup is isolated after the timeline with correct budget propagation, and the program title is read from the manifest at publish time for every listed show. The remaining gaps are test tightness and formatting only.
