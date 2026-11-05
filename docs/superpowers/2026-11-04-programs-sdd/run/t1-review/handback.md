### Spec Compliance

- ✅ Spec compliant. Every item in the brief's Produces list is in the diff: `program_title` (site.py:47-57), `block_title` (site.py:60-65), `occurrence_spans` (site.py:68-86), `build_timeline(clock=)` with per-show `block`/`nominal_start`/`program: None` and a document-level `blocks` that omits `end` when it is None (site.py:89-129), `build_lineup` (site.py:132-139), `build_notes` `program` (site.py:279), the `$presents` fill (site.py:390), show.html line 29 (`$presents`), and the temporary `clock=clock_mod.IMPLICIT_CLOCK` on `publish._publish_site` (publish.py:239-240, 251). Every test the brief names is present, and the helper and existing-test changes match Step 1: `_page(program=)`, `clock=CLOCK` on every existing `build_timeline` call, the `$presents` template assertion, and the fallback assertion added to `test_show_page_escapes_and_fills_every_placeholder`. I found nothing extra.
- Checked `occurrence_spans` against the brief's definition ("end = start of the first row whose key differs, appearing after that key's first row"). Only the most recent new key can still be open, because opening a new key closes the previous one. The open key is then closed by either a new key or a revisited earlier key (the `elif`, site.py:84-85). So the definition holds, including for A, B, A orders.
- Checked identity formatting. `Occurrence.nominal_iso` is `us_to_iso(self.nominal_us)` (clock.py:281-283). So lineup `nominal_start` matches the `grid.us_to_iso` form used in plan rows, as the global constraint requires.
- Checked the title source. The program title in notes comes from the manifest (`program_title(manifest)`, site.py:279), never from `ShowAnalysis.meta`. The timeline `program` stays None for Task 2.
- Checked old notes. A notes doc with no `program` key renders the fallback, because `notes.get("program")` gives None and `_text` turns that into `""` (site.py:390). That covers Review Focus 5 for the server-side page.
- ⚠️ Cannot verify here: the Debian 12 / Python 3.11 gate (`packages/transmitter/scripts/test-in-debian12.sh`) was not run because Docker is not running (handback.md). The new syntax is 3.10+ (`X | None`, builtin generics), so no risk is visible, but the controller should run the gate when Docker is available.
- ⚠️ Cannot verify here: wrapping a 60-character title at 320 px (Review Focus 1) is a CSS/smoke matter that belongs to Task 4, not this diff.

### Strengths

- `program_title` is total. It never raises on non-dict manifests, a non-dict `dj_audio`, or non-string or blank titles, and all eight degenerate inputs are pinned in the test (test_site.py:480-484).
- Escaping is done once, on the server, through `html.escape`. The hostile-title test (`test_show_page_escapes_program_title`) checks both that the escaped form is present and that the raw `<b>Late` is absent.
- `test_timeline_adds_block_fields_and_blocks_without_changing_old_fields` compares against a real baseline (the same rows with the block fields stripped) rather than a hand-written expectation. That is a good guard for "additions only" on `timeline.json`.
- `blocks` is sorted by span start, not by set iteration order (site.py:120), so the output is deterministic.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. site.py:84-85: no test covers the revisit branch of `occurrence_spans`. `_rows()` (test_site.py:507-510) never returns to an earlier key, so deleting the `elif` would leave every test green. This is the brief's "first row whose key differs" rule in the case where the differing row is not a new key. Fix: add a case with rows A, B, A and assert that B ends at the second A's start.
2. test_site.py:574-576, `test_lineup_bytes_are_stable_for_equal_content` (plan-mandated): it compares NOW against NOW+1, so it only catches a wall-clock or `now` field in the output. Nothing else can differ across one microsecond. It does pin "no timestamp of its own", which is the requirement, so this is Minor.
3. test_site.py:561-567, the lineup window test: it pins the upper bound (`max(starts) < NOW + 8d`) and that every listed occurrence ends after NOW-1d. It does not pin that the earliest occurrence that qualifies is included, so a too-narrow lower bound would pass. Coverage only; the call itself matches the brief exactly (site.py:135).
4. publish.py:240: the temporary `clock=` parameter has no annotation, unlike its neighbours. Task 2 replaces it, so this is cosmetic.

### Assessment

**Task quality:** Approved

**Reasoning:** The diff carries out the brief item by item, the span algorithm matches the stated definition, and escaping and the fallback behave correctly. The gaps are an untested revisit branch and two weak window/stability assertions. They are coverage polish, not correctness problems.
