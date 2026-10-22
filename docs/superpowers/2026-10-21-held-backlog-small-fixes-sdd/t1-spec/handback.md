### Spec Compliance (SPEC role) — ✅ Spec compliant ; ⚠️ Cannot verify from diff: the harness acceptance for slice D ("no show gains a flag") is a later task's measurement, not this commit's.

Reviewed: task-1-brief.md, spec "Slice D" + Kickoff, global-constraints.md, implementer handback, review package bfaa837..feedc82.

### Strengths
- Every matcher the spec names is folded, on both sides:
  - `structure.fuzzy_norm_title` calls `fold_curly_apostrophes` first, before the `&` fold (structure.py:83). `title_components` and `contains_sequence` get the fold through it.
  - vet_research: `_song_tokens` is used in `_title_match` (:128), `_known_song` (:141), `right_show_gate` `research_known` (:193) and `tape_known` (:201), and `grounding_flags` `known` (:238). A grep shows no other `normalize_song` call left in vet_research.py.
  - brief: `_song_norm` is used in `song_components` (:126), `known_song`'s exact test (:163) and `briefing_guard`'s `exact` (:231). `components`, the joined-components set and `song_comma_components` all go through `song_components` or `exact`. A grep shows no other `normalize_song` call left in brief.py.
- `fold_curly_apostrophes` changes only U+2019 and U+2018 (structure.py:62). The test checks that `“` (U+201C) is not folded.
- `songs.py` has a zero-line diff, so `normalize_song` and `DEFAULT_ALIASES` are byte-identical. A (pin) test locks `normalize_song("Don’t Ease Me In") == "don t ease me in"`.
- Every test in the brief is present verbatim. I worked through each against the old code, and each fails today:
  - vet both-ways: 2 unknown songs out of 2, so it flags.
  - vet segue chain: He's Gone and Don't Ease Me In are unknown, which is 2 of 3, so it flags. `Truckin'` already matched by containment.
  - right-show gate: today asserted = 2, not 4.
  - brief both-ways and segue chain: today "don t ease me in" ≠ "dont ease me in", and `song_components` gives "he s gone".
  - test_structure.py: the module import fails.
  - The one pin is marked.
- The CLAUDE.md clause matches the brief word for word. The commit message has the test command and result, and the orchestrator's trailer.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
- CLAUDE.md:778: the new clause was put on one line of about 230 characters inside a paragraph wrapped at about 80. It renders the same, but it breaks the file's wrapping. Fix: re-wrap the line. (Formatting only.)
- packages/llama/tests/test_structure.py:2077: the new imports (`contains_sequence`, `fold_curly_apostrophes`) were added mid-file with `# noqa: E402`. The brief's snippet shows them at the top. This file already uses scattered imports, so it is consistent with local style. (Code-quality lane; noted only.)

### Assessment
**Task quality:** Approved
**Reasoning:** The diff folds exactly U+2019/U+2018 at every matcher the spec lists, on both sides of each comparison. `normalize_song` and `DEFAULT_ALIASES` are untouched. Every test the brief requires is present and fails on the pre-change code.
