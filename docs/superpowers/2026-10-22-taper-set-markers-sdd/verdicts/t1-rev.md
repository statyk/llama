### Spec Compliance
- ❌ Issues found:
  - **Song lines have their track prefix stripped twice**, so the reader's titles drift from `_emit_items`'s cleaning, against the brief's interface ("title: song text after _emit_items-style cleaning").
    - Where: `taper.py:234-236` strips `_TRACK_PREFIX`/`_NUM_PREFIX` from the line, and `_song_titles` then strips both again (`taper.py:210-212`), because `rest = core` for song lines (`taper.py:173`).
    - Probe: `Set 1:\n01 Bertha\n02 100 Years\n...\n04 72 (This Highway's Mean)`. The reader gives `Years` and `(This Highway's Mean)`; `parse_setlist` gives `100 Years` and `72 (This Highway's Mean)`.
    - Cache sweep (read-only, every `md_*.json` whose `taper_text_for` source is not `none`): **87 texts** carry a reader title that is a parse title with its leading number removed, and **48 of them assert**. Examples: `32 Things`→`Things` (moe2007-07-14.flac16), `20 Eyes`→`Eyes` (ymsb2005-10-31.at4041.flac16), `Hours Awake` (lotus2008-04-05.flac16).
    - Details under Important 1.
  - Every other requirement listed in the review brief checks out against the code and tests. Evidence:
    - Recognised forms: `taper.py:73-120`.
    - Track-prefix strip before the marker test: `:234-237`.
    - Inline split, exactly as `_emit_items` does it, with no truncation: `:150-157`.
    - Leading-block rule: `:277-290`.
    - Continuation and set+encore lines: `:90-92`, `:272-276`, `:291-292`.
    - Void rules, all of them: decreasing, skip, set 4+ (`:126-132`, `:314`), empty set (`:252-253`, `:262-263`, `:299-300`), numbered marker after the encore (`:269-271`).
    - Cross-check last, as a subset test: `:322-327`.
    - `encore_like` only on non-marker lines and marker-line rests: `:238-247`.
    - Timestamp, bare-number and filler drops: `:137-142`, `:213-221`.
    - `taper_text_for`'s source rule and list joining: `:332-355`.
    - Protected names: the diff only *uses* `is_filler` (the import at diff line 66, the call at diff line 237). No protected name or do-not-retune constant is edited.
    - `git diff main -- packages/llama/src/llama/setlist.py` is empty (0 bytes).
- ⚠️ Cannot verify from the diff alone (these need an orchestrator or operator ruling, not implementer work):
  1. **Spec gap with real cases: the encore-like veto input misses trailing or bracketed `E` forms.** This is the spec's anti-goal. The implementer followed the spec's list literally. Raised as Important 2.
  2. **The brief's `lotus-2005-10-15` claim (`asserts`) cannot hold on the real text.**
     - The real lines are `~Disc 1: Set 1+Encore~`, a bare `Encore`, and `~Disc 2: Set 2~`. The colon disc form is not a recognised form.
     - The test pins `asserts=False, reason="one set"` (`test_taper.py:1491-1495`). I verified the excerpt is a verbatim match of `md_lotus2005-10-15.481.json`.
     - The spec's own sentence (the line asserts nothing, and the later marker starts the encore) does hold. The brief needs correcting, not the code.
  3. **Source-rule cost (implementer concern 3), spec-literal.**
     - `railroadearth-2009-01-15`'s description has an inline `17 E: …`, which counts as a marker. So the notes' full `Set One:`/`Set Two:` structure is never read.
     - Related: a prose `4th set` also counts as "a marker" for source selection (`taper.py:342`), so it would hide markers in the notes. The spec says set 4+ is "recognised for voiding only", which is ambiguous on this point.
     - Both only make the taper own less. Worth a one-line ruling on whether "explicit marker" for source selection should mean a set-or-encore start only.
  4. **Substituted excerpts** (sibling recordings for antibalas, moe 2002-06-22 and gd1981-10-16; a synthetic `3. Encore: Higgins`). They are disclosed in the handback and cite their identifiers. I spot-checked six excerpts against the cache, and all six are byte-equal to the cited description: GRATEFUL_SHRED, TTB, GD_1990_03_22, LOTUS, DNB, PAF.

### Strengths
- **The "own less" direction is applied consistently wherever the spec is silent.** Examples:
  - `void: continuation without its set's header` instead of guessing where an unmarked set began (`taper.py:278-279`, `:293-294`).
  - A trailing empty `Encore:` counts as an empty set (`:262-263`).
  - A set-and-encore line raises `encore_like` (`:272-276`).
  - `E`/`ENC` take no bracket decoration, so `(E)` and `[E]` are not markers (`:113-120`).
  - The `- ` requirement on the dash keeps `E-Bow the Letter` from being an encore line (`:76-79`).
- **The cross-check really backstops the reader's narrower header shapes.** Probe: `Set 3 & Encore: …` after sets 1-2 gives `cross-check: 3`, so set-3 songs mislabelled as encore are not asserted. `Set 1 (8:20pm)`, which `_SET_LINE` reads and the reader does not, gives `no markers`.
- **The tests are real and specific.**
  - Excerpts are verbatim and cite their cache file.
  - Every brief bullet has its test, plus parametrised synthetic void and encore-like cases (`test_taper.py:1529-1550`, `:1707-1724`).
  - The `parse_setlist` pin uses literals captured on main (`:1796-1890`).
  - The implementer's mutation pass (22 of 23 caught, and the survivor's reasoning holds) is a better check than most tasks get.
- `parse_setlist` is untouched, and the reader imports its helpers unchanged. The module has one clear job, and its docstring states its exact scope.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **Double track-prefix strip on song lines** (`taper.py:234-236` with `taper.py:210-212`).
   - What's wrong: for a song line, `_classify` returns `core` (already stripped of `_TRACK_PREFIX`, plus `_NUM_PREFIX` when enumerated) as `rest`. `_song_titles` then strips both prefixes again, so a digit-leading title on an enumerated tracklist loses its number.
     - `01 100 Years` → `Years`
     - `04 72 (This Highway's Mean)` → `(This Highway's Mean)`
     - `_emit_items` strips once and keeps `100 Years`.
   - Measured: 87 cached texts, 48 of which assert (sweep above).
   - Why it matters:
     - It breaks the interface contract Task 2 builds on.
     - Section 3's placement matches these titles against tracks. A mangled boundary item stops matching, so the boundary goes unplaced and the yield is lost. Checked: `fuzzy_title_eq(n("Years"), n("100 Years"))` is False, and `Eyes` vs `Eyes of the World` is False. So in the cases I checked it fails safe (own less), not wrong.
     - It also makes the reader's titles disagree with the canonical setlist's, which Task 2/3 measurements will compare.
   - How to fix: strip once. For example, `_song_titles` takes a `prefixed: bool`, or `_scan` passes the unstripped `line` for song lines and lets `_song_titles` do the single strip, exactly as `_emit_items` does. Marker rests keep their single strip. Add a test with an enumerated `NN 100 Years` line asserting the title equals `parse_setlist`'s.

2. **Spec gap: trailing or bracketed `E` encore notations raise no `encore_like`, so an encore the taper wrote is silently folded into the last set.** This is the spec's anti-goal. Not an implementer error: spec section 2 and the brief fix the regex. **Needs a ruling before Task 2 relies on the veto.**
   - Real cases. Each one gives `asserts=True, has_encore=False, encore_like=False`:
     - `gd1985-03-31.sonyecm220t.keshavan.miller.106791.flac16` and three sibling recordings (`…124768.chasingwilma.flac24`, `…nak300.morris.114487.flac24`, `…nak300.barfield-lane.104927.flac24`). The description ends `…-> Day Tripper, E`, and the reader yields an item `('E', '2')`.
       - The library's `gratefuldead-1985-03-31` has a `US Blues` encore track. Its selected recording (`gd85-03-31.oade.connor…`) has no markers, so it is unaffected today. If a sibling were selected, Task 2's "no encore marker → last set runs to the end" rule would ship `US Blues` as set 2.
     - `ymsb2007-10-05.Analog_Nagra_Reel_to_Reel.flac`, where `Traffic Jam E\nDim Lights Thick Smoke` marks the encore.
     - Synthetic shapes the spec's list also misses: `US Blues (E)` (a trailing `(E)`), and an own-line `[E]`. The latter is pinned as a plain set-1 title in `test_taper.py:1670`, with no `encore_like` assertion.
   - Why it matters: the stakes paragraph names this exact failure ("an encore the taper wrote silently folded into the last set"). The veto exists to prevent it, and its input list has holes.
   - How to fix, after a ruling: widen only the *veto input*, which is not a marker form, so the "builder adds no other form" constraint is untouched and the change can only make the taper own less. Candidates:
     - a split song item that is exactly `E`/`E\d`/`ENC` after decoration
     - a song line ending in `\s(?:E|\(E\)|\[E\])$` or `,\s*E$`
     - an own-line `[E]`

     Measurement 5 or Task 3 should count the collateral (for example Mogwai's `D to E`, which a "line ends in ` E`" rule would also hit). The cache sweep found 6 asserting texts with such tokens, so the population is small and cheap to hand-check.

#### Minor (Nice to Have)
1. **`14 E. Playin' Reprise` is detected only when the text is enumerated** (`taper.py:239` tests `_ENCORE_LIKE_START` on `core`, which keeps a bare `14 ` unless `_NUM_PREFIX` ran). This follows the spec literally ("after track-prefix stripping"), but on a non-enumerated text the same line would not set `encore_like`. Since this is a veto input (own-less direction), consider also testing after an unconditional `^\d{1,3}\s+` strip.
2. **The extra void rules go beyond the spec's list and are not called out in the module docstring**: `continuation without its set's header`, empty set at end of text, and filler-only sets counting as empty. All three are own-less and documented in the handback. A one-line mention in the docstring would keep Task 3's measurement from rediscovering them.
3. **`_classify` returns a 5-tuple** (`taper.py:160-173`) that callers destructure positionally. A small NamedTuple would read better. Polish.
4. **`taper_text_for` scans the chosen text once to choose it**, and `read_taper_structure` scans it again. That is cheap and fine. Noted only because `_has_marker` and `read_taper_structure` could drift if the scan grows side effects.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** Important 1 is a real, measured defect that breaks the brief's title contract (87 cached texts, 48 of them asserting), with a one-line fix. Important 2 is a spec gap, not implementer error, but it hits the stakes anti-goal on real texts and needs a ruling before Task 2's placement trusts `encore_like`. Everything else matches sections 1-2 closely, and the tests are strong.
