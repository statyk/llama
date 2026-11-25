import pytest

from emcee.tts.strict_verify import strict_problem, tokens


@pytest.mark.parametrize("text,want", [
    ("Then, at 2:30 Eastern, The Music Never Stopped", ["then", "at", "two", "thirty", "eastern", "the", "music", "never", "stopped"]),
    ("at 12:05", ["at", "twelve", "oh", "five"]), ("at 2:00", ["at", "two"]),
    ("You're listening to LMA Radio.", ["youre", "listening", "to", "lma", "radio"]),
    ("l m a radio", ["lma", "radio"]),
])
def test_tokens(text, want):
    assert tokens(text) == want


def test_tokens_of_hard_names():
    assert tokens("with moe.,") == ["with", "moe"]
    assert tokens("Hot Tuna & Friends") == ["hot", "tuna", "and", "friends"]
    assert tokens("Beyoncé") == ["beyonce"]
    assert tokens("STS9") == ["sts", "nine"]
    assert tokens("10,000 Maniacs") == ["ten", "thousand", "maniacs"]
    assert tokens("Blink-182") == ["blink", "one", "hundred", "eighty", "two"]


@pytest.mark.parametrize("text,heard", [
    ("Then, at 2:30 Eastern, The Music Never Stopped", "Then at two thirty Eastern, the music never stopped."),
    ("a few minutes before midnight Eastern.", "A few minutes before midnight, Eastern."),
    ("with Dark Star Orchestra.", "With Dark Starr Orchestra."),           # keys equal (STR/STR), not an edit
])
def test_passes(text, heard):
    assert strict_problem(text, heard) is None


@pytest.mark.parametrize("text,heard,why", [
    ("followed by Ryan Adams,", "Followed by Ryan Adam.", "final"),        # swallowed final consonant
    ("around quarter past 11 Eastern.", "Around quarter past 12 Eastern.", "template"),
    ("around quarter past 11 Eastern.", "Around a quarter past 11 Eastern.", "template"),
    ("with Dark Star Orchestra.", "With Dork Stars Orchestra.", "names"),   # two name edits
    ("with Cracker.", "", "nothing"),
])
def test_fails(text, heard, why):
    assert why in strict_problem(text, heard)


def test_id_piece_tokens_are_all_template():         # no name tolerance for the ID
    id_text = "You're listening to LMA Radio. Live concert tapes from the Live Music Archive."
    assert strict_problem(id_text, "You're listening to LMA Radio. Live concert tapes from the Live Music Archive.") is None
    assert "template" in strict_problem(id_text, "You're listening to LMA Radio. Live concert tape from the Live Music Archive.")


def test_expect_overrides():
    assert strict_problem("with moe.,", "With Mo.", expect="with mo") is None
    assert "expect" in strict_problem("with moe.,", "With Moe.", expect="with mo")


# Shawn's ruling 2026-11-25: name tokens compare by Metaphone key.
@pytest.mark.parametrize("text,heard", [
    ("with Raq.", "With rack."),                                      # RK/RK
    ("followed by Pardners,", "Followed by partners."),               # PRTNRS
    ("with The McCourys.", "With the Macquaries."),                   # MKKRS
    ("with Bonerama.", "With Bonarama."),                             # BNRM
    ("with Club d'Elf.", "With Club Delph."),                         # TLF
    ("followed by Little Feat,", "Followed by little feet."),         # FT
    ("with Hayes Carll.", "With Hayes Carl."),                        # KRL
    ("Coming up next, Pardners in Crime continues", "Coming up next, Partners in Crime continues"),
])
def test_phonetic_passes(text, heard):
    assert strict_problem(text, heard) is None


@pytest.mark.parametrize("text,heard,why", [
    ("with Ryan.", "With Brian.", "final"),                                  # RYN/BRN
    ("followed by Ryan Adams,", "Followed by Brian Adams,", "names"),        # two token edits
    ("followed by Ryan Adams,", "Followed by Ryan Adam,", "final"),          # ATMS/ATM
    ("Ripple continues", "Nipple continues", "names"),                       # RPL/NPL, final stays template
    ("Then, at 2 Eastern, The Music Never Stopped",
     "Then, at 2 Eastern, The Music Never Stops", "final"),                  # STPT/STPS
    ("Coming up next, Ripple in Crime continues",
     "Coming up next, Nipple in Crime continues", "names"),                  # span count same, key differs
    ("with Hayes Carll.", "With Hayes Carll Band.", "final"),
    ("Ripple continues", "continues", "spans"),                              # swallowed title
    ("Coming up next, Live at the Fillmore", "Coming up next, at the Fillmore", "names"),
    ("Coming up next, Live at the Fillmore", "Coming up next, at the Fillmore", "spans"),
    ("Hayes Carll continues", "Hayes Carll Band continues", "words wanted"),  # now a length failure
    ("Coming up next, Pardners in Crime continues",
     "Coming up next, Pardners in continues", "words wanted"),
])
def test_phonetic_fails(text, heard, why):
    assert why in strict_problem(text, heard)


@pytest.mark.parametrize("text,heard,why", [
    ("with Grateful Dead.", "With Dead.", "1 heard"),
    ("with Cracker.", "With Big Cracker.", "2 heard"),
    ("followed by George Porter, Jr. and Runnin' Pardners,",
     "Followed by George, Jr. and Runnin' Pardners,", "heard"),
    ("with Dark Star Orchestra.", "With Dark Star Big Orchestra.", "4 heard"),
])
def test_no_token_insert_or_delete_in_names(text, heard, why):
    assert why in strict_problem(text, heard)


def test_final_template_token_stays_exact():
    assert "final" in strict_problem("Ripple continues", "Ripple continue")


def test_no_key_token_does_not_crash():
    assert strict_problem("with Blink 1000000.", "With Blink 1000000.") is None
    assert strict_problem("with Blink 1000000.", "With Blink 1000001.") is not None
