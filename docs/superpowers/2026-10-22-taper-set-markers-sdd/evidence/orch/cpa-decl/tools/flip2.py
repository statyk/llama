import sys; sys.argv=[sys.argv[0]]
exec(open(sys.path[0]+"/fliptest.py").read().split("T = [")[0])
T=[("joerussosalmostdead-2019-03-03", [(r"re:Set One @ \(.*?\):", "Set One:"), (r"re:Set Two\s*\(.*?\):", "Set Two:")], None, None, "R-FORM header + @ (time range)"),]
T0=[
 ("clubdelf-2004-05-20", [("->?(@15:57) 24:48", ""), (r"re:^Tr-\d+ ", ""), (r"re:\s+\d+:\d\d\s*$", "")], None, None, "R-ITEM drop junk/Tr-/durations"),
 ("stantonmoore-2001-11-20", [(r"re:^\d+\.\s*\?.*$", "")], None, None, "R-ITEM drop ? items"),
 ("joerussosalmostdead-2019-03-03", [("Set One @ (8:16PM - 9:18PM):", "Set One:"), (r"re:^Set Two\s+\(9:53PM - 11:37PM\):", "Set Two:")], None, None, "R-FORM header + @ (time range)"),
 ("philleshandfriends-2008-11-18", [("Disc I 1st Set", "1st Set"), ("Disc III 2nd Set Con't", "2nd Set cont."), ("Disc II 2nd Set", "2nd Set")], None, None, "N-FORM Disc N Mth Set"),
 ("umphreysmcgee-2006-12-31", [(r"re:^(Set I+) \([\d:]+\)$", r"\1"), (r"re:\s+\d*:\d\d\s*$", "")], None, None, "R-FORM header+(dur) and trailing durations"),
 ("deepbananablackout-2006-03-18", [(r"re:^Tr-\d+ ", ""), ("Set 1 Disc 1", "Set 1"), ("Set 1 cont. Disc 2", "Set 1 cont.")], None, None, "R-ITEM Tr- + N-FORM"),
 ("yondermountainstringband-2005-10-13", [(r"re:^(Disc \d - Set \d)(.*) \([\d:]+\):", r"\1\2:"), (r"re:^\d\d: ?", "")], None, None, "R-FORM Disc-Set+(dur) + NN: prefix"),
]
for a in T:
    try: run(*a)
    except AssertionError as e: print("ERR", a[0], e)
