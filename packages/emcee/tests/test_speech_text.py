from pathlib import Path

from emcee.speech_text import Lexicon, load_lexicon, normalize_for_speech


def test_expands_greater_than_segue_to_into():
    # A literal setlist segue leaking into prose must not be read "greater than".
    out = normalize_for_speech("Help on the Way > Slipknot", Lexicon.empty())
    assert ">" not in out
    assert "Help on the Way into Slipknot" == out


def test_expands_ampersand_and_percent():
    assert normalize_for_speech("Jerry & Bob", Lexicon.empty()) == "Jerry and Bob"
    assert normalize_for_speech("100% live", Lexicon.empty()) == "100 percent live"


def test_clean_prose_is_unchanged():
    # Identity on ordinary text — so unaffected cache keys don't churn.
    text = "Good evening, night owls. It's June 10th, 1973."
    assert normalize_for_speech(text, Lexicon.empty()) == text


def test_lexicon_respells_whole_word_case_insensitively():
    lex = Lexicon({"Sugaree": "Shugaree"})
    assert normalize_for_speech("They opened with Sugaree tonight.", lex) == \
        "They opened with Shugaree tonight."
    assert normalize_for_speech("sugaree", lex) == "Shugaree"


def test_lexicon_does_not_match_inside_other_words():
    lex = Lexicon({"Weir": "Weer"})
    # "weird" must not become "Weerd".
    assert normalize_for_speech("that weird jam", lex) == "that weird jam"


def test_lexicon_prefers_longest_phrase():
    lex = Lexicon({"Way": "Wayy", "Help on the Way": "Help on the Wave"})
    assert normalize_for_speech("Help on the Way", lex) == "Help on the Wave"


def test_symbols_then_lexicon_and_whitespace_tidied():
    lex = Lexicon({"Mydland": "Midland"})
    assert normalize_for_speech("Brent Mydland  &   the band", lex) == \
        "Brent Midland and the band"


def test_empty_lexicon_apply_is_identity():
    assert Lexicon.empty().apply("nothing to do here") == "nothing to do here"


def test_load_lexicon_includes_baked_in_seed():
    lex = load_lexicon()
    # Seeded, owner-confirmed entries.
    assert normalize_for_speech("Sugaree", lex) == "Shugaree"
    assert normalize_for_speech("Mydland", lex) == "Midland"


def test_workspace_overlay_adds_and_overrides(tmp_path: Path):
    (tmp_path / "pronunciations.csv").write_text(
        "written,spoken,note\n"
        "Sugaree,Sugar-ee,override the seed\n"
        "Pigpen,Pig Pen,new entry\n"
    )
    lex = load_lexicon(tmp_path)
    assert normalize_for_speech("Sugaree", lex) == "Sugar-ee"   # overlay wins
    assert normalize_for_speech("Pigpen", lex) == "Pig Pen"     # added
    assert normalize_for_speech("Mydland", lex) == "Midland"    # seed still present


def test_missing_overlay_is_fine(tmp_path: Path):
    lex = load_lexicon(tmp_path)  # no pronunciations.csv in tmp_path
    assert normalize_for_speech("Sugaree", lex) == "Shugaree"


def test_malformed_overlay_is_ignored_not_raised(tmp_path: Path, caplog):
    # A row missing the spoken column is skipped; a totally broken file warns.
    (tmp_path / "pronunciations.csv").write_text("this is not,valid\ncsv at all")
    lex = load_lexicon(tmp_path)  # must not raise
    assert normalize_for_speech("Sugaree", lex) == "Shugaree"  # seed intact


def test_seed_expands_gdtrfb_abbreviation():
    # Phil read "GDTRFB" aloud letter by letter; speech-only respelling.
    lex = load_lexicon()
    spoken = "Going Down the Road Feeling Bad"
    assert normalize_for_speech("GDTRFB", lex) == spoken
    assert normalize_for_speech("gdtrfb", lex) == spoken                    # case-insensitive
    assert normalize_for_speech("GDTRFB > Jam", lex) == f"{spoken} into Jam"  # beside a segue
    assert normalize_for_speech("(GDTRFB)", lex) == f"({spoken})"
    assert normalize_for_speech("XGDTRFBY", lex) == "XGDTRFBY"             # whole word only


def test_drops_taper_footnote_marks_from_titles():
    # Setlist footnote marks copied into prose were voiced "times", "asterisk"
    # and worse (ratdog-2007-04-22, operator 2026-11-02).
    lex = Lexicon.empty()
    assert normalize_for_speech("Sammy sings Loose Lucy * like a man", lex) \
        == "Sammy sings Loose Lucy like a man"
    assert normalize_for_speech("for Loose Lucy *.", lex) == "for Loose Lucy."
    assert normalize_for_speech("on the Earth Day Rap ^, and", lex) == "on the Earth Day Rap, and"
    assert normalize_for_speech("Dark Star*† into Drums‡", lex) == "Dark Star into Drums"


def test_drops_encore_prefix():
    lex = Lexicon.empty()
    assert normalize_for_speech("They came back for E: Samson and Delilah.", lex) \
        == "They came back for Samson and Delilah."
    assert normalize_for_speech("E: U.S. Blues closed it.", lex) == "U.S. Blues closed it."
    # Only a bare token before a capitalized word on the same line.
    assert normalize_for_speech("ABE: Lincoln spoke", lex) == "ABE: Lincoln spoke"
    assert normalize_for_speech("a solo in the key of E: bright and hard", lex) \
        == "a solo in the key of E: bright and hard"
    assert normalize_for_speech("they vamp in E:\n\nNext paragraph.", lex) \
        == "they vamp in E:\n\nNext paragraph."


def test_mark_glued_to_a_word_front_keeps_words_apart():
    assert normalize_for_speech("It was *really* good", Lexicon.empty()) == "It was really good"


def test_footnote_strip_keeps_paragraph_breaks():
    # Chunking splits on blank lines; a mark opening a paragraph must not merge it.
    assert normalize_for_speech("One thought.\n\n* Another.", Lexicon.empty()) \
        == "One thought.\n\n Another."
