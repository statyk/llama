# t15b-impl handback: DONE_WITH_CONCERNS (minor)
Commits: 3c3f218 feat(replay) (gate), 3855523 test(junk) (NFA pin). Not pushed.

## Part A (replay.py, appended after `track count`, order preserved)
- not included: `(?:\bnot|n['’]t)\s+(?:(?:been|yet|being)\s+)?included\b`
- not listed:   same with `listed`
- does not appear: `(?:\bnot|n['’]t)\s+appear(?:s|ed|ing)?\b`
- unlisted: `\bunlisted\b`
- not in the setlist (controller scope change): `(?:\bnot|n['’]t)\s+(?:in|on)\s+(?:the\s+|this\s+|that\s+|its\s+)?(?:set\s?list|track\s?list(?:ing)?)\b`
- no separate track: `\bno\s+(?:(?:separate|own|distinct|individual|titled)\s+)?tracks?\b`
Plus the one-line comment on raw vs normalized scanning in `briefing_reusable`.
Tests: 27 new parametrized cases in test_each_absence_wording_refuses (contractions incl. curly apostrophe, not been, do/did/don't/didn't, not appearing, set list/track list/tracklist/track listing, on/in, no track of their own/its own, no tracks).
RED: first batch (4 terms) `-k absence_wording`: 15 failed, 20 passed. Second batch (2 terms): 12 failed, 35 passed. GREEN: test_replay.py 170 passed.
Note: "not part of the setlist" is caught earlier by existing `not part of` (order unchanged), so not a case.

## Part B
`test_a_not_fade_away_crowd_chant_is_kept_operator_ruling` (2 params: `Not Fade Away Chant`, `Crowd Doing Not Fade Away`), asserts short_tag_is_junk False and file kept via filter_files, excluded == [], short_kept named. Docstring quotes ruling 2. junk.py untouched.
Mutant (scratch copy via git ls-files|tar, llama.__file__ verified in scratch; NONPERF += `|\bnot\s+fade\s+away\b`; predicted: both params of the new pin fail): new pin failed for both params as predicted; also failed test_deny_vocabulary_corpus and test_ruling2_keep_cases_stay_kept[Not Fade Away] (plain "Not Fade Away" tag also hit, expected side effect of that mutant). 4 failed, 82 passed.

## Part C re-measure (~/.llama-harness/piece4/ckb/15b/final.txt, final_15b.py, same 15a dump)
Refused 1014/1014, 901/901; still reusable 0 (unchanged: 15a already refused all).
Per new term (rows of 1014 / of 901; only-hit): not included 15/12; not listed 14/13; does not appear 157/138; unlisted 15/12; not in the setlist 51/44; no separate track 37/31. Only-hit = 0 for every new term (so they change no outcome today).
First-hit distribution unchanged (names 406, excluded 389, implausibly short 133, left out 49, too short 25, track count 5, absent 3, not part of 2, missing 1, not present 1).
(Only-hit counts for older terms shifted slightly because the new terms now co-fire: excluded 5->3, left out 5->3, track count 5->1.)

## Suite
`./.venv/bin/python -m pytest -q -p no:cacheprovider`: 5146 passed, 1 skipped, 8 deselected (baseline 5117 + 29 new cases: 27 wording + 2 NFA).

## Concerns
None blocking. `does not appear` is broad (157 rows) by design; `no track`/`not appear` can over-refuse, which only costs a brief.
