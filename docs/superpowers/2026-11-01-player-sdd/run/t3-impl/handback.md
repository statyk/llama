Status: DONE
Commit: d77fa889 antenna: pure timeline helpers for the new player
Tests: cd antenna && npm test && npm run typecheck -> 22 files / 444 tests pass, tsc clean.
Files: antenna/public/assets/timeline.js (new), antenna/test/timeline.test.ts (new, 18 tests). nowplaying.js untouched.
Notes:
- TDD: I wrote the module and tests together; no separate RED run was captured (not demonstrated).
- First commit had a typecheck error (implicit any in tests); fixed and amended before reporting. Final commit is green.
- longGeneric worked in the Workers test runtime ("Eastern Time"); no formatter injection needed.
- tapeLog considers all shows with start <= atMs (newest first), not only the current one; comingUp = start > atMs; justAired = end <= atMs.
- tidyTitle only touches a trailing segue mark (">" / "->" / "-->" -> " >").
Concerns: none.

## Fix round 1
Commit: see below. Test-only; timeline.js unchanged.
- Fixture `recent` entry now has a track file "wrong"; tapeLog asserted with exact toEqual at a time past its end; new justAired test (object-shaped and real slug-list `recent: ["prev-1"]`); tapeLog also checked with the slug-list shape.
- Mutant (scratch copy, own tree, no shared caches): showsOf concatenates object entries of timeline.recent. Predicted red: tapeLog "ignores recent", justAired "ignores recent". Result: CAUGHT, 4 failed / 15 passed (those two plus two comingUp/null tests that share showsOf).
- Real tree: vitest timeline 19 passed; full `npm test` 444+1 pass, typecheck clean.
