VERDICT: NEEDS FIXES

Task 17 (t17-rev-spec): spec-compliance review of ea3ca04 (4ff1126..ea3ca04). The commit changes only docs/playout-setup.md.

### Findings

#### Critical
None.

#### Important
1. **[plan-mandated] docs/playout-setup.md:363 (section 8, "A dashboard toggle is undone and alerted").** The checklist tells the operator to expect an alert titled "Kill switch toggled by hand" (`waf-corrected`). The code sends **"Kill switch corrected"** (antenna/src/guard.ts:295, `title: "Kill switch corrected"`). The brief's verbatim text copies the plan's original title (plan line 2375), and a later fix renamed it in code. Extras D says the code wins when the doc and the code differ, but the implementer reported "Deviations: None". This matters because this checklist item is on the WAF/blocking path, and the Step 3 failure rule there is "stop, do not share, bring back a fix task". An operator who waits for a subject that never arrives can record a false fail and halt the checkpoint. **Fix:** change the quoted title to "Kill switch corrected". I checked every other quoted subject in sections 7 and 8 against the code and they all match: "Station blocked: spend" (conditions.ts:55), "Station blocked: guard blind" (:62), "Kill switch not reconciled" (guard.ts:304), "Published lead below floor" (clock.ts:290).

#### Minor
1. **docs/playout-setup.md:195 (section 4 step 3, extras A).** The corrected parenthesis says `deploy:assets` uploads "(JS/CSS and hls.js; …)". The code also uploads **`offair.html`**: antenna/scripts/deploy-assets.mjs:27 has `["offair.html", "public/offair.html", HTML, HOUR]`, and its header comment says "offair.html and the app assets incl. hls.js". The doc follows extras A's wording ("JS/CSS/hls.js only"), but that wording is wrong against the code. It has no operational effect because the operator runs the same command either way. **Fix:** "(offair.html, JS/CSS and hls.js; …)". The added sentence "`index.html` is not uploaded" is correct and agrees with the script.
2. **Implementer concern (a): `KILL_SWITCH_DESCRIPTION` and `ALERT_REPEAT_HOURS` are not named in the doc. Verdict: not Missing.** The brief lists them under Interfaces → "Consumes", which describes what the task depends on, not a list of things to document. The brief's verbatim text never names them, and Step 2's grep list leaves them out. The doc states both behaviours with values that match the committed vars (wrangler.jsonc:30 `"station: kill switch"`, :34 `"6"`): see 6.2 step 6 and section 7 "Each repeats every 6 h". Optional polish: in 6.2 step 6, add "(the Worker var `KILL_SWITCH_DESCRIPTION`)" so an operator who renames the rule knows which setting has to follow it.
3. **docs/playout-setup.md:345–349 (6.2 numbering).** The extras C item `STATION_NAME` was inserted as step 5, which pushes the brief's verbatim "5. **Kill switch.**" to step 6. Nothing cross-references "6.2 step 5", so nothing breaks. It is still a small departure from "append exactly as below". Putting STATION_NAME after the kill-switch step would keep the brief's numbering.
4. **docs/playout-setup.md:211 (the paragraph section 4 step 4 kept, as the brief requires).** "The WAF kill switch (section 2 step 7) remains the hard stop" now sits beside the new "Do **not** toggle the kill-switch rule in the dashboard". In that paragraph's context (off-air) the guard enables the rule by itself, so the two statements do not strictly contradict. The phase-1 checklist item at around line 247 ("temporarily enable the kill-switch rule") would, after phase 2 is deployed, be undone within a minute and raise `waf-corrected`. Neither is in the brief's scope; I note them only so the operator is not surprised if a phase-1 item is ever re-run.

### ⚠️ Cannot verify from diff
- Every runtime claim in section 8 (latencies, "within ~1 min", the 403 on the R2 custom domain, production conditional-put behaviour). These are the operator's Step 3 checks by design.
- "~3 min" to `dead-clock` and "about an hour" to `guard-stale`. Both are consistent with the code: 2 consecutive stale checks at 120 s, and 45 min plus the cache refresh. Only a live run can confirm them.

### Strengths
- **Edits 1–4 are byte-exact.** Edit 4 was compared mechanically against the brief (`cmp`: identical). Edits 1–3 each appear exactly once, and the replaced phase-1 text ("phase 2 (the cost guard) ships", "Off-air by hand") is gone.
- **Sections 6–8 keep every line of the brief's verbatim block.** A mechanical diff shows only additions plus one sanctioned rewrite: the "Cloud alerts need R2" bullet, extended as extras C directs.
- **Every extras item landed in a sensible place, with the meaning the extras give it:**
  - A: 4 step 3, including the fresh-bucket note, with the `--dry-run` mention kept.
  - B1: 8, first item.
  - B2 and B6: sub-bullets of the off-air item.
  - B3: section 7 and 8.
  - B4: the already-playing item.
  - B5: its own section 8 item.
  - B7: section 7 and 8.
  - All seven C bullets.
  - D: both tables complete.
  - E: the config table plus env secrets plus the R4 floor.
- **The alert table matches the code.** Every cloud key, priority and once/resolvable kind matches conditions.ts, guard.ts and clock.ts, and the families match `CLOCK_KEYS`/`GUARD_KEYS` (alerts.ts:35–51).
- **The config table matches the code.** Every default and bound matches config.py (`ge=31`, `ge=1, le=65535`, 6.0/120.0/45.0, the smtp.gmail.com and 587 defaults, the `email_from` fallback, the +16 validator).
- **Status strings match the code.** `CORRUPT (…)`, `offair CORRUPT`, `<doc> unreadable: …`, `honoured (period end unknown)` (service.py:277–303, cloudstate.py:185).
- **The unit claims match** packages/transmitter/systemd/transmitter@.service: Type=notify, WatchdogSec=45min, Restart=always, and the ExecStart venv path.
- **Nothing contradicts R1–R17.** I checked R2 (corrupt guard is a spend trip, corrupt offair is off the air), R4, R5 ($100 cap), R7, R8, R12, R13 (once-keys and the 15-min cooldown), R14 (cron-trigger-then-rule order), R15 and R16.
- **Step 3 was not done.** There is no `docs/superpowers/*-playout-phase2-verification.md`, and the commit touches one file.

### Checks run
- **Brief verbatim, sections 6–8.** I extracted the brief's ````markdown block and ran `diff` against the doc from "## 6. Phase 2". Result: additions only, plus the extras-C rewrite of "Cloud alerts need R2", plus the 6.2 renumber (Minor 3).
- **Brief verbatim, edit 4.** I extracted the quoted text, unescaped `\"`, and ran `cmp` against doc line 200: IDENTICAL. For edits 1–3, `grep -cF` returned 1 each, and the old phase-1 text is absent.
- **Step 2 name grep.** 21 lines. Each of the 12 names plus `transmitter@` appears in the doc and in code (antenna/src/{guard,alerts,meter,latch,clock}.ts, wrangler.jsonc, transmitter config.py, cloudstate.py, the unit file). `KILL_SWITCH_DESCRIPTION` and `ALERT_REPEAT_HOURS` have 0 doc hits (concern (a), Minor 2).
- **Step 2 email grep (public repo):** no output. I also scanned for 32-hex IDs and long token-like strings, in both the doc and the diff's added lines: none.
- **Concern (b), "alarms after 10 checks".** Checked against packages/transmitter/src/transmitter/deadclock.py:26 `TROUBLE_CHECKS = 10`, applied at :101–105 to any status other than 200 or 403 ("cannot be fetched … for N minutes"). The claim is **sourced and correct**. It is consistent with R4: the 403 path is separate (`forbidden_checks = 17` = guard_check_minutes + 2, deadclock.py:66) and the stale path is 2 consecutive checks.
- **Concern (b), "~30 s player buffer".** Checked against antenna/public/player.js:60 `new window.Hls({ liveSyncDurationCount: 3 })`, which is 3 × 10.24 s ≈ 30.7 s behind the live edge, so the claim is **sourced**. The "25 s stall watch" is also sourced: nowplaying.js:77 `stallMs = 15000, probeEveryMs = 10000, verdictsNeeded = 2`, constructed with defaults (player.js:21), gives 15 s + 10 s = 25 s.
- **Alert keys and titles.** I grepped `key:`/`priority:` in antenna/src/{conditions,guard,clock}.ts and read alerts.ts:35–51. All match the table. This turned up the waf-corrected title mismatch (Important 1), and `grep "toggled by hand"` finds it only in the plan, not in code.
- **Config keys.** Compared `git diff ccf0f16..HEAD -- packages/transmitter/src/transmitter/config.py` against the doc's table: all match. `guard_check_minutes` predates the branch and is documented anyway, which is fine.
- **deploy:assets contents.** Read antenna/scripts/deploy-assets.mjs:1–31: it uploads offair.html (Minor 1). antenna/public/index.html references style.css, assets/hls.min.js and player.js, so the fresh-bucket note is correct.
- **Takeover flags.** Checked `$D/TAKEN_OVER` and `$D/taken-over/t17-rev-spec`: neither exists. No tests were run; this is a docs task, and the Step 2 checks above stand in for them.
