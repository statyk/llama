Status: DONE
Commit: 4c380435 antenna: drop the probe; docs for the new player
Tests: antenna npm test 518 passed; npm run smoke 56 passed. Transmitter untouched (not run).

Done:
- Deleted antenna/public/assets/preview/probe.html and probe.js.
- antenna/scripts/deploy-assets.mjs: removed probe manifest code; unknown argument exits 2 (checked before any upload); --remove-preview refuses (exit 1, nothing deleted) any key in .preview-<n>.json not starting with assets/preview/<n>/ or containing "..". --preview, --remove-preview and .preview-<n>.json handling otherwise unchanged. No script test file exists in the repo, so shown by hand with --dry-run and ANTENNA_BUCKET=x (no bucket write): `--bogus` rc=2; `--preview` with no round rc=2; plain dry run rc=0; --preview 9 dry run lists no probe keys; temp .preview-9.json with `assets/hls.min.js` or `assets/preview/9/../../x` -> refused rc=1; with only in-prefix keys -> lists the deletes, rc=0. Temp file removed; real .preview-*.json and .env untouched.
- docs/playout-setup.md section 4 step 3: asset list (frozen root files plus everything under assets/), --preview/--remove-preview with the prefix limit, deploy order, rollback, known phone limits, the (see cautions) note. Section 8: off-air wording for the new player; the kill-switch grep note (the new index.html does not contain "off the air", only assets/page.js does, so grep is valid only against the new page; marked "confirm on the live page first", not verified live); the blip check now covers the HTTP-answer wait, "Lost the stream." after ~10 min (giveUpMs) with Try again, and Play-while-on behavior.
- CLAUDE.md: one compact bullet after the antenna bullet (script args, Play wait, parse_briefing pointer, iOS limits, doc pointers).
- Parent spec: one-line phase 4 pointer under the antenna heading.
- player-probe doc: note that probe files were deleted; results untouched.

Concerns: the playout-setup item at the old "line 607" (step 7 Player assets) left as is; the new-page judgement is covered in step 3. Step 7's "We'll be back shortly" wording is the old player's and I did not check it against the new page.
