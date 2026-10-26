# task1-fix1 handback
Status: DONE
I1: test_publish interstitial test now has show at seg 100 (4 segs) and interstitial at 104, publishing 100..109. Mutant (scratch copy, shadowing proven via transmitter.__file__ in scratch): removing the _publish_site guard -> test FAILS (1 failed); removing the build_timeline guard -> publish test still passes (the _publish_site guard shields it) but test_site::test_timeline_lists_no_interstitial_rows FAILS (see log). Unmutated: passes.
I2: PlanRow.to_json writes phase-1 fields always, scheduler fields only when != default, then extra. New tests: phase-1 row serialises to exactly 8 keys; read_plan+write_plan leaves a phase-1 file byte-identical. Runbook subsection rewritten per R5.
Full suite: 588 passed, 1 skipped.
