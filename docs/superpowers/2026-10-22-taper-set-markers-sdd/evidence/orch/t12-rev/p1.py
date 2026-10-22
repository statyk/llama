from llama.taper import _classify, _preprocess, read_taper_structure, _scan
lines = """Set 1 (acoustic)
Set 1 (Acoustic):
Set I is Bobby and Jerry playing acoustic
Set I (45:00) is Bobby and Jerry
Set 1 (50:28) Bertha
Set 1 (50:28) - Bertha
Set I...
Set II... and then the band came back
Set 2 ... a long jam:
Set 1 - Disc 1 recorded by Joe
Disc 1 set in Boston
Disc 1 Set 1
Disc 2 Set 2 - Sugaree
CD 2 set 2: transferred by Joe
Disc 1: Set 1 audience
disc 1 [set 1] (61:20)
Set 1 Disc 1: 74:16
Set 1 Disc 1: Bertha
Set One / Disc Two
Set 2 Disc 3
Set 1 1/2 Disc
Set 1/2
SET 1/2
(Start Set 2)
Disk 3: Encore
CD2 Set 2 Part1
Disc 2 - NRPS
Disc 1 Set 1 of 2
Set 1 (9:30PM - 10:46PM):
Set 1 (9:30 PM-10:46 PM)
Set 2 (1:05:59)
Set 2 (2003)
Set 2 (12:00) (Electric):
Set 2 - (50:28)
Set 2 (the late show)
Set 2 cont. (50:28)
Set 2 & Encore (50:28):
Set 1 disc 1 -- source: SBD
Set 1 (8:00pm)
First Set (45:00):
Disc 1 Set 1 (taper: Joe)
Disc/Set 1
Disc/Set1
CD 1/Set 1
Disc One, Set One: Bertha, Sugaree
Set 3 Disc 2 Encore
Set 1 Disc 1 Encore:
set 1 - disc 1 - Bertha
Set 1 cd 1 lineage: SBD > DAT
1. Set 1 Disc 1
Set 1 Disc 10
Set 1 Disc 7
Set 1 Disc 1st
Set 2: Disc 2
Disc 2: Encore
Set II CD III
disc 01:set i :
Disc 2 - Set II...
""".splitlines()
for ln in lines:
    print(repr(ln), '->', _classify(ln))
