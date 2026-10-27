# Checkpoint B — arm, freeze, re-selection check, marking dry run (read-only)

Code: bulk-apply at **d1bb0127** (Task 15 complete after one fix round; tree clean). All commands from the worktree with its own interpreter; `--campaign-dir ~/.llama-harness/bulk/campaign` (scratch). `find ~/.llama -newer <start marker>` and the same over the station found **no file written**.

## Commands and outputs

1. `./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/bulk/checkpoint-arm.json` — rc 0, ~50 s; arm sha `d1bb0127`, generated `2026-10-27T06:44:21.488053+00:00`, 3983 shows: clean 1252, clean-changed 1709, needs-brief 3, needs-llm 654, **newly-held 220**, still-held 135, still-held-package 1, structure-changed 9 (sha256 `8eaa1792b210e75c…`). An identical-count arm at 5fb225b6 (before the fix round) is kept as `checkpoint-arm-5fb225b6.json`.
2. `bulk_apply.py freeze --arm …/checkpoint-arm.json` — rc 0: **654** needs-LLM shows frozen (`campaign/needs-llm-frozen.json`).
3. `bulk_apply.py reselect-check --source ~/.llama-harness/piece4/fw1/m3_changed-r1.json --write` — rc 0: **17 of 20** source rows re-select (`campaign/reselections.json`).
4. `bulk_apply.py mark --arm …/checkpoint-arm.json` (dry run) — rc 0. Full output `~/.llama-harness/bulk/cpb-mark-dryrun.txt`:

```
marking plan: 2551 show(s)
  changed by the held-backlog fixes: delivered unvoiced 1322, delivered voiced 116, packaged 347, briefed 13, held 80
  replay needs an LLM call: delivered unvoiced 344, delivered voiced 20, packaged 99, briefed 4, held 185
  stored briefing fails today's guard: delivered unvoiced 1, delivered voiced 0, packaged 2, briefed 0, held 1
  recording re-selection: delivered unvoiced 11, delivered voiced 0, packaged 4, briefed 0, held 2
by arm outcome: clean 2, clean-changed 1683, needs-brief 3, needs-llm 654, newly-held 130, still-held 70, structure-changed 9
voiced: 136: (list below)
unreadable station manifests: 0
unreplayable, not marked: 0
emcee running: no
dry run: nothing written (pass --apply)
```

## Counts by reason × state

| reason | delivered unvoiced | delivered voiced | packaged | briefed | held | total |
|---|---|---|---|---|---|---|
| changed by the held-backlog fixes | 1322 | 116 | 347 | 13 | 80 | 1878 |
| replay needs an LLM call | 344 | 20 | 99 | 4 | 185 | 652 |
| stored briefing fails today's guard | 1 | 0 | 2 | 0 | 1 | 4 |
| recording re-selection | 11 | 0 | 4 | 0 | 2 | 17 |

**2551 shows marked** (2551 in the plan line). By arm outcome: clean 2, clean-changed 1683, needs-brief 3, needs-llm 654, newly-held 130, still-held 70, structure-changed 9. Of the arm's 220 newly-held rows, 130 are marked (the other 90 are left unmarked by the rule; I have not broken down why); the plan expected "near the table's 220" because the backfill has not run.

Unreadable station manifests: **0**. Unreplayable, not marked: **0**. emcee running: no. Delivered shows with no station copy: none reported.

## Voiced (136) — these get a station mark; re-delivery needs `deliver <slug> --replace-voiced` then `emcee voice <slug>` each

`allenstone-2012-11-04`, `belafleckandtheflecktones-2002-08-10`, `cracker-2005-11-01`, `dumpstaphunk-2008-04-25`, `dumpstaphunk-2009-11-14`, `dumpstaphunk-2011-07-06`, `dumpstaphunk-2011-07-21`, `georgeporterjr-2018-10-05`, `gratefuldead-1968-02-14`, `gratefuldead-1968-10-12`, `gratefuldead-1970-04-15`, `gratefuldead-1971-02-18`, `gratefuldead-1971-04-29`, `gratefuldead-1971-08-06`, `gratefuldead-1972-05-11`, `gratefuldead-1972-05-26`, `gratefuldead-1972-08-27`, `gratefuldead-1972-09-28`, `gratefuldead-1973-02-09`, `gratefuldead-1973-03-24`, `gratefuldead-1973-06-22`, `gratefuldead-1973-08-01`, `gratefuldead-1973-11-21`, `gratefuldead-1973-12-18`, `gratefuldead-1974-02-24`, `gratefuldead-1974-05-14`, `gratefuldead-1974-05-19`, `gratefuldead-1974-05-21`, `gratefuldead-1974-06-18`, `gratefuldead-1974-06-23`, `gratefuldead-1974-07-19`, `gratefuldead-1974-07-31`, `gratefuldead-1974-09-11`, `gratefuldead-1974-09-18`, `gratefuldead-1975-06-17`, `gratefuldead-1976-06-14`, `gratefuldead-1976-06-29`, `gratefuldead-1976-07-18`, `gratefuldead-1977-02-26`, `gratefuldead-1977-03-18`, `gratefuldead-1977-04-23`, `gratefuldead-1977-05-07`, `gratefuldead-1977-05-08`, `gratefuldead-1977-05-09`, `gratefuldead-1977-05-13`, `gratefuldead-1977-05-15`, `gratefuldead-1977-05-18`, `gratefuldead-1977-05-28`, `gratefuldead-1977-06-09`, `gratefuldead-1977-11-04`, `gratefuldead-1977-11-06`, `gratefuldead-1978-04-12`, `gratefuldead-1978-04-24`, `gratefuldead-1978-09-02`, `gratefuldead-1978-11-24`, `gratefuldead-1978-12-16`, `gratefuldead-1979-10-27`, `gratefuldead-1979-12-01`, `gratefuldead-1980-06-21`, `gratefuldead-1980-09-02`, `gratefuldead-1980-11-30`, `gratefuldead-1981-05-01`, `gratefuldead-1982-08-10`, `gratefuldead-1982-10-09`, `gratefuldead-1982-10-10`, `gratefuldead-1983-06-20`, `gratefuldead-1983-10-15`, `gratefuldead-1983-10-17`, `gratefuldead-1984-04-13`, `gratefuldead-1985-06-24`, `gratefuldead-1985-06-25`, `gratefuldead-1985-06-27`, `gratefuldead-1985-06-28`, `gratefuldead-1985-06-30`, `gratefuldead-1985-09-07`, `gratefuldead-1987-09-18`, `gratefuldead-1988-07-02`, `gratefuldead-1989-07-07`, `gratefuldead-1989-10-26`, `gratefuldead-1990-03-19`, `gratefuldead-1990-03-22`, `gratefuldead-1990-03-24`, `gratefuldead-1990-03-29`, `gratefuldead-1990-07-06`, `gratefuldead-1990-09-20`, `gratefuldead-1991-06-17`, `gratefuldead-1991-09-10`, `gratefuldead-1993-08-22`, `gratefuldead-1995-03-23`, `jjgreyandmofro-2007-03-09`, `jjgreyandmofro-2007-03-29`, `jjgreyandmofro-2007-04-10`, `karldensonstinyuniverse-1998-06-13`, `karldensonstinyuniverse-2000-11-01`, `karldensonstinyuniverse-2000-11-02`, `karldensonstinyuniverse-2001-03-08`, `karldensonstinyuniverse-2004-01-08`, `karldensonstinyuniverse-2009-01-10`, `karldensonstinyuniverse-2010-08-27`, `lettuce-2002-06-09`, `lettuce-2008-05-02`, `lettuce-2008-07-11`, `lettuce-2009-11-14`, `lettuce-2010-11-14`, `lettuce-2011-01-18`, `lettuce-2014-12-06`, `localh-2004-12-31`, `mogwai-2006-05-03`, `newmastersounds-2011-06-04`, `robertrandolphandthefamilyband-2004-02-21`, `robertwalters20thcongress-2001-06-16`, `smashingpumpkins-1993-06-30`, `smashingpumpkins-1997-01-08`, `soulive-1999-04-15`, `soulive-2001-02-03`, `soulive-2001-09-01`, `soulive-2001-10-20`, `soulive-2002-04-20`, `soulive-2004-07-01`, `soulive-2004-08-29`, `soulive-2004-11-18`, `soulive-2005-02-18`, `soulive-2005-05-06`, `soulive-2009-09-12`, `soulive-2014-11-15`, `tedeschitrucksband-2013-11-23`, `tedeschitrucksband-2016-08-05`, `tedeschitrucksband-2017-11-04`, `tedeschitrucksband-2018-10-13`, `tedeschitrucksband-2019-01-22`, `tedeschitrucksband-2022-03-26`, `tedeschitrucksband-2022-07-16`, `tedeschitrucksband-2023-03-31`, `themotet-2002-04-18`, `themotet-2007-04-22`, `yondermountainstringband-2010-10-15`

## Re-selection list (17; marked with start stage `select`)

- `gratefuldead-1966-12-01`: gd1966-12-01.sbd.32800.shnf -> gd66-12-01.sbd.ladner.8575.sbeok.shnf
- `gratefuldead-1968-10-13`: gd1968-10-13.sbd.gans.miller.owen.9386.shnf -> gd1968-10-13.sbd.miller.owen.7772.sbeok.shnf
- `gratefuldead-1969-04-21`: gd1969-04-21.sbd.clugston.6182.shnf -> gd1969-04-21.sbd.miller.88465.sbeok.flac16
- `gratefuldead-1970-05-06`: gd70-05-06.sbd.gans.94.sbefail.shnf -> gd1970-05-06.sbd.gans-hall.95.shnf
- `gratefuldead-1972-11-18`: gd1972-11-18.sbd-set2.lai.9182.shnf -> gd1972-11-18.123077.sbd.miller.flac16
- `gratefuldead-1973-10-29`: gd1973-10-29.sbd.kaplan.1070.shnf -> gd1973-10-29.sbd.miller.32352.sbeok.flac16
- `gratefuldead-1974-05-25`: gd1974-05-25.sbd.jmiller.205.sbeok.shnf -> gd74-05-25.sbd.moog.2635.sbeok.shnf
- `gratefuldead-1978-12-30`: gd1978-12-30.sbd.tonyg.8826.shnf -> gd78-12-30.sbd.miller.18092.sbeok.shnf
- `gratefuldead-1981-12-09`: gd1981-12-09.sbd.miller.87349.sbeok.flac16 -> gd81-12-09.sbd.clugston.13061.sbeok.shnf
- `gratefuldead-1983-10-08`: gd1983-10-08.senn441.silberman.miller.97883.sbeok.flac16 -> gd83-10-08.fob-aud.willy.11734.sbeok.shnf
- `gratefuldead-1985-11-10`: gd1985-11-10.sbd.doughty.12202.shnf -> gd85-11-10.sbd.barbella.12264.sbeok.shnf
- `gratefuldead-1987-07-06`: gd87-07-06.beyerM88s.connor.2583.sbeok.shnf -> gd1987-07-06.138790.pcm.sbd.miller.flac1644
- `gratefuldead-1988-03-27`: gd1988-03-27.sbd.jerugim.braverman.fix-406.3383.shnf -> gd88-03-27.matrix.braverman.17262.sbeok.shnf
- `gratefuldead-1988-06-23`: gd1988-06-23.sbd.unknown.9456.shnf -> gd88-06-23.sennheiser.ladner.17407.sbeok.shnf
- `gratefuldead-1990-03-16`: gd90-03-16.sbd.willy.5227.sbeok.shnf -> gd1990-03-16.sbd.miller.85201.sbeok.flac16
- `gratefuldead-1990-07-14`: gd1990-07-14.sbd.unknown.31950.shnf -> gd1990-07-14.sbd.miller.106403.flac16
- `gratefuldead-1991-06-25`: gd91-06-25.sbd.screenwriter.489.sbeok.shnf -> gd91-06-25.sbd.miller.26350.sbeok.shnf

Absent from the 20 source rows (expected: the three voiced shows): `gratefuldead-1973-11-14` (voiced: its station manifest carries dj_audio; arm outcome `clean`, so it is not marked and therefore not in the marked-voiced list above), `gratefuldead-1974-09-11` (voiced), `gratefuldead-1977-04-23` (voiced).

## For Shawn

The plan asks you to confirm the marking rule before Task 16 runs (overnight ruling: I continue to Tasks 16-17 meanwhile; any ruling here becomes a follow-up). Points worth your eye:
- 2551 of 3983 shows would be marked; 136 of them voiced (116 changed + 20 needs-LLM).
- needs-LLM: all 654 frozen shows are marked — 652 under the needs-LLM reason, 2 under re-selection, which takes priority (by arm outcome needs-llm = 654); they re-process with `--with-gather-llm`.
- `stored briefing fails today's guard` marks 4 (held problems only, after overrules — Task 4b ruling).
- Reviewer minors on marking ledgered as RECOMMEND-FIX for a follow-up before any `mark --apply`: (M1) a station mark written without its record line is not reversible by `unmark`; (M2) a missing show dir or unreadable show.json silently drops a row from the plan; (M3) `--campaign-dir` should be refused with `--apply`.

Nothing has been applied; the scratch campaign dir is `~/.llama-harness/bulk/campaign` and is not read by llama.
