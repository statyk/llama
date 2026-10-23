# c1n-fix1 handback
Status: DONE. Commit 5c8a6d1 test(lossless_titles): pin C-1's count to signature positions (test file only).
New test: test_c1_counts_confirmed_signature_positions_not_any_c_change (signature {2,3}, only track 2 C2-confirmed, track 5 C2 at a non-signature position; changed == {1,4}; demoted == (), track 4 'Big River' still ships, no shifted note).
HEAD: focused run 38 passed (test_lossless_titles.py).
Mutant (scratch copy under scratchpad/c1nfix1, llama.__file__ proven under scratch, PYTHONDONTWRITEBYTECODE=1): line 248 -> 'if len(delivered_shift) >= 2 and len(changed) >= 2:' -> '1 failed, 37 passed'; the only failure is the new test (assert at test_lossless_titles.py:569, demoted contained 2 extra items).
Full suite: 4788 passed, 1 skipped, 8 deselected, 26 warnings in 71.83s.
Judgement calls: none.
