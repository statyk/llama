# t8-rev — Task 8 review (spec compliance + code quality), 0038589..e416018

### Spec Compliance

- ✅ Spec compliant. Every Interfaces item in task-8-brief.md is present and matches the brief's regexes character for character: `_PLACEHOLDER` (placeholders.py:29-32), `_TIMESTAMP` (:38), `_LEADING_TIMESTAMP` (:42), `_DATE_PATTERNS` (:50-55), `_FILENAME_SHAPES` (:61-65), `RESIDUE_TOKENS` with the start-anchored prefix (:69-83), `is_residue` with the 4-digit exemption (:121-125), `is_placeholder_title("")` → False (:130-135), `is_junk_tag` without letter counting (:138-143). Imports are only `re` and `fuzzy_norm_title` (:15-17). `CanonicalBuild.corroboration` is a trailing field (gather.py:771) built once, in `build_canonical` (gather.py:832), from raw parses before `_strip_head_banner` (gather.py:857), keyed by `fuzzy_norm_title` and skipping empty keys (gather.py:794-799), over `lma:` plus setlist.fm only.
- ✅ Ruling 3 (spec :250-253; plan Global Constraints): the vocabulary leaves out `"chosen"`, leaves out every `lma:` sibling whose `" ".join(desc.split())` equals the chosen description (gather.py:790-792), and leaves out `"llm"`, because the extract_setlist parse is created after line 832 and never enters `parses` at that point.
- ✅ The do-not-retune grep over the diff for `is_real_title|title_fraction|_TRACK_NUM_PREFIX|normalize_song|DEFAULT_ALIASES|GD_SHORTHAND|_RECOVER_BELOW|_RECOVER_SIBLING_ABOVE|TAIL_GUARD|TRACKS_REMAINING|MAX_SKIP|SHORT_FRACTION_OF_MEDIAN|MIN_PLAUSIBLE_SEC|MIN_MEDIAN_SAMPLE|align_coverage_threshold|_ENUMERATED_MIN|_STRUCTURE_PREFIX|_FOOTNOTE_TAIL|_YEAR_LIKE` gets one hit, a docstring mention (placeholders.py:11). `git diff --stat` over titles.py, structure.py, songs.py, junk.py and config.py is empty.
- ✅ Ruling 2: the predicates sit in a new module beside `is_real_title`, and titles.py is untouched.
- ✅ The P5 ruled limitation is pinned (test_placeholders.py `test_residue_class_demotes_the_ruled_limitation_cases`: `Jam 12-31-99`, `Master`, `Matrix`).
- ✅ The spec's "Testing" near misses for these classes (`1979`, `Song #1`, `Untitled`, `Untitled #12`, `3AM`, `?`, `07:22 - IB49`, `12-28-99`) are all present as cases.
- ⚠️ This diff cannot show whether Tasks 9/10 consume `corroboration` read-only (see Minor 2), or whether Task 9 gates the residue class on `is_real_title` as plan :1421 says (see the answer to flagged point 3).

#### Rulings on the flagged points

**(1) `recording_level_junk` requires a non-empty `fuzzy_norm_title(item_title)`, not just a non-empty `item_title` (placeholders.py:155-156). This is accepted, and it is the more faithful reading.**
- The spec says "the item's own title on every file" (spec :569).
- Take an item title of `---` with tags `?`, `!`, `...`. All of them normalise to `""`, so under the brief's literal wording the three tags would count as "the item's own title" even though none of them is.
- The stricter guard only demotes less, which is the safe direction for 2b.
- It is pinned by `test_recording_level_junk_item_title_that_normalizes_to_nothing_never_matches`.
- The brief's wording should be amended to match.

**(2) The shared mutable `{}` default (gather.py:771) is Minor; see Minor 2.**

**(3) Uncorroborated short tags (`FF`, `J`, `42`, `7-11`) and 2b. The implementer's framing is wrong about Task 9, and right about `is_placeholder_title`.**

What the spec says:
- Spec :565-568 defines the class: "**pure filename residue**: after deleting the identifier, date, disc/track, lineage and extension tokens, fewer than 3 letters remain (...). A pure 4-digit title is exempt." Taken in isolation, that text does catch `42`.
- Spec :576-577 scopes it: "Only `tags` and `sibling-format` titles are judged."
- A `tags` title at the tag rung has already passed `is_real_title`, which needs 3 or more letters or a 4-digit year (titles.py:140-148).
- So in the spec's 2b, `42`, `FF`, `J`, `7-11` and `I-55` are never judged. They fail `is_real_title`, never become a `tags` title, and are exactly the population 2a (spec :494-510) exists to accept, with the junk veto explicitly "does not reject a core for having fewer than 3 letters" (spec :509-510).
- The spec does NOT intend real short titles to be demotable by 2b, corroborated or not.

What Task 9 does:
- Plan :1421 consumes the residue class as `is_real_title(t) and is_residue(t)`.
- That gate, not the corroboration exemption, is what keeps `42`/`FF`/`J`/`7-11` from being demoted.
- The handback's "only 2a's corroboration exemption protects them in 2b" is incorrect, and the Task 9 reviewer should not be steered by it.
- Placeholder and timestamp positions are judged without the `is_real_title` gate (plan :1419). So `4:20` (a timestamp) and `Tr 7` would be demoted unless corroborated. They fail `is_real_title` today too, so demotion only stops them reaching the positional `setlist` rung. That is the safe direction.

Where the plan goes beyond the spec:
- `is_placeholder_title` (placeholders.py:130-135, plan-mandated at plan :1245) composes the classes WITHOUT the `is_real_title` scope.
- Measured in the worktree's own venv (`llama.__file__` inside the worktree), `is_placeholder_title` returns True for all of `42`, `FF`, `J`, `7-11`, `I-55` and `4:20`. Those are 2a's targets.
- No code in the repo and no later task in the plan consumes `is_placeholder_title` (grep over packages/, scripts/ and the plan: only Task 8's own definition, test and mutant (d)). Task 9 composes the component predicates itself.
- So this is not wrong behaviour today. It is a latent hazard on the strict surface: a predicate named as "2b's per-title classes" is broader than 2b, and a later caller using it in good faith would demote 2a's class. Recorded as Minor 1 (plan-mandated).

**"One equivalent survivor" (f-equiv: dropping the `startswith("lma:")` filter changes nothing): verified equivalent.**
- At gather.py:832, `parses` holds only `"chosen"` and `lma:` sources: `_collect_parses` at gather.py:365, with setlist.fm inserted after (:833-834) and the LLM parse built later.
- The chosen parse's description is `_description(chosen_meta)` (gather.py:363), and `chosen_meta` is the very `meta` that build_canonical passes as `_description(meta)` at :832. Its whitespace-normalised description therefore always equals `chosen_ws`, and the copy check drops it.
- When the chosen description is blank, `chosen_ws == ""` and the chosen parse is still dropped. Any blank sibling is dropped with it, which is harmless because a blank description parses to no items.
- setlist.fm is never subject to the copy check (gather.py:793-794), so its items always count, which is correct.
- When the chosen recording is absent from `candidate.recordings`, there is no `"chosen"` parse at all, and copies are still recognised via `_description(meta)`.
- One caveat: the equivalence is positional, holding because corroboration runs before the setlist.fm insert. The `lma:` filter is the guard that would survive a later reordering, so keeping both is right.

### Strengths

- `_corroboration` is a small pure helper with `zip(..., strict=True)` (gather.py:790). A future break in the `parses`/`descriptions` pairing raises instead of silently mis-pairing.
- It is called at the one point where the lists are still parallel, and that ordering constraint is commented at gather.py:828-831.
- Reading the chosen description from `meta` rather than from the `"chosen"` parse (gather.py:832) covers a selected recording missing from `candidate.recordings`. That is a real robustness gain over the brief's wording.
- The setlist.fm parse enters the vocabulary exactly when it would rank (only a non-empty `from_setlistfm` result), with no extra fetch.
- Each regex carries a comment naming its spec class and the near miss that bounds it, as the brief requires (placeholders.py:23-83).
- The mutation table is credible and well formed:
  - every mutant has a named predicted test;
  - the copy check's whitespace normalisation (e2) was mutated separately;
  - the two survivors found were (g) the empty-key guard and (h) the item-title guard, and both got tests.
- The handback's numbers (3383 passed = 3294 + 89) and its RED evidence are consistent with the diff's test count.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **placeholders.py:130-135, `is_placeholder_title` (plan-mandated, plan :1245).**
   - It is broader than spec 2b's scope (spec :576-577): `is_placeholder_title("42"/"FF"/"J"/"7-11"/"I-55"/"4:20")` are all True.
   - Nothing consumes it, and Task 9 composes the classes differently (plan :1419-1421).
   - Fix, cheapest first: (a) state in the docstring that this is the classes un-scoped, and that 2b judges the residue arm only on `is_real_title` titles, which is what Task 9 does; or (b) gate the residue arm on `is_real_title` inside it; or (c) drop it.
   - The human or orchestrator decides. The brief named it, so changing it is a plan amendment.
2. **gather.py:771, `corroboration: dict[...] = {}`.**
   - This is one dict shared by every `CanonicalBuild` constructed without the field.
   - Today the only construction (gather.py:860) passes a fresh dict, so nothing is shared in practice. Task 9's planned `frozenset(cb.corroboration)` (plan :1423) is read-only.
   - A later consumer that mutates `cb.corroboration` on a default-constructed instance would poison every other one.
   - Fix if wanted: `types.MappingProxyType({})` as the default with a `Mapping[str, tuple[str, ...]]` annotation, or a comment that it is read-only.
3. **Ruled-limitation scope is wider than the pin's three examples (placeholders.py:69-71).**
   - The anchored prefix `^[a-z&]+\s*\d{2,4}[-._]\d{2}[-._]\d{2,4}` consumes ANY single-word title followed by a date. Measured: `Ripple 1970-09-20`, `Drums 1977-05-08`, `Encore 12-31-99`, `Sbd`, `Aud` and `Remastered` are all `is_residue` True, and the date-suffixed ones pass `is_real_title`, so Task 9 would demote them.
   - Corroboration cannot exempt `Ripple 1970-09-20`, because its normalised form is not `ripple`.
   - This is the P5 ruling's mechanism, so it is not a defect. Checkpoint B's pre-screen should know the class is "one word + date", not "Jam + date". Consider adding `Ripple 1970-09-20` to the limitation pin so the scope is visible.
4. **Plan-mandated test nits in test_stage_gather.py `test_build_canonical_corroboration_names_setlistfm`.**
   - The assertion `any(sources == (f"lma:{M_IDENT}",) ...) or any(f"lma:{M_IDENT}" in sources ...)` is redundant: the first disjunct implies the second.
   - The mid-file `from llama.stages.gather import build_canonical` is an E402-style placement. No ruff config enforces it.
5. **Coverage gap.** No test covers the selected recording being absent from `candidate.recordings` while a sibling copies its description: the path that justifies reading `_description(meta)` at gather.py:832. A mutant that takes `chosen_desc` from the `"chosen"` parse (or `""` when there is none) would survive. Low risk; add a test if Task 9/10 relies on it.

Checks run:
- The do-not-retune grep over the diff, and `git diff --stat` over the protected modules: both clean, as above.
- One focused probe of predicate outputs in the worktree venv (`llama.__file__` confirmed inside the worktree), for flagged point (3) and Minor 3.
- Read `_collect_parses`/`_description` (gather.py:97-101, :347-367) and `is_real_title` (titles.py:140-148) for the equivalence check and point (3).
- Grepped the repo and plan for consumers of `is_placeholder_title`: none outside Task 8.
- Grepped the repo for `CanonicalBuild(` constructions: one, gather.py:860.
- The suite was not re-run.

### Assessment

**Task quality:** Approved

**Reasoning:** The predicates and the cross-source vocabulary match the brief and spec ruling 3 exactly, no protected constant moved, and the mutation work is sound. The flagged deviation (1) is the safer reading of the spec. Point (3) is answered by Task 9's `is_real_title` gate, not by corroboration. The one plan-level hazard is the unconsumed, over-broad `is_placeholder_title` (Minor 1), which is for the orchestrator or human to settle.
