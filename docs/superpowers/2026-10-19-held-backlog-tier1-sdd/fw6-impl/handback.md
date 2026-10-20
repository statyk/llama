# fw6 handback

Status: DONE. Commit 3c75471 `feat(titles): strip a hyphen/underscore-joined track number on enumerated tapes (fw6)`.
Suite: `./.venv/bin/python -m pytest -q` -> 3780 passed, 1 skipped, 8 deselected (was 3762; +18).

## Changes
- titles.py: `_JOINED_NUM_PREFIX = re.compile(r"^\d{1,3}[-_](?=[^\d\s])")` with a comment block; its own vote in `clean_tag_titles` after the spaced and glued passes (same voters/gate_basis, same constants); no footnote-tail strip. Protected predicates/constants untouched.
- gather.py: note `stripped joined track number: track {i + 1} '{raw}' -> '{tag_titles[i]}'` beside 2c's (tag_source == "tags" only, never an overridden position); import added.
- scripts/replay_holds.py: family `("2d", "stripped joined track number:")`.
- Scope: clean_tag_titles is called only on tag titles (gather's tag_layer / sibling-format recovery); override, setlist and sibling-align text do not pass through it (grep confirmed).
- Tests: test_titles.py (6 new: hyphen tape incl `22-I Know You Rider`/unnumbered `Bertha`, underscore tape, `01-200 More Miles` left as-is (false negative, named), vote-passes negative with 1922/2001/4-20/24-7 Spyz/1-800-Suicide, 2-of-10, M80/7-Up non-enumerated); test_stage_gather.py (2: RRE fixture rewritten to `NN-Title` -> 23 verbatim notes; none under format recovery).

## Mutation table (fresh rsync copies, PYTHONPATH + private PYTHONPYCACHEPREFIX, shadowing proved: llama.__file__ under the copy each time)
| mutant | predicted | caught by |
|---|---|---|
| M1 lookahead `(?=\S)` | never_touches_numeric_titles (4-20/24-7) | test_joined_strip_never_touches_numeric_titles_when_the_vote_passes (+ the digit-remainder test) |
| M2 drop `_` | underscore tape test | test_joined_strip_removes_underscore_numbers |
| M3 no vote | 2-of-10 test | test_joined_strip_vote_fails_on_two_of_ten (+ m80_and_7_up) |
| M4 drop count=1 | equivalent (^ anchor) | SURVIVED, equivalent: `^` can match only at position 0 |
| M5 lookahead `[A-Z][a-z]` | 22-I Know You Rider row | test_joined_strip_removes_hyphen_numbers_and_leaves_unnumbered_titles |

## Cache census (13,339 md_*.json read-only; filter_files per audio format, new vs same code with the joined pattern disabled)
8 distinct items (12 item-format rows) change; no item hit by gather's note differently.
- BL2014-04-20.matrix [mp3] 13/16: `01-Trying to Start Out Clean`->`Trying to Start Out Clean`; `03-Two Hearts Down`->`Two Hearts Down`; `04-Good Morning Mama`->`Good Morning Mama`
- DSO2009-07-18.VasaParkAKG391FOB.FLAC_478 [mp3, flac] 24/28 each: `02-Bertha--]`->`Bertha--]`; `03-Good Lovin`->`Good Lovin`; `04-Brown Eyed Women`->`Brown Eyed Women`
- DSO2012-05-19 [mp3, flac] 21/23: `01-Hell In A Bucket`->`Hell In A Bucket`; `03-Walkin' Blues`->`Walkin' Blues`; `04-Ramble On Rose`->`Ramble On Rose`
- MountainGoats2012-06-27 [mp3] 27/31: `01-Pure Milk (partial)`->`Pure Milk (partial)`; `02-Dinu Lipatti's Bones`; `03-Intro to Stars Around Her`
- TheDead2009-04-29.TheDead04-29-2009AKG391OTS [mp3, flac] 16/20: `101-touch of grey`->`touch of grey`; `102-Pride Of cucamonga`->`Pride Of cucamonga`; `103-Crazy Fingers`->`Crazy Fingers`
- rhd2008-06-20.mk4 [mp3, flac] 13/13: `01-Long Tall Sally`->`Long Tall Sally`; `02-I'm On To You`; `03-Altar Junkie`
- tmg2017-06-02 [mp3] 45/45: `01_The Goats Take The Stage At The Fillmore`->`The Goats Take The Stage At The Fillmore`; `02_The Grey King and the Silver Flame Attunement`; `03_Rain in Soho`
- tmg2019-05-08 [mp3] 31/37: `06_In League with Dragons`->`In League with Dragons`; `08_Sax Rohmer #1`->`Sax Rohmer #1`; `10_Wear Black`->`Wear Black`

Closest calls (remainder <= 3 chars or non-letter start): 23, all in tmg2017-06-02 / tmg2019-05-08, all banter/applause annotation tracks such as `08_(Banter) There are people...`->`(Banter) There are...`, `11_[banter]`->`[banter]`, `28_[applause]`->`[applause]`, `40_(Applause) Encore Break 2`. The number is correctly removed; these are non-song tracks that were never real titles. None looks like a destroyed real title. Observations (not tuned): `02-Bertha--]` keeps a pre-existing `--]` tail; `TheDead` numbers are disc-track `101`-style (stripped, correct). Census data in the log.

## Fix round 1 (commit 33f44b4)
Suite: 3786 passed, 1 skipped, 8 deselected.
- I1: recovery test now sets mp3 tags to `NN-x` (unusable) so recovery fires; asserts track 1 is `Pig In A Pen` / `sibling-format` and no joined note.
- I2: 2c RRE test asserts no `stripped joined track number:` note.
- m1: comment corrected (mandatory `[-_]` keeps bare 1922/2001 out; `\d{1,3}` keeps `2001-A Space Odyssey` out; lookahead keeps 4-20/1-800/24-7). Added `2001-A Space Odyssey` row to the passing-vote negative test (now 40 of 46 voters).
- m2: one-line accepted-loss note (`7-Up`-style on an enumerated tape; 0 in the 13,339-item cache).
- m3: correction to my earlier scope claim: sibling-align donor tag titles DO pass through `clean_tag_titles` (gather.py, correspondence.py:310); this is the same reach 2c already has. Override and setlist text still do not.
| mutant | predicted | caught by |
|---|---|---|
| M7 drop `.match(raw)` from note condition | 2c RRE test | test_2c_strips_railroad_earths_glued_numbers_and_notes_each |
| M8 `tag_source == "tags"` -> True | recovery test | test_2d_notes_nothing_under_format_recovery (my first batch attempt garbled the multi-line mutant; re-run singly on the correct mutant) |
| M9 `\d{1,3}` -> `\d+` | 4-digit row | test_joined_strip_never_touches_numeric_titles_when_the_vote_passes |
