# task10-rev: Task 10 + task9-fix3 review (98ae05a..afccbc8)

### Spec Compliance
- ✅ Spec compliant. site.py, antenna/templates/show.html and test_site.py match the brief's Steps 1/2/4 listings verbatim (I compared the diff to brief lines 22-321). All Produces symbols are present with the briefed signatures. Template placeholders are exactly the 11 listed. The scope constraint holds: no llama/emcee/herder code touched, and no new imports outside transmitter.
- ⚠️ Cannot verify from diff: (1) how the deployed publisher finds `antenna/templates/show.html`. The test uses `parents[3]` from the repo layout, so the publisher task should check this. (2) Cache-Control and the ordering of notes/show uploads before the timeline that references them. That is publisher work (later task) and is not exercised here.

### task9-fix3 (c7b7391)
- (a) ADDRESSED. test_pipeline.py:345 `UNSTABLE_MAX_CALLS = 10`. `_unstable` raises AssertionError on the 11th call. render_step catches only FrameCountDrift and TransmitterError (pipeline.py:259-261), so the error propagates. Checked with mutant M2 (pipeline.py:252 `exclude = False`). Predicted red: the two guard tests. Observed: exactly those 2 failed with "measured 11 times: the re-plan loop is unbounded", 23 passed, 1.3 s, no hang.
- (b) ADDRESSED. test_pipeline.py:392 `test_the_second_mismatch_rule_is_per_slug`. Checked with mutant M3 (pipeline.py:252 `exclude = bool(mismatched)`). Predicted red: only that test. Observed: exactly that test failed, 24 passed. Residual, see Minor 1.
- How the mutants ran: scratch `git archive HEAD` copies, empty cwd, `<worktree>/.venv/bin/python -m pytest` with PYTHONPATH shadowing, PYTHONDONTWRITEBYTECODE=1, and a MUTANT_SENTINEL printed from the mutated pipeline.py in every run.

### Strengths
- file_starts reuses `render.show_layout`, the same layout the encoder uses (site.py:32). It adds encoder priming, which matches render.py's docstring: priming frames are part of the aired output. The cut uses `row.end_frame`, which is absolute (layout.py:35), so a recovery cut is handled correctly.
- HTML escaping:
  - Every value is escaped once.
  - The description is truncated before it is escaped, so an entity cannot be split.
  - `safe_substitute` is single-pass, so a `$name` inside a briefing is not re-expanded.
- read_package_notes takes only `.name` of `briefing.file`, so a manifest cannot make it read outside the package.
- The key names in build_notes match llama's real manifest (llama/manifest.py:28-31: show.artist/date/venue/city, source.url/lineage/profile; ManifestTrack set/title/segue).
- Spend surface: nothing in this diff serves or uploads anything. The page's only fetch is the static notes JSON.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. The "package changed" arm still has the same per-slug rule unpinned (pipeline.py:241). Mutant M4 there (`exclude = bool(mismatched)`) was predicted to survive and did: 188 passed across the full transmitter suite. The fix3 finding named the frame-count arm, so this is outside its letter. But two packages re-voiced before one render call is a normal `emcee run` outcome. Under the mutant, the second package would be dropped from the plan instead of re-planned in place. Fix: a sibling of the fix3 test that changes two packages' keys.
2. site.py:86 catches only OSError for the briefing. A briefing.md that is not UTF-8 raises UnicodeDecodeError, which is a ValueError, out of a function whose contract is "None when unreadable". The manifest read on the line above already catches ValueError. Same pattern: if the manifest's `briefing` is not a dict, line 83 raises AttributeError. llama always writes UTF-8 and v3 manifests, so the risk is low.
3. site.py:99-105: `show.get("artist", meta.get(...))` falls back to the cached meta only when the key is absent, not when it is null. llama writes `venue`/`city` as null when unknown. Today that changes nothing, because meta comes from the same manifest. It is a latent trap if meta ever carries a better value.
4. Test coverage gaps, none of them reachable by a currently plausible bug:
   - Nothing distinguishes an absolute `cut_frame` from a relative one: test_site.py:36 uses start_frame=0.
   - Nothing exercises the 24 h lower bound `end_us <= lo` (site.py:43).
   - Nothing checks the `[:10]` cap or the most-recent-first order of `recent` (site.py:60).
5. site.py:136: the archive URL goes into `href` HTML-escaped but its scheme is not checked. It comes from the llama manifest, which is trusted input, so this is noted only.

### Assessment
**Task quality:** Approved
**Reasoning:** The code matches the brief, agrees with the renderer's layout and llama's manifest schema, and escapes correctly. Both task9-fix3 fixes are verified by mutants. The remaining items are minor: one unpinned sibling arm of the per-slug rule, and narrow exception handling.
