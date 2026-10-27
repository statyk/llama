# Checkpoint A2 — overrule backfill dry run with Shawn's Checkpoint A rulings (read-only)

Code: bulk-apply at 4a27c6c6 (T14b: rules a-d + basis note; review Approved, no Critical/Important). Command, from the worktree (`llama.__file__` resolved inside it):
`./.venv/bin/python scripts/bulk_apply.py backfill --base ~/.llama-harness/piece4/migration-base.json --verdicts ~/.llama-harness/t3/verdicts --rehold-verdicts ~/.llama-harness/t3/rehold-verdicts > ~/.llama-harness/bulk/backfill-dryrun-a2.txt`
rc 0, stderr empty, last line "dry run: nothing written (pass --apply)"; `find ~/.llama -newer <run-start marker>` found no file.
Full output: `/Users/shawn/.llama-harness/bulk/backfill-dryrun-a2.txt` (sha256 `65ddfaa6fe9ae6fa91c8e92e7238b520df40a1c521cdf6c9e23cacb658122f4b`, 39841 bytes, 713 lines).

## Totals

`totals: shows considered 195, shows with no verdict 15, flags recorded 485, flags listed 30, shows fully covered 184 of 195`
`recorded by basis: verdict 316, rule a 32, rule b 0, rule c 15, rule d 122`

Was (Checkpoint A, 884dd4ad): 195 / 15 / 316 recorded / 62 listed / 141 of 180 covered.
- rule a (verdict action `fix`, structure families): 32 flags — jerrybase set-count 14, jerrybase closer 9, research N sets 4, venue mismatch 2 (both `other_flags` free-text lines), city 2, setlist-evidence-multiple-sets 1.
- rule b (rehold `overrule`): 0. Every still-listed flag on the rehold-`overrule` shows the backfill considers is either taken by rule a first (precedence a > b) or excluded by NEVER (research-song / titles). The 2 `escalate` shows record nothing.
- rule c (delivered, no verdict): 15 flags on the 15 shows of Checkpoint A's List 2 (one base flag each); all now print per flag, none `no verdict`.
- rule d (`overrule_if_reheld_on`, not raised by the base arm): 122. Cross-check against `~/.llama-harness/bulk/backfill-not-in-base.json` (174 pairs over 36 shows): its `overrule_if_reheld_on` subset is exactly 122 pairs and equals the rule-d set (0 extra, 0 missing); the other 52 pairs are spurious-verdict rulings on non-base flags, left as they are (neither recorded nor listed), per the ruling.
- Check: 316 + 32 + 0 + 15 + 122 = 485; 62 − 32 = 30.

## The 30 flags still listed (each show re-holds on these when the apply reaches it; it lands in triage)

By reason: verdict never ruled on this flag 24, ruled research-wrong 4, ruled research-right-show-wrong 2. By class: research asserts unknown song 23 (21 never ruled + 2 ruled research-right-show-wrong; 9 of them on rehold-`overrule` shows: bandofheathens-2009-07-27 ×2, furthur-2011-02-11 ×4, geoffachisonandthesouldiggers-2003-05-28 ×3 — kept listed by the NEVER exclusion the ruling applies to rule b), unresolved track titles 3, research N sets 3 (ruled research-wrong), wrong date 1 (ruled research-wrong). Shows not fully covered: 11 of 195.

- `bandofheathens-2009-07-27`: research asserts unknown song: Nine Steps Down — verdict never ruled on this flag
- `bandofheathens-2009-07-27`: research asserts unknown song: Hangin' Tree — verdict never ruled on this flag
- `charliehunter-2004-05-22`: unresolved track titles — verdict never ruled on this flag
- `derektrucksband-2005-06-17`: research asserts wrong date: June 16 — ruled research-wrong
- `furthur-2011-02-11`: research asserts unknown song: Prelude — verdict never ruled on this flag
- `furthur-2011-02-11`: research asserts unknown song: Part I — verdict never ruled on this flag
- `furthur-2011-02-11`: research asserts unknown song: Let It Grow — verdict never ruled on this flag
- `furthur-2011-02-11`: research asserts unknown song: Liberty — verdict never ruled on this flag
- `geoffachisonandthesouldiggers-2003-05-28`: research asserts unknown song: Matchbox — verdict never ruled on this flag
- `geoffachisonandthesouldiggers-2003-05-28`: research asserts unknown song: Thundering in the Thickets — verdict never ruled on this flag
- `geoffachisonandthesouldiggers-2003-05-28`: research asserts unknown song: Walking Blues — verdict never ruled on this flag
- `godspeedyoublackemperor-2022-02-25`: unresolved track titles — verdict never ruled on this flag
- `mymorningjacket-2011-05-31`: research asserts 2 sets but structure has 1 — ruled research-wrong
- `railroadearth-2007-09-29`: research asserts 3 sets but structure has 2 — ruled research-wrong
- `stevekimockband-2002-04-20`: unresolved track titles — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Tongue 'n Groove — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Moon People — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: A New Africa — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Severe Tire Damage — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Sabertooth — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Five B4 Funk — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: You're the One — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Elmer's Revenge — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Why Can't We All Just Samba — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Long Form Part IV — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Hillbillies on PCP — verdict never ruled on this flag
- `stevekimockband-2002-04-20`: research asserts unknown song: Avalon — verdict never ruled on this flag
- `yondermountainstringband-2005-10-21`: research asserts 3 sets but structure has 2 — ruled research-wrong
- `zachdeputy-2010-07-02`: research asserts unknown song: Scrambled Eggs — ruled research-right-show-wrong
- `zachdeputy-2010-07-02`: research asserts unknown song: Outro — ruled research-right-show-wrong

## Notes for Shawn (no question; recorded so nothing is silent)
- The 9 rehold-`overrule` research-song flags stay listed because rule (b) carries the same NEVER exclusions as (a), as ruled. If the rehold "overrule" was meant to cover those songs, that is a one-line change (drop `research-song` from (b)'s exclusions) — say so and it becomes a follow-up; otherwise those 3 shows go to triage.
- Every recorded overrule names its basis in a new optional `note` on the overrule (`backfill verdict: …`, `backfill rule a (verdict action fix): …`, … `rule d (overrule_if_reheld_on, not raised by the base arm): …`).
- Latent, measured 0 on this data: a null-subject rule (e.g. jerrybase set-count) recorded by rule d also covers a differently worded listed flag of the same kind; the dry run would still show it listed. Runbook caveat at Task 18.

Nothing has been applied.

## Addendum — rule (b) covers research-song (parent ruling), re-run at 3497e77e

Parent ruling (llama-redo, Shawn may veto): a rehold `decision: overrule` covers `research asserts unknown song` flags on that show; it still never covers `unresolved track titles` or a flag ruled research-wrong / research-right-show-wrong. Rule (a) unchanged (songs excluded). Commit 3497e77e (T14c).

Same command (`--rehold-verdicts` included), from the worktree at 3497e77e: rc 0, stderr empty, nothing written under `~/.llama`. Output `/Users/shawn/.llama-harness/bulk/backfill-dryrun-a3.txt` (sha256 `c51b76883bc0b43eaf33f2f13c46043a6c6c53da72a24b0c0e675d046b620051`, 713 lines).

`totals: shows considered 195, shows with no verdict 15, flags recorded 494, flags listed 21, shows fully covered 187 of 195`
`recorded by basis: verdict 316, rule a 32, rule b 9, rule c 15, rule d 122`

Change from the run above: rule b 0 → 9, exactly the 9 rehold-`overrule` research-song flags (bandofheathens-2009-07-27 ×2, furthur-2011-02-11 ×4, geoffachisonandthesouldiggers-2003-05-28 ×3); listed 30 → 21; fully covered 184 → 187 of 195. No other line moved. The 21 still listed: stevekimockband-2002-04-20 (12 songs + titles), charliehunter-2004-05-22 (titles), godspeedyoublackemperor-2022-02-25 (titles), the 4 ruled research-wrong (derektrucksband-2005-06-17 date, mymorningjacket-2011-05-31, railroadearth-2007-09-29, yondermountainstringband-2005-10-21 set counts), the 2 ruled research-right-show-wrong (zachdeputy-2010-07-02 songs).
