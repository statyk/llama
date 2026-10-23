# Piece 3 title hand-check: common brief

You are hand-checking track titles for **llama**. llama is a tool that takes concert recordings from the archive.org Live Music Archive and packages them for a radio station. Each show has a list of audio tracks, and llama works out a song title for each one. The candidate fixes being considered all fill or change track titles automatically.

The operator's goal is to **clear held-for-review shows without hand work, while shipping titles that are right**. Your judgements decide which fixes are accurate enough to run automatically. Treat a wrong title as worse than a missing one: a missing title holds the show for a human, while a wrong title can ship on air silently.

## What you read
Each show is one packet: `~/.llama-harness/piece3/census/packets/<CLASS>/<slug>.md`. A packet holds:
- the per-track table: filename, duration, the title current code ships, `title_source`, and the class-specific candidate columns;
- the canonical setlist llama built;
- the description the uploader (the "taper") wrote for the recording;
- the other-format copies of the same item;
- notes and flags;
- the overnight adjudicator's verdict, when there is one.

Optionally, you may also read the cached archive.org metadata for the item, at `~/.llama/cache/md_<identifier>.json`. It contains the file list with each file's tags (`title`, `track`, `length`, `format`, `original`). Read it, never write it.

## How to judge "right"
- **The taper's description is presumed correct** unless there is clear contrary evidence (operator ruling). Its numbered list, if it has one, is usually the play order.
- **Durations matter.** A 40-second track is tuning, crowd or an intro, not a 9-minute jam. Two adjacent tracks carrying the same song title usually means the titles are shifted by one, unless the song really was split across two files (a "Jam > Song" pair, or a song cut at a disc change).
- The file's own raw tag, when it is a real title, is strong evidence of what that file holds.
- These titles are REAL and acceptable: "J", "Untitled #12", numeric titles such as "420", "1 in 7", "2:22", "I-55" and "7-11", and a band's self-titled song.
- Spelling or punctuation variants of the right song count as **right** ("Sailin On" equals "Sailing On").
- A segue pair shipped as one title of only one of the songs counts as **right-partial**.
- If the evidence does not let you decide, say `cant-tell`. Do not guess. A confident wrong verdict is the worst outcome here.

## Output
Write one JSON object per show, one per line, to `~/.llama-harness/piece3/handcheck/<AGENT>/rows.jsonl`:
```json
{"slug": "...", "class": "<CLASS>", "tracks": [{"n": 3, "candidate": "<title the fix would ship>", "verdict": "right|right-partial|wrong|cant-tell", "correct_title": "<your best reading, or null>", "why": "<one short line of evidence>"}], "show_verdict": "<class-specific, see your section>", "note": "<anything odd, one line>"}
```
List in `tracks` only the tracks your class section names, not every track.

Work through your packet list in order. Append each show's row as soon as you finish it. Every few shows, echo a progress line into `~/.llama-harness/piece3/handcheck/<AGENT>/<AGENT>.log`. Create that log file as your very first action.

When all shows are done:
1. Write `~/.llama-harness/piece3/handcheck/<AGENT>/handback.md`: counts per verdict, the 3-5 most instructive examples, and any pattern you noticed (under 40 lines).
2. Touch `~/.llama-harness/piece3/handcheck/<AGENT>/done`.
3. Return the handback text as your final reply.

Never name a file starting with REPORT/SUMMARY/FINDINGS/ANALYSIS.

## Hard limits
- Read-only everywhere except your own `handcheck/<AGENT>/` directory.
- Never run `llama`, `emcee`, git-mutating commands, or anything that writes under `~/.llama`.
- No web access is needed. Work from the packets and the cache.

---

## Class S: the whole-tape `setlist` rung (positional copy)
When the canonical setlist has exactly as many items as the tape has tracks, llama copies canonical item N onto track N for every track without a usable tag, with NO content check. The column `canonical item N` shows what it copies. Rows with `title_source` = `setlist` are the copied ones. The fear is an off-by-one: an extra filler track (crowd, tuning, intro) plus a song missing from the tape keeps the counts equal while every copied title lands one track late.
- **`tracks`:** every track whose `title_source` is `setlist`. Is the copied title right for that file?
- **`show_verdict`:**
  - `all-right`;
  - `shifted` (copied titles systematically off by a position);
  - `some-wrong-not-shift`;
  - `cant-tell`.
- **`note`:** if any are wrong, say what a simple automatic check could have caught it. Candidates: adjacent duplicate title, a real raw tag disagreeing with the canonical item at the same position, a short filler-length track given a song title, a raw tag naming a song the canonical list has at a different position. Also say whether that check would WRONGLY fire on a show you judged all-right. That is the key number: a check that holds good shows costs the operator time.

## Class C: same item, lossless original vs MP3 derivative tags
An archive.org item often has both FLAC originals and MP3 derivatives, matched file-for-file by filename stem. The packet's C columns give the delivered (usually MP3) tag and the other-format (usually FLAC) tag for each stem, plus a `category`. The candidate fix: **per track, prefer the other-format (lossless) title when it is a real title and the delivered one is blank, a placeholder, or different.**
- **`tracks`:** every track where the two tags differ (category not `(same)`). `candidate` = the other-format title. Is it right? In `why`, also say whether the delivered title was right.
- **`show_verdict`:**
  - `fix-helps`: the fix makes the show's titles more right;
  - `fix-neutral`;
  - `fix-hurts`: the fix would make a right title wrong;
  - `cant-tell`.

## Class D: the description is a numbered list with one title per track
The candidate fix: copy description line N onto track N by position, for tracks that are still `unresolved`. The `positional candidate` column shows the copy.
- **`tracks`:** every track whose `title_source` is `unresolved`. Is the positional candidate right for that file? Use durations, the tape's raw tags on neighbouring tracks, and the canonical setlist.
- **`show_verdict`:**
  - `all-right`;
  - `shifted`;
  - `some-wrong-not-shift`;
  - `cant-tell`.
- **`note`:** for any show with a wrong fill, would this gate have blocked it: "every track that has its own real tag agrees with the description line at the same position, and no tagged position disagrees"? Also: would that gate have blocked a show you judged all-right?

## Class A_rev: real short titles thrown away
Current code demoted a raw tag to `unresolved` because it does not look like a real title. Examples: "J", "420", "VA", "I-55", "12-28-99". The candidate fix would keep that tag as the title.
- **`tracks`:** each track named in the `demoted tag` column. `candidate` = the demoted tag. Is it the real title of that track? Use the description, the canonical setlist and the operator's overrides as evidence.
- **`show_verdict`:**
  - `fix-helps`;
  - `fix-hurts`;
  - `mixed`;
  - `cant-tell`.

## Class A: junk inside a title that currently passes as real
The shipped title carries a timestamp, filename residue, a track number, a set/disc prefix or `.wav`. Examples: `06:58 - Who Took the Happiness Out?`, `Greensky Bluegrass - d2t07-In Control`, `20-To Be Without You`, a bare `01.`.
- **`tracks`:** each track the `A shape` column marks. `candidate` = your proposed cleaned title: strip ONLY the junk; never rewrite the song name. Is the cleaned title the right song?
- **`show_verdict`:**
  - `strip-fixes-it`;
  - `strip-not-enough`: the remaining text is still not the right title, e.g. a bare `01.` leaves nothing;
  - `strip-would-damage`: the "junk" is actually part of a real title, like `20 Eyes` or `3 AM`;
  - `cant-tell`.

## Class U: effectively untagged tape, description list matches the file count
The tape has fewer than 2 real track tags. The selected description gives a list with exactly as many entries as there are files. The candidate fix copies entry N onto track N (the `positional candidate` column). The fear: the taper split or merged songs across files differently from the list (a song spanning two files, two songs in one file, a set-break or banter file the list omits, or a list entry with no file). The counts still match by coincidence, so every title after the mismatch lands one or more tracks late. The packets include up to three TAGGED sibling recordings of the same show, from other tapers, with per-file titles and durations. Use them: line up durations (a sibling's `A > B` file can equal the sum of two files here, and a set-break or banter file has a short or crowd-only duration), together with the description's own notes (e.g. "I did the best I could on tracking").
- **`tracks`:** EVERY track. `candidate` = the positional candidate. Is it the song on that file? `correct_title` is your best reading.
- **`show_verdict`:** `all-right` / `shifted` (titles systematically off by one or more from some track on) / `some-wrong-not-shift` / `cant-tell`.
- **`note`:**
  - the first wrong track number, if any;
  - whether a tagged sibling was available and decisive;
  - one line on what deterministic check would have caught a wrong case. Candidates: sibling duration alignment, description set sizes vs filename disc boundaries, a written duration on the list, a list line the files lack.
