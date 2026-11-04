### Spec Compliance

PASS: Spec compliant. Every brief item is in the diff: `concert_stub`, `where_line`, `render_show_page` from `sections` with its signature unchanged, the placeholders added and removed as listed, the one setlist rule, `archive_link` with target/rel, `show.js` with `textContent` only, and all the brief's tests. Set labels, the ticket, liner notes, zone line, lineage, disclaimer and back link match spec "Show pages" (lines 264-295).

Additions, each judged:
- `$artist` (show.html, site.py `values`): justified. The ticket needs the artist alone, and `$title` carries the date. Falls back to the slug, as `_title` does. Mutant M15 shows the fallback is unpinned (Minor 3).
- `<b class="year">` / `<b class="label">`: fine, a forced consequence of the brief's `"<b>" not in page` tests. The classes have no CSS.
- `$lineage` as a fragment: correct behaviour, misleading name (Minor 5).
- Set labels: correct on real data. All 69,217 tracks in 3,625 library manifests carry `set` in {'1'..'5','encore'}, so every label reads "Set N" or "Encore".
- serve.mjs / smoke.pw.mjs: justified, show.js had no other test. Widening `ALLOWED` to `/show/` applies to every smoke test, but it is same-origin and static, so no constraint is lost.
- radio.css:385 `.meta b`: outside the brief's file list. The handback lists it under Implemented but not under its "beyond the brief" concerns. One harmless line.

Cannot verify from the diff:
- **The implementer's screenshots do not exist.** `.superpowers/player-smoke/` holds only `.last-run.json`, and no `t9-shots` directory exists under the worktrees or the temp area. That folder is Playwright's `outputDir` (antenna/playwright config), which is emptied on each run, so a later smoke run probably wiped them (inferred, not observed). I re-rendered instead, see Checks.
- **For the operator, not the implementer: dangling "(see cautions)".** The spec cuts the Cautions section but publishes the rest "as written". 471 of 3,625 library briefings keep a literal "see cautions" in the sections the page renders, and 611 use a form of the word. Visible on gratefuldead-1977-05-08 ("missing a chunk of this pairing (see cautions)"). The spec records the operator accepting the cut, not these leftovers. Needs a ruling: leave, or strip in `parse_briefing` (which also feeds Task 10's panel).

### Strengths

- The malformed-field work is real and measured. At base aed6e294, a non-string artist, date, venue, url, lineage or title raised through `_publish_site`. At HEAD every one of those renders (fuzz matrix below).
- The setlist rule is a true port of notes.js `setlistLine`, same regex as `tidyTitle`.
- The description is cut before escaping, so no entity is split. The slug is encoded with exactly encodeURIComponent's safe set.
- `concert_stub` is tight: `fullmatch` plus `re.ASCII` plus a caught `ValueError`.
- The 4 smoke scenarios pin show.js behaviour.
- The test additions pin most of what matters: all 12 mutants where I named a red test were caught by it (see Mutation).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None in this diff.

#### Minor (Nice to Have)

1. test_site.py:330, `test_non_string_fields_never_stop_the_render` omits setlist `title` and `set`, the two remaining `_text` guards. Mutants M2 (site.py:227) and M3 (site.py:235) both survived, on exactly the unattended path this task exists to protect. Fix: add `{"title": 5, "set": 2}` and a null `set` in a multi-set show to that test. The code itself is correct: the fuzz passes.
2. **Pre-existing, not this diff, and it answers the malformed-notes question.** Malformed input can still stop timeline.json. Reproduced at HEAD and at base:
   - `show` or `source` not an object: `AttributeError` in `build_notes`/`pick` (site.py:171-178).
   - `tracks` a non-iterable: `TypeError` (site.py:190).
   - A lone surrogate from a JSON `\ud800` in any rendered field: `UnicodeEncodeError` at `.encode()` (publish.py:264).
   
   Any of these aborts the whole `_publish_site` loop before the timeline PUT (publish.py:273). The horizon still advances and an alert fires (service.py:161). But timeline.json stays stale until that show leaves the window, and `publish_all` stops after one batch per tick, which slows catch-up.
   Measured exposure: 0 of 3,625 manifests. Suggested follow-up, not for this task: a per-show `try` in `_publish_site`, or type checks in `read_package_notes`.
   `quote()` (site.py:~285) now raises on a surrogate slug too, but the page's `.encode()` already did. Not a regression.
3. Unpinned details:
   - M15: artist slug fallback.
   - M11: `SLUG_SAFE` emptied.
   - M7: escape-then-cut would split an entity at character 200. `test_show_page_description_stops_at_200_characters` uses only `x`; an `&` near the cut pins it.
4. site.py:230 (and `tidyTitle`): the rule normalises only the last mark, so stacked marks stay. "When The Dust Settles >>>" renders "When The Dust Settles >> >". 98 of 69,217 library tracks render with more than one trailing `>`. Not the brief's doubled-mark case, and the spec's wording covers one mark. Any fix must change Python and timeline.js together. `\s*(?:-*>\s*)+$` would do it.
5. show.html:46, site.py:302: `$lineage` now holds HTML while every other fragment is named `*_html`. Rename to `$lineage_html`.
6. site.py:249 / radio.css:72: the first set label inside `.jcard` carries `.kick`'s 15px top margin on top of the card padding, visible as extra space at the top of the card on multi-set shows (implementer's concern 5). `.jcard .kick:first-child { margin-top: 0; }`.
7. smoke.pw.mjs `showPage` blanks the template rather than using site.py output (implementer's concern 6), so no automated test runs show.js against a real render. The pytest `data-slug` pin plus my render below cover it for now.

### Checks run

- Malformed-field fuzz: 15 manifest paths by 13 bad values, through `build_notes`, `json.dumps`, `render_show_page`, `.encode()`, at HEAD and base. At HEAD the only raises are those in Minor 2. All field-type raises from base are gone. A `$` in a value is not re-expanded. Log: t9-review.log.
- Real render, in a scratch copy with system Chrome, at 1200/390/320: gratefuldead-1977-05-08, tedeschitrucksband-2018-08-23 (the longest lineage word in the library, 78 characters) and the hostile fixture.
  - `scrollWidth` equals the viewport in all nine, console clean, no failed requests, `window.pwned` unset.
  - The only element overflow is `.bstub`, which is the notch pseudo-elements.
  - Grouping, stub, ticket and disclaimer match the mockup. The long lineage wraps through `overflow-wrap: anywhere` (radio.css:52).
- Named risk, kill switch vs. new paths: the allowlist (docs/playout-setup.md:88-96) admits `/show/` and `/assets/`, and the kill switch 403s both, as it did `/show/`. No regression. `cassette-og.png` exists in assets.
- Named risk, template loading: read as UTF-8 at service start (service.py:75). Fine.
- Not rechecked: the Debian run (handback says only a docstring changed after it), and `↗` (U+2197) on real iOS, where it may fall to the emoji font. Worth a look in the Task 12 device pass.

### Mutation

Scratch `git archive`, `transmitter.__file__` confirmed inside the copy, fresh pycache per mutant, expected test named first. Baseline 79 passed.

- Caught by the named test: M1 `_title` date raw; M4 `concert_stub` no `_text` (the int param, plus the non-string test); M5 `where` unescaped; M6 set label unescaped; M8 flag always adds a mark; M9 labels always; M10 page_url unquoted; M12 first_text `p` only; M14 date_stub unescaped; M17 fineprint dropped; M19 lineage unescaped. M16 `data-slug` dropped: named test caught it, plus the slug test.
- Survived, as predicted: M2, M3, M7, M11, M15 (gaps above); M13 year unescaped (equivalent, digits only); M18 `#zone` dropped (pytest only; a smoke test reads it).
- show.js in smoke: MJ1 day comparison flipped, red on "are written in the listener's zone…" as named. MJ2 zone written before the empty check, red on "say so when the show has none" as named. Baseline 4 passed.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation meets the brief and spec, and removes every field-type crash on the publish path. What remains is test gaps and polish, plus a pre-existing structural-manifest risk and a "(see cautions)" ruling for the operator, neither of which blocks this task.
