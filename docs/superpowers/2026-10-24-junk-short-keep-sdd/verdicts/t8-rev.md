# t8-rev: Task 8 review (packets / score / sibvocab), 5d3e452..76c1830

### Spec Compliance

- ✅ **Spec compliant.** All three subcommands exist with the interfaces in the brief:
  - `packets` builds the strata and sizes from spec 6(c) (`scripts/short_keep_probe.py:76-78`).
  - Kept/dropped come from the candidate's membership, not `r1_dec` (`:435-438`). `rule_would` comes from that same membership (`:203` in the diff).
  - Every `r_packets.py` item field is present, with `rule_would` in place of `rule_R_would`. Neighbours come from cached metadata via `CacheOnlyIA`, and the description is cut to `[:3000]`.
  - `score` writes `score.md` with the four parts of the bar (`BAD_KEPT`/`BAD_DROPPED`/`RIGHT_BAR`, `:81-83`; `passed` at `:494`), every wrong row, and `first10.md`.
  - `sibvocab` uses the brief's regex character for character, and the `tagged` + `jc is None` filter.
  - Protected names (global constraints): the diff touches only `scripts/`, and `llama.junk` is only imported (`length_seconds`). None of the untouched constants or functions appear in the diff.
- ⚠️ **Cannot verify from the diff** (for Task 9 and the controller, not a Task 8 defect):
  - The spec's kept strata are kinds `music`/`music-fragment`/`spoken`/`mixed-with-tuning`. The packet therefore never draws the 16 census rows that r1 keeps with kind `crowd` (13), `non-performance` (2) or `spoken-broadcast` (1). Examples: `Crowd Check`, `Unity College chanting`, `Banter Promote CD`, `Stage Banter: Consummation Station`. The "zero kept non-performance" part of the bar only probes rows whose census kind is something else. This follows the spec as written and needs no code change. Task 9 should say it in `acceptance.md`.
  - The spec's fourth part of the bar ("every wrong row in an accepted class (section 7) or fixed before merge") is a human judgment. `score.md`'s `PASS` covers only the three automated parts.

**Checks I ran:**
- **Real-data dry run.** I built a proxy candidate from `r1/arm_r1.jsonl`: `filenames` = its track files, `short_kept` = r1 `keep*`. I ran `packets` on it, read-only against `~/.llama`, with output in my scratchpad. Result: 60 rows, every stratum full at its spec size, and each kept stratum's `census_kind` matches its stratum.
- **Neighbours over all 3,547 reference rows.** Every row resolves its `show.json` identifier and its `md_<id>.json`. No row has empty neighbours. Every row has exactly one `this`. 71 rows have an empty description (the item has none).
- **`sibvocab` on the real file.** 630 of 5,024 kept sibling short tags match. The 5,024 total equals the figure in spec section 8, premise 3.
- **Bar arithmetic.** `54/60 >= 0.9` is `True` in floats, as are 27/30, 45/50 and 63/70.

### Strengths

- The derivation of kept (`sk = dict(zip(filenames, short_kept))`) and the skip (`:438`) handle two cases correctly. The skip leaves out a file that is in the candidate show but was not kept by the short rule (an operator re-admission). The 173 operator-included rows that r1 keeps still count as kept, because `filter_files` marks a rule-kept file as `short_kept` before readmit (`junk.py:472`).
- Shuffling all rows after drawing the strata (`rng.shuffle(items)`) makes `first10.md` a mixed sample for the operator's premise-2 look. The source script left rows grouped by stratum, which would have made rows 1-10 all music.
- The draw is deterministic: each pool is sorted by `(slug, name)` before the seeded shuffle, so it does not depend on the order of `r1_files.jsonl`.
- `score` fails loudly when an answer is missing (`:494`), and a malformed answers file is a Refusal (exit 2). A fenced or garbled Sonnet output therefore cannot score as a pass.
- `test_sibvocab_filters_kept_tags` pins `jc` non-null, untagged, the `\bdj\b` word boundary (`Odjinn`) and a `missing` sibling.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **`scripts/test_short_keep_probe.py:403-440` (`_packet_world`): the fixture cannot tell candidate membership from `r1_dec`, so the task's central derivation has no test.**
   - The fixture's candidate keeps exactly the rows whose `r1_dec` is not `drop-*` (`:428`). It never has a file in the candidate show without `short_kept`.
   - Scratch-copy mutation, with the sentinel proving the copy was the code under test:
     - **M1:** `kept = bool(sk.get(e["name"]))` replaced by `kept = not e["r1_dec"].startswith("drop")`. Predicted to survive; **survived** (4 passed).
     - **M2:** the `continue` at `:438` removed. Predicted to survive; **survived**.
     - For contrast, removing the placeholder precedence, emptying `BAD_KEPT`, swapping `BAD_DROPPED` and dropping the missing-answer clause were each caught.
   - **Why it matters.** Under M1 the packet grades the reference arm instead of the branch. The candidate exists precisely because it may differ from r1 (Task 9 Step 4 lists those differences), and no test would notice.
   - **Fix:** add three fixture rows and assert their outcomes:
     - an `r1_dec="keep"` row that the candidate drops: not drawn, or at least never `rule_would: keep`;
     - an `r1_dec="drop-junk"` row (kind `music`) that the candidate keeps: drawn into `music` with `rule_would: keep`;
     - a file in the candidate's `filenames` with `short_kept` false and `r1_dec="drop-junk"`: never drawn.
2. **`scripts/short_keep_probe.py:349-350` (INSTRUCTIONS): an un-ruled direction is attributed to the operator.**
   - The banter line reads "Stage banter and band talk are KEPT: a ~30 s band intro mid-set, stage announcements, **tuning chatter that is the band talking to the crowd**."
   - The tuning phrase appears in neither the brief's list of rulings, nor `r-INSTRUCTIONS.md`, nor `decisions-r1.md`, nor the spec. I grepped all four for "chatter".
   - It sits under "Operator direction (Shawn, 2026-10-23)". It is also in tension with the next bullet, "tuning-only audio DROP".
   - **Why it matters.** It invites a checker to call a bare `Tuning` tag "keep". That would score a `drop-junk` row (8 in the packet) as `rule_right: false`, and the bar allows at most 6 wrong rows. The instrument could fail falsely on wording the operator never gave.
   - **Fix:** delete the phrase. If mixed tags need saying, use spec 2.3's own example: "a mixed tag such as `tuning/banter` or `intro/tuning` is kept".

#### Minor (Nice to Have)

1. **`scripts/short_keep_probe.py:400-404` (`dropped_today`): the field covers only short-arm drops.**
   - `_neighbours` sets it to "name is in `r1_files` for this slug". The source script used `bool(reasons)`, meaning dropped today for any reason. The implementer flagged this.
   - Measured against `arm_r1`:
     - 59 neighbour entries in 37 of the 3,547 rows are files r1 does not keep but are shown `dropped_today: false`;
     - 735 entries are files the candidate keeps but are shown `dropped_today: true`. That is right for "today", but the checker cannot see the candidate's own decision on a neighbour.
   - About 0.6 rows of a 60-row packet are affected. `position` is given directly, so the impact is small.
   - **Suggestion:** add `kept_now` (the name is in the candidate's `filenames`) beside `dropped_today`.
2. **`scripts/short_keep_probe.py:435`: a row lacking `short_kept`, or with a length mismatch, is silently misread.**
   - With `sk = dict(zip(..., c.get("short_kept") or []))`, a row lacking `short_kept` (for example the base arm passed as `--cand` by mistake) yields `{}`. Every file in the show is then treated as dropped, which contradicts "dropped = not in it". A length mismatch truncates silently.
   - The only signal is the "short strata" print.
   - `repro` in the same script refuses a replayable row lacking the fields. Refuse the same way here, and test membership with `name in set(c["filenames"])`.
3. **`scripts/short_keep_probe.py:389`: `except Exception: return [], ""` swallows a cache miss, or a JSON error, and returns a row with no neighbours and no description.**
   - It does not trigger on real data (0 of 3,547).
   - Still, count `ia.misses` and identifier-less rows in the stdout line rather than shipping hollow rows silently.
4. **`scripts/short_keep_probe.py:477`: the answers dict is built as `{a["row"]: a ...}`.**
   - A duplicated row number (two checkers' halves concatenated with an overlap) is silently last-wins.
   - An answer for a row not in the packet is silently ignored.
   - A `rule_right` that contradicts `decision` vs `rule_would` is taken at face value.
   - **Suggestion:** refuse duplicates and unknown rows, and list inconsistent rows in `score.md`.
5. **`scripts/test_short_keep_probe.py:497-538`: the exactly-90% boundary has no test.**
   - The tests use 10/11 and 9/11. **M5** (`>=` to `>`) **survived**.
   - 54/60 is a plausible real outcome. Add a 9-of-10 case.
   - Also untested: a kept `spoken-broadcast` row and a dropped `segue-or-continuation`/`fragment` row. Only `non-performance` and `song` are tested.
6. **`scripts/test_short_keep_probe.py:466` only asserts `1 <= len(nb) <= 5`.**
   - **M6** (a ±1 window instead of ±2) **survived**.
   - The fixture has 150+ files, so assert `len(nb) == 5` for an interior row.
7. **`scripts/short_keep_probe.py:505-514` (`first10.md`): two gaps for the operator's look.**
   - It prints the grader's answer beside each row, so the operator's premise-2 check is not blind (anchoring risk). Consider putting the answers in a separate trailing section.
   - It omits `position` and `floor_sec`, which decide the untagged rows.
8. **`scripts/short_keep_probe.py:340-341` (INSTRUCTIONS): the rule summary omits crowd and applause.**
   - It lists junk as "(tuning, dead air, silence, tape flip, fade, noise, soundcheck)". `JUNK_PART` also drops crowd/audience/applause/cheering and encore or set break.
   - It is wording only, because the direction bullets cover crowd. Add "crowd, applause".
9. **`score.md` labels the result `PASS` without noting that the spec's fourth part (wrong rows in an accepted class) is still open.** One line would prevent the label being read as the whole 6(c) bar.

### Assessment

**Task quality:** Needs fixes

**Reasoning:**
- The code is correct on real data:
  - the strata fill at the spec sizes;
  - every neighbour and identifier resolves;
  - the bar arithmetic holds at 54/60;
  - `sibvocab`'s total matches the spec's 5,024.
- Two things need fixing before Task 9 relies on it:
  - The kept/dropped-from-candidate derivation, the one thing that makes this the branch's hand-check rather than the reference's, has no test (M1/M2 survive).
  - The checker instructions carry an invented "tuning chatter" direction attributed to the operator, which could tip `drop-junk` rows wrong and fail the bar falsely.
