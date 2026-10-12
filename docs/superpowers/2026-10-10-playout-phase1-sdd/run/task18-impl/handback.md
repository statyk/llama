Status: DONE_WITH_CONCERNS
Commit: see `git log -1` on playout-phase1 (docs/playout-setup.md only).
Tests: 2438 passed, 7 deselected (./.venv/bin/python -m pytest -q -p no:cacheprovider); transmitter imports from the worktree.
Corrections vs brief (code wins):
- 3.3: config path is $TRANSMITTER_ROOT/config.toml when set; unknown keys are errors.
- 3.3: prune_margin_minutes (real key, default 10) floor is 4 -> REFUSED at config load (pydantic ge=4), not floored.
- 3.3: show template = <[antenna] dir>/templates/show.html; missing -> ConfigError at publish.
- 3.4: fallback render prints "horizon updated" or "horizon deferred"; antenna only sees fallback once state/horizon.json names it.
- 3.7 (new): epoch is created at first open_station and stored in <root>/epoch.json; no command changes it; check_epoch refuses publish on mismatch with publish.json; changing root/TRANSMITTER_ROOT or deleting epoch.json would re-epoch; MEDIA-SEQUENCE restarts at 0, players reload.
- 4.2: added wrangler deploy --dry-run first (not run by me). 4.3: mentioned deploy-assets --dry-run.
- 4.4: off-air needs usable fallback (horizon.fallback_version + index.json len>=1); else nothing written, `offair-without-fallback` console.error once/invocation, players keep last playlist; WAF kill switch only hard stop.
- 4.5 (new): MAX_PUTS=10, d != 10.24 -> refused ("horizon-refused" log), LOOP_SECONDS clamped to 75 ("loop-clamped").
Verified unchanged: bucket llama-radio, R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY, npm ci/test/deploy:assets, ANTENNA_BUCKET, fallback render <loop> --notice, status lines, ALERT logging, .station-root marker, clock log fields (event "clock", lagMs).
Concerns (left as in brief):
- WAF allowlist lists /embed.html but no such asset/object exists in antenna/public or deploy-assets (harmless).
- Section 2 step 9 mentions `monthly_budget_usd`, which is not a key in transmitter config at HEAD (phase-2 concept).
- Brief's "plan refuses without marker" holds (open_station->require_root path via station scan); not separately exercised.
