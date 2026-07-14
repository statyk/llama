from llama.songs import matches_sequence, normalize_song


def test_normalize_strips_punctuation_and_case():
    assert normalize_song("Goin' Down The Road Feeling Bad") == "goin down the road feeling bad"
    assert normalize_song("St. Stephen") == "saint stephen"


def test_aliases_map_to_canonical():
    assert normalize_song("China Cat") == "china cat sunflower"
    assert normalize_song("Rider") == "i know you rider"
    assert normalize_song("GDTRFB") == "goin down the road feeling bad"


def test_caller_aliases_extend_defaults():
    assert normalize_song("Werewolves", {"werewolves": "werewolves of london"}) == "werewolves of london"
    assert normalize_song("Rider", {"werewolves": "werewolves of london"}) == "i know you rider"


def test_matches_sequence_adjacent_only():
    setlist = ["Morning Dew", "China Cat Sunflower", "I Know You Rider", "Johnny B. Goode"]
    assert matches_sequence(setlist, ["China Cat Sunflower", "I Know You Rider"])
    assert matches_sequence(setlist, ["china cat", "rider"])  # aliases apply
    assert not matches_sequence(setlist, ["Morning Dew", "I Know You Rider"])  # not adjacent
    assert not matches_sequence(setlist, ["Dark Star"])
