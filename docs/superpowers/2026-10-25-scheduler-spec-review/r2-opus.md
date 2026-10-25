R2 Opus: SOUND. 3 I, 8 m.
O2-1 [I] truncate+re-plan races unlocked plan/render CLI vs service (render from old read) -> mid-song cut. (frontier mechanism, R)
O2-2 [I] frozen rule vs recovery (rows over rendered-unpublished dropped by recovery); new run's run_start row unfrozen -> next row in past. (frontier, R)
O2-3 [I] gap assertion via write_plan validates all rows; smaller gap -> junction inside rendered segment R. (frontier/gap, R)
O2-4 [m] two-pass can write nothing repeatedly -> always write >=1 row (run2 exact pick else run1 analysed pick).
O2-5 [m] rollback round-trip drops new keys; interstitial rows need string slug/dir/key; [interstitials] key breaks old strict config.
O2-6 [m] announcement interface: which boundary for later (last); actual start = first piece incl next clip; lookahead must reach named blocks; announcement rows record named occurrences, breakage judged when named block's first row freezes; missing two-block audio -> one-block form.
O2-7 [m] removal: leave interstitials out of timeline.json; nowPlayingText no-show text -> station name.
O2-8 [m] estimate inputs: scan must carry sizes/total_duration_sec/voiced profile; unvoiced keyed by manifest mtime+size; not all clips 64 kbps; schedule keeps estimates in memory.
O2-9 [m] invalid clock -> keep last-valid snapshot; render_step re-plan uses it.
O2-10 [m] anchors: defer to phase 4 or title on rows.
O2-11 [m] code claims: render_step does re-plan persisted rows; replan_from returns skipped row's start.
