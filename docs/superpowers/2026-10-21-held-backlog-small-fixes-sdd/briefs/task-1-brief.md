### Task 1: Slice D, the curly-apostrophe fold at the matching layer

**Files:**
- Modify: `packages/llama/src/llama/structure.py` (new `fold_curly_apostrophes`, used by `fuzzy_norm_title`)
- Modify: `packages/llama/src/llama/stages/vet_research.py` (`_title_match`, `_known_song`, `right_show_gate`'s `research_known`/`tape_known`, `grounding_flags`' `known`)
- Modify: `packages/llama/src/llama/stages/brief.py` (`song_components`, `known_song`'s exact test, `briefing_guard`'s `exact` builder)
- Modify: `CLAUDE.md` (one clause in the fuzzy-matching paragraph)
- Test: `packages/llama/tests/test_structure.py`, `test_stage_vet.py`, `test_stage_brief.py`

**Interfaces:**
- Produces: `structure.fold_curly_apostrophes(text: str) -> str`, which returns `text` with `"’"` and `"‘"` replaced by `"'"` and nothing else changed. Task 2 does not use it. The harness picks it up through `fuzzy_norm_title`.

- [ ] **Step 1: Write the failing tests**

`test_structure.py`:
```python
from llama.songs import normalize_song
from llama.structure import contains_sequence, fold_curly_apostrophes, fuzzy_norm_title

def test_fuzzy_norm_title_folds_curly_apostrophes():
    assert fuzzy_norm_title("Don’t Ease Me In") == fuzzy_norm_title("Don't Ease Me In")
    assert fuzzy_norm_title("‘Round And Round") == fuzzy_norm_title("'Round And Round")
    assert fold_curly_apostrophes("a’b‘c“d") == "a'b'c“d"   # only the two

def test_normalize_song_still_splits_on_a_curly_apostrophe():   # (pin) the strict list
    assert normalize_song("Don’t Ease Me In") == "don t ease me in"

def test_contains_sequence_matches_a_curly_description():
    assert contains_sequence("Bertha &gt; Don’t Ease Me In", ["Don't Ease Me In"])
```

`test_stage_vet.py` (uses `grounding_flags`, `right_show_gate`, `ResearchVetting`, `Show`, `Track`):
```python
def _curly_show(titles):
    return Show(performance_id="GratefulDead/1973-06-10", identifier="gd73", artist="Grateful Dead",
                date="1973-06-10", tracks=[Track(index=i, set="1", title=t, filename=f"t{i}.mp3",
                                                 title_source="tags") for i, t in enumerate(titles, 1)])

@pytest.mark.parametrize("tape,research", [
    (["He’s Gone", "Don’t Ease Me In"], ["He's Gone", "Don't Ease Me In"]),   # curly on tape
    (["He's Gone", "Don't Ease Me In"], ["He’s Gone", "Don’t Ease Me In"]),   # curly in research
])
def test_vet_matches_curly_and_straight_apostrophes_both_ways(tape, research):
    v = ResearchVetting(asserted_songs=research, asserted_dates=["1973-06-10"], context="")
    flags, _, _ = grounding_flags(v, _curly_show(tape))
    assert not any("unknown song" in f for f in flags)

def test_vet_folds_curly_apostrophes_in_a_tape_segue_chain():
    # two unknowns today (He's Gone, Don't Ease Me In) of three asserted -> flagged today
    v = ResearchVetting(asserted_songs=["He's Gone", "Don't Ease Me In", "Truckin'"], asserted_dates=[], context="")
    flags, _, _ = grounding_flags(v, _curly_show(["He’s Gone > Truckin’", "Don’t Ease Me In"]))
    assert not any("unknown song" in f for f in flags)

def test_right_show_gate_counts_a_curly_tape_title_as_asserted():
    tape = ["He’s Gone", "Don’t Ease Me In", "Truckin’", "Sugar Magnolia"]
    v = ResearchVetting(asserted_songs=["He's Gone", "Don't Ease Me In", "Truckin'", "Sugar Magnolia"],
                        asserted_dates=["1973-06-10"], context="")
    _, info = right_show_gate(v, _curly_show(tape), date_flags_raw=[])
    assert info["asserted"] == 4 and info["unknown"] == []
```

`test_stage_brief.py` (uses the file's `_briefing`, `Show`, `Track`):
```python
def _tape(*titles):
    return Show(performance_id="GratefulDead/1973-06-10", identifier="gd73", artist="Grateful Dead",
                date="1973-06-10", tracks=[Track(index=i, set="1", title=t, filename=f"t{i}.mp3",
                                                 title_source="tags") for i, t in enumerate(titles, 1)])

@pytest.mark.parametrize("track,mention", [("Don’t Ease Me In", "Don't Ease Me In"),
                                           ("Don't Ease Me In", "Don’t Ease Me In")])
def test_guard_matches_curly_and_straight_apostrophes_both_ways(track, mention):
    problems = briefing_guard(_briefing(per_set={"1": ["x"]}, mentioned_songs=[mention]), _tape(track))
    assert not any("unknown song" in p for p in problems)

def test_guard_folds_curly_apostrophes_inside_segue_chains():
    problems = briefing_guard(_briefing(per_set={"1": ["x"]}, mentioned_songs=["He's Gone", "Truckin'"]),
                              _tape("He’s Gone > Truckin’"))   # today: "he s gone" != "hes gone"
    assert not any("unknown song" in p for p in problems)
    assert song_components("E: He’s Gone >") == ["hes gone"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_structure.py packages/llama/tests/test_stage_vet.py packages/llama/tests/test_stage_brief.py -q -k "curly or apostroph"`
Expected: FAIL. `fold_curly_apostrophes` is not defined, and the vet/brief cases report unknown songs. The `normalize_song` pin passes.

- [ ] **Step 3: Implement**

- In `structure.py`, add `fold_curly_apostrophes` and call it first in `fuzzy_norm_title`: `norm_title(fold_curly_apostrophes(title).replace("&", " and "))`. Extend the docstring by one sentence: the curly fold lives here for the same reason the `&` fold does. `title_components` and `contains_sequence` inherit the fold through `fuzzy_norm_title`, and both sides of `contains_sequence` already pass through it.
- In `vet_research.py`, add a module-local `_song_tokens(name: str) -> list[str]` that returns `normalize_song(fold_curly_apostrophes(name)).split()`. Replace every `normalize_song(x).split()` in `_title_match`, `_known_song`, `right_show_gate` (`research_known`, `tape_known`) and `grounding_flags` (`known`) with it. Import `fold_curly_apostrophes` from `llama.structure`.
- In `brief.py`, add a module-local `_song_norm(s: str) -> str` that returns `normalize_song(fold_curly_apostrophes(s))`. Use it in `song_components` (per part), in `known_song`'s exact test, and in `briefing_guard`'s `exact` set. The `components` builders reach it through `song_components`.
- In `CLAUDE.md`'s "`align()` matches fuzzily" paragraph, after "folding `&`→`and`", add: "and curly apostrophes (`’`/`‘`) to `'` (`structure.fold_curly_apostrophes`, also applied by vet_research's and brief's song matchers on both sides)". The sentence that says `normalize_song` stays untouched still holds.

- [ ] **Step 4: Run the targeted tests, then the full suite**

Run: the Step 2 command, then `./.venv/bin/python -m pytest -q`
Expected: PASS, and the full suite is green.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/src/llama/stages/vet_research.py packages/llama/src/llama/stages/brief.py packages/llama/tests/test_structure.py packages/llama/tests/test_stage_vet.py packages/llama/tests/test_stage_brief.py CLAUDE.md
git commit -m "feat(match): fold curly apostrophes at the matching layer (slice D)"
```

---

