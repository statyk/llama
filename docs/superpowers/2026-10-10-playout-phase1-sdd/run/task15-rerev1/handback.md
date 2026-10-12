## task15-rerev1 (6091a65..59feaf2)
- **Important 1 (pin the fallback→live EXT-X-DISCONTINUITY): ADDRESSED.** The new assertion is at `antenna/test/playlist.test.ts:69-71`. I re-ran my mutant from the first review (switch tag fires only on live→fallback) in a scratch copy of 59feaf2. Predicted: "treats N < horizon.first as absent" goes red alone. Result: exactly that test failed (1 failed, 12 passed), so the mutant is now killed.
- **Minor 2 (the +1 numbering): ADDRESSED.**
  - `playlist.ts:94` is `floor(n_fi/len) + 1 - tagsThrough`, with no clamp. It cannot go negative, because only live entries come before `fi`, so `tagsThrough ≤ 1`.
  - The comment at `:81-89` records this as a deliberate deviation and cites RFC 8216 §6.2.2.
  - Both `+1` assertions are present (`test:59`, `test:87`).
  - The new regression test is at `test:96-117`.
  - I re-ran my probe on 59feaf2 over cur 0..30 to 0..80. It found no renumbering and no negative sequence in any of the five original scenarios: empty horizon with len 7, 3 and 1, and dropouts with len 7 and len 50.
- **Skipping null playlists (`test:108`) hides nothing.** A renumbering needs a segment listed in two playlists, so a playlist that is not written cannot contain one. The probe confirms the null results occur only at cur 0..2 over an empty horizon at the epoch. That is the brief's grace hold over `last = -1`, and it means nothing is written.
- **New breakage in the fix diff:** none. Keying segments by `uri+pdt` (`test:110-111`) identifies each grid slot correctly.
- **Out of scope, as expected:** the probe still renumbers segments on a live↔fallback transition (with first=4: at the fallback→live window going pure-live, and on the later dropout). That is the spec-accepted pure-live restart at 0, not the clamp.
- Scratch copy removed; probe and mutant output are in `task15-rerev1.log`.

Verdict: Approved
