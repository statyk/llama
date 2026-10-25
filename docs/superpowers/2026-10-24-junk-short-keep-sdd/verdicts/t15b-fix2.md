# t15b-fix2 handback: DONE
Terms keep names/positions; comment rewritten. Patterns: not included/listed `(?:\bnot|n['’]t|\bcannot)(?:\s+[\w'’-]+){0,3}?\s+included|listed\b`; not in the setlist `...(?:in|on)\s+(?:word\s+){0,3}?(?:set|track)[\s-]?list(?:ing)?s?\b`; no separate track `\b(?:no|without)\s+(?:word\s+){0,3}?tracks?\b`; not tracked separately `(?:\bnot|n['’]t)\s+(?:word\s+){0,2}?tracked\b`.
RED on ea664f3: 13 failed, 71 passed (-k absence_wording). GREEN: test_replay.py 207 passed. 
Re-measure (ckb/15b-r2): refused 1014/1014, 901/901; first-hit distribution unchanged; sole-hit 0 for all new terms. Rows hit 1014/901: not included 23/19, not listed 26/23, not in the setlist 92/83, no separate track 80/70, not tracked separately 4/4.
5183 passed, 1 skipped, 8 deselected, 26 warnings in 40.05s
