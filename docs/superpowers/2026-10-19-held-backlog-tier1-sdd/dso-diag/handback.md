# dso-diag handback: darkstarorchestra-2012-05-19

Status: DONE (read-only). No commits and no worktree edits. Code read from a snapshot of `4cd1ebc` (`git archive`), removed afterwards. Model: Opus.
(The `M brief.py` / `M test_stage_brief.py` in `git status` belong to the concurrent agent, not to me.)

## Verdict
**This is a guard false alarm.** The fresh briefing describes the right show correctly. The cause is the show's own titles: 21 of 23 still carry a **hyphen-separated track number** (`01-Hell In A Bucket`). Neither of the existing strip predicates removes that form (`_TRACK_NUM_PREFIX` needs whitespace, and `_GLUED_NUM_PREFIX` needs a digit followed directly by a letter). The LLM correctly dropped the numbers in `mentioned_songs`, and 3b's exact matcher then could not find `hell in a bucket` among `01 hell in a bucket`. Research is right, and the brief prompt did not fail.

## Answers

**Q1. What setlist the briefing describes, and where it came from.** The briefing describes the tape's own setlist, in tape order. That setlist is DSO's recreation of the Grateful Dead's 9/12/1991 Madison Square Garden show, plus the bonus cuts.
- `~/.llama/cache/md_DSO2012-05-19.json`, `metadata.description`: `"First Set\n1- Hell In A Bucket\n2- Bertha … 8- Let It Grow\nSecond Set\n9- Sugar Magnolia … 18-Sunshine Daydream\nEncore\n19-Box Of Rain\nBonus Cuts\n20-Saint of Circumstance\n21-China Cat\n22-I Know You Rider\n23-Satisfaction\n\nOriginal show was 09/12/1991\nMadison Square Garden, NYC"`.
- `briefing.json` `mentioned_songs` is the 23 MP3 tag titles with the `NN-` removed, in order. It even keeps the tag misspelling `Follish Heart` and the mistag `Gotta Be Heaven`. Its `cautions` correctly flag both: track 20 is really Saint of Circumstance, and `Follish` is a misspelling.
- `research.md:17`: "DSO's two sets and Box of Rain encore follow the 9/12/91 setlist exactly …". `research.md:50`: "Track 20 is labeled "Gotta Be Heaven" but is actually **Saint of Circumstance**". `reviews.json` reviewer wjcudeadhead: "#20 is actually... Saint of Circumstance".
- `vetting.json` agrees: it asserts the same songs, sets 2, date 2012-05-19, and has `flags: []`.

**Q2. show.json's titles and title_sources.** All 23 tracks have `title_source: "tags"`. The titles are **real titles with the prefix still on**: `01-Hell In A Bucket`, `03-Walkin' Blues`, … `22-I Know You Rider`. Only `Bertha` and `Satisfaction` are clean, because their raw tags carry no number, and those are exactly the two songs the guard did *not* flag.
- The raw tags are identical in the cache (VBR MP3 and 24bit Flac), for example `'01-Hell In A Bucket'`. The one exception is track 20: the MP3 tag is `'20-Gotta Be Heaven'` and the FLAC tag is `'20-Saint of Circumstance'`. Format recovery does not fire because the MP3 `title_fraction` is 1.0.
- The Tier 1 replay did **not** change the titles: `~/.llama-harness/G2-cand-held.json` has `title_changes: []` for this show.
- Why the prefix survives (`packages/llama/src/llama/titles.py`):
  - L167 `_TRACK_NUM_PREFIX = ^\d{1,3}(?!\d)[.)\-:]?\s+(?=\S)` needs whitespace after the separator. `01-Hell` has none.
  - L187 `_GLUED_NUM_PREFIX = ^\d{2}(?=[A-Z][a-z])` needs the letter immediately after the digits. `01-H` has a hyphen in between.
  - So both votes in `clean_tag_titles` (L220/L233) count 0 and nothing is stripped.
- I reproduced the exact 21 flags with snapshot code. `normalize_song('01-Hell In A Bucket')` gives `'01 hell in a bucket'`, and `song_components` gives `['01 hell in a bucket']`. `known_song('Hell In A Bucket', …)` is False, because `stages/brief.py:119-126` is exact plus whole-component matching only ("No fuzzy, loose or subphrase matching").
- By contrast, vet's matcher (`stages/vet_research.py:118-126` `_title_match`, a contiguous token-run containment) **does** accept `hell in a bucket` inside `01 hell in a bucket`. So vet passed and brief failed on the same titles.

**Q3. Why "the old stored briefing passed".** The premise is wrong. **There was no old briefing.**
- The G2 row has `stored_brief_guard: null`. `replay.py:460-461` sets that field only `if ws.briefing_json.exists()`, and `briefing_guard` always returns a list, so `null` means no `briefing.json` existed.
- The show was held at gather on 2026-10-15 for `venue mismatch: archive 'Mighty High Festival-Tuxedo Ridge' vs jerrybase ''`. That is the only stored flag; the jerrybase row for this date has an empty venue column. `pipeline.py:90-92` returns before `run_brief` when a show needs review, so the show was **never briefed**.
- Tier 1's 1a (a blank jerrybase venue is no evidence) removed that flag. That unblocked the brief leg for the first time. The harness classified the show `needs-brief`/`fresh`, which is a prediction conditional on an LLM call it cannot make, not a prediction that the show clears.
- The prefix defect was latent all along, hidden behind the venue hold.
- Timing correction: all of the new files (`briefing.*`, `show.json`, `vetting.json`, `notes.json`) are stamped **09:37**, not 09:5x.

**Q4. One-sentence verdict.** It is a guard false alarm caused by a title-cleaning gap (a hyphen-separated `NN-` track number survives into `show.json`); the briefing and research describe the right show accurately. Evidence is in Q1 and Q2.

**Q5. Proposed fix (not built).**
- **Where:** `packages/llama/src/llama/titles.py`, as a third predicate and vote beside `_TRACK_NUM_PREFIX` and `_GLUED_NUM_PREFIX`. It must not loosen either of them (both are protected). It also needs a `stripped … track number` operator note in `gather.py` ~L1131-1140, mirroring 2c's.
- **What:** `_SEP_NUM_PREFIX = re.compile(r"^\d{1,3}[-_](?=\S)")`, stripped with count=1 only when the same recording-level vote passes (`_ENUMERATED_MIN_FILES` 3, `_ENUMERATED_MIN_COVERAGE` 0.8). Two details matter:
  - Do **not** copy 2c's `[A-Z][a-z]` lookahead. On this show it would leave `22-I Know You Rider` unstripped, which is still one false flag. The separator itself is the disambiguator here.
  - `_` must be included: the Mountain Goats tapes use the `01_Title` form.
- **Why here and not in the guard:** fixing the titles also fixes what goes on air. Today several packaged and delivered shows ship prefixed titles in their manifests and pass the guard only because the LLM happened to echo the prefixes; see Blast radius. Relaxing `known_song` instead would hide the DSO flag and leave the broadcast defect in place.
- **Risk:**
  - A real title shaped `NN-…` or `NN_…` on an enumerated tape. `12-Bar Blues` is safe because the strip is count=1 (`07-12-Bar Blues` becomes `12-Bar Blues`). A lone `24-7` on an unnumbered tape is safe because of the vote.
  - The real exposure is a non-enumerated tape where ≥80% of the titles happen to start `\d{1,3}-`. That is implausible, but it should be measured.
  - Packaged shows whose titles change will show up as `clean-changed` and need a redo from gather plus a re-deliver. Their emcee scripts may name the prefixed titles.
- **Measurement:**
  1. A census over `~/.llama/cache/md_*.json`. I ran a quick pre-check with snapshot code (VBR MP3 tags, ≥3 tagged files, excluding items already passing the spaced or glued vote). Of **12,249** items, `^\d{1,3}[-_](?=\S)` passes the vote on **9**: DSO2012-05-19, DSO2009-07-18 (`02-Bertha--]`, which has residue), MountainGoats2012-06-27, tmg2017-06-02, tmg2019-05-08, BL2014-04-20, rhd2008-06-20.mk4, TheDead2009-04-29 (`101-touch of grey`), and gd2009-04-28. All of them look like genuine enumerations. The 2c-style `NN[-_]Upper+lower` form passes on only 4. The full census should hand-check every stripped title, as A1 did.
  2. A `replay_holds.py run --all` base-vs-candidate comparison. `title_changes` should be confined to those shows, with this one moving from held to cleared after a fresh brief.
  3. Mutants: remove the `_` from the class; add the `[A-Z][a-z]` lookahead (should be caught by an `I Know You Rider` case); drop the vote; drop count=1.
- **Separate, smaller follow-ups seen here (not causes):**
  - `D.NN - Title` (davealvin-2018-12-09, `1.02 - Downey to Lubbock`, packaged with these titles) and `D-NNN Title` (builttospill-1997-10-13, `1-002 Joyride`) are further enumeration forms that none of the three predicates covers.
  - DSO's `structure.conflicts` lists the raw `1- Hell In A Bucket` lines, so the description parser kept the numbers too. That is why coverage is 0.0. Jerrybase anchoring still produced the correct breaks [8,18].
  - Tracks 20-23 (bonus cuts) are labelled `encore`. The briefing cautions about this.

## Blast radius (read-only scan of `~/.llama/shows`)
- **Shows held right now by this same false alarm: one** (this show). It is the only show in the library whose stored flags include `briefing mentions unknown song` while its titles carry a numbered prefix.
- **DSO:** 109 shows with a `show.json` (61 packaged, 48 held). I re-ran `briefing_guard` with snapshot code over every DSO briefing:
  - all **61 packaged** pass;
  - 47 held have no briefing;
  - 1 held passes;
  - 1 held fails (this show).
  - The library has no pattern of DSO briefings describing the recreated Dead show "instead of" the tape. This show is the only DSO tape with prefixed titles.
- **Latent, already shipped: packaged shows whose manifests carry prefixed titles.** Each passed the guard only because its briefing echoed the prefixed titles verbatim (`mentioned_songs` = `02-Do You Still Love Me`, …), or named no songs:
  - ryanadams-2017-05-06
  - theblacklillies-2014-04-20 (library audio still present, so probably not yet delivered)
  - mountaingoats-2017-06-02 (`01_…`, `mentioned_songs` = [])
  - mountaingoats-2019-05-07 (`00_…`)
  - mountaingoats-2019-05-08 (39 of 45 tags prefixed)
  - davealvin-2018-12-09 (`1.02 - …` form, not covered by the proposed regex)
  - Five of these have an empty library `package/audio`, consistent with deliver's purge.
  - The guard's verdict on these shows depends on whether the LLM happens to strip the prefixes. A fresh brief on any of them, for example after any `fix`, can flip them to held exactly as DSO did.
- **Held, numbered, and not briefed yet:** mountaingoats-2012-06-27 (`01-…`, held for unresolved titles) is the next likely DSO-style flip. builttospill-1997-10-13 and robertwalters20thcongress-2009-04-29 carry other numbered forms.
- **Not related:** railroadearth-2013-*/2014-* use the glued `01Title` form that 2c handles. billystrings, blackberry-smoke, joerussosalmostdead and railroadearth-2019-04-08 show `NN Title.mp3` strings, but those are `title_source: unresolved` placeholders, not tag titles.

## Commands and artifacts
- Snapshot: `git archive 4cd1ebc | tar -x` into `$TMPDIR/dso-snap-uF5wL9` (removed). Code run with `PYTHONPATH=<snap>/packages/llama/src:<snap>/packages/herder/src .venv/bin/python` and `PYTHONDONTWRITEBYTECODE=1`. `llama.__file__` resolved inside the snapshot.
- Scan scripts (read-only): `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-held-backlog-tier1/14455d61-96ec-47d7-bf0b-86cfb6e7a6b5/scratchpad/scan.py` and `…/scratchpad/census.py`. Their outputs are teed into `dso-diag.log`.
- No `llama` command was run. `~/.llama` was only read.
