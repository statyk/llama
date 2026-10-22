
THIRD_SET_SPLIT = ("Set One:\n1- Bertha\n2- Let It Grow\nSet Two:\n1- Scarlet Begonias\n"
                   "2- Fire On The Mountain\nThird Set\n1- Truckin\n2- Morning Dew")


def test_split_ordinal_header_is_set_like():
    # The reader leaves `Third Set` as the set-2 items `Third` and `Set`; without the veto set
    # 3 would merge into set 2 (owned `1 1 2 2 2 2`).
    tt = read_taper_structure(THIRD_SET_SPLIT)
    assert tt.asserts is True and ("Set", "2") in [(i.title, i.set) for i in tt.items]
    assert tt.set_like is True
    tracks = mk(["Bertha", "Let It Grow", "Scarlet Begonias", "Fire On The Mountain", "Truckin",
                 "Morning Dew"])
    d = decide_taper(tracks, {"description": THIRD_SET_SPLIT}, aliases={},
                     today_sets=["1", "1", "2", "2", "3", "3"])
    assert d.placement is None and d.reason == "veto: set-like text"


@pytest.mark.parametrize("line", ["Set", "- Set -", "[Set]", "*set*"])
def test_bare_set_item_is_set_like(line):
    tt = read_taper_structure(f"Set 1:\nBertha\nSet 2:\nScarlet Begonias\n{line}\nTruckin\n")
    assert tt.asserts is True and tt.set_like is True, line


def test_bare_set_item_real_case_is_not_owned():
    tt = read_taper_structure(DSO_2012_05_19)
    assert tt.asserts is True and label(tt, "Set") == "1" and tt.set_like is True
    d = decide_taper(_mk_today(DSO_2012_05_19_TRACKS, DSO_2012_05_19_TODAY),
                     {"description": DSO_2012_05_19}, aliases=GD_SHORTHAND,
                     today_sets=DSO_2012_05_19_TODAY)
    assert d.placement is None and d.reason == "veto: set-like text"


def test_set_like_checks_every_token_in_an_item():
    # Finding 2, M1: the item's first token is an exempt continuation of its own set; the
    # second names another set.
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\nSet 2 con't from set one\n"
                              "Truckin\n")
    assert tt.asserts is True and tt.set_like is True


def test_continuation_must_follow_the_token_directly():
    # Finding 2, M2: a `con't` later in the item is no continuation of the token.
    tt = read_taper_structure("Set 1:\nBertha\nSet 2:\nSugaree\n"
                              "Set 2 starts here (con't from disc 1)\nTruckin\n")
    assert tt.asserts is True and tt.set_like is True


def test_set_like_token_in_a_set_three_item():
    # Finding 2, M6.
    text = "Set 1:\nBertha\nSet 2:\nSugaree\nSet 3:\nScarlet Begonias\nend of set two\nTruckin\n"
    tt = read_taper_structure(text)
    assert tt.asserts is True and label(tt, "end of set two") == "3" and tt.set_like is True
    d = decide_taper(mk(["Bertha", "Sugaree", "Scarlet Begonias", "Truckin"]),
                     {"description": text}, aliases={}, today_sets=["1", "2", "3", "3"])
    assert d.placement is None and d.reason == "veto: set-like text"
