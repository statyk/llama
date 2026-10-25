# t23-rev: review of Task 23 (docs only), range 4dd0ea6..04f68b4. Reviewer: Opus

**Assessment: Needs fixes.** There are 2 Important findings, both one-sentence text fixes, and 4 Minors. No Critical findings. The code range is empty (`git diff 4dd0ea6..04f68b4 -- packages scripts antenna` shows nothing), so the fixes are doc edits only.

## Spec compliance (t23-extra.md (a)-(m), plan Task 23 Step 1, CLAUDE.md items)

- ✅ (a) spec: 2.3 NONPERF wording (spec:191-196), the 685→691 count with the 3 census-music rows (spec:209-212), the zero-duration cross-references (spec:62, :80, :235-237), and section 7's false-positive class (spec:922-926). The implementer is right that `Exit Music (For a Film)` hits the `<x> music` alternative, not the call-sign one. That matches t10-rev's own "separately, the ruled `exit music` group".
- ✅ (b) spec 5.3 (spec:678-716): the 15a gate, ruling "2", 15b's design, 100%, and the 1,017 marked superseded. The budget sentence in this same block is wrong; see Important 2.
- ✅ (c) spec 5.4 identifier gating (spec:748-755).
- ✅ (d) spec:916-921: the ruling is verbatim and the pin test exists (test_short_keep_rule.py:183).
- ✅ (e) spec:927-928, verbatim.
- ✅ (f) CLAUDE.md:72-74 (the "marks or counts" text is gone), :333-334 "(single name only)", and the process-check limitation at spec:510-512 and CLAUDE.md:674. See Minor 1 on where the limitation sits relative to the runbook.
- ✅ (g) CLAUDE.md:1107-1115 replaces the FORMAT_BY_AUDIO sentence (no old text remains). Spec 2.6 is spec:255-286.
- ✅ (h) spec 2.6, section 7 (spec:942-946, supersession stated), CLAUDE.md:674.
- ✅ (i) spec:697-710 matches `replay._RESTORED_WORDING` and `_APOSTROPHES` term for term.
- ✅ (j) spec:593-598 and :626-628. CLAUDE.md:674.
- ✅ (k), (l) spec 2.7 (spec:298-326) and CLAUDE.md:674. The unfreezing of `blend_segues`' pooling is stated.
- ✅ (m) spec:606-608 and CLAUDE.md:674.
- ✅ Plan Step 1: the gotchas paragraph (CLAUDE.md:965-981), the piece-4 Architecture bullet (:674), the Commands entry (:225-241), the overrides bullet (:531-535) and the deliver bullet (:72-74, :87-93).
- ✅ Every filed follow-up in t23-extra appears in the CLAUDE.md bullet (briefly) and in the README (in full).
- ❌ Unchanged CLAUDE.md text now contradicts piece 4 (check 4). See Important 1.

## Strengths

- Every quoted ruling is byte-verbatim against the ledgers and acceptance.md. I checked "2", "Go ahead and add them", the NFA ruling, "Leave it, low risk and unlikely.", "Go on both. Recommendations accepted on all points", "Let's do that targeted fix" and "Why would we pick a format with 1 file for a concert containing many songs?".
- The implementer read the code, not the brief. Two examples:
  - The add guard reads SHIPPED sets.
  - `endswith(">")` covers both `>` and `->`.
- The five FW1 numbers match the orch-r4 ledger exactly: 15,607; 0/31 flips; 2,017; 23/414; 20.
- The SDD record is clean (check 6 below).
- Style is kept. The piece-4 bullet is one dense paragraph like piece 2 and piece 3, and only the eight intended hunks were touched.

## Issues

### Critical
None.

### Important

**1. CLAUDE.md:68 (unchanged text) is now false.** It reads: "With no `show.json`, `fix` still accepts `--set-*`/`--clear-*` and filename `--exclude`/`--unexclude`."
- Piece 4 makes positional edits require `show.json` (cli.py:3368-3370: `if (positional or numeric_clears) and not sws.show.exists(): refuse_no_show_json()`). The edits affected are `--set-title`, `--set-breaks`, `--set-encore`, `--suggest-titles` and a track-number `--clear-title`.
- test_fix.py:1316 pins this: "a positional set refuses and names the repair".
- At e37f670, `--set-title`/`--set-breaks`/`--set-encore` worked without `show.json`.
- An agent reading line 68 would expect `fix <show> --set-breaks 9 --no-run` to stage overrides on a pre-gather show. It does not.
- **Fix:** "With no `show.json`, `fix` still accepts `--set-venue`/`--set-city`/`--set-date`, the three `--clear-*` flags (`--clear-title` by filename only) and filename `--exclude`/`--unexclude`; a positional `--set-title`/`--set-breaks`/`--set-encore` or a track-number `--clear-title` needs `show.json` (piece 4: a number means `show.json`'s numbering). Every other flag refuses…"

**2. spec:714-715 understates the bulk-apply brief budget.** It reads: "The bulk apply budgets about 1,000 fresh briefings, plus the de-doubling's (13) and the segue donor's (371)."
- The same block measures 1,112 `fresh` over the 1,410 changed shows (spec:713; acceptance.md:347).
- FW3 (A) adds 34 reuse→fresh rows (orch-r5 ledger:53, tfw3-impl handback:27). The sentence leaves them out.
- FW4's +371 is measured against cand-d, so it adds on top of FW3's 34.
- The total is therefore about 1,112 + 13 + 34 + 371 ≈ 1,530, not about 1,384. This is the number the bulk-apply plan will size its meter waves from, and the operator is on the 5x plan.
- **Fix:** "The bulk apply budgets about 1,110 fresh briefings for the rule (Checkpoint B), plus the de-doubling's 13, the segue-bearing donor's 34 (FW3) and FW4's 371: about 1,530."

### Minor

1. **spec:468-469 and :611 (runbook step 1 of both runbooks) still say to "Confirm with the process check that no `llama` process is running".**
   - The limitation is two paragraphs below (spec:510-512), not in the step an operator follows. Plan Appendix A/B step 1 has the same wording ("must print no `llama` process").
   - Low risk: the script prints `PROCESS_NOTE` on every run (rekey_overrides.py:519, :1531).
   - Fix: append "(it cannot see an interactive loop sleeping between passes: stop that by hand)" to both step 1s.
2. **CLAUDE.md:674 (piece-4 bullet, `--restore`) says it "lists the reapply batches, runs and station destinations created since".**
   - For destinations the test is a manifest newer than the snapshot (`_station_since`, rekey_overrides.py:1300). That means re-delivered or re-voiced, not created. The bullet's very next sentence relies on the mtime reading.
   - Fix: "…and station destinations whose manifest changed since (re-delivered or re-voiced)".
3. **CLAUDE.md:164 (reapply, unchanged) says a delivered show that cleared prints `re-deliver with: llama deliver <name>`.**
   - Since piece 4 that hint is suppressed for a voiced destination, and an unreadable one prints deliver's refusal instead (cli.py:3798-3811). The deliver bullet (:93) says so, but the reapply bullet does not.
   - Fix: add "(not for a voiced destination, piece 4)".
4. **CLAUDE.md:548 (`--include` placement, unchanged) is now incomplete, not wrong.** It reads "after the junk arms and after duplicate-listing dedupe but before play-order derivation".
   - Re-admission now also follows the derivative dedupe, and an included copy wins its group.
   - Optionally add "and the derivative dedupe".
   - Nit: :1105-1106 "tried in order" now sits before a running-time choice. The next sentence corrects it.

## The implementer's 4 concerns

1. **Exit Music class:** correct. The code (junk.py:128, `exit|outro|closing ... music`) and t10-rev both put it under the `<x> music` alternative. The spec describes the two classes separately, as the code behaves. No change needed.
2. **Segue numbers:** verified.
   - G5's 23 removed / 0 real lost is tfw4-fix1:69/:86, after the leading-word narrowing.
   - "about 1,050 shows (as first built)" is 1,055 (orch-r5:66).
   - "about 2,000" is 2,124 − 60 + 12 − 6 ≈ 2,070.
   - 6 real lost and +371 match orch-r5:77.
   - One unstated cost: the leading-word form reopens 1 false mark (warrenzevon-1994-02-07 #16, tfw4-fix1:73). That is optional to add to 2.7.
3. **Spec 5.2's counts left as the original:** acceptable as design-time numbers. A one-line "(design-time; Checkpoint C counts in acceptance.md)" after spec:644 would stop a reader from sizing from 1,537. The Checkpoint C arm says changed 1,545.
4. **Reapply for packaged/delivered shows not built:** correct per the plan's Open gaps. CLAUDE.md:674 and the README say so.

## SDD record (check 6)

- orch, orch-r1 … orch-r4 `ledger.md` are byte-identical to $D (cmp). orch-r5's copy is an exact prefix of the live ledger (cmp EOF at byte 23,326), as the README says (it re-syncs at the finish).
- `orch-r5/checkpoint-c.md` and `orch-r4/fw1-rulings.md` are byte-identical to their sources.
- All 90 `verdicts/*.md` are byte-identical to `$D/<task>/handback.md`. Every task dir with a handback at copy time is covered. The only dir without one is `tfw2-rev` (dead claim). `t23-impl` was written after the copy, as the README says.
- No file is over 256 KB. The 100 files total 905,487 bytes, which is 900,003 plus the 5,484-byte README, as the README states.
- No source tree, diff, brief or log is committed: every path is a ledger, the README, mutation.md, checkpoint-c.md, fw1-rulings.md or a verdict. mutation.md is untouched.
- The README is accurate:
  - The 6 session ids match each ledger's header.
  - Review mode: Opus, with the Sonnet hand-check checkers t9-hc1, t9-hc2 and t10-a4hc noted (orch-r1:40, :62).
  - Contents, the not-committed list and the filed follow-ups (all items from t23-extra, plus Q5) are complete.

## Fact-check table (checked against code at 04f68b4, acceptance.md, ledgers)

| # | claim (location) | result |
|---|---|---|
| 1 | `junk._apply_short_rule`; `short_keep: bool = True`, False = v2.17.0 (CLAUDE.md:674) | checked (junk.py:201, :539, :600) |
| 2 | reason `spam-shaped name or tag` (gotchas) | checked (junk.py:106) |
| 3 | tripwire: URL/`www.`/domain/`@name` in stem or either tag; follow/download/subscribe stem only; `follow me/us` tag only | checked (junk.py:135-137, :160-164) |
| 4 | every part junk, `intro/tuning` kept; zero duration stays dropped | checked (junk.py:150-157, :217) |
| 5 | untagged kept only when interior; edge and filename-junk drop | checked (junk.py:250-255, short_verdict) |
| 6 | `ordering["short_kept"]`, `Track.short_kept`, `_songish_coverage ... and not t.short_kept` | checked (junk.py:676; models.py:181; structure.py:1191) |
| 7 | operator's 239 includes; 173 already included | checked (spec:54, :83) |
| 8 | Overrides types `dict[str,str]`, `list[int|str]|None`, `int|str|None` | checked (models.py:223-225) |
| 9 | one resolver `override_keys.resolve_positions` via compute_gather | checked (gather.py:1286 in title_inputs, called at :1803) |
| 10 | message `overrides.json uses track-number keys; run the migration`; mixed; dangling in one message | checked (override_keys.py:114-127, :152-167) |
| 11 | lax-int legacy examples; vendored v2.17.0 model; old model rejects migrated | checked (override_keys.py:11-15; test_override_keys.py:4, :70) |
| 12 | staleness refusal text `re-gather under the new rule first (llama redo <show> --from gather)`; shared helper `gather.final_kept` | checked (cli.py:1436-1443) |
| 13 | `fix --exclude` refuses a keyed file naming the `--clear-*` flag; clears skip staleness; `--clear-title` takes a filename | checked (cli.py:1471-1475, :3367-3409, :3316) |
| 14 | `replay.briefing_reusable`, `_RESTORED_WORDING`, vocabulary list, windows, U+02BB/U+02B9 | checked (replay.py:278, :303-385, :447) |
| 15 | 1,014/1,014, 901/901, name arm 406, 1,112/298/0, "~98%"→100% | checked (acceptance.md:334-349) |
| 16 | budget "about 1,000 + 13 + 371" (spec:714) | **wrong** (Important 2) |
| 17 | `.audio-aside/`, `DURATION_TOLERANCE_S`, `read_duration`, library before station, `source.identifier` gating, `build_package` re-check | checked (audio_reuse.py:35, :84-107, :133-160; package.py:24, :63) |
| 18 | 138 of 288 multi-item GD dates share names | checked (t13-rev:26) |
| 19 | `_destination_is_voiced` (only missing = unvoiced), batch marks refused and continues, `_replace_destination` on changed track list, hint suppressed | checked (cli.py:2491-2498, :2650-2661, :2600-2606, :3798-3811) |
| 20 | `--replace-voiced` one named show, refuses any selector | checked (cli.py:2714-2716) |
| 21 | `PREFER_VBR_DERIVATIVE = False`; `duplicate derivative`; include wins, exclude never kept; stem-named copy wins in non-_vbr groups | checked (junk.py:398, :413, :436, :439-482) |
| 22 | running-time choice, ties by order, fallback, after both dedupes; `short_keep=False` first-non-empty; only the migration passes it | checked (junk.py:500-534, :612-624; rekey_overrides.py:297) |
| 23 | 15,607 / 0 / 31; 2,017 of 2,017; 23 shows / 414 files; 20 GD; 13 lib / 48 cache | checked (orch-r4 ledger:71, :120; junk.py:400-404; tfw1-fix1:76) |
| 24 | donor ranked only among segue-bearing LMA parses when setlist.fm wins | checked (gather.py:976-988) |
| 25 | G5 `_drop_dangling_segues` / `_leads_with_filler`, `_FILLER` verbatim with `.match`, chosen donor only | checked (gather.py:885-923, :987) |
| 26 | `donor_segues` add guard (not last; shipped set equal or title ends `>`), skipped on LLM branch | checked (gather.py:1044-1048, :1970-1979) |
| 27 | `REKEY_MIN_VERSION = "2.18.0"`, `.rekey.lock`, `rekey-applied.json`, snapshot `manifest.json` last | checked (rekey_overrides.py:22-25, :81-84) |
| 28 | `--restore` refusals incl. another or unreadable record; rename to `rekey-applied.restored-<UTC>.json` on success | checked (rekey_overrides.py:1368-1437) |
| 29 | process-check note printed (dry run and gates) | checked (rekey_overrides.py:359, :519, :1531) |
| 30 | `--restore` lists destinations "created since" (CLAUDE.md:674) | **imprecise** (Minor 2; code: manifest mtime newer) |
| 31 | `repro` refuses an empty arm / different roots; probe subcommands and args; `voiced-precheck` exit 0 only all pass | checked (short_keep_probe.py:1-29, :584-599, :902-937) |
| 32 | `replay_holds --rekey-overrides` imports `rekey_raw`, stamps `overrides_rekeyed`, measurement only | checked (replay_holds.py:40, :274, :1452-1455) |
| 33 | `fix` with no show.json accepts `--set-*` (CLAUDE.md:68, unchanged) | **wrong** (Important 1) |
| 34 | 685→691, 13,202 drops / 75,277 titles; 3 census-music rows | checked (t10-impl:8; t10-rev:19-23, :55) |

Rulings quoted verbatim (check 3): all match (see Strengths).

Commits: eac1a07 and 04f68b4 each state the suite line (5468 passed, 1 skipped, 8 deselected) and carry the trailer. `git status` is clean.
