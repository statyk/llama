Task 12 done. nowPlayingText(np, timelineLoaded, stationName="llama radio") returns stationName when loaded with no show; player.js:161 passes document.title (index.html title is "llama radio").
TDD: RED = "expected 'We'll be back shortly.' to be 'llama radio'" (1 failed/425). GREEN: cd antenna && npm test -> 426 passed; build-pages --check passed, pages.ts unchanged.
Off-air check: nowPlayingText is called only at player.js:161 (timeline tick). All off-air paths go through offAir(text) (player.js:43; callers 73,77,82,87,92,94,147) with their own text; hlsErrorNotice (76) and classifyProbe (147) feed offAir, never nowPlayingText. offair.html is a separate page.
Files: antenna/public/nowplaying.js, antenna/public/player.js, antenna/test/nowplaying.test.ts.
Concerns: none; the 'Reconnecting...' stalled branch (player.js ~155) untouched.
