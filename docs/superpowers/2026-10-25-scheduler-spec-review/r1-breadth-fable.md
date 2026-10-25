Breadth (Fable): Foundation SOUND. 5 I, 11 m.
F1 [I] frontier/frozen undefined (= S1). Def: F=(highest seg idx existing in render/seg/<epoch> or <= listed_bound)+1 x SEGMENT_FRAMES; rows start>=F re-plannable; spanning F frozen whole; encode presence irrelevant; plan_step truncates to F and re-plans every step (drop until_frame early return).
F2 [I] pure scheduler vs analysis handshake undefined; rows w/ estimated frames would loop in render. Pieces carry frames|None + estimate; scheduler stops at first estimated piece to commit, returns "analyse me"; pipeline analyses & re-calls.
F3 [I] retiring planner removes [planner] seed -> strict config ConfigError on hugo -> crash loop. Keep seed as tie-break.
F4 [I] rollback: old PlanRow(**data) rejects new keys (= S6). Ship tolerant from_json first, or sidecar; runbook.
F5 [I] feasibility-sim.py can't produce baseline (weighted 1000 overrun, hard-coded path, flat +4 min, excludes dead/funk/dead-family from fill). Name edits; commit edited script.
F6 [m] interstitials re-validation (= S2).
F7 [m] timeline entries for interstitials -> notes/page PUTs, recent pollution. kind interstitial excluded from notes/page/recent; player shows station name (small antenna change).
F8 [m] DJ clip durations exist nowhere; estimate = total_duration_sec + fixed clip allowance; exact from analysis cache when present.
F9 [m] announcement at boundary into X names X -> "Stay tuned for X at 11" airs as X begins. Decide wording/placement.
F10 [m] Y's profile not covered by lock -> accepted limitation, counted announcement-broken.
F11 [m] aired.jsonl idempotency key; plan.jsonl never trimmed.
F12 [m] miss/bends/nominal_start must persist on rows.
F13 [m] interstitials folder: inside station root w/o manifest is invisible to all three (cited) -> default <root>/interstitials/.
F14 [m] compromise step 1 circular; structural fill (block longer than max_shows can fill) reported as compromise -> noise. Distinguish.
F15 [m] tie-break shuffle_rank(seed, slug).
F16 [m] "phase 1's existing property" overstated.
