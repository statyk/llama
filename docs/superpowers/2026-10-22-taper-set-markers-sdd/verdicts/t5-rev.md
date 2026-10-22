# t5-rev handback: DONE (review of f4c7a84..3cccc05)

### Spec Compliance

- ✅ Spec compliant (spec §5 and the Task 5 brief).
  - The tripwire gate is `taper_owned or alignment != "jerrybase"` (gather.py:1603). That is exactly the spec's skip condition (not owned AND alignment is jerrybase), so the decision rests on ownership plus mechanism and never on the `alignment` string alone. Mutants: reverting the gate to the old `alignment != "jerrybase"` is CAUGHT by `test_tripwire_runs_on_owned_show_agreeing_with_anchoring`. Making the tripwire always run is CAUGHT by the pin `test_tripwire_skipped_when_numbered_breaks_came_from_anchoring`.
  - The closer is compared against the taper's TEXT items: `songs = [i.title for i in taper.items if i.set == st.name]` and then `songs[-1]` (gather.py:~118). That is "the taper's own last song" as the spec puts it, and it does not use placed tracks. `TaperText.items` holds only non-filler songs (taper.py:140), so the last item is the last song.
  - The mapping is by set name: jerrybase "1".."3" maps to the taper's same label, and "encore" maps to the taper's "encore". If the taper has no such set, the song list is empty and the flag becomes a note. Jerrybase's last numbered set maps to its own number, never to the taper's last set, which fits the spec's "last numbered means jerrybase's last" clause.
  - Duplicate closers (my reasoning, checked against jerrybase.py:300-316): `closer_contradictions` emits hard flags in `event.sets` order, at most one per set. Whether a set is flagged depends only on the closer string and the tracks. So two sets with the same closer are either both flagged or both unflagged, and consuming sets in order maps each flag to its own set. Mapping is correct.
  - Closers matched only partially: the flag text uses `st.closer` verbatim, so the exact-string match on the regex group is sound. The anchored `(.*)` also handles closers that contain `'`.
  - Set count: `taper_n` excludes "encore" and so does `jb_n` (gather.py:~103-104). Scratch probe: taper with 2 sets plus an encore against jerrybase with 3 numbered sets correctly gives a note and no flag.
  - Notes go to `op_notes` (gather.py:1608, 1631) and never to `conflicts`. The test asserts that conflicts do not get the count note. The fixed strings match the plan exactly.
  - Shows the taper does not own are untouched: the helper is only called under `taper_owned`.
- Soft "not found in tracks" notes still go to `notes`, as today. I checked whether this is newly reachable on an owned show whose step 1 was anchored. It is not: `anchor_breaks` succeeds only when every closer matched (jerrybase.py:236-262), so no soft note can arise there.
- Constraints: `git diff main -- packages/llama/src/llama/setlist.py` is empty (0 lines). Grepping the diff's +/- lines for every protected name and do-not-retune constant finds nothing. jerrybase.py and structure.py are untouched. No existing test line is removed or changed.

### Strengths
- The gate condition is spelled as the spec's own predicate, and the comment says why (gather.py:1600-1603).
- The helper is pure, small, and documented. Order-consuming the flags by closer string gets the mapping right without touching the protected `closer_contradictions`.
- The count demotion runs only on the jerrybase set-count flag (gather.py:1628), so the `structure_guard` fallbacks are left alone.
- Mutants run in a scratch copy (import of the copy proven, `PYTHONDONTWRITEBYTECODE=1`, prediction stated first), against test_stage_gather.py and test_taper.py (517 tests):
  - CAUGHT, as predicted: M1 (`agrees = True`), M7 (old gate), M8 (always run), M10 (closer notes sent to `notes`/conflicts), and M11 (count flag kept hard).

### Issues

#### Critical
None.

#### Important
None.

#### Minor
1. **The encore exclusion in the taper's set count is not pinned** (gather.py:~103, `taper_n` excluding encore). Mutant M5, which counts the encore, SURVIVES the full gather and taper files. Through gather it is observable: taper with 2 sets plus an encore against jerrybase `("Charlie","1"),("Echo","2"),("Foxtrot","3")`.
   - Real code: no count flag, and the note `structure has 2 sets but jerrybase shows 3 (taper's markers)`.
   - M5: the hard flag `structure has 2 sets but jerrybase shows 3` stays.
   - I ran this probe test in the scratch copy: it passes on HEAD and fails on M5.
   - Fix: add it as a test. This is the case the orchestrator asked about.
2. **Mapping by set number is not pinned** (gather.py:~116-120). Mutant M2 compares the closer against the last song of ANY taper set and SURVIVES. Every behavioural test uses a closer that ends no taper set. Through gather a difference is nearly unreachable: a closer equal to the taper's set-j last song sits at break j by placement. So pin it directly on the helper. Probe, passing on HEAD: jerrybase `("Foxtrot","1"),("Golf","2")`, TP_DESC, flag for 'Foxtrot', expect a note.
3. **Fuzzy song matching is not pinned** (gather.py:~119). Mutant M6 (raw `songs[-1] == st.closer`) SURVIVES, because every test uses identical strings. Fix: one helper test where the taper text differs only in case, `&`/`and`, or a dropped subtitle from jerrybase's closer, and the flag stays hard.
4. **Consuming duplicate closers in order is not pinned** (gather.py:~110-115, `n not in used`). Mutant M3 SURVIVES. The behaviour is correct by reasoning (see above), and a duplicate closer across sets is rare. An optional direct helper test would pin it.
5. **The test that the closer flag stays hard on agreement is weak** (test_stage_gather.py:3671). `hard = [flag]; assert flag in hard` is tautological. Worse, `kept == [flag]` also holds when `_CLOSER_FLAG` fails to parse the flag, because an unparsed flag is kept. So the test cannot tell "agreed" from "not recognised". Other tests do catch drift in the regex or the wording, so the suite as a whole is fine.
   - Fix: build the input flag from `jerrybase.closer_contradictions` on a small track list, or add a control in the same test that disagrees on the same flag and expects a note.
   - The brief asked for "first asserts the input list really contains the flag". Taken literally against a synthetic list, that instruction is the tautology.
6. **Cosmetic** (gather.py:91, gather.py:17):
   - The parameter `taper` shadows the module `llama.taper` inside the helper. It is harmless now, because the annotation is a string and the body does not use the module.
   - `TaperText` could be imported beside `TaperDecision` and annotated directly.
   - `JerrybaseEvent` is inserted out of alphabetical order in the models import.
7. **The helper is the only parser of `closer_contradictions`' flag wording** (gather.py:87). If that wording changes, the failure is safe: flags stay hard. Today's gather tests would catch the change. This needs no action beyond keeping that in mind.

### Assessment

**Spec:** ✅
**Task quality:** Approved

**Reasoning:** The behaviour matches §5 exactly: the gate, the text-based last song, mapping by number including the encore, encore-excluded counts, and notes going only to `op_notes`. All constraints hold. The gaps are in test strength, not correctness: four surviving mutants (M2, M3, M5, M6) on edges the tests don't reach. M5 is the one worth a follow-up test, since it is reachable through gather.

Checks run: 10 mutants in a scratch copy (`git archive 3cccc05`, cwd scratch, PYTHONPATH shadowing proven via `llama.__file__`), plus 2 probe tests. All scratch copies removed afterwards. No repo edits and no commits.
Status: DONE
