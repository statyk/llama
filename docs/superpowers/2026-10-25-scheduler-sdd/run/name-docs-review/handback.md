### Accuracy

Range 579f619..00afe1f touches only `docs/playout-setup.md` (3 insertions, 2 deletions). No code or config changed (`git diff --stat 579f619..00afe1f -- . ':!docs'` is empty). Every new claim checked against the code:

- **Row 361: show pages use `<title>`, `og:site_name` and the back link.** Correct. `publish.py:263-264` calls `site.render_show_page(..., station_name=p.cfg.antenna.station_name)`. `site.py:144` maps it to `$station`. `antenna/templates/show.html:6` (`<title>$title · $station</title>`), `:8` (`og:site_name`) and `:17` (`← $station` back link) use it. The template path comes from `service.py:73`.
- **Row 361: "hugo's own alert subjects".** Correct. `alerts.py:390` builds the `Dispatcher` with `cfg.antenna.station_name`, and `alerts.py:292` and `:328` prefix subjects with it. The same subject is also hugo's own ntfy `Title` (`alerts.py:168-179`), so "subjects" covers hugo's pushes too.
- **Row 361: "the titles of relayed pushes".** Correct. `service.py:212-213` passes `cfg.antenna.station_name` to `relay.Relay`.
- **Step 8: "they must match, section 6.2 step 6".** Correct. That is line 373, the line the ruling cites. `STATION_NAME` is `antenna/wrangler.jsonc:44` (`"llama radio"`). It controls only the Worker's email subjects: `antenna/src/alerts.ts:363` passes it to `emailChannel`, and the Worker sends no ntfy.
- **Step 8: "hugo reads its config at start".** Correct. `cli.py:206` calls `load_config` once, before `Runner.run()`. There is no reload or SIGHUP path in `packages/transmitter/src`. A restart applies the change.
- **Step 8: "the antenna side takes effect at the next Worker deploy".** Correct. It is a `vars` entry in `wrangler.jsonc`. The dry-run-then-deploy wording matches line 401 and the project's deploy convention.
- **Tests do not pin the `wrangler.jsonc` value.** `alerts.test.ts:494/497/521` and `test_relay.py` use literals. Changing the var will not fail `npm test`.
- **Cross-references.** `7.4 step 8` (rows 361 and 558) resolves to line 581, which is step 8. Step 8 was appended at the end of 7.4, so no earlier step number moved. Nothing anywhere else refers to a 7.4 step number (grep over docs/, packages/, antenna/src, CLAUDE.md). 00afe1f's step-number fix is correct.

**Ruling compliance.**
- (a) Row 361 now names the show pages (title, og:site_name, back link) as well as alert subjects and push titles. Done.
- (b) The new 7.4 step sets `station_name = "LMA Radio"` in hugo's config.toml together with `STATION_NAME`, says they must match (citing :373 as 6.2 step 6), notes that alert subjects are renamed too, and says the antenna side takes effect at the next Worker deploy. Done.
- No code change. Done.
- Additions beyond the ruling: the hugo-restart sentence (accurate and useful) and one cross-reference sentence in 7.3 (see Minor 1).

### Issues

#### Critical
None.

#### Important
None.

#### Minor
1. **7.3 (line 558) overstates one source.** "The show pages and alerts take it from `station_name`" is wrong for antenna's email alerts, which take the name from the Worker's `STATION_NAME` (`alerts.ts:363`). Step 8 covers both, so this is harmless, but "The show pages and hugo's alerts take it from `station_name`; antenna's emails from `STATION_NAME` (7.4 step 8)" would be exact.
2. **Order against step 1 is awkward.** In checklist order, step 8 always comes after step 1's restart, so "restart again if the edit comes later" always applies. "Do this before step 1's restart, or restart again after" reads cleaner. The text is correct as it stands.
3. **Not covered, optional (beyond the ruling).**
   - Changing `station_name` changes every rendered page, which is digest-compared (`publish.py:265-266`). So the next publish pass re-PUTs `notes/` and `show/` for every show in the site window (a handful of PUTs).
   - Pages of shows outside that window (`publish.py:241`: aired more than a day ago) are never re-rendered and keep "llama radio" in their title and back link.
   - The step also does not say to commit the `wrangler.jsonc` edit. Like `METRONOME` (line 656), an uncommitted var reverts at the next deploy from a clean checkout.

   Any of these could be a clause in step 8. None is required by the ruling.

### Assessment

**Task quality:** Approved
