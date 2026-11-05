# t1-impl report
Status: DONE. Implemented program_title, block_title, occurrence_spans, build_lineup, build_timeline(clock=) with block/nominal_start/program fields and "blocks", build_notes "program", $presents in show.html + render_show_page; temporary clock=IMPLICIT_CLOCK arg on publish._publish_site.
Tests: RED (impl reverted via patch): 19 failed, 94 passed in test_site.py. GREEN: 113 passed. packages/transmitter: 985 passed, 1 skipped. Full suite: 6637 passed, 1 skipped, 8 deselected.
Files: packages/transmitter/src/transmitter/site.py, publish.py, tests_transmitter/test_site.py, antenna/templates/show.html.
Debian12: not run, Docker is not running.
Concerns: none. (26 warnings in full suite are pre-existing.)
