# Task 12 (prune) — handback

Status: DONE_WITH_CONCERNS (one minor concern; everything passes)

Commits (branch playout-phase1, on 1d99568):
- ecd89dc feat(transmitter): prune by computed key range after advancing horizon.first
- efe266f fix(transmitter): floor prune_margin_minutes at 4 min, derived from the live window

Files: packages/transmitter/src/transmitter/publish.py (PruneReport, prune);
packages/transmitter/src/transmitter/config.py (PRUNE_MARGIN_FLOOR_MINUTES, template comment);
packages/transmitter/tests_transmitter/test_prune.py (new, 15 tests);
packages/transmitter/tests_transmitter/test_config.py (+6 test cases).

Tests added: the brief's 7 (unused `grid` import dropped, M5; E is helpers.E = 4e9 s, I1) plus:
guard unreadable fails closed; prune raises PublishLocked under a held publish_lock and makes no S3 call;
failed horizon PUT deletes nothing; spent PUT budget -> stopped="put-budget", no delete;
high_water > last -> stopped="high-water", nothing written; high_water preserved; configured margin honoured;
config: floor value pinned, below-floor (0, 1.5, 3.99) is ConfigError naming prune_margin_minutes, 4 accepted, template states it.

Commands:
- ./.venv/bin/python -c "import transmitter; print(transmitter.__file__)" -> worktree packages/transmitter/src (also .venv311)
- ./.venv/bin/python -m pytest -q -p no:cacheprovider -> 2399 passed, 7 deselected (3.14, full repo)
- ./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider -> 250 passed (3.11.15)
- packages/transmitter/scripts/test-in-debian12.sh (at efe266f) -> ffmpeg 5.1.9-0+deb12u1, Python 3.11.2, 250 passed, rc 0

Ruling 1: PRUNE_MARGIN_FLOOR_MINUTES = ceil(((6 + 3) * 10.24 + 5 + 120) / 60) = ceil(217.16 s / 60) = 4.0,
computed in config.py from named constants (window k=6, grace 3, d from grid.D_US, live.m3u8 max-age 5 s,
player-lag/clock-skew allowance 120 s) with the arithmetic in a comment. Field(default=10.0, ge=floor);
template comment now says "at least 4". Ruling 2: applied. Ruling 3: prune takes publish_lock (non-blocking)
and the guard check first; both pinned (lock test + tripped + unreadable guard tests).

Mutation (scratch git-archive copy, cwd = copy, PYTHONPATH shadow, per-mutant PYTHONPYCACHEPREFIX,
sentinel test + printed __file__ proved the copy was imported; predictions written into the script first):
- M0 control: 251 passed (250 + sentinel)
- M1 floor ge -> 0: predicted the 3 below-floor params fail -> exactly those 3 CAUGHT
- M2 lag allowance 120 -> 30 (floor 3): predicted floor-pin test + [3.99] -> exactly those 2 CAUGHT
- M3 horizon PUT moved after the deletes: predicted advances-first-before-deleting, failed-horizon-deletes-nothing,
  spent-budget -> exactly those 3 CAUGHT
- M4 high-water deferral removed: predicted the high-water test -> CAUGHT (1)
- M5 n_max not bounded by last: predicted never-moves-past-last -> CAUGHT (1)

Brief vs code:
1. Added a high-water deferral the brief lacks: when state.high_water > state.last (crash between a horizon PUT and
   the save of `last`), prune returns stopped="high-water" without writing anything. Otherwise its horizon rewrite
   (bounded by state.last per the brief) would move R2's `last` backwards, breaking publish.py's documented rule
   "the horizon is never rewritten below that mark". publish_batch reconciles on its next tick; prune resumes after.
   high_water is never modified (state is loaded and saved whole).
2. PutBudgetExceeded on the horizon PUT reports stopped="put-budget" (as PublishReport does) rather than only
   error="horizon: ..."; a PublishError still gives error="horizon: ...".
3. Brief's test imported `grid` unused -> dropped. helpers.make_publisher already had prune_min (default 1).

Concerns:
- The deferral (1) is my call within the ruling "bounded by state.last; never move high_water"; if the manager wants
  prune instead to write the horizon with last = high_water, that is a different behaviour. Low stakes: a deferred
  prune only delays deletes (storage), never spend or listing.
- Plan/spec docs still show `prune_margin_minutes ... ge=0` / no floor (docs/superpowers/plans/...md:1825,
  spec :353); not edited (out of task scope).
