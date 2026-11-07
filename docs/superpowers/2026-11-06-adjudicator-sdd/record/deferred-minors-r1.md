Task 8: minor (deferred): cli --accept reads the record without ctx.sink's path while runner.accept_proposal reads _record_path(ctx, entry); agree only because CLI never sets sink.
Task 8: minor (deferred): render_proposal's `show` parameter unused after SLUG (kept for the plan signature).
Task 9: minor (deferred): conftest fixture uses raising=False (covered by test_config_default_enables_hook on rename).
Task 9: minor (deferred): cli.py:704 `ran` term redundant (mirrors :709); deferred-pass gate pause records no boundary (consistent with cli.py:738-742 rule).
Task 10: minor (deferred): acceptable_state judges currency via is_current(ws) re-reading disk rather than rec.digest vs show_digest (expected_at guards the apply).
Task 10: minor (deferred): adjudicate --accept `acceptable` closes over loop var `entry` (late binding).
Task 11b: minor (deferred): R2 propagating-Exception branch unpinned (MR2c MISSED, double fault: ShowChanged propagating + Ctrl-C in the rewrite -> batch continues).
Task 11b: minor (deferred): an interrupted log.warning inside undo()'s handler replaces the original (theoretical).
Task 1: minor (deferred): test_config.py four blank lines before test_adjudicate_section_defaults_on_and_is_strict
Task 1: minor (deferred): template test is a substring check after [adjudicate] (tomllib assert would be tighter)
Task 1: minor (deferred): ShowNotes docstring test is a doc check (plan-mandated)
Task 2: minor (deferred): lineage_table uses `or`, an empty era scores dict falls back to the global table.
Task 2: minor (deferred): pin accepted for a scored recording with kept_tracks == 0 (fails later in gather)
Task 2: minor (deferred): no test for --clear-include with another file flag, or N whose file not in include
Task 2: minor (deferred): cli.py nested conditional stage expression >100 cols
Task 2: minor (deferred): import ordering select_recording.py:9, test_override_keys.py:667
Task 2: minor (deferred): `if recording` truthiness vs `is not None` guard inconsistency
Task 2: minor (deferred): no test pins "overrides.include printed once" (cli.py:3910 gate)
Task 3: minor (deferred): setlistfm section dumps every cached setlist for artist+date, not gather's _pick (multi-event dates include other performances; setlistfm is weak/propose-only evidence)
Task 3: minor (deferred): SETLISTFM_CAP=5000 added (builder's call)
Task 3: minor (deferred): NUL stripped (consequence of brief's test input)
Task 3: minor (deferred): length_of not tested with one-side-unknown cases
Task 3: minor (deferred): _render re-reads vetting/notes/briefing per cap-loop pass
Task 3: minor (deferred): _read_text catches only FileNotFoundError (non-UTF-8 research fails the bundle -> FAILED for that show)
Task 3: minor (deferred): len<=BUNDLE_CAP assert in brief test is vacuous (real coverage in oversize test)
Task 3: minor (deferred): sibling ia.metadata may write md_<id> cache files under <root>/cache and hit network (outside show dir; pilot reads real IA)
Task 3: minor (deferred): _secs f"{s:g}" exponent at >=1e6 s (unreachable)
Task 3: minor (deferred): long inline-conditional f-strings bundle.py:239,242
Task 4: minor (deferred): ProposeOnly with an invalid evidence kind fails the whole verdict (could drop instead)
Task 4: minor (deferred): structure op line "encore not in breaks_after" extra vs brief (now enforced by schema per m5)
Task 4: minor (deferred): adjudicate.md:113 over-long line
Task 5: minor (deferred): structure edit from setlistfm/jerrybase at medium/low gets bar label `structure` not `propose-only` (outcome same; accept is op-based)
Task 5: minor (deferred): inline kind/bar literals in _title_anchor etc. (thresholds/sets are constants)
Task 5: minor (deferred): quote_ok on "\n".join lets a quote stitch two rows (short/medium/structure/venue bars only; plan-mandated)
Task 5: minor (deferred): normalize lacks NFC (fails closed)
Task 5: minor (deferred): fail-closed test asserts only "malformed: edit 0" prefix, not per-kind reason
Task 5: minor (deferred): "bar passes, still vetoed" case covers include only
Task 5: minor (deferred): F3 same-stem compare is case-sensitive; a case-mismatched original row counts as "another" row (fail-open direction, pre-fix behaviour; rare on LMA)
Task 6: minor (deferred): !r quoting in diff/changes lines renders "Truckin'" vs brief's '<old>' form (report text)
Task 6: minor (deferred): n_res tuple readability apply.py:316
Task 6: minor (deferred): no test for switch + city / switch + overrule refusal specifically
Task 7: minor (deferred): _accept_pairs keys flags against bundle.show (post) while held_proposal keys verdict overrule evidence against pre — titles-kind key can disagree (narrow; applied[].index vs evidence_kinds mismatch)
Task 7: minor (deferred): M1 wrap is bare except Exception (no RateLimited re-raise; none can arise at steps 1-2)
Task 7: minor (deferred): test helper ApplyCalled reused as stale guard (naming)
 - CO6 (final review): deferred minors throughout this ledger ("minor (deferred)") for triage; parent rulings recorded above.
