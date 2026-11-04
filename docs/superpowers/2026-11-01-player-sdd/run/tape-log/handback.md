# Tape log rework: handback
Commits on playout-player (not merged/pushed):
- 3b70b816 tape log: tapeLog returns the on-air show first to last with played/now/next; collapsed window of 5, button, dimming, marker; spec bullet updated.
- (next commit) #now-show line under Now playing; pages.ts regenerated; spec Now playing bullet.
Results (cd antenna): npm test 523 (519 baseline: +4 net, tapeLog tests replaced 4 old with 8); typecheck clean; npm run smoke 104 (baseline 91: +11 tape log, +3 show line; 2 old tests adjusted: first-row asserts now li.now; Show all uses exact name).
Screenshots: .superpowers/polish-shots/log-{320,390,1200}-{collapsed,expanded}.png (25-song tape). Viewed 1200 expanded and 320 collapsed: cassette stays top, nothing overlaps.
Contrast: next rows #5e5240 on band #d9cbaa = 4.74:1 (on paper 5.75). First choice #62553f was 4.52, too thin.
Decisions: now bold relies on Special Elite synthetic bold (subtle), so the oxblood arrow marker carries it; expanded list grows band as accepted. CLAUDE.md has no tape-log text; unchanged.
