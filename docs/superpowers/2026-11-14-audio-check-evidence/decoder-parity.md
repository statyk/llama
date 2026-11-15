# Decoder parity (Task 4, step 6)

`classify_file` (miniaudio decode to 16 kHz mono, bundled ONNX YAMNet, rule 0.55/120/0.60) run over
the 30 `music_chosen` tracks of `population2.tsv` (the 4 `Silence` rows excluded) plus the 19 `near`
rows of `sample3.json` (one, newridersofthepurplesage-1974-11-29 `23 - crowd & tuning.mp3`, is also
chosen), 48 distinct files, read from `/Volumes/media/lma-radio/delivered/` (read-only).
Script: `decoder_parity.py` in this directory. "pop" = `run_055`/`frac_055`/`music_chosen` from population2.

**Result: 48 of 48 run, 0 verdict flips, 0 blocking flips, 0 missing on the share. Fallback (native-rate
decode + numpy/soxr resample) NOT taken.** Only run/frac drift: derektrucksband-2008-12-31 `21 - crowd.mp3`
frac 0.65 to 0.69; themotet-2012-10-31 `01 - Intro.mp3` run 130 to 140, frac 0.87 to 0.93. Neither changes a verdict.

Truncation note: miniaudio returns partial audio (no error) for a cut MP3, so `decode.py` maps a last
MPEG1-layer-III frame running past EOF, and a FLAC that decodes to under 98% of its STREAMINFO length,
to `DecodeError`. A cut that lands exactly on a frame boundary, or a non-MPEG1 file, is not detected.

| slug | file | label | grp | pop run/frac | now run/frac | pop verdict | now verdict | flip | blocker |
|---|---|---|---|---|---|---|---|---|---|
| acousticsyndicate-2004-06-12 | 01 - Tuning.mp3 | junk | near | 100/0.67 | 100/0.67 | junk | junk |  |  |
| bobbyleerodgers-2010-01-13 | 08 - Intro_Tuning.mp3 | junk | chosen | 140/0.61 | 140/0.61 | music | music |  |  |
| brotherspast-2006-11-17 | 10 - tuning.mp3 | song | chosen | 240/1.00 | 240/1.00 | music | music |  |  |
| buttholesurfers-2009-10-14 | 01 - Intro.mp3 | unsure | chosen | 120/1.00 | 120/1.00 | music | music |  |  |
| darkstarorchestra-2003-09-04 | 01 - Tuning.mp3 | junk | near | 110/0.78 | 110/0.78 | junk | junk |  |  |
| darkstarorchestra-2007-09-07 | 02 - Crowd_Tuning.mp3 | song | chosen | 280/1.00 | 280/1.00 | music | music |  |  |
| darkstarorchestra-2007-12-04 | 11 - tuning.mp3 | junk | chosen | 180/0.70 | 180/0.70 | music | music |  |  |
| derektrucksband-2008-12-31 | 21 - crowd.mp3 | junk | chosen | 140/0.65 | 140/0.69 | music | music |  |  |
| dirtydozenbrassband-2005-05-28 | 01 - intro.mp3 | song | chosen | 670/0.94 | 670/0.94 | music | music |  |  |
| discobiscuits-2007-06-26 | 07 - Intro.mp3 | unsure | chosen | 140/0.93 | 140/0.93 | music | music |  |  |
| drive-bytruckers-2011-10-22 | 01 - Intro.mp3 | song | chosen | 180/0.90 | 180/0.90 | music | music |  |  |
| furthur-2010-05-28 | 01 - Tuning.mp3 | junk | near | 90/0.60 | 90/0.60 | junk | junk |  |  |
| gratefuldead-1970-11-08 | 01 - Tuning.mp3 | junk | near | 90/0.65 | 90/0.65 | junk | junk |  |  |
| gratefuldead-1971-12-15 | 01 - Tuning.mp3 | junk | chosen | 130/0.84 | 130/0.84 | music | music |  |  |
| gratefuldead-1972-05-07 | 01 - Intro.mp3 | song | chosen | 520/0.95 | 520/0.95 | music | music |  |  |
| gratefuldead-1977-05-07 | 21 - Tune Up.mp3 | junk | near | 90/0.69 | 90/0.69 | junk | junk |  |  |
| gratefuldead-1988-03-24 | 20 - Crowd_Tuning.mp3 | song | chosen | 550/1.00 | 550/1.00 | music | music |  |  |
| gratefuldead-1989-10-26 | 09 - Tuning.mp3 | junk | near | 110/0.84 | 110/0.84 | junk | junk |  |  |
| gratefuldead-1991-04-28 | 01 - Tuning.mp3 | junk | chosen | 150/0.94 | 150/0.94 | music | music |  |  |
| gratefuldead-1991-09-26 | 01 - Tuning.mp3 | junk | chosen | 300/1.00 | 300/1.00 | music | music |  |  |
| gratefuldead-1991-09-26 | 10 - Tuning.mp3 | song | chosen | 330/1.00 | 330/1.00 | music | music |  |  |
| gratefuldead-1993-03-24 | 01 - Tuning.mp3 | junk | near | 90/0.67 | 90/0.67 | junk | junk |  |  |
| gratefuldead-1993-09-13 | 01 - Tuning.mp3 | junk | chosen | 170/0.85 | 170/0.85 | music | music |  |  |
| greatamericantaxi-2007-08-05 | 01 - Intro.mp3 | song | chosen | 330/0.87 | 330/0.87 | music | music |  |  |
| greenskybluegrass-2008-02-29 | 28 - Outro.mp3 | junk | near | 100/1.00 | 100/1.00 | junk | junk |  |  |
| greenskybluegrass-2009-04-18 | 01 - Intro.mp3 | song | chosen | 190/1.00 | 190/1.00 | music | music |  |  |
| greenskybluegrass-2014-07-17 | 01 - intro.mp3 | song | near | 100/0.67 | 100/0.67 | junk | junk |  |  |
| johnkadlecik-2014-03-29 | 01 - Tuning.mp3 | junk | near | 100/0.71 | 100/0.71 | junk | junk |  |  |
| kellerwilliams-2002-10-26 | 37 - Outro.mp3 | junk | near | 100/0.91 | 100/0.91 | junk | junk |  |  |
| meatpuppets-2013-04-02 | 18 - Crowd.mp3 | song | chosen | 180/0.95 | 180/0.95 | music | music |  |  |
| mountaingoats-2012-01-31 | 01 - Intro.mp3 | junk | near | 100/0.91 | 100/0.91 | junk | junk |  |  |
| mymorningjacket-2007-03-10 | 01 - Intro.mp3 | junk | chosen | 140/1.00 | 140/1.00 | music | music |  |  |
| newridersofthepurplesage-1974-11-29 | 23 - crowd & tuning.mp3 | song | chosen | 120/0.63 | 120/0.63 | music | music |  |  |
| newridersofthepurplesage-1974-11-30 | 19 - crowd & tuning.mp3 | song | chosen | 160/0.80 | 160/0.80 | music | music |  |  |
| philleshandfriends-2008-10-31 | 01 - Intro_Tuning.mp3 | junk | near | 90/0.60 | 90/0.60 | junk | junk |  |  |
| radiators-1996-02-17 | 01 - Tuning.mp3 | song | chosen | 160/0.94 | 160/0.94 | music | music |  |  |
| radiators-1996-02-17 | 17 - Tuning.mp3 | song | chosen | 150/0.74 | 150/0.74 | music | music |  |  |
| radiators-2004-11-19 | 01 - Tuning_Intro.mp3 | junk | near | 90/0.69 | 90/0.69 | junk | junk |  |  |
| radiators-2006-02-12 | 01 - Tuning & Intro.mp3 | junk | near | 90/0.79 | 90/0.79 | junk | junk |  |  |
| railroadearth-2013-03-29 | 20 - Crowd.mp3 | song | chosen | 420/0.91 | 420/0.91 | music | music |  |  |
| smashingpumpkins-1998-05-19 | 17 - Crowd Noise.mp3 | song | chosen | 400/0.76 | 400/0.76 | music | music |  |  |
| smashingpumpkins-2007-10-04 | 01 - Intro.mp3 | song | near | 90/0.64 | 90/0.64 | junk | junk |  |  |
| smashingpumpkins-2008-08-12 | 01 - Intro.mp3 | song | chosen | 120/0.92 | 120/0.92 | music | music |  |  |
| spoon-2003-07-15 | 01 - Intro.mp3 | junk | near | 90/1.00 | 90/1.00 | junk | junk |  |  |
| stevewynn-1985-06-14 | 01 - Intro.mp3 | unsure | near | 100/0.91 | 100/0.91 | junk | junk |  |  |
| themotet-2012-10-31 | 01 - Intro.mp3 | junk | chosen | 130/0.87 | 140/0.93 | music | music |  |  |
| umphreysmcgee-2006-05-04 | 21 - Crowd.mp3 | song | chosen | 220/1.00 | 220/1.00 | music | music |  |  |
| yondermountainstringband-2006-08-25 | 21 - outro.mp3 | song | chosen | 510/0.98 | 510/0.98 | music | music |  |  |

Tracks run: 48 of 48; flips: 0; blocking flips: 0; missing on share: 0
