# census2: rule R ("drop a short file only when its tag says junk")

**Ground state.** At start and end, HEAD was e37f670, the tree was clean, and `llama.__file__` resolved inside the main checkout. Nothing in the repo or `~/.llama` was written. I made no LLM calls and dispatched no subagents. I used the census-1 `dump.jsonl`. Replays went through the same harness, with R patched into `junk._keep_and_exclude` in-process.
- **Harness change:** I added an opt-in `P45_COV_EXCLUDE=1` patch of `structure._songish_coverage` to `~/.llama-harness/piece45/dump.py`. The census-1 copy is kept as `dump_census1.py`.
- **Meter at hand-back:** 5h 6%, week 80%.

## Rule R as measured
- **Scope:** files whose ONLY drop reason is `implausibly short`. That is 3,547 files in 1,870 shows. The convention-mismatch (111), duplicate-listing (40) and conv+short (7) arms are untouched, and so are the constants.
- **Deny core.** The tag is denied only when EVERY part of it (split on `/ , & + ; and - > ~`) matches:
  - tuning: `tuning`, `tune up`, `tuning up`, `set N tuning`, `tunning`, `re-tune`, `instrument change`;
  - silence: `dead air`, `silence`, `blank`, `empty`;
  - tape edges: `tape flip/change/cut/end/gap`, `side/disc flip`, `gap`, `cut-in`, `fade in`, `fade out`;
  - noise: `noise`, `hiss`, `static`, `test tone`;
  - `soundcheck`.
  - Mixed tags such as `intro/tuning` or `tuning/banter` are kept, because they contain spoken show content.
- **Deny extra (non-performance), matched anywhere in the tag:** `commercial`, `promo`, `promoting the new CD`, `station plug`, `station ID`, `news broadcast`, `house music`, `PA music`, `intro music`, `recorded music`, `pre-show music`, `advert`. Justification from the data: these are the only non-performance items among short drops, 16 files. Examples: KZEW radio commercials #1/#2, a Lowell George KLOL promo, 3 "station plug" files, a WXRT station ID, `Old News Broadcast`, `Amore (house music)`, `PA Music >`, `Intro Music` ×3.
- **Optional extra "R+crowd":** also deny a tag made only of crowd words: `crowd`, `applause`, `cheering`, `audience`, `encore/set break`, `encore call`, `waiting`. Combinations with tuning (`crowd/tuning`) count.
- **Untagged files** count as untagged when there is no real title, or the tag is a placeholder, timestamp or filename residue (`placeholders.is_junk_tag`).
  - Measured: 138 interior, 59 at the head/tail edges.
- **Operator excludes:** none of the short-only drops is operator-excluded, so rule 4 never fires.

## (a) What R re-admits: 3,133 files in 1,716 shows (about 55 hours of audio)

| kind | files | shows | examples |
|---|---|---|---|
| spoken (band / crew / stage) | 1,653 | 1,068 | `Intro` 458, `banter` 263, `Band Intros` 54, STS9 `Murph` 45, `outro` 36, `donor rap` 32, `Stage Announcements` (GD 1972-08-27 d2t07/d3t01/d3t05: 28/58/48 s, all re-admitted), `thank you` |
| music (song / segue / continuation) | 864 | 622 | `Drums >`, `Jam >`, `Slipknot!`, `St. Stephen` reprises, `WRS Prelude`, `Fastball`, `Maple Leaf Rag`, `Who Do You Love->` |
| crowd | 315 | 246 | `Crowd` 153, `Encore Break` 38+, `crowd encore call`, `applause` |
| untagged, interior | 138 | 89 | untagged mid-tape files; timestamp-led `1:04) Banter` counts here |
| mixed with tuning | 91 | 73 | `crowd/tuning` 39, `intro/tuning` 15, `tuning/banter` 13 |
| music fragment | 51 | 45 | `(false start)`, `My Blue Heaven [tease]`, `Honkytonk Woman (aborted)`, `Chainsaw tease >` |
| spoken broadcast (radio DJ, interview) | 21 | 16 | `DJ talk`, `Jerry Garcia interview`, `Ken Kesey Interview`, `Q104.3 DJ intro` |

- **Still dropped by R:** 339 deny-core, 16 non-performance and 59 untagged edge files.
- **The "music" kind is a catch-all** for tags that are not spoken, crowd or deny. It contains some spoken bits the taper titled: `"really hot show"`, `(new sample)`, `Dead battery`, `"Get Down From The Balcony"`, `Let Phil Sing Rant`. My census-1 look put that at roughly 15-25% of the named-only part of this kind.
- **Tiny files:** R re-admits 6 files under 5 s, 3 of them 0-1 s (metadata length 0, e.g. `Promised Land \>`).

**Untagged-file variants:**

| variant | files re-admitted | shows |
|---|---|---|
| R as specified (keep interior, drop edge) | 3,133 | 1,716 |
| keep all untagged | 3,192 | 1,739 |
| drop all untagged | 2,995 | 1,635 |
| R+crowd (interior variant) | 2,850 | 1,628 |

- R+crowd still keeps 32 crowd files whose tags mix crowd with a spoken part.
- **Untagged interior files carry little evidence.** 84 have no sibling evidence at all. 40 have sibling evidence of "split", i.e. the file is part of a longer sibling track (tuning or a song head). Each one re-admitted ships as an unresolved track, which is a hold by design.

## (b) Deny-list behaviour
**Drops 339 files:**
- `tuning` 269; `set 1/2 tuning` 12; `tune up` and `tuning up` 9; `tuning >` 6;
- 33 `fade in`/`fade out` (4-17 s, one 73 s);
- `dead air` 3, `silence` 1, `blank` 1, `[tape flip]` 1.
- By duration: 77 under 30 s, 103 at 30-60 s, 117 at 60-90 s, 49 at 90-120 s, 9 over 120 s (tuning up to 201 s).

**Wrongly dropped music: none found.**
- None of the 339 is operator-included.
- No sibling labels any of them as a song: where a sibling pairs with one, it is either `tuning` or "split" (the tuning is folded into the sibling's next song).
- No canonical setlist lists `Tuning` as a song. Where tapers list "tuning" in their own notes, it is still tuning.
- The 9 long tuning files (Disco Biscuits, Kimock, Furthur) are tuning by every source.
- Closest to music: `Mexican Hat Dance Tuning` (GD 1972-09-28, 60 s). It is NOT denied, because it has a non-deny part; R keeps it.

## (c) Spam safety
- **No URL, @handle, "follow", "download" or spam-shaped file exists among the 3,547 short-only drops.** The regex's only hits were taper footnotes (`@@` on JRAD tags) and the promo/commercial files above.
- **Spam is not in this arm's scope.** The `FOLLOW-ME @BYPIKENO.mp3` class is caught by the convention-mismatch arm, which R leaves untouched.
- **Non-performance items exist, and the deny extra catches them:** the 16 files above (commercials, promos, station IDs and plugs, house/PA/intro music).
- **What R does keep:** 21 radio-broadcast spoken files (DJ talk, interviews). These are part of an FM broadcast recording, not band content. They are kept and listed for the hand-check.

## (d) Replay: holds cleared / added (1,716 R shows)

| variant | cleared | added | flags changed | same |
|---|---|---|---|---|
| R, coverage as today | 20 | 147 | 55 | 1,494 |
| **R, re-admitted tracks out of the coverage denominator** | 19 | **102** | 55 | 1,540 |
| R+crowd, coverage as today | 20 | 141 | 55 | 1,412 |
| R+crowd, out of coverage | 19 | 98 | 55 | 1,456 |

- **Coverage exclusion removes 48 low-confidence adds** (lowconf added 75 → 27).
- **Of the 102 remaining adds:**
  - **73 are shows with position-keyed overrides.** The inserted track shifts `overrides.titles`/`set_breaks`/`encore_after` onto the wrong tracks, which produces `unresolved track titles` and unknown-song flags. These are a simulation artifact that a filename re-key would remove.
  - 6 come from re-admitting an untagged interior file: it is a new unresolved track, a hold by design.
  - 2 lose a whole-tape positional rung, because the count changes.
  - 21 are other: re-admitted spoken titles like `Weather Delay`, `Eulogy...`, or `curfew?` move alignment or vet, and a few sets.
- **Cleared by state:** 12 delivered, 6 held, 1 voiced, 1 packaged.
- **Added by state (covex):** 69 packaged, 29 delivered, 3 held, 1 briefed.

## (e) Override renumbering exposure
- **268 R shows** have a position-keyed override at or after an inserted file; 259 under R+crowd.
- **On 130 of them (131 under R+crowd), an override title now sits on a different file with NO flag.** Examples:
  - aquariumrescueunit-1997-11-08;
  - belafleckandtheflecktones-2003-02-11, -02-21, -2007-06-29;
  - billystrings-2018-07-20;
  - blackberry-smoke-2014-11-21, -2024-05-17;
  - bandofheathens-2009-07-27.
- **R cannot ship without re-keying positional overrides by filename**, plus a migration of existing `overrides.json`. This is 268 shows here, against 81 for the census-1 union arm.

## (f) Re-delivery split (R; shows)
Gain classes:
- **severe:** at least one re-admitted file is music, or a fragment/untagged file inside a `>` chain.
- **minor:** spoken, crowd, mixed or untagged only.

| state | severe | minor |
|---|---|---|
| voiced | **37** | **31** |
| delivered, unvoiced | 399 | 709 |
| packaged | 150 | 257 |
| held | 47 | 75 |
| briefed | 2 | 9 |

- **Lists** (each row: slug, then re-admitted files as name, seconds, tag, kind):
  - `~/.llama-harness/piece45/voiced-severe-R.json` (37 shows);
  - `~/.llama-harness/piece45/voiced-minor-R.json` (31 shows);
  - R+crowd versions under `-R+crowd.json` (37 / 29).
- **My read of the 37 voiced-severe: about 34 are real music.** Mostly GD `St. Stephen`/`Drums`/`Space`/`WRS Prelude`/`Slipknot!` pieces, `Funiculi Funicula`, `Hey Jude`, `La Bamba`, plus soulive `Sex Machine`. Doubtful: `Mexican Hat Dance Tuning`, `Dead battery`, `"Get Down From The Balcony"`, `Let Phil Sing Rant`.

## (g) Hand-check packet
- **`~/.llama-harness/piece45/packets/r/`:** `packet.jsonl` (41 rows) + `INSTRUCTIONS.md`. The schema asks keep/drop under Shawn's direction, whether R decided right, and the kind.
- **Strata:**
  - music 7, fragment 3, spoken 7, spoken-broadcast 3, crowd 4, mixed-with-tuning 3;
  - untagged-interior 5, untagged-edge 2;
  - deny-list tuning/fade/silence 4, deny non-performance 3.
- **No spam suspects exist to sample.** The non-performance stratum stands in for them.

## Open questions for Shawn
1. **Crowd-only short files** (315: `Crowd`, `Encore Break`): keep (R) or drop (R+crowd)? They behave like tuning, a gap between songs, but they are performance ambience.
2. **Radio-broadcast talk** (21 files, DJ intros, interviews): keep as part of the broadcast, or add `DJ`/`interview` to the non-performance deny?
3. **Untagged interior files** (138): keeping them adds an unresolved-title hold each. Interior-only (R) or drop all? Edge files are already dropped.
4. **Override re-keying is a precondition** (268 exposed, 130 silent mis-titles). Re-key by filename at migration, or exclude those shows from the first apply?
5. **Re-delivery:** 1,108 delivered-unvoiced shows change (399 severe), which is cheap. Re-voice the 37 voiced-severe now, and park the 31 voiced-minor?

## Recommendation
- **R with the non-performance extra, coverage exclusion and filename re-keyed overrides.** The deny list drops no music I could find, and the spam check is clean.
- **R+crowd is the safer cut** if Shawn agrees crowd breaks are tuning-like. It costs nothing in music.
- **Build-blocking caveat:** without the override re-key, R silently mis-titles 130 shows.

## Files
All in `~/.llama-harness/piece45/`:
- `r.py` → `r_files.jsonl`, `r_summary.json`, `exempt_R*.json`;
- `arm_R{,_covex}.jsonl`, `arm_R+crowd{,_covex}.jsonl` (replays) → `r_cmp.py` → `r_cmp.json`;
- `voiced-{severe,minor}-R{,+crowd}.json`;
- `r_packets.py` → `packets/r/`.

**Re-run:**
```
cd ~/.llama-harness/piece45
PY=/Users/shawn/projects/llama/.venv/bin/python
$PY r.py
for k in R R+crowd; do
  $PY dump.py --exempt exempt_$k.json --out arm_$k.jsonl
  P45_COV_EXCLUDE=1 $PY dump.py --exempt exempt_$k.json --out arm_${k}_covex.jsonl
done
$PY r_cmp.py && $PY r_packets.py
```
