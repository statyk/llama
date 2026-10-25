# t15b-fix1 handback: DONE
Commit: see git log (fix(replay): absence phrasings cover the passive, cannot, ...). Not pushed.
Changes (replay.py): not included/not listed now `(?:\bnot|n['’]t|\bcannot)\s+(?:(?:be|been|yet|being)\s+)?(?:\w+ly\s+)?included|listed\b`; not in the setlist: up to 3 intervening words, `set[\s-]?lists?|track[\s-]?lists?|track\s+listings?`; no separate track: `\b(?:no|without(?:\s+an?)?)\s+(?:separate|separately titled|own|distinct|individual|titled|dedicated|standalone|stand-alone)? tracks?`; new last term `not tracked separately`.
RED on 3855523 (24 new cases): `-k absence_wording`: 24 failed, 47 passed.
GREEN: `./.venv/bin/python -m pytest packages/llama/tests/test_replay.py -q -p no:cacheprovider`: 194 passed. Full suite: see below.
Re-measure (~/.llama-harness/piece4/ckb/15b-r1/final.txt): refused 1014/1014, 901/901; first-hit distribution unchanged. Rows hit (1014/901), sole-hit 0 for all new: not included 16/13, not listed 14/13, not in the setlist 92/83 (was 51/44), no separate track 37/31, not tracked separately 3/3, does not appear 157/138, unlisted 15/12.
5170 passed, 1 skipped, 8 deselected, 26 warnings in 41.89s
