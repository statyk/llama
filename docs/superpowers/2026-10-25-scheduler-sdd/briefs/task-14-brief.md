### Task 14: Runbook and project notes

**Files:**
- Modify: `docs/playout-setup.md`, `CLAUDE.md` (transmitter paragraph), `packages/transmitter/src/transmitter/config.py` docstring/template if needed

- [ ] **Step 1: Runbook** — a "Clock and schedule" section: where `clock.toml` lives; edit a draft, check it with `transmitter schedule --clock draft.toml` then move it into place; what `status` says for an invalid clock; edits reach air after the persisted plan (about one lead plus one show). An "Announcements" section, copy-paste: `transmitter announcements --export <dir>`; on the Mac `cd /Volumes/media/lma-radio/delivered/interstitials && for f in ann-*.txt; do emcee say "$f"; done`; station IDs are any `id-*.mp3`. The rollback subsection from Task 1 stays (it already covers `[interstitials]`); check that the commits it names match the final history.
- [ ] **Step 2: CLAUDE.md** — update the transmitter Commands bullet (`schedule`, `library`, `announcements`, plan lock, `clock.toml`) and the architecture paragraph (append-only scheduler, pieces, interstitials folder, `aired.jsonl`), in the file's existing terse style.
- [ ] **Step 3: Full verification** — `./.venv/bin/python -m pytest -q` (whole repo), `cd antenna && npm test`, and `packages/transmitter/scripts/test-in-debian12.sh` (needs docker; if unavailable, say so in the report).
- [ ] **Step 4: Commit**

```bash
git add docs/playout-setup.md CLAUDE.md packages/transmitter/src/transmitter/config.py
git commit -m "docs: scheduler runbook (clock, announcements, rollback) and project notes"
```
