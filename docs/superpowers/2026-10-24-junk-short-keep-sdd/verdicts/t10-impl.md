# t10-impl report: DONE (Sonnet)

Commit: cbd35c5 "fix: apply Checkpoint A rulings ..." (on held-backlog-junk-filter). Step 2 (cand-a2.json) left to the orchestrator.

Changes
- junk.py: NONPERF gains closing|exit|outro music, over/on (the) PA, case-sensitive call sign via scoped (?-i:[KW][A-Z]{2,3}) + qualifier (incl. wrap\w*), host #N. _apply_short_rule first loop skips zero-duration (`or not e["duration_sec"]`). Nothing else in junk.py touched.
- tests: new ruling tests in test_short_keep_rule.py (6 library tags + closing/exit/outro/KDHX ID/WXRT-FM drop; Ardmore PA, WAR, NFA, Terrapin, Intro, Band Intro, Stage Banter, lowercase `kdhx intro`/`wake intro` kept; zero-length stub dropped, 4 s file still kept). Shown failing first (12 failed), then green.
- Dry run (existing tests whose expectation changes): only test_deny_vocabulary_corpus (ruling 2, 6 fixture rows keep -> drop-nonperf; counts 2822/685 -> 2816/691). No existing test uses zero-length files; none else changed. Full suite confirmed no other change.
- Spec 2.3 (code block + two bullets) and section 7 (very short files ~6 -> ~3, sibling crowd/tuning limitation, doubled _vbr follow-up) edited, each marked "(Checkpoint A ruling, 2026-10-24)".

Corpus re-measure over all 3,547 r1_files.jsonl rows (old HEAD junk vs new; scratch t10/remeasure.py): 11 rows differ, 9 are decision changes:
- Ruling 1 keep -> drop: bluegroundundergrass-2008-04-04 trk04 (kind music), gratefuldead-1973-10-29 gd73-10-29d2t01_vbr (music), gratefuldead-1974-09-11 gd74-09-11v3d2t03_vbr (music).
- Ruling 2 keep -> drop: guster-2006-07-28 WXRT Intro (spoken), joerussosalmostdead-2020-02-21 Played over PA (music-fragment), railroadearth-2006-02-18 on PA (music), theotherones-2002-08-03 d2t03 (spoken), d2t14 HOST #12 (census kind music), d4t08 (spoken).
- Two more rows (giantsand-1996-02-03 blank, gratefuldead-1991-04-05 Tuning) flip junk -> zero-drop: both already dropped, no decision change.
No other row changed.

Tests: ./.venv/bin/python -m pytest -q -> 5012 passed, 1 skipped, 8 deselected (77 s).

Concerns: the brief's "no row of census kind song/music/segue/fragment may newly drop" is literally tripped by the census labels on the named rows (music/music-fragment on 3 ruling-2 rows and 3 ruling-1 stubs), but these are exactly the rows the rulings name (PA playback, PA celebration, HOST #12 intermission, audio-less stubs); no other music-kind row changed. Orchestrator should be aware when citing "0 music lost".
