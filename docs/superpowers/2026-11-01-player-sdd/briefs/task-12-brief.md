### Task 12: Docs, preview, go-live

**Model hint:** sonnet for the docs; the deploy steps are the operator's.

**Files:**
- Modify: `docs/playout-setup.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-10-09-playout-design.md` (a one-line pointer), `antenna/scripts/deploy-assets.mjs`, `docs/superpowers/2026-11-01-player-probe.md`
- Delete: `antenna/public/assets/preview/probe.html`, `probe.js`

- [ ] **Step 1: Docs.** In `docs/playout-setup.md`: the asset list and `--preview` (around lines 195 and 607), the off-air expectations and new "Lost the stream." state (lines 207-209, 636-642), the kill-switch grep note, the deploy order. In `CLAUDE.md`: the player's module layout, frozen root files, `npm run smoke`, `sections` in notes, the Cautions literal. In the parent spec: phase 4 points to this design.

- [ ] **Step 2: Delete the probe, remove its manifest code from `deploy-assets.mjs`, and commit.** `antenna: drop the probe; docs for the new player`.

- [ ] **Step 3: Final branch review** by the orchestrator, Opus (review mode), then the finish menu. Merge to `main` is the operator's call. The rest happens from `main`.

- [ ] **Step 4: HUMAN CHECKPOINT: launch, in the spec's order,** with the old player live until step 4. `main` must be pushed before hugo's pull; that push is the operator's OK.
  1. `ANTENNA_BUCKET=lma-radio npm run deploy:assets`.
  2. On hugo: `git pull` and `sudo systemctl restart transmitter@<user>`. Wait for `notes/<slug>.json` of an upcoming show to carry `sections`: up to about 4 hours. Check: `curl -s https://listen.lma-radio.com/notes/<slug>.json | python3 -c "import json,sys; print(len(json.load(sys.stdin)['sections']))"`.
  3. `--preview 2`. The operator judges `https://listen.lma-radio.com/assets/preview/2/index.html` against the mockups, panel included, on phone and computer. A fix found here goes through commit, Opus review, merge and push, then `deploy:assets` again (hugo pull if the template changed), then a new round number. When the operator is satisfied, `--remove-preview <n>` for every round used.
  4. Wait out the one-hour cache for any asset a fix changed. Then `npx wrangler deploy --dry-run`, then `npx wrangler deploy`. Within about 2 minutes `/` is the new page.

- [ ] **Step 5: Manual checks by the operator:** iPhone lock screen, the car display, a dropout on the road (airplane mode for at least 4 minutes with the screen locked), all from the home-screen version as well as Safari, and Chrome on a computer. Also the off-air checks in `docs/playout-setup.md` section 8, with times recorded. Rollback: revert the page commits and `npx wrangler deploy`; the old root files are still published.

- [ ] **Step 6: Record results** in `docs/superpowers/2026-11-01-player-probe.md` and commit.
