# t2-impl report
Status: DONE_WITH_CONCERNS (Docker down; debian12 gate not run).
Implemented: LINEUP_KEY/LINEUP_CACHE, PublishState.lineup, _publish_site loads live_clock(save=False) (temp clock param removed), sets show["program"] from manifest before the unchanged-notes continue, lineup PUT after timeline only on digest change, non-budget errors logged "lineup step failed" and old digest kept; digest threaded into publish_batch state save. CLAUDE.md sentence added. Updated existing put-order/state-equality tests.
RED: 7 failed/49 passed of test_publish.py before implementation (missing program, lineup PUT, state.lineup). GREEN: full suite 6646 passed, 1 skipped.
