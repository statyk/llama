# t15b-fix3 handback: DONE
Windowed (negation = not|never|n't|cannot; separators [\s,()]+; words [\w'’-]+): not present/represented/part of (3 words), not included/listed/does not appear (5 words), not in the setlist, no separate track (no|without, 3), not tracked separately (3). `not a track` and `unlisted` unchanged (not plain negation / plain word). Comment rewritten.
RED on d14e54c: 17 failed, 84 passed (-k absence_wording; one case per quoted form). First GREEN try had one failure ("not, in fact, have been included" needs 4 words), window widened to 5 for included/listed/appear.
GREEN: test_replay.py 224 passed. Full suite: see last line.
Re-measure ckb/15b-r3: refused 1014/1014, 901/901. First-hit distribution identical to r2. Rows hit (1014/901): does not appear 190/169, not included 25/20, not listed 34/31, not present 213/193, not represented 9/9, not part of 167/142, no separate track 86/76, not tracked separately 4/4; sole-hit 0 for all of them.
5200 passed, 1 skipped, 8 deselected, 26 warnings in 39.68s
