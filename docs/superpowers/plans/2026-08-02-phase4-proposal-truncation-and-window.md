# Phase 4 proposal — header truncation, then the two-pointer window

> **Status: PROPOSAL, not an executable plan.** Written 2026-08-02 by the
> independent phase-3 review (Fable), against `main` @ `a997e49` (1261 passed /
> 7 deselected, re-verified). Per the project workflow this seeds a spec and a
> task-level plan; it is deliberately not in checkbox form. Not committed —
> owner's call. All new measurements below were made with a fifth,
> independently written harness (`scratchpad audit/audit_window.py` and
> siblings, preserved alongside the phase-3 ledger) whose miss classifier was
> validated by exactly reproducing `align()`'s matched vector on every row of
> both corpora (0 divergences), a bar the phase-3 instrument could not meet.

## What the review verified (baseline pairs stated)

Every phase-3 headline number reproduces exactly at `a997e49` vs `673c357`:
anchoring 560/756 with 0 disagreements; end-to-end non-Dead coverage
0.4655 → 0.5033 (matched 5839/12215 → 6070/11734); full-corpus Dead
0.7592 → 0.7765; the recorded miss buckets; `dash-tolerance-FULL.patch`
applies cleanly to main; the 149/145 truncation sizing reproduces **to the
digit** — but only once the parser's own preprocessing (`<br>` AND generic
tag stripping AND `html.unescape`) is mirrored; an honest quick check with
ad-hoc preprocessing reads **82/78**. The number is right and
preprocessing-sensitive; any phase-4 re-measure must reuse the parser's own
text preparation.

## The adjudicated finding, strengthened

Phase 3's central claim — the A-bucket rise is a migration (C→A), the cascade
theory is falsified, and "do not widen the 4-item window" is inverted — is
**correct and was understated**. Under a true-pointer classifier (mirroring
`align()`'s real loop instead of exact-`==`), non-Dead misses at HEAD are:

```
A ahead of window   3878  68.5%   (recorded: 3436 / 60.7%)
C absent            1747  30.8%   (recorded: 2213 / 39.1%)
B behind               39   0.7%
D in-window             0         (structurally zero under the true pointer)
```

The phase-3 classifier's pointer drift biased *against* its own conclusion.

**The decisive experiment the phase never ran — a lookahead sweep of the real
`align()`, end-to-end (baseline pair: `a997e49` L=3 vs same code, larger L):**

```
non-Dead e2e (641 shows)          Dead stored-setlists (1082 shows)
L=3   0.5033   6070/11734          L=3   0.7765   16649/20945
L=5   0.6043   +1075,  73 win /  0 loss    L=5   +465,  46 win /  3 loss
L=8   0.7302   +2411, 159 win /  1 loss    L=8   +1207, 101 win /  9 loss
L=12  0.8089   +3235, 212 win /  3 loss    L=12  +1568, 133 win / 15 loss
L=999 0.8565   +3799, 250 win /  6 loss    L=999 +1781, 151 win / 16 loss
```

Two guarded designs both capture ~93% of the unlimited-window gain with a
smaller loss tail: **two-tier** (exact matches at unlimited range, fuzzy
confined to today's window): non-Dead 0.8337, 226 win / 2 loss; Dead stored
0.8448, 93 win / 14 loss. **Unique-anchor** (window first, then a unique
exact title anywhere ahead as resync) is within noise of it. The Dead loss
tail (14 shows / 98 tracks) persists under the uniqueness guard, so it is
order-divergence (tape order vs setlist order), not repeated titles — it
needs enumeration, not a cleverer rule.

Nuance to carry into the spec: A is still cascade-*shaped* — 92% of A misses
sit in shows with ≥10 of them, and in 223 of 237 A-heavy shows the *first*
miss is already beyond the window (a leading block of unclaimed items). That
does not rescue the old rule; it explains why the sweep gains are so large —
restoring reach re-syncs whole shows at a stroke. Window widening and "fixing
the desync" are the same lever, not two.

**Coverage is not the only gate.** A long-range match assigns a distant
item's *set label*; the win/loss counts above are a proxy. The implementation
phase must add a set-label gate (below), not ship on coverage alone.

## Sizing the two levers in the same currency

The "5×" framing in the phase-3 record compares *description counts* (149 vs
C1's 31). In matched-track units on the non-Dead corpus (the only corpus
where end-to-end is authoritative — iacache covers 874/874 non-Dead but
39/1181 Dead):

- **Truncation fix (naive prototype, L=3 unchanged):** 140 corpus rows sit in
  the truncation shape; their matches go 377 → 1506 (**+1129**). Zero of the
  39 Dead iacache rows are in the shape; Dead-side incidence is **unknown**,
  not zero.
- **Window/desync (guarded designs, current parses):** **≈ +3500** matched.
  Mostly disjoint populations: truncation-shape shows have almost no items
  today, so the sweep gains barely touch them. The levers compose.

Both dwarf phase 3's own end-to-end gain (+231). Phase 3's largest deliverable
was information, not coverage — that is not a criticism; it is why this
proposal exists.

## Proposed sequence

### 4a. Parser: the encore-as-first-marker truncation fix (option b), with its coupled patch

1. Fix `parse_setlist` so an encore marker as `first_marker` with song-like
   content above it does not truncate the header (option (b) from the phase-3
   record; the C1 reorder already fixed the split-created-marker half).
2. **Land `dash-tolerance-FULL.patch` in the same change, never before** —
   verified to apply cleanly at `a997e49`; its header lists the two coupled
   obligations (rewrite the "SET MARKERS ONLY" comment; retarget
   `test_encore_rule_above_a_tracklist_does_not_truncate`, which exists to
   fail when the hunk lands early). `nmas2013-02-13.16.44` (32→6 under the
   patch alone) is the worked example proving the coupling direction.
3. **Re-rank `rank_parses`**: confidence currently sorts above multi-set and
   item count — the amplifier that turned an 8-item encore-only parse into
   shipped structure over a 34-item sibling. Measure the re-rank over both
   corpora's sibling sets before changing it; this is the cheap insurance
   that the *next* parser defect doesn't ship either.

Gates (all over the 923-description sweep + both corpora, in the units ruling
17 fixed): **songs lost = 0** anywhere; the 145 ≥10-item blocks recovered;
`gd74_windsor` canary byte-identical; anchoring 560/756, 0 disagreements;
re-measure the buckets — expect a further C→A migration (state the prediction
and what it means if it fails, exactly as the phase-3 plan did for the
cascade theory).

### 4b. Matcher: the window/desync redesign (spec on post-4a numbers)

Spec first, informed by 4a's re-measured buckets. Design candidates, all
pre-measured above and preserved in the audit scripts: plain L=5 (free at
current state — 0 losing shows on non-Dead, 3 on Dead stored), two-tier,
unique-anchor. Requirements for the spec:

- **Set-label gate, not just coverage:** on shows whose parsed setlists carry
  set labels, aligned labels must agree at least as often as at L=3; jerrybase
  anchoring must stay 560/756 with 0 disagreements; bucket B must not balloon
  (the wide-window failure mode is a spurious jump converting downstream
  misses to B).
- **Per-show enumeration of every losing show** (there will be ~2–16), each
  classified junk-vs-song like C1's gate — no netting off.
- Fold in the one measured matching-layer remainder: **track-side numeric and
  duration prefixes** on tag titles (`18 Lost My Driving Wheel`,
  `[05:20] KC Jones**`) — 244 of the 1747 residual non-Dead C misses carry
  one; 96 match an item once stripped. The floor is +96; the same enumerated
  gate logic the parser side used applies (do not strip unconditionally).

Do 4a before 4b: the window frontier will shift once 145 descriptions regain
their setlists, and the window redesign should be measured once, on the tree
it will ship against. If 4b must be split, plain L=5 is the only piece cheap
and safe enough to land early — but landing it early means re-baselining
every measurement twice; prefer once, properly.

### 4c. Instrument work (parallel, cheap, no model cost)

**Backfill `iacache` for the 1142 missing Dead rows.** It is throttled
archive.org calls, not model spend, and it removes phase 3's single biggest
instrument limit: end-to-end numbers would become authoritative on the corpus
the product actually serves. Every Dead end-to-end claim currently rides on
39 rows. This also settles whether the truncation defect really is a
non-Dead-only phenomenon (currently unknowable).

## What I would NOT do

- **No further title-matching ambition.** D = 0 structurally under the true
  pointer; the residual C sample is absent songs, filename-only tracks, and
  prefix junk — no near-miss title pairs. The phase-2/3 ruling stands.
- **No Space synthesis yet.** 4a + 4b move the same 218-row population from
  two directions; re-measure after, per the spec's own reasoning.
- **Not the 175 credit-shaped titles** as their own workstream — fold into 4a
  only if the same regex file is already open and the gate is free.
- **Not `_NEVER_EQUAL` space-collapse keying** (verified latent, not live) and
  **not broad `_NOISE` format-chatter widening** (declined once, with the
  `Gathering Flowers For The Master's Bouquet` counter-example on record).
- **No eponymous-band re-check** unless the collection set widens (neither
  corpus contains one; recorded limitation, not a defect).

## Evidence that would change this sequencing

- If 4a's recovered blocks turn out junk-heavy (≥10 *items* but few real
  songs — measure songs, not items), demote 4a below 4b.
- If the set-label gate shows wide-window matches degrading Dead set
  assignment where jerrybase does not anchor (the 196 unanchored jerrybase
  shows), the window design needs an anchoring-aware guard before shipping.
- If backfilled Dead iacache shows the truncation shape materially present on
  Dead descriptions, 4a's priority rises further; if it shows Dead end-to-end
  behaviour diverging from the 39-row indication, stop and re-derive before
  either lever ships.

## Writing the phase-4 plan differently (the phase-3 lesson, made concrete)

The phase-3 diagnosis — "the plan was the weakest artifact" — is half right.
The disease is **unexecuted assertion**: every one of the run's five recorded
errors, the pre-parsed-corpus instrument bug, and the reviewer's false
correction was a claim about behaviour that was never run. The plan is where
such claims pool, because plans are written before execution and per-task
reviewers treat plan text as ground truth (the I1 false rationale survived
every review *because* it was transcribed from the plan). Implementation had
zero errors not because implementers were better but because implementation
is the only layer whose claims are mandatorily executed. So push execution
into the other layers:

1. **Plan smoke test before the plan ships:** every fenced regex/code/test
   block in the plan runs in a scratch harness against the plan's own
   examples. (`_NUM_LINE` failed the plan's *own named test*; one `python -c`
   would have caught it before dispatch.)
2. **Every number in the plan carries its baseline pair and instrument** —
   the rule the run already adopted; write it into the plan template, not
   just the ledger.
3. **Each task states its predicted metric movement and a falsification
   clause.** The phase-3 plan's "if A does not fall, the cascade theory is
   wrong — say so plainly" was its single most valuable sentence; make it
   per-task standard.
4. **Reviewers may cite the plan for WHAT, never for WHY.** Rationales in
   comments and tests must be re-derived from observed behaviour; anything
   copied verbatim from the plan is untested by definition.
5. **Instruments are code:** any measurement classifier claiming to mirror
   shipped behaviour must prove it — reproduce the shipped function's output
   exactly over the full corpus (0 divergences) before its numbers are
   recorded. The phase-3 classifier could not; the audit harness does; make
   it the entry bar.
6. **Gates in songs-lost / show-level units, written by the owner** (ruling
   17), with losing shows enumerated, never netted.
7. Keep what worked: implementer refusal culture, independent re-derivation
   before recording, one writer per worktree, the ledger's
   correction-in-place discipline.
