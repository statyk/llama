# Checkpoint A — overrule backfill dry run (read-only)

Code: bulk-apply branch at 884dd4ad (Task 14 complete; its fix round touched only the --apply unit). Command, from the worktree: `./.venv/bin/python scripts/bulk_apply.py backfill --base ~/.llama-harness/piece4/migration-base.json --verdicts ~/.llama-harness/t3/verdicts > ~/.llama-harness/bulk/backfill-dryrun.txt` — rc 0, stderr empty, last line "dry run: nothing written (pass --apply)"; `find ~/.llama -newer <run-start marker>` found no file.

Full output: `/Users/shawn/.llama-harness/bulk/backfill-dryrun.txt` (sha256 `950aa6fed6cbe6c121a310356acb3c023c5a3b36d836d77c72b270f94f00281c`, 32382 bytes, 590 lines).

## Totals

`totals: shows considered 195, shows with no verdict 15, flags recorded 316, flags listed 62, shows fully covered 141 of 180`

Planning measured 195 / 15 / 316 / 62 / 141 of 180: **identical**. The 62 listed = 54 `verdict never ruled on this flag` + 4 `ruled research-wrong` + 2 `ruled research-right-show-wrong` + 2 `only in other_flags (free text)` (the plan's "56 never ruled on" counted the 2 `other_flags` ones with them). No considered show is held today (none skipped by that rule).

## List 1 — the 62 listed flags (not recorded; each show re-holds on these when the apply reaches it)


### `verdict never ruled on this flag` — 54

- `bandofheathens-2009-07-27`: research asserts unknown song: Nine Steps Down — rehold-verdict: **overrule**
- `bandofheathens-2009-07-27`: research asserts unknown song: Hangin' Tree — rehold-verdict: **overrule**
- `bobweir-2013-03-01`: structure has 2 sets but jerrybase shows 1
- `campervanbeethoven-2004-06-13`: research asserts 1 sets but structure has 2 — rehold-verdict: **overrule**
- `charliehunter-2004-05-22`: unresolved track titles
- `darkstarorchestra-2002-05-21`: jerrybase set closer 'Going Down the Road Feelin' Bad' is not at a set break — rehold-verdict: **overrule**
- `darkstarorchestra-2003-01-25`: jerrybase set closer 'It's All Over Now, Baby Blue' is not at a set break — rehold-verdict: **overrule**
- `darkstarorchestra-2004-04-20`: jerrybase set closer 'Black Muddy River' is not at a set break — rehold-verdict: **overrule**
- `darkstarorchestra-2005-11-16`: jerrybase set closer 'Going Down the Road Feelin' Bad' is not at a set break — rehold-verdict: **overrule**
- `darkstarorchestra-2007-07-06`: structure has 2 sets but jerrybase shows 1 — rehold-verdict: **overrule**
- `darkstarorchestra-2011-07-31`: structure has 2 sets but jerrybase shows 1
- `delmccouryband-2008-05-24`: setlist evidence shows multiple sets but alignment found none — rehold-verdict: **overrule**
- `furthur-2011-02-11`: research asserts unknown song: Prelude — rehold-verdict: **overrule**
- `furthur-2011-02-11`: research asserts unknown song: Part I — rehold-verdict: **overrule**
- `furthur-2011-02-11`: research asserts unknown song: Let It Grow — rehold-verdict: **overrule**
- `furthur-2011-02-11`: research asserts unknown song: Liberty — rehold-verdict: **overrule**
- `furthur-2012-09-23`: jerrybase set closer 'Black Peter' is not at a set break — rehold-verdict: **overrule**
- `geoffachisonandthesouldiggers-2003-05-28`: research asserts unknown song: Matchbox — rehold-verdict: **overrule**
- `geoffachisonandthesouldiggers-2003-05-28`: research asserts unknown song: Thundering in the Thickets — rehold-verdict: **overrule**
- `geoffachisonandthesouldiggers-2003-05-28`: research asserts unknown song: Walking Blues — rehold-verdict: **overrule**
- `godspeedyoublackemperor-2022-02-25`: unresolved track titles
- `gratefuldead-1969-03-28`: structure has 2 sets but jerrybase shows 1 — rehold-verdict: **overrule**
- `gratefuldead-1970-05-01`: structure has 2 sets but jerrybase shows 1
- `gratefuldead-1970-05-01`: research asserts 3 sets but structure has 2
- `gratefuldead-1977-05-17`: research asserts 3 sets but structure has 2 — rehold-verdict: **overrule**
- `gratefuldead-1980-10-10`: structure has 3 sets but jerrybase shows 2 — rehold-verdict: **overrule**
- `gratefuldead-1980-10-14`: structure has 3 sets but jerrybase shows 2 — rehold-verdict: **overrule**
- `gratefuldead-1984-04-21`: jerrybase set closer 'Not Fade Away' is not at a set break — rehold-verdict: **overrule**
- `gratefuldead-1985-11-10`: jerrybase set closer 'It's All Over Now Baby Blue' is not at a set break
- `moe-2004-09-04`: recordings of this date disagree on city: 'Snow Ridge Ski Area, Turin, NY' (selected) vs 'Turin, NY' — rehold-verdict: **overrule**
- `philleshandfriends-2001-02-18`: structure has 2 sets but jerrybase shows 1 — rehold-verdict: **overrule**
- `philleshandfriends-2001-07-07`: structure has 2 sets but jerrybase shows 1
- `philleshandfriends-2001-12-31`: structure has 3 sets but jerrybase shows 1 — rehold-verdict: **overrule**
- `philleshandfriends-2005-07-16`: jerrybase set closer 'I Know You Rider' is not at a set break — rehold-verdict: **overrule**
- `philleshandfriends-2007-10-07`: structure has 3 sets but jerrybase shows 1 — rehold-verdict: **overrule**
- `philleshandfriends-2008-06-15`: recordings of this date disagree on city: 'Bonnaroo , TN' (selected) vs 'Manchester, TN' — rehold-verdict: **overrule**
- `philleshandfriends-2008-07-04`: structure has 2 sets but jerrybase shows 1 — rehold-verdict: **overrule**
- `philleshandfriends-2008-11-18`: jerrybase set closer 'Mountains of the Moon' is not at a set break — rehold-verdict: **overrule**
- `philleshandfriends-2008-11-18`: structure has 2 sets but jerrybase shows 1 — rehold-verdict: **overrule**
- `philleshandfriends-2008-12-31`: structure has 2 sets but jerrybase shows 1
- `ryanadams-2007-10-25`: research asserts 3 sets but structure has 2
- `stevekimockband-2002-04-20`: unresolved track titles
- `stevekimockband-2002-04-20`: research asserts unknown song: Tongue 'n Groove
- `stevekimockband-2002-04-20`: research asserts unknown song: Moon People
- `stevekimockband-2002-04-20`: research asserts unknown song: A New Africa
- `stevekimockband-2002-04-20`: research asserts unknown song: Severe Tire Damage
- `stevekimockband-2002-04-20`: research asserts unknown song: Sabertooth
- `stevekimockband-2002-04-20`: research asserts unknown song: Five B4 Funk
- `stevekimockband-2002-04-20`: research asserts unknown song: You're the One
- `stevekimockband-2002-04-20`: research asserts unknown song: Elmer's Revenge
- `stevekimockband-2002-04-20`: research asserts unknown song: Why Can't We All Just Samba
- `stevekimockband-2002-04-20`: research asserts unknown song: Long Form Part IV
- `stevekimockband-2002-04-20`: research asserts unknown song: Hillbillies on PCP
- `stevekimockband-2002-04-20`: research asserts unknown song: Avalon

### `ruled research-wrong` — 4

- `derektrucksband-2005-06-17`: research asserts wrong date: June 16
- `mymorningjacket-2011-05-31`: research asserts 2 sets but structure has 1
- `railroadearth-2007-09-29`: research asserts 3 sets but structure has 2
- `yondermountainstringband-2005-10-21`: research asserts 3 sets but structure has 2

### `only in other_flags (free text)` — 2

- `darkstarorchestra-2011-07-31`: venue mismatch: archive 'Fuji Rock Festival - Field of Heaven' vs jerrybase 'Naeba Ski Resort'
- `philleshandfriends-2008-12-31`: venue mismatch: archive 'Bill Graham Civic Center' vs jerrybase 'Bill Graham Civic Auditorium'

### `ruled research-right-show-wrong` — 2

- `zachdeputy-2010-07-02`: research asserts unknown song: Scrambled Eggs
- `zachdeputy-2010-07-02`: research asserts unknown song: Outro

## List 2 — the 15 shows with no verdict (all `delivered` in the base arm), with their base flags

- `aquariumrescueunit-2005-01-08`: single-set structure for a long show (161 min)
- `beneventorusso-2005-08-27`: recordings of this date disagree on city: 'Skye-Top Festival Grounds , Van Etten,NY' (selected) vs 'Van Etten,NY'
- `darkstarorchestra-2009-11-14`: low-confidence structure alignment
- `deadandcompany-2015-10-29`: low-confidence structure alignment
- `dumpstaphunk-2008-04-25`: unresolved track titles
- `gratefuldead-1977-05-09`: venue mismatch: archive 'Buffalo Memorial Auditorium' vs jerrybase 'War Memorial Auditorium'
- `gratefuldead-1978-09-16`: recordings of this date disagree on city: 'Giza, Egypt' (selected) vs 'Cairo, Egypt'
- `lotus-2010-06-10`: unresolved track titles
- `mymorningjacket-2018-03-05`: research asserts 3 sets but structure has 2
- `railroadearth-2007-01-28`: unresolved track titles
- `ryanadams-2007-06-06`: recordings of this date disagree on city: 'London, England' (selected) vs 'London, UK'
- `smashingpumpkins-1997-06-28`: recordings of this date disagree on city: 'Roskilde, Denmark' (selected) vs 'Roskilde, DK'
- `soulive-2004-02-08`: unresolved track titles
- `stringcheeseincident-2005-03-25`: low-confidence structure alignment
- `umphreysmcgee-2005-11-12`: unresolved track titles

## Question 1 (plan): the listed flags
The 62 flags in List 1 and the 15 no-verdict shows in List 2 are not recorded, so each such show re-holds on them when the bulk apply reaches it (fails safe: it lands in triage). Do you want any of them recorded as overrules — by reason class, or show by show?

## Question 2 (plan): `~/.llama-harness/t3/rehold-verdicts/`
34 files, shape `{slug, decision, why}` with no per-flag ruling: 32 `overrule`, 2 `escalate` (`furthur-2012-07-07`, `soundtribesector9-2001-03-16`). The backfill does not read them (the plan left this to you; the spec does not name the directory). Overlap with this dry run: 27 of the 34 shows are in it, carrying 31 of the 62 listed flags (tagged **overrule** in List 1; 4 of the 27 also have a recorded flag, and 3 of those have nothing listed); the other 7 are outside the backfill rule (`furthur-2012-07-07`, `moe-2005-09-03`, `particle-2003-06-14`, `robertrandolphandthefamilyband-2005-06-03`, `ryanadams-2000-09-28`, `soundtribesector9-2001-03-16`, `stevekimockband-2000-03-31`).
Options: (a) list only, as now; (b) read them: a show-level `overrule` records every base flag still listed on that show (a show-level ruling standing in for per-flag ones; `escalate` stays listed); (c) something narrower you name. (b) or (c) changes Task 14's rule and would be follow-up T14b.

## Observation (Task 14 reviewer, Minor; not one of the plan's questions)
Verdict rulings on flags the base arm did NOT raise are neither recorded nor listed: 174 (slug, flag) pairs over 36 shows (spurious / flag-spurious rulings plus `overrule_if_reheld_on` entries; 13 of those shows also have a rehold-verdict). None of the 174 is raised by `migration-post.json`, so dropping them costs nothing today, but `overrule_if_reheld_on` exists for flags that may re-appear on a re-hold. Options: leave as is; print them in a separate `not raised by the base arm` section; or record the `overrule_if_reheld_on` ones (a rule change → T14b). The pairs: `~/.llama-harness/bulk/backfill-not-in-base.json`.

Any ruling here becomes follow-up task T14b; Task 14's rule is unchanged until then. Nothing has been applied.
