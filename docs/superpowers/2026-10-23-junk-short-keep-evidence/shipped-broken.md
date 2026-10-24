# Shipped-but-broken examples (running list)

Started 2026-10-23 during the pieces 4-5 sizing census, at Shawn's request: every concrete show
found to have shipped (packaged/delivered/voiced, no hold) with a real defect, so it can be
returned to whatever pieces 4-5 end up building. States are from `llama status --all --json` at
2026-10-23 ~20:10. Sources: census `~/.llama-harness/piece45/` (handback at the session scratchpad
`piece45/census/handback.md`), hand-check answers `packets/<class>/answers.jsonl`.

Held shows found with the same defects are listed separately at the bottom (they are already
stopped, so they are not on air).

| show | state | class | defect | evidence | confidence |
|---|---|---|---|---|---|
| gratefuldead-1989-10-08 | delivered | 5c shifted tags | own tags one track late from track 15 (d2t05 "Drums >" is Eyes of the World at 558 s, matches sibling; Space/Miracle/Wheel each one slot late; "The Wheel" twice). Audio complete, titles wrong. | hc-5b row 28 | high |
| deadandcompany-2016-07-15 | delivered | 5c shifted tags | every MP3 tag one track late | piece-3 finding; census 5c 2+-sibling stratum | high |
| minutemen-1985-11-30 | delivered | 5a partial / 5b | last 8 songs absent from the selected item (its notes admit it); sibling `minutemen1985-11-30` runs ~100 min vs 83 | hc-5a row 7 | high |
| gratefuldead-1976-06-03 | delivered | 5b better sibling | selected lacks One More Saturday Night, The Wheel and Drums; sibling has them | hc-5b row 10 | medium-high |
| littlefeat-1975-10-31 | delivered | 5b better sibling | four songs missing from the selected tape | hc-5b row 2 | medium-high |
| jeffaustinband-2018-04-28 | delivered | 5b better sibling | selected is Set B only; the sibling is an AUD (toss-up per Shawn's lineage point) | hc-5b row 5 | medium |
| gratefuldead-1990-07-08 | delivered | 5b (encore) | selected lacks the encore Knockin' on Heaven's Door | hc-5b row 1 | medium |
| gratefuldead-1978-04-15 | delivered | 5b (encore) | selected lacks the encore One More Saturday Night | hc-5b row 32 | medium |
| gratefuldead-1981-09-12 | delivered | 5b (encore) | selected lacks the encore Good Lovin' | hc-5b row 37 | medium |
| gratefuldead-1971-07-02 | delivered | 5b truncation? | Playin' in the Band 299 s vs 486 s on sibling; first 17 tracks 386 s shorter in total. Unconfirmed: needs a listen | hc-5b row 3 | low |
| gratefuldead-1972-08-27 | delivered | 5b truncation? | same master as sibling (most tracks match to the second) but five songs 80-200 s shorter, Sugar Magnolia 510 s vs 702 s. Needs a listen | hc-5b row 33 | low-medium |
| (piece 4, 242 shows) | mostly delivered | 4-seg junk drop | short segue/continuation pieces dropped as "implausibly short" -> audible hole on air. Full list: census `p4` rows of the segue arm, silent subset | census + hc-p4 (13/13 music) | high (class) |
| (piece 4-conv) | — | 4-conv | filename-convention drop removed whole songs (281-712 s) and their neighbours; 8 silent shows | hc-p4 rows 34-37 | high (class) |

## Held (already stopped; not on air)

- gratefuldead-1994-08-01: selected is the set-2-only source; full siblings exist. Shawn (2026-10-23): plausible that a partial is deliberate (era, only part worth hearing) -- not automatically wrong.
- philleshandfriends-2006-10-28: selected is set 1 only.
- discobiscuits-2002-10-02: selected is disc 3 only.
- soulcoughing-1998-10-25: selected is a 72-min promo excerpt; sibling is the full 21-song DAT board remaster.
- gratefuldead-1984-03-31: encore "It's All Over Now, Baby Blue" is not on the item at all (all three siblings have it).

## Added from the 5c hand-check (packets/5c/answers.jsonl), all delivered

| show | class | defect | evidence | confidence |
|---|---|---|---|---|
| gratefuldead-1977-05-22 | 5c scramble | item files unpadded (D1T1..D1T11); checker says the item's tags were applied in string-sort order, so set-1 tracks are mislabelled (sel2 954 s = Sugaree on 3 siblings, sel3 271 s = El Paso ...). llama's own order is natural (D1T2..D1T11, `order_source: track-tags`, `reordered: true`); verify whether audio order is also wrong | hc-5c row 2, 3 siblings | high (titles) |
| gratefuldead-1979-09-01 | 5c shift | a non-song/stub track pushes later tags early (sel12 1001 s = Fire, sel11 = Scarlet ...) | hc-5c row 3, 2 siblings | high |
| gratefuldead-1982-08-08 | 5c shift | tags one song early from ~track 13 (Beyer sibling durations match to the second) | hc-5c row 4 | high |
| gratefuldead-1991-09-26 | 5c shift | tags TWO songs ahead from ~track 14; encore (Brokedown / We Bid You Good Night) not in the audio at all | hc-5c row 5 | high |
| localh-2008-05-13 | 5c shift | file t01 missing; the taper's own tags were assigned positionally from the 17-line description, so every title is one late against the description's written durations (our #1 "The One With Kid" is 177 s = Michelle's 2:57); #15 is an unlisted extra. title_source `tags` (not a piece-3 fill) | hc-5c row 21 | high |
| minutemen-1985-11-30 | 5c shift (also 5a above) | Political Nightmare tag placed at 22 instead of 15, so tracks 15-22 are one early | hc-5c row 22 | high |
| gratefuldead-1991-03-31 | other: unmarked filler | ~40 min of another show appended after the true encore (Knockin' at 17), no filler marker, so it would air as encore | hc-5c row 36 | high |
| philleshandfriends-2006-02-25 | 5c shift? | five tight duration pairs suggest a one-song offset; song-length priors cut both ways | hc-5c row 24 | low |
| gratefuldead-1980-12-13 (HELD, not shipped) | file order | encore One More Saturday Night is file d1t11, before Scarlet: titles right, order wrong | hc-5c row 40 | medium |

Census caveat found by hc-5c: the census 5c verdicts used RAW tags, so rows 6, 7, 9, 10, 18, 28, 30 looked shifted but ship correctly via operator overrides. Any 5c flag must compare SHIPPED titles.
