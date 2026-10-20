# Docs-only commit: "Recorded at Checkpoint F" block in the plan, plus 5c.2 "dropped" markers

File: docs/superpowers/plans/2026-10-19-held-backlog-tier1.md (ONLY this file).

## 1. The Recorded-at-F block
Find the "## Checkpoint F (operator): slice 5 lists; 5c ships only if its lists pass" section. Directly under its **Ask:** paragraph (the one ending "On approval, the approved rows go to `$H/approved-F.txt`."), insert a block in the same style as the existing "**Recorded at Checkpoint E (operator, 2026-10-19):**" block under Checkpoint E (read it first and match its format: a bold heading line, then bullets, then the existing `---` separator stays after it):

**Recorded at Checkpoint F (operator, 2026-10-20):**
- First measurement at tier1-cp-F = a92dd72 (Tasks 17, 18 and the E docs; PREV = tier1-cp-E2): hard check 1 passed (0 `set_breaks` changes on the 636 shows whose stored alignment is already `jerrybase`; the 5c.3 fold never created a second candidate). 5a cleared 2 shows, both right (railroadearth-2007-09-13, yondermountainstringband-2000-11-02). 5c.1 (6/6) and 5c.3 (8/8) read clean.
- **5c.2 REJECTED and dropped.** `anchor_numbered_sets` produced 5 wrong structures: gratefuldead-1971-04-29 (delivered; moved the Uncle John's Band encore into set 2), deadandcompany-2018-06-16 (released a hold on a wrong structure), and removed correct set breaks on gratefuldead-1980-10-31, gratefuldead-1970-05-14 and ratdog-2003-05-01, where jerrybase records fewer numbered sets than the tape (ratdog's set-2 row is one of the CSV loader's 117 skipped malformed rows). It also released 9 holds with a visible encore left in the last numbered set. **Task 18b** (098c2b2) removed the arm, its gather call and notes.json routing, its tests and the `compare` note-id row; 5c.1 and 5c.3 are kept unchanged.
- Re-measure at tier1-cp-F2 = 098c2b2 (PREV = tier1-cp-E2): 39 shows differ from the first F; 36 return exactly to their E2 replay (the 3 breaks restored, both wrong structures held again, the encore releases held again). The other 3 (darkstarorchestra-2008-08-31, philleshandfriends-2001-11-17, philleshandfriends-2008-07-06) carry a 5c.1 filler-tail note in place of one hard closer flag — 5c.2 had masked them at F — with no outcome change. Hard check 1 passed again. Slice 5 approved as 5a + 5c.1 + 5c.3; approved rows in `$H/approved-F.txt`; there is no `rejected-F.txt`.

## 2. "Dropped" markers on the 5c.2 text (history stays; mark, don't delete)
- The Contracts table row whose first cell is `5c.2` (~line 78): append to its last cell, inside the cell, the text ` — **dropped at Checkpoint F (Task 18b); no producer**`.
- The File Structure rows that mention 5c.2 / `anchor_numbered_sets` (~lines 129 and 142): after the words `5c.2 call` (line 129) and `` `anchor_numbered_sets` `` (line 142), add ` (dropped at Checkpoint F)`.
- The `notes.txt` grouping bullet (~line 989) that lists `5c.2` among the note ids: after `` `5c.2` `` add ` (dropped at Checkpoint F)`.
- In Task 18's text: at the start of the `anchor_numbered_sets(...)` bullet (~line 2573) and the `compute_gather` bullet that calls it (~line 2574), insert `**Dropped at Checkpoint F (Task 18b).** ` immediately after the leading `- `. Leave the Task 18 test code blocks as they are.
- Checkpoint F's item 2 (~line 2703), the clause "`structure_changed.txt` must list only shows carrying a 5c.2 note or a lost closer flag": append after it ` (after Task 18b: a lost closer flag only)`.
Use grep to find each line; line numbers are approximate. Do not touch any other text.

## Rules
Docs only. Change nothing else in the file and nothing in any other file (the spec stays as approved; the plan's Recorded-at block is the record). One commit, message `docs(plan): record Checkpoint F decisions (5a and 5c.1/5c.3 approved, 5c.2 dropped)`, ending with the two trailer lines from common.md (use your own model name in Co-Authored-By). Docs-only, so no test suite is needed; run `git diff --stat HEAD~1` after committing and confirm exactly 1 file changed, and `git diff HEAD~1 | grep '^-' | grep -v '^---'` shows no removed lines other than the ones you edited in place.
