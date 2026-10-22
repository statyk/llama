import json
T = "packages/llama/src/llama/taper.py"; TT = "packages/llama/tests/test_taper.py::"
G = TT + "test_token_glued_to_cont_or_disc_is_a_song_title"
M = [
 dict(id="S0-base", file=None, predicted=[], collateral=[]),
 dict(id="S1-sentinel", file=T, old='            if str(number) == item.set and _CONT_AFTER.match(item.title[m.end():]):',
      new='            raise RuntimeError("SENTINEL")', predicted=["test_set_like_negatives[*] and every reader test with a non-encore item (_set_like runs in read_taper_structure)"], collateral=[]),
 dict(id="o", file=T, old='    r"(?:set\\s*(?P<tok>one|two|three|iii|ii|i|[123])(?!\\w)"',
      new='    r"(?:set\\s*(?P<tok>one|two|three|iii|ii|i|[123])"',
      predicted=[TT + "test_set_like_negatives[Set In Stone]", G + "[Set2cont]", G + "[Set 2cont:]", G + "[Set IIcont]",
                 G + "[Set 1CD1]", G + "[Set 1Disc 1]"], collateral=[]),
 dict(id="o2", file=T, old='    r"|(?P<ord>first|second|third)\\s+set(?!\\w)"', new='    r"|(?P<ord>first|second|third)\\s+set"',
      predicted=[TT + "test_set_like_negatives[songs from the first setlist]", TT + "test_set_like_negatives[Second Settlement]"], collateral=[]),
 dict(id="o3", file=T, old='    r"|(?P<ordn>1st|2nd|3rd)\\s+set(?!\\w))"', new='    r"|(?P<ordn>1st|2nd|3rd)\\s+set)"',
      predicted=[TT + "test_set_like_negatives[2nd settle]", TT + "test_set_like_negatives[1st Setting Sun]"], collateral=[]),
]
json.dump(M, open("mutants.json", "w"), indent=1)
