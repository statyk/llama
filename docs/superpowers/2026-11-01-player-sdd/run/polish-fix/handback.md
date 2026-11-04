# polish-fix handback
Commits (branch playout-player, on 25028832, not pushed/merged):
- 3551b10e player polish: items 1-5 (smoke.pw.mjs, radio.css, spec line)
- aacf9d84 regenerated cassette-512/og, icon-180/192 (make-art: alignSelf center, waitUntil load)
Tests (from antenna/): npm test 519 passed; npm run typecheck clean; npm run smoke 76 passed (3.5m; includes 320/390/1200 shape tests with window-in-label assertion and label-to-window gap). npm test includes the pages freshness check.
Notes: item 1 not mutation-checked (reasoned: window listener fires after document, so defaultPrevented is now seen). .now-notes is hidden in the fixture's empty state so its spacing was not visible in screenshots; padding is the existing inline-block. Fallback block appended at end of radio.css; spec line added after the cassette proportions sentence. PNGs viewed: centred, whole, only "LMA Radio / ON THE AIR" text. Shots: .superpowers/polish-shots/cassette-320.png, cassette-390.png (gitignored). A stray duplicate smoke run was stopped.
