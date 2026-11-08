# Segue restore: measurement (2026-11-07)

Code: branch segue-restore @ 81f45e95. Script: scripts/segue_restore_measure.py. Raw outputs were in the session scratchpad (m-spot/, m-lib/).

## 1. Spot A/B (10 trial spot-check shows, offline, recorded LLM alignment)

PASS. Arm A (pass off) equals the stored segues on all 10 shows; all 8 stored-llm shows replayed on the llm path.
- deadandcompany-2015-10-31 track 18 China Cat Sunflower: restored (setlist.fm).
- None of the 9 good re-run changes reverted (Uncle John's Band on 2015-11-10 and the 5 lettuce-2008-08-06 drops stay dropped).
- Other adds: dumpstaphunk-2009-02-09 tracks 5 Greazy Groceries, 10 She's Music (deterministic alignment; predicted, the selected description has both); furthur-2010-09-25 track 13 Tuning (deterministic alignment; unpredicted: a mark FROM a filler track into Mountain Song).

## 2. Library (every show with no gather LLM touchpoint, offline)

Scanned 3325 shows (658 skipped for an LLM touchpoint), 0 errors.
- Shows changed: 40; segues added: 84 (all setlist.fm).
- Changed by state: delivered unvoiced 26, delivered voiced 9, library-only 5. A v2.23.0 campaign arm shows all 35 delivered ones as a visible segues change; mark would take them off air.
- Adds by info form: > 59, -> 3, ) (> 9, other 6, unmatched 7.
- Donor-said-no skips (not added): 198; by form > 118, -> 8, ) (> 17, other 8, unmatched 47.

Changed shows:

- davidnelsonband-2009-06-27 (delivered unvoiced): 14 'Turkish Nut Roll'
- deadandcompany-2016-06-23 (delivered voiced): 12 'Space'
- deadandcompany-2016-07-02 (delivered voiced): 11 'Terrapin Station'
- deadandcompany-2017-06-03 (delivered voiced): 1 "Playin' in the Band"; 6 'Me and My Uncle'; 9 'China Cat Sunflower'; 10 'I Know You Rider'; 11 'China Doll'; 12 'Eyes of the World'; 13 'Deal'; 14 'Drums'; 15 'Space'; 17 'Looks Like Rain'
- deadandcompany-2017-06-04 (delivered voiced): 9 'Help on the Way'; 10 'Slipknot!'; 11 "Franklin's Tower"; 12 'Scarlet Begonias'; 13 'Fire on the Mountain'; 14 'Drums'; 15 'Space'; 16 'The Other One'
- deadandcompany-2017-06-28 (delivered unvoiced): 12 'Drums'; 13 'Space'
- deadandcompany-2022-06-14 (delivered voiced): 12 'Drums'; 13 'Space'
- derektrucksband-2005-11-06 (delivered unvoiced): 8 'Sahib Teri Bandi - Maki Madni'
- derektrucksband-2006-10-28 (delivered unvoiced): 4 'Sahib Teri Bandi'
- derektrucksband-2006-11-03 (delivered unvoiced): 7 'Drums'
- discobiscuits-2002-12-26 (delivered unvoiced): 3 'Crickets'
- discobiscuits-2005-08-26 (delivered unvoiced): 2 'Shem-Rah Boo->(1)'
- discobiscuits-2006-08-26 (delivered unvoiced): 15 '7-11 (Ending)'
- discobiscuits-2009-01-30 (delivered unvoiced): 9 'Reactor>@'
- discobiscuits-2009-06-04 (delivered unvoiced): 11 'Park Ave'
- drive-bytruckers-2006-09-27 (delivered unvoiced): 26 'Let there Be Rock'
- furthur-2012-09-21 (library-only): 3 'Slipknot'
- gratefuldead-1967-11-10 (library-only): 11 'Drums'
- gratefuldead-1968-10-12 (delivered unvoiced): 11 'Jam'
- gratefuldead-1969-04-05 (delivered unvoiced): 12 'Drums'
- gratefuldead-1983-10-14 (delivered unvoiced): 17 'Space'
- gratefuldead-1985-06-28 (delivered voiced): 13 'Space'
- gratefuldead-1986-07-04 (delivered unvoiced): 14 'Space'
- gratefuldead-1987-03-27 (delivered unvoiced): 9 'Touch of Grey'
- gratefuldead-1991-06-14 (delivered unvoiced): 10 'Help on the Way'
- gratefuldead-1991-10-27 (library-only): 1 'Sugar Magnolia'; 13 'Mona'; 15 'Space'; 16 'The Wheel'; 17 'I Need a Miracle'; 18 'Wharf Rat'
- gratefuldead-1993-08-21 (delivered voiced): 7 'China Cat Sunflower'
- joerussosalmostdead-2018-04-21 (delivered unvoiced): 3 'Feel Like A Stranger @'
- joerussosalmostdead-2024-09-07 (delivered voiced): 1 'My Brother Esau'; 3 'Let it Grow'; 4 'Help on the Way'; 5 'Slipknot'; 6 'Fire and Brimstone'; 8 'Dark Star'; 9 "Where's Sly?"; 12 'Pigs (Three Different Ones)'
- lettuce-2008-05-02 (delivered unvoiced): 14 "That's the Way of the World"
- mymorningjacket-2017-07-15 (library-only): 8 'Tropics (Erase Traces)'; 10 'Compound Fracture'; 13 'Spring (Among The Living)'; 14 'Dondante'; 15 'Victory Dance'
- robynhitchcock-2007-03-18 (delivered voiced): 8 'Lo And Behold / Life During Wartime'
- soundtribesector9-2001-03-16 (library-only): 1 'Evasive Maneuvers'
- soundtribesector9-2005-08-12 (delivered unvoiced): 1 'Music,Us'
- soundtribesector9-2006-04-26 (delivered unvoiced): 10 'Warrior'; 11 'Crystal Instrument'
- soundtribesector9-2007-12-30 (delivered unvoiced): 1 'Moonsocket'; 12 'Grow'
- stringcheeseincident-2007-03-27 (delivered unvoiced): 1 'Magic Carpet Ride'; 2 'Rhythm Of The Road'; 3 'These Waves'; 5 'Dirk'; 6 'Shakedown Street'; 11 'Under African Skies'; 13 'Looking Glass'; 15 'Jellyfish'
- tedeschitrucksband-2022-03-26 (delivered unvoiced): 10 'Soul Serenade/Sugaree'; 14 'Learn How To Love'
- thedead-2009-05-10 (delivered unvoiced): 2 'Slipknot'
- thewaybacks-2006-04-28 (delivered unvoiced): 9 'St. Stephen > The Eleven'

### Hand-check: 20 sampled adds

- gratefuldead-1991-10-27 track 13 'Mona' info='also with Gary Duncan - First time since 1972.) (>'
- joerussosalmostdead-2024-09-07 track 12 'Pigs (Three Different Ones)' info='->'
- gratefuldead-1993-08-21 track 7 'China Cat Sunflower' info='>'
- tedeschitrucksband-2022-03-26 track 14 'Learn How To Love' info='with drum solo section, >'
- discobiscuits-2006-08-26 track 15 '7-11 (Ending)' info=None
- joerussosalmostdead-2024-09-07 track 3 'Let it Grow' info="'Tennessee Jed' tease) (>"
- gratefuldead-1986-07-04 track 14 'Space' info='->'
- deadandcompany-2022-06-14 track 12 'Drums' info='>'
- joerussosalmostdead-2024-09-07 track 9 "Where's Sly?" info="'Terrapin Station' tease) (->"
- thewaybacks-2006-04-28 track 9 'St. Stephen > The Eleven' info=None
- joerussosalmostdead-2024-09-07 track 5 'Slipknot' info='Elizabeth Reed tease) (>'
- gratefuldead-1987-03-27 track 9 'Touch of Grey' info='->'
- deadandcompany-2017-06-03 track 9 'China Cat Sunflower' info='>'
- joerussosalmostdead-2024-09-07 track 8 'Dark Star' info='Daytripper tease) (-> Pigs (Three Different Ones)  jam ->'
- tedeschitrucksband-2022-03-26 track 10 'Soul Serenade/Sugaree' info=None
- deadandcompany-2016-07-02 track 11 'Terrapin Station' info='John Mayer lead vocals on "Lady With a Fan") (>'
- deadandcompany-2017-06-03 track 15 'Space' info='>'
- joerussosalmostdead-2018-04-21 track 3 'Feel Like A Stranger @' info='> Jam >'
- derektrucksband-2005-11-06 track 8 'Sahib Teri Bandi - Maki Madni' info=None
- deadandcompany-2017-06-03 track 11 'China Doll' info='lead vocals sung by Oteil for the first time ever) (>'

### Hand-check: 20 sampled donor-said-no skips

- thedead-2015-06-28 track 11 'Wharf Rat' info='Bob Weir lead vocal) (>'
- gratefuldead-1990-03-19 track 7 "It's All Over Now" info='->'
- gratefuldead-1989-07-17 track 4 'Me and My Uncle' info='>'
- gratefuldead-1991-06-17 track 3 'Brown-Eyed Women' info="> 'Dark Star' tease >"
- derektrucksband-2005-11-19 track 4 'Sahib Teri Bandi > Maki Madni > Sahib Teri Bandi' info=None
- thedead-2015-06-28 track 13 "He's Gone" info='Bob Weir and Bruce Hornsby traded vocals) (>'
- tedeschitrucksband-2019-07-16 track 2 "Don't Know What It Means" info='->'
- deadandcompany-2017-06-25 track 2 'Brown Eyed Women' info='>'
- radiators-2010-10-29 track 8 'Ooh La La' info='-->'
- thedead-2015-06-28 track 14 'Drums>Space' info=None
- thedead-2015-06-28 track 16 "Death Don't Have No Mercy" info='First time since 1990. Bob Weir lead vocal) (>'
- gratefuldead-1987-03-26 track 1 'In The Midnight Hour' info='->'
- deadandcompany-2017-11-14 track 15 'A Love Supreme' info='>'
- deadandcompany-2017-06-01 track 14 'Space' info="> 'Dark Star' reprise >"
- derektrucksband-2009-04-15 track 13 'Get Out Of My Life Woman > Who Knows > Get Out Of My Life Woman*' info=None
- deadandcompany-2015-11-01 track 3 'Bertha' info='John Mayer on lead vocals) (>'
- gratefuldead-1988-06-23 track 11 'Man Smart, Woman Smarter' info='->'
- mymorningjacket-2019-08-02 track 11 'War Begun' info='>'
- tedeschitrucksband-2026-08-01 track 7 'Machine Gun' info='Instrumental -->'
- deadandcompany-2021-09-18 track 15 'The Days Between' info=None

### Hand-check verdicts (orchestrator, against the sampled description lines)

- Adds: no clear misfire in 20. Classic segues (China Cat > Rider x2, Drums >, Space >, Touch of Grey ->, Dark Star ->, Pigs ->) agree with the tapes where the description lists them; about 9 can't be checked from the description (JRAD 2024-09-07 and others have none). The `) (>` form (setlist.fm joined notes) reads right in all sampled cases.
- Skips: mixed, and several look like setlist.fm was right and the donor simply didn't notate the segue (gratefuldead-1989-07-17 Me and My Uncle -> Cumberland Blues, which the selected tape's own description writes with `->`; Space > on deadandcompany-2017-06-01). The skip rule follows the standing "tape notes stand" steer; 198 skips vs 84 adds means relaxing it would roughly triple the reach. Left for Shawn.

## 3. Live sample (37 held needs-LLM shows, real LLM, read-only)

Seed 20261108 over the 615 shows still awaiting fix for an LLM call (the 37 trial shows of 2026-10-27 excluded). Meter before: 5h 25%, 7d 24%. 35 of 37 replayed on the llm path; 2 (stevekimockband-2004-07-09, thenewdeal-2005-07-30) fell back to the deterministic alignment because the LLM result missed the coverage threshold (normal gather behaviour, not an error).

The LLM's own changes versus stored (before the pass): 11 shows, 11 adds, 3 drops; far less churn than the 10-27 trial (17 of 37 shows, 19 adds, 17 drops).

Drops and what the pass did:
- radiators-2010-06-05 track 6 `Sunglasses On > Rockin' Pneumonia ...` → restored (the deterministic alignment).
- thenewdeal-2005-07-30 track 9 `jam 5 >`: title ends in an arrow, so it still renders as a segue; untouched by design.
- derektrucksband-2005-04-08 track 1 `Sahib Teri Bandi > Maki Madni > Sahib Teri Bandi` → Crow Jane: setlist.fm marks it but the donor's own alignment says no, so skipped (taper notes stand). Unclear which is right.

Restores (2, both E2): the radiators drop above, and godspeedyoublackemperor-2000-10-31 track 4 `John Hughes` (a continuous-set band; plausible).

LLM adds the pass leaves alone (non-goal: the pass never blocks adds): mostly plausible jam flows; one looks wrong, warrenzevon-1990-12-08 `Werewolves Of London` → `encore break 2` (a segue into filler, made by the LLM itself, not by the pass). Two (gratefuldead-1973-12-12 `Wharf Rat ->`, thenewdeal `DJ Omen >`) only set the flag on a title that already shows the arrow.

Verdict: the pass caught the one listener-visible bad drop it could see, added nothing wrong, and the LLM's own churn is now small. Residual risk: LLM-made segues into filler (one in 37), outside this pass.
