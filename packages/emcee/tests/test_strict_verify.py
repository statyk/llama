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
    ("with Dark Star Orchestra.", "With Dark Starr Orchestra."),           # one name edit
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
