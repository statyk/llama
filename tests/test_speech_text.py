from llama.speech_text import Lexicon, normalize_for_speech


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
