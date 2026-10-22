import sys
src=open(sys.argv[1]).read(); name=sys.argv[2]
M={
 'M1_first_match_only': ("for m in _SET_LIKE.finditer(item.title):", "for m in list(_SET_LIKE.finditer(item.title))[:1]:"),
 'M2_cont_search': ("_CONT_AFTER.match(item.title[m.end():])", "_CONT_AFTER.search(item.title[m.end():])"),
 'M3_no_same_set': ("if str(number) == item.set and _CONT_AFTER", "if _CONT_AFTER"),
 'M4_only_without_encore': ("    if taper.set_like:\n", "    if taper.set_like and not taper.has_encore:\n"),
 'M5_no_veto': ("    if taper.set_like:\n", "    if False:\n"),
 'M6_skip_set3_too': ('if item.set == "encore":', 'if item.set in ("encore", "3"):'),
}
a,b=M[name]; assert src.count(a)==1,(name,src.count(a)); open(sys.argv[1],'w').write(src.replace(a,b))
