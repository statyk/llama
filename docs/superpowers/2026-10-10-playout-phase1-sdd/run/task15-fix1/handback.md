# task15-fix1 handback
Status: DONE. Commit 59feaf2 (on 6091a65). Files: antenna/src/playlist.ts, antenna/test/playlist.test.ts. Python untouched.
- IMPORTANT 1: "treats N < horizon.first as absent" now asserts #EXT-X-DISCONTINUITY 3 lines before seg/e1/100.aac.
- MINOR 2: discSeq = floor(n_fi/len) + 1 - tagsThrough, no clamp; the comment states the +1, why the clamp renumbered, RFC 8216 6.2.2, and that it is a deliberate deviation. The two floor(N/7) assertions are now +1. New test "never renumbers a segment's discontinuity across reloads early in an epoch": successive reloads cur=0..3*len+10 over 4 cases (empty horizon with len 7 and len 3; dropouts at 20/len 50 and at 2/len 3). It keys each segment by uri+PDT and asserts its effective discontinuity number never changes. Before the fix it failed with "empty, len 7: fallback/v1/1.aac @ cur=6: expected 0 to be 1".
- Test-side decision: the regression test skips null playlists. An empty horizon at the epoch (first=0, last=-1) hits the grace hold (cur - last = 1..3), so end = -1, nothing is listed, and buildPlaylist returns null for cur 0..2. That is the brief's existing behaviour (null = write nothing); no code change.
Gates: npm test 13 passed; npm run typecheck clean.
Mutants (scratch copies via git archive, run from the scratch cwd; unmutated baseline copy 13/13 green; predictions written to the log before each run, all matched):
- M1, the reviewer's mutant (switch tag only live->fallback): 1 red, "treats N < horizon.first".
- M2, the old clamp restored: 3 red (switch disc, floor+1 numbering, never-renumbers).
- M3, clamp kept with +1 outside it: 1 red, never-renumbers. The regression test alone pins the clamp.
Concern: none new. Cleanup: the scratch copies under scratchpad/mut15-* are left in place (a safety check blocked rm -rf with a variable path).
