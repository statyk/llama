### Spec Compliance (Task 15)

- ✅ Spec compliant: the code is the brief's code verbatim. `antenna/src/grid.ts`, `antenna/src/playlist.ts`, `antenna/src/index.ts`, `antenna/test/playlist.test.ts`, the configs and the `.gitignore` lines (16-17) all match the brief. Every clock rule from the constraints is implemented: k=6 window (`playlist.ts:36`); grace `0 < cur−last ≤ grace` (`:35`); `N < first` treated as absent (`:38`); fallback `N mod len` with a discontinuity tag at each loop start and at each switch (`:78-80`); off-air = notice + ENDLIST (`:49-60`, `:67`); null means write nothing (`:66-73`). `wrangler.jsonc` sets `workers_dev:false` and `preview_urls:false`, has no routes and no `account_id`.
- Prohibitions: no credentials (named risk; checked): grepping `wrangler.jsonc`, `package.json` and `worker-configuration.d.ts` for 32-hex IDs, `account_id` and `api_token` finds only the wrangler types hash and one line of runtime docs. Every lockfile `resolved` URL is registry.npmjs.org. `git check-ignore` matches `antenna/node_modules`. `.wrangler/` is not tracked. The lockfile is committed.
- ⚠️ Cannot verify here (Task 16 / whole-branch): when the epoch changes, N restarts at 0, so MEDIA-SEQUENCE drops. The spec treats an epoch change as a rare re-render-everything event. Confirm Task 16 or the docs handle the player side.

### Strengths
- Pure, small and well commented. `buildPlaylist` never lists anything past `cur` or past `horizon.last`, and returns null whenever a needed fallback or notice is missing (`:68-73`).
- The off-air MEDIA-SEQUENCE design (`indexAt(scheduledTime+loopMs)`) is correct: it stays at or above live and stays constant within one invocation. A test pins this (`playlist.test.ts:103-117`).

### Issues

#### Critical
None.

#### Important
1. **The discontinuity at the fallback→live switch is not tested** (`playlist.ts:79`; test-only fix). Mutant run in a scratch copy: replace the clause with `entries[i-1].kind === "live" && e.kind === "fallback"`. Predicted: nothing goes red. Result: all 12 tests pass, so the mutant survives. Fallback segment k carries timestamp k·d (`fallback.py:2-3`), and the spec requires the tag "at each switch in either direction". Without it, every recovery from an outage gets an untagged timestamp jump. Fix: in "treats N < horizon.first as absent" (`test:65-68`), assert that `#EXT-X-DISCONTINUITY` comes 3 lines before `seg/e1/100.aac`.

#### Minor
2. **The epoch-start clamp the implementer raised is a real defect, and it is wider than reported** (`playlist.ts:89`; plan-mandated). Verified with a reload-by-reload probe on the real code:
   - **Rules broken:** RFC 8216 §6.2.2 says that when a tag leaves the window, the server must raise EXT-X-DISCONTINUITY-SEQUENCE so the remaining segments keep their discontinuity numbers. The spec's own rule ("during pure fallback the discontinuity sequence is floor(N/len)") is broken too.
   - **What triggers the clamp:** `tagsThrough ≤ 1` always, because only live entries come before `fi`. So the clamp fires exactly when `n_fi < len` and either `fi > 0` or `n_fi = 0`. In plain terms: an empty horizon at the start of an epoch, or ANY live→fallback dropout during the first `len` segments of an epoch.
   - **Empty horizon, len=7:** while segment 0 is in the window, segments 1-5 carry disc 1. At cur=6 they renumber to 0.
   - **The implementer's "self-consistent when len > window" claim is wrong:** the renumbering above happens with len=7 > 6. len=3 renumbers the same way.
   - **Dropout, len=50, at segment 20:** fallback segments 21-25 go from disc 1 to disc 0 two segments into the outage. That is a second renumbering inside pure fallback, beyond the transition glitch the spec accepts.
   - **Impact:** at most one extra reload or glitch, early in an epoch only. As far as I recall (not verified here), hls.js absorbs cc drift on reload; Safari's behaviour is unmeasured. It does not affect spend, and no missing segment gets listed.
   - **Fix (tried in scratch):** number fallback N as `floor(N/len)+1`, i.e. `discSeq = Math.floor(entries[fi].n/len) + 1 - tagsThrough;` with no clamp. The value can never go negative. The probe found zero inconsistencies across all 5 scenarios. Exactly the two floor(N/7) assertions fail, `test:59` and `test:80-86`, and they need +1. Cost: 1 line of code, 2 assertions, a regression test for early-epoch reloads, and a spec wording change to `floor(N/len)+1`. The wording change is the human's call. Pure-live windows renumber to 0 by spec acceptance either way.
3. **Off-air with no published fallback writes nothing, so the operator's off-air lever does nothing** (`playlist.ts:67`; plan-mandated by `test:126`). This is on the strict spend surface. Players keep polling the stale `live.m3u8` (cached, cheap) instead of being stopped by ENDLIST. A playlist with only ENDLIST and no segments would stop them without listing anything missing. At minimum, Task 16 should log or alert loudly when `offair && fb === null`.
4. Test-output noise reported by the implementer: `wrangler types` printed an @types/node hint, and npm lists 3 extraneous packages. Both are harmless.

### Assessment
**Task quality:** Approved. The Important item is a test-only fix: one assertion.
**Reasoning:** The builder is correct on every spend-relevant path. The one behaviour that is not pinned (the fallback→live tag) and the epoch-start numbering defect inherited from the brief are both cheap to fix and do not affect spend.

### task14-fix2 (commit 675cb6c): ADDRESSED
- `test_publish.py:144-158` drives the REAL `publish_batch`:
  - a crash after the horizon PUT leaves high_water at 109;
  - `105.aac` is deleted, so the batch stops at 104 < 109;
  - this reaches `publish.py:291-298`.
- It asserts `held is True`, "horizon held" in the error, no uploads, exactly one horizon PUT (no new one), and that local `last`/`high_water` are unchanged.
- Reading the code: the mutant `report.held = True → pass` falls through to the horizon PUT, so `held is True` fails. That kills it, as the implementer's scratch mutant run reports (exactly this test red).
